import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const TCG_API_KEY = Deno.env.get("POKEMON_TCG_API_KEY") ?? "";
const API_BASE = "https://api.pokemontcg.io/v2/cards";

// Process this many sets per invocation to stay within Edge Function timeout.
// With ~200 sets and BATCH_SIZE=30, a daily cron finishes all sets in ~7 days (= weekly refresh).
// Or schedule it to run multiple times per day to finish faster.
const BATCH_SIZE = 30;

const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

type SetMapping = { our: string; tcg: string };

async function getSetMappings(): Promise<SetMapping[]> {
  // JA set IDs in our DB look like `SV7a-ja`; pokemontcg.io uses the
  // lowercase stem `sv7a`. EN IDs pass through unchanged.
  const rows: SetMapping[] = [];
  let offset = 0;
  const pageSize = 1000;
  while (true) {
    const { data } = await sb
      .from("sets")
      .select("id, language")
      .in("language", ["en", "ja"])
      .range(offset, offset + pageSize - 1);
    if (!data || data.length === 0) break;
    for (const row of data as { id: string; language: string }[]) {
      const our = row.id;
      const tcg = row.language === "ja" && our.endsWith("-ja")
        ? our.slice(0, -3).toLowerCase()
        : our;
      rows.push({ our, tcg });
    }
    if (data.length < pageSize) break;
    offset += pageSize;
  }
  // Stable order so the offset cursor is deterministic across runs
  rows.sort((a, b) => a.our.localeCompare(b.our));
  return rows;
}

function normalizeCardIdToTcg(ourId: string): string | null {
  if (!ourId.endsWith("-ja")) return null;
  const stem = ourId.slice(0, -3);
  const dash = stem.lastIndexOf("-");
  if (dash === -1) return null;
  const setCode = stem.slice(0, dash);
  const number = stem.slice(dash + 1);
  const n = parseInt(number, 10);
  if (Number.isNaN(n)) return null;
  return `${setCode.toLowerCase()}-${n}`;
}

async function buildJaRemap(): Promise<Map<string, string>> {
  // Reverse-lookup: pokemontcg.io-format id -> our `-ja` id.
  const remap = new Map<string, string>();
  let offset = 0;
  const pageSize = 1000;
  while (true) {
    const { data } = await sb
      .from("cards")
      .select("id")
      .like("id", "%-ja")
      .range(offset, offset + pageSize - 1);
    if (!data || data.length === 0) break;
    for (const row of data as { id: string }[]) {
      const tcg = normalizeCardIdToTcg(row.id);
      if (tcg) remap.set(tcg, row.id);
    }
    if (data.length < pageSize) break;
    offset += pageSize;
  }
  return remap;
}

async function getLastOffset(): Promise<number> {
  // Use a simple row in prices_cache to track progress.
  // We store the offset as the market_price of a sentinel row.
  const { data } = await sb
    .from("prices_cache")
    .select("market_price")
    .eq("card_id", "__refresh_offset__")
    .single();
  return data?.market_price ?? 0;
}

async function setLastOffset(offset: number): Promise<void> {
  await sb.from("prices_cache").upsert({
    card_id: "__refresh_offset__",
    market_price: offset,
    failed: false,
  });
}

async function fetchPricesForSet(
  setId: string
): Promise<{ card_id: string; market_price: number | null; failed: boolean }[]> {
  const headers: Record<string, string> = {};
  if (TCG_API_KEY) headers["X-Api-Key"] = TCG_API_KEY;

  const rows: { card_id: string; market_price: number | null; failed: boolean }[] = [];
  let page = 1;

  while (true) {
    const url = `${API_BASE}?q=set.id:${setId}&select=id,tcgplayer&page=${page}&pageSize=250`;

    let resp: Response | undefined;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        resp = await fetch(url, { headers });
        break;
      } catch {
        if (attempt < 2) await new Promise((r) => setTimeout(r, 3000));
        else return rows;
      }
    }

    if (!resp) break;

    if (resp.status === 429) {
      await new Promise((r) => setTimeout(r, 30000));
      continue;
    }
    if (!resp.ok) break;

    const json = await resp.json();
    const cards = json.data ?? [];

    for (const card of cards) {
      const p = card.tcgplayer?.prices ?? {};
      const market =
        p.holofoil?.market ??
        p.normal?.market ??
        p.reverseHolofoil?.market ??
        p["1stEditionHolofoil"]?.market ??
        null;
      rows.push({ card_id: card.id, market_price: market, failed: market === null });
    }

    if (cards.length < 250) break;
    page++;
  }

  return rows;
}

Deno.serve(async () => {
  try {
    const setMappings = await getSetMappings();
    const hasJa = setMappings.some((s) => s.our !== s.tcg);
    const jaRemap = hasJa ? await buildJaRemap() : new Map<string, string>();
    const offset = await getLastOffset();
    const batch = setMappings.slice(offset, offset + BATCH_SIZE);

    if (batch.length === 0) {
      // We've gone through all sets — reset to 0 for next cycle
      await setLastOffset(0);
      return new Response(
        JSON.stringify({ ok: true, message: "Full cycle complete, reset to 0" }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    console.log(
      `Processing sets ${offset + 1}-${offset + batch.length} of ${setMappings.length}`
    );

    let totalPriced = 0;
    let totalCards = 0;

    let setsProcessed = 0;

    for (const { our, tcg } of batch) {
      const rows = await fetchPricesForSet(tcg);

      // If API returned nothing, it's probably down — stop and retry next run
      if (rows.length === 0) {
        console.log(`  Set ${our} returned 0 results, API may be down — stopping`);
        break;
      }

      // For a JA set, pokemontcg.io returns English prints — rewrite each
      // card_id to its `-ja` equivalent and drop cards we don't have in our
      // DB. For an EN set, pass through unchanged.
      const isJa = our !== tcg;
      const remapped: typeof rows = [];
      for (const r of rows) {
        if (isJa) {
          const jaId = jaRemap.get(r.card_id);
          if (jaId) remapped.push({ ...r, card_id: jaId });
        } else {
          remapped.push(r);
        }
      }

      // Only upsert rows that have a price
      const priced = remapped.filter((r) => r.market_price !== null);
      if (priced.length > 0) {
        for (let j = 0; j < priced.length; j += 500) {
          await sb.from("prices_cache").upsert(priced.slice(j, j + 500));
        }
      }

      totalPriced += priced.length;
      totalCards += rows.length;
      setsProcessed++;

      // Rate limit delay
      if (!TCG_API_KEY) await new Promise((r) => setTimeout(r, 1000));
    }

    // Only advance offset for sets we actually processed
    if (setsProcessed > 0) {
      const nextOffset = offset + setsProcessed;
      await setLastOffset(nextOffset >= setMappings.length ? 0 : nextOffset);
    }

    const msg = `Sets ${offset + 1}-${offset + batch.length}/${setMappings.length}: ${totalPriced} priced / ${totalCards} cards`;
    console.log(msg);
    return new Response(JSON.stringify({ ok: true, message: msg }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    console.error("refresh-prices error:", err);
    return new Response(JSON.stringify({ ok: false, error: String(err) }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
});

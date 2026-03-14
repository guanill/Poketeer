/**
 * generate-catalog.mjs
 *
 * Fetches every English set + card from api.pokemontcg.io and writes
 * a compact catalog to public/catalog.json. Run once from the project root:
 *
 *   node scripts/generate-catalog.mjs
 *
 * The output is bundled inside the APK so the app can browse sets/cards
 * and scan without any network connection (images still come from CDN).
 */

import { writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dir = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dir, '..');
const OUT  = resolve(ROOT, 'public', 'catalog.json');

const BASE = 'https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master';
const DELAY_MS  = 50; // ms between set fetches (GitHub has high rate limits)

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function fetchJson(url, retries = 3) {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, {
        headers: { 'User-Agent': 'poketeer-catalog-gen/1.0' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    } catch (e) {
      if (attempt === retries) throw e;
      const wait = attempt * 2000;
      process.stdout.write(`\n  [retry ${attempt}] ${e.message}, waiting ${wait}ms...\n`);
      await sleep(wait);
    }
  }
}

// ── Sets ──────────────────────────────────────────────────────────────────────
async function fetchAllSets() {
  console.log('Fetching sets from GitHub data repo...');
  const raw = await fetchJson(`${BASE}/sets/en.json`);
  // GitHub repo returns array directly
  const sets = raw.map(s => ({
    id: s.id,
    name: s.name,
    series: s.series,
    printedTotal: s.printedTotal,
    total: s.total,
    releaseDate: s.releaseDate,
    images: {
      symbol: `https://images.pokemontcg.io/${s.id}/symbol.png`,
      logo: `https://images.pokemontcg.io/${s.id}/logo.png`,
    },
  }));
  // Sort newest first
  sets.sort((a, b) => (b.releaseDate ?? '').localeCompare(a.releaseDate ?? ''));
  console.log(`  -> ${sets.length} sets`);
  return sets;
}

// ── Cards (one JSON file per set) ─────────────────────────────────────────────
function pickCard(c, setId, setName, setSeries, setReleaseDate) {
  return {
    id: c.id,
    name: c.name,
    supertype: c.supertype,
    subtypes: c.subtypes ?? [],
    hp: c.hp ?? '',
    types: c.types ?? [],
    number: c.number,
    artist: c.artist ?? '',
    rarity: c.rarity ?? '',
    set: {
      id: setId,
      name: setName,
      series: setSeries,
      images: {
        symbol: `https://images.pokemontcg.io/${setId}/symbol.png`,
        logo: `https://images.pokemontcg.io/${setId}/logo.png`,
      },
    },
    images: {
      small: c.images?.small ?? `https://images.pokemontcg.io/${setId}/${c.number}.png`,
      large: c.images?.large ?? `https://images.pokemontcg.io/${setId}/${c.number}_hires.png`,
    },
    nationalPokedexNumbers: c.nationalPokedexNumbers ?? [],
  };
}

async function fetchAllCards(sets) {
  console.log(`Fetching cards for ${sets.length} sets...`);
  const allCards = [];
  let done = 0;

  for (const set of sets) {
    try {
      const cards = await fetchJson(`${BASE}/cards/en/${set.id}.json`);
      if (Array.isArray(cards)) {
        allCards.push(...cards.map(c => pickCard(c, set.id, set.name, set.series, set.releaseDate)));
      }
    } catch {
      // Some sets may not have a JSON file yet, skip silently
    }
    done++;
    process.stdout.write(`\r  ${done}/${sets.length} sets  (${allCards.length} cards)   `);
    if (done < sets.length) await sleep(DELAY_MS);
  }

  console.log(`\n  -> ${allCards.length} cards`);
  return allCards;
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
  const t0 = Date.now();

  const sets = await fetchAllSets();
  const cards = await fetchAllCards(sets);

  mkdirSync(resolve(ROOT, 'public'), { recursive: true });

  const catalog = {
    version: 1,
    generatedAt: new Date().toISOString(),
    sets,
    cards,
  };

  console.log('Writing public/catalog.json...');
  writeFileSync(OUT, JSON.stringify(catalog));

  const kb = Math.round(Buffer.from(JSON.stringify(catalog)).length / 1024);
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  console.log(`Done! ${kb} KB written in ${secs}s → ${OUT}`);
}

main().catch(e => { console.error(e); process.exit(1); });

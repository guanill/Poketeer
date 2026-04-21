"""
scrape_pokemon_card_foils.py — Scrape foil pack images from pokemon-card.com
across ALL expansion pages, match to DB JA sets, optionally update logo_url.

Usage:
    python supabase/scrape_pokemon_card_foils.py --fetch --dry-run
    python supabase/scrape_pokemon_card_foils.py --dry-run    # use cached pages
    python supabase/scrape_pokemon_card_foils.py              # apply to DB
"""
import asyncio
import io
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")
sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))

BASE_URL = "https://www.pokemon-card.com"
CACHE_DIR = ROOT / "supabase" / ".pcard_pages"
CACHE_DIR.mkdir(exist_ok=True)
MAX_PAGES = 15  # site reports "全 10ページ" with a broad date range

DATE_RANGE_QS = (
    "dateLowerY=1998&dateLowerM=1&dateLowerD=1"
    "&dateUpperY=2030&dateUpperM=12&dateUpperD=31"
)


# -----------------------------------------------------------------------
# Japanese product name (cleaned) → DB set ID
# -----------------------------------------------------------------------
NAME_TO_SET_ID: dict[str, str] = {
    # ── Mega Evolution era (M) ─────────────────────────
    "ニンジャスピナー": "M4-ja",
    "ムニキスゼロ": "M3-ja",
    "MEGAドリームex": "M2pt5-ja",
    "インフェルノX": "M2-ja",
    "メガシンフォニア": "M1S-ja",
    "メガブレイブ": "M1-ja",
    # ── Scarlet & Violet era (SV) ──────────────────────
    "ホワイトフレア": "SV11W-ja",
    "ブラックボルト": "SV11B-ja",
    "ロケット団の栄光": "SV10-ja",
    "熱風のアリーナ": "SV9a-ja",
    "バトルパートナーズ": "SV9-ja",
    "テラスタルフェスex": "SV8a-ja",
    "超電ブレイカー": "SV8-ja",
    "楽園ドラゴーナ": "SV7a-ja",
    "ステラミラクル": "SV7-ja",
    "ナイトワンダラー": "SV6a-ja",
    "変幻の仮面": "SV6-ja",
    "クリムゾンヘイズ": "SV5a-ja",
    "サイバージャッジ": "SV5M-ja",
    "ワイルドフォース": "SV5K-ja",
    "シャイニートレジャーex": "SV4a-ja",
    "未来の一閃": "SV4M-ja",
    "古代の咆哮": "SV4K-ja",
    "レイジングサーフ": "SV3a-ja",
    "黒炎の支配者": "SV3-ja",
    "ポケモンカード151": "SV2a-ja",
    "スノーハザード": "SV2P-ja",
    "クレイバースト": "SV2D-ja",
    "トリプレットビート": "SV1a-ja",
    # ── Sword & Shield era (S) ─────────────────────────
    "VSTARユニバース": "S12a-ja",
    "パラダイムトリガー": "S12-ja",
    "白熱のアルカナ": "S11a-ja",
    "ロストアビス": "S11-ja",
    "Pokémon GO": "S10b-ja",
    "スペースジャグラー": "S10P-ja",
    "タイムゲイザー": "S10D-ja",
    "ダークファンタズマ": "S10a-ja",
    "バトルリージョン": "S9a-ja",
    "スターバース": "S9-ja",
    "VMAXクライマックス": "S8b-ja",
    "25th ANNIVERSARY COLLECTION": "S8a-ja",
    "フュージョンアーツ": "S8-ja",
    "摩天パーフェクト": "S7D-ja",
    "蒼空ストリーム": "S7R-ja",
    "イーブイヒーローズ": "S6a-ja",
    "漆黒のガイスト": "S6K-ja",
    "白銀のランス": "S6H-ja",
    "双璧のファイター": "S5a-ja",
    "連撃マスター": "S5R-ja",
    "一撃マスター": "S5I-ja",
    "シャイニースターV": "S4a-ja",
    "仰天のボルテッカー": "S4-ja",
    "伝説の鼓動": "S3a-ja",
    "ムゲンゾーン": "S3-ja",
    "爆炎ウォーカー": "S2a-ja",
    "反逆クラッシュ": "S2-ja",
    "VMAXライジング": "S1a-ja",
    "ソード": "S1W-ja",
    "シールド": "S1H-ja",
    # ── Sun & Moon era (SM / sn / SMP) ─────────────────
    "TAG TEAM GX タッグオールスターズ": "SM12a-ja",
    "オルタージェネシス": "SM12-ja",
    "ドリームリーグ": "SM11b-ja",
    "リミックスバウト": "SM11a-ja",
    "ミラクルツイン": "sn11-ja",
    "スカイレジェンド": "SM10b-ja",
    "ジージーエンド": "sn10a-ja",
    "ダブルブレイズ": "SM10-ja",
    "フルメタルウォール": "SM9b-ja",
    "ナイトユニゾン": "SM9a-ja",
    "タッグボルト": "SM9-ja",
    "GXウルトラシャイニー": "SM8b-ja",
    "ダークオーダー": "SM8a-ja",
    "超爆インパクト": "SM8-ja",
    "フェアリーライズ": "SM7b-ja",
    "迅雷スパーク": "SM7a-ja",
    "裂空のカリスマ": "SM7-ja",
    "チャンピオンロード": "SM6b-ja",
    "ドラゴンストーム": "SM6a-ja",
    "禁断の光": "SM6-ja",
    "ウルトラフォース": "SM5+-ja",
    "ウルトラムーン": "SM5M-ja",
    "ウルトラサン": "SM5S-ja",
    "GXバトルブースト": "SM4+-ja",
    "覚醒の勇者": "SM4S-ja",
    "超次元の暴獣": "SM4A-ja",
    "光を喰らう闇": "SM3N-ja",
    "ひかる伝説": "SM3+-ja",
    "闘う虹を見たか": "SM3H-ja",
    "新たなる試練の向こう": "sm2+-ja",
    "アローラの月光": "SM2L-ja",
    "キミを待つ島々": "SM2K-ja",
    "サン&ムーン": "SM1+-ja",
    "サン＆ムーン": "SM1+-ja",
    "コレクション ムーン": "SM1M-ja",
    "コレクション サン": "SM1S-ja",
    "ムービースペシャルパック名探偵ピカチュウ": "SMP2-ja",
    "名探偵ピカチュウ": "SMP2-ja",
    # ── XY era (XY / CP) ───────────────────────────────
    "ベストオブXY": "XY11a-ja",
    "THE BEST OF XY": "XY11a-ja",
    "めざめる超王": "XY10-ja",
    "破天の怒り": "XY9-ja",
    "赤い閃光": "XY8b-ja",
    "青い衝撃": "XY8a-ja",
    "バンデットリング": "XY7-ja",
    "エメラルドブレイク": "XY6-ja",
    "ガイアボルケーノ": "XY5a-ja",
    "ファントムゲート": "XY4-ja",
    "ライジングフィスト": "XY3-ja",
    "ワイルドブレイズ": "XY2-ja",
    "コレクションX": "XY1a-ja",
    "コレクションY": "XY1b-ja",
    # CP (Concept Pack) series
    "20th Anniversary": "CP6-ja",
    "20thアニバーサリー": "CP6-ja",
    "冷酷の反逆者": "CP5-ja",
    "プレミアムチャンピオンパックEX×M×BREAK": "CP4-ja",
    "プレミアムチャンピオンパック EX×M×BREAK": "CP4-ja",
    "ポケキュンコレクション": "CP3-ja",
    "伝説キラコレクション": "CP2-ja",
    "マグマ団VSアクア団 ダブルクライシス": "CP1-ja",
    # ── HGSS / Legend (L) era ──────────────────────────
    "頂上大激突": "L3-ja",
    "ロストリンク": "LL-ja",
    "よみがえる伝説": "L2-ja",
    "ハートゴールドコレクション": "L1a-ja",
    "ソウルシルバーコレクション": "L1b-ja",
    # ── PCG (EX ruby/sapphire – diamond/pearl mix) ─────
    "さいはての攻防": "PCG9-ja",
    "きせきの結晶": "PCG8-ja",
    "ホロンの幻影": "PCG7-ja",
    "ホロンの研究塔": "PCG6-ja",
    "まぼろしの森": "PCG5-ja",
    "金の空、銀の海": "PCG4-ja",
    "ロケット団の逆襲": "PCG3-ja",
    "蒼空の激突": "PCG2-ja",
    "伝説の飛翔": "PCG1-ja",
    # ── ADV (Ruby/Sapphire) era ────────────────────────
    "とかれた封印": "ADV5-ja",
    "ex1マグマVSアクア": "ADV4-ja",
    "ex1マグマVSアクア ふたつの野望": "ADV4-ja",
    "ふたつの野望": "ADV4-ja",
    "天空の覇者": "ADV3-ja",
    "砂漠のきせき": "ADV2-ja",
    "第1弾拡張パック": "ADV1-ja",  # ADV era bare title, image path says /adv/
    # ── E (e-Card) era ─────────────────────────────────
    "神秘なる山": "E5-ja",
    "裂けた大地": "E4-ja",
    "海からの風": "E3-ja",
    "地図にない町": "E2-ja",
    "基本拡張パック": "E1-ja",
    # ── neo era ────────────────────────────────────────
    "闇、そして光へ": "neo4-ja",
    "めざめる伝説": "neo3-ja",
    "遺跡をこえて": "neo2-ja",
    "金、銀、新世界へ": "neo1-ja",
    # ── PMCG / Gym (Base set era) ──────────────────────
    "闇からの挑戦": "PMCG6-ja",
    "リーダーズスタジアム": "PMCG5-ja",
    "ロケット団": "PMCG4-ja",
    "化石の秘密": "PMCG3-ja",
    "ポケモンジャングル": "PMCG2-ja",
}


# -----------------------------------------------------------------------
# Fetch pages
# -----------------------------------------------------------------------
async def fetch_all_pages(max_pages: int = MAX_PAGES):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await context.new_page()
        for n in range(1, max_pages + 1):
            url = (
                f"{BASE_URL}/products/index.html?productType=expansion"
                f"&{DATE_RANGE_QS}&page={n}"
            )
            print(f"Fetching page {n}: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4500)
            for _ in range(4):
                await page.keyboard.press("End")
                await page.wait_for_timeout(500)
            html = await page.content()
            count = html.count("product-card")
            print(f"  page {n}: {count} product-card occurrences")
            if count == 0:
                print(f"  No products on page {n}, stopping.")
                break
            (CACHE_DIR / f"page_{n:02d}.html").write_text(html, encoding="utf-8")
            # Stop early if pagination shows no "next" link
            if 'class="next"' not in html:
                print(f"  No next link on page {n}, stopping.")
                break
        await browser.close()


# -----------------------------------------------------------------------
# Parse
# -----------------------------------------------------------------------
def parse_products(html: str) -> list[dict]:
    products = []
    blocks = re.split(r'<div class="product-card">', html)[1:]
    for block in blocks:
        img_match = re.search(r'<img src="([^"]+)"', block)
        title_match = re.search(r'<div class="product-title"><span>([^<]+)</span>', block)
        if not img_match or not title_match:
            continue

        title = title_match.group(1).strip()
        # Strip full- and half-width corner brackets
        bracketed = re.sub(r'[「」『』【】｢｣]', '', title).strip()
        # Strip leading 第N弾 markers, then common product-type prefixes, then 第N弾 again
        title_clean = re.sub(r'^第\d+弾\s*', '', bracketed).strip()
        title_clean = re.sub(
            r'^(拡張パック|強化拡張パック|ハイクラスパック|サブセット|'
            r'スペシャルセット|コンセプトパック|ジム拡張|ポケモンジム\s*ジム拡張|'
            r'強化パック|ムービースペシャルパック)\s*',
            '', title_clean,
        ).strip()
        title_clean = re.sub(r'^第\d+弾\s*', '', title_clean).strip()
        title_clean = title_clean.replace('\u3000', ' ').strip()
        # If cleaning left an empty string, fall back to the bracket-stripped title
        if not title_clean:
            title_clean = bracketed

        # Skip starter decks, deluxe sets, promos — they aren't expansion sets
        lower = title
        skip_keywords = (
            'デラックス', 'スタートデッキ', 'バトルパートナーズ構築済',
            'プレミアムトレーナーボックス', 'バトルアカデミー',
            'デッキビルドボックス', 'スターターセット', 'スペシャルデッキ',
            'クラシック', 'ポケモンワールドチャンピオンシップ',
        )
        if any(k in lower for k in skip_keywords):
            continue

        img_src = img_match.group(1)
        full_url = BASE_URL + img_src if img_src.startswith('/') else img_src
        products.append({
            "title_raw": title,
            "title": title_clean,
            "img_url": full_url,
        })
    return products


def parse_all_cached_pages() -> list[dict]:
    """Parse every cached page HTML and dedupe by title."""
    seen: dict[str, dict] = {}
    for path in sorted(CACHE_DIR.glob("page_*.html")):
        html = path.read_text(encoding="utf-8")
        for prod in parse_products(html):
            # Keep first occurrence
            seen.setdefault(prod["title"], prod)
    return list(seen.values())


# -----------------------------------------------------------------------
# Match + report + update
# -----------------------------------------------------------------------
def match(products: list[dict]) -> tuple[list[tuple[str, dict]], list[dict]]:
    matched: list[tuple[str, dict]] = []
    unmatched: list[dict] = []
    for prod in products:
        title = prod["title"]
        if not title or len(title) < 3:
            unmatched.append(prod)
            continue
        sid = NAME_TO_SET_ID.get(title)
        if not sid:
            # Loose contains match as fallback — require both sides non-trivial
            for key, candidate in NAME_TO_SET_ID.items():
                if len(key) < 3:
                    continue
                if key in title or title in key:
                    sid = candidate
                    break
        if sid:
            matched.append((sid, prod))
        else:
            unmatched.append(prod)
    return matched, unmatched


def load_db_ja_sets() -> dict[str, dict]:
    """Return {set_id: set_row} for all JA sets in DB."""
    res = sb.table("sets").select("id,name,name_en,logo_url").like("id", "%-ja").execute()
    return {row["id"]: row for row in (res.data or [])}


def report(matched, unmatched, db_sets):
    print(f"\n{'='*70}\nMATCH REPORT\n{'='*70}")
    print(f"Products scraped: {len(matched) + len(unmatched)}")
    print(f"  Matched:   {len(matched)}")
    print(f"  Unmatched: {len(unmatched)}")
    print(f"DB JA sets:  {len(db_sets)}")

    # Duplicate detection — same set_id mapped twice
    sid_count: dict[str, int] = {}
    for sid, _ in matched:
        sid_count[sid] = sid_count.get(sid, 0) + 1
    dups = {sid: n for sid, n in sid_count.items() if n > 1}
    if dups:
        print(f"\n⚠  {len(dups)} DB set(s) matched by multiple products (would overwrite):")
        for sid, n in dups.items():
            print(f"   {sid}: {n} candidates")
            for s, p in matched:
                if s == sid:
                    print(f"     - {p['title']!r} → {p['img_url']}")

    # Sets being updated
    print(f"\nMATCHED — image that would be set on each DB set:")
    for sid, prod in sorted(matched, key=lambda x: x[0]):
        row = db_sets.get(sid)
        if not row:
            print(f"  {sid}: ⚠  NOT IN DB  — {prod['title']!r}")
            continue
        current = "(has logo)" if row.get("logo_url") else "(no logo)"
        print(f"  {sid:12}  {row['name']:28}  {current}")
        print(f"     product: {prod['title']!r}")
        print(f"     image:   {prod['img_url']}")

    if unmatched:
        print(f"\nUNMATCHED products (no DB mapping):")
        for p in unmatched:
            print(f"  {p['title']!r}")

    # Sets in DB that got no image
    covered = {sid for sid, _ in matched}
    missing = [sid for sid in db_sets if sid not in covered]
    if missing:
        print(f"\nDB sets NOT covered by any product ({len(missing)}):")
        for sid in sorted(missing):
            print(f"  {sid}: {db_sets[sid]['name']}")


def apply_updates(matched, db_sets):
    applied = 0
    for sid, prod in matched:
        if sid not in db_sets:
            continue
        sb.table("sets").update({"logo_url": prod["img_url"]}).eq("id", sid).execute()
        applied += 1
    print(f"\nApplied {applied} logo updates to DB.")


def main():
    dry_run = "--dry-run" in sys.argv
    do_fetch = "--fetch" in sys.argv

    if do_fetch:
        asyncio.run(fetch_all_pages())
    elif not any(CACHE_DIR.glob("page_*.html")):
        print("No cached pages. Run with --fetch first.")
        sys.exit(1)

    products = parse_all_cached_pages()
    print(f"Parsed {len(products)} unique products from cached pages.")

    matched, unmatched = match(products)
    db_sets = load_db_ja_sets()
    report(matched, unmatched, db_sets)

    if dry_run:
        print("\n[DRY RUN] No DB writes.")
    else:
        print("\nApplying updates...")
        apply_updates(matched, db_sets)


if __name__ == "__main__":
    main()

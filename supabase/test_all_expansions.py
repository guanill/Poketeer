"""Quick probe: fetch expansion listing with broad date range and count products."""
import asyncio
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "supabase" / ".pcard_pages" / "all_expansions.html"


async def main():
    from playwright.async_api import async_playwright

    url = (
        "https://www.pokemon-card.com/products/index.html"
        "?productType=expansion"
        "&dateLowerY=1998&dateLowerM=1&dateLowerD=1"
        "&dateUpperY=2026&dateUpperM=12&dateUpperD=31"
    )
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = await ctx.new_page()
        print(f"GET {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4500)
        for _ in range(6):
            await page.keyboard.press("End")
            await page.wait_for_timeout(500)
        html = await page.content()
        OUT.write_text(html, encoding="utf-8")
        print(f"product-card count: {html.count('product-card')}")
        # Look at pagination
        import re
        pag = re.search(r'<nav class="Pagination">.*?</nav>', html, re.DOTALL)
        if pag:
            print("PAGINATION:", pag.group(0)[:500])
        await browser.close()


asyncio.run(main())

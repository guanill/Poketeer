"""Fix Thai sets: add release dates, English names in parentheses, and pack images."""

import io
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.seed")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

IMG_BASE = "https://asia.pokemon-card.com/th/card-img/products"

UPDATES = {
    "MA4-th": {
        "name": "วอยด์บลาสต์ (Void Blast)",
        "release_date": "2026-03-20",
        "logo_url": f"{IMG_BASE}/th_ma4_pkg.png",
    },
    "MA3-th": {
        "name": "วิวัฒนาการเมก้า ดรีมex (Mega Evolution Dream ex)",
        "release_date": "2026-01-16",
        "logo_url": f"{IMG_BASE}/ma3t_pkg.png",
    },
    "MA2-th": {
        "name": "อัคคีสีคราม (Azure Blaze)",
        "release_date": "2025-11-07",
        "logo_url": f"{IMG_BASE}/th_news_MA2_pillow_img.png",
    },
    "MA1-th": {
        "name": "วิวัฒนาการเมก้า (Mega Evolution)",
        "release_date": "2025-09-12",
        "logo_url": f"{IMG_BASE}/MA1_pillow_img_THA.png",
    },
    "SV10s-th": {
        "name": "การผงาดของผู้ไร้พ่าย (Rise of the Undefeated)",
        "release_date": "2025-06-13",
        "logo_url": f"{IMG_BASE}/th_SV10s_pillow_img.png",
    },
    "SV9s-th": {
        "name": "สายใยแห่งโชคชะตา (Threads of Fate)",
        "release_date": "2025-04-11",
        "logo_url": f"{IMG_BASE}/SV9s_pillow_img_THA.png",
    },
    "SV8a-th": {
        "name": "เทศกาลเทรัสตัลex (Terastal Festival ex)",
        "release_date": "2025-02-07",
        "logo_url": f"{IMG_BASE}/SV8a_pillow_img_20240911.png",
    },
    "SV8s-th": {
        "name": "สเตลลาร์สายฟ้าฟาด (Stellar Thunder)",
        "release_date": "2024-12-13",
        "logo_url": f"{IMG_BASE}/SV8s_pillow_img_THA_20240625.png",
    },
    "SV7s-th": {
        "name": "แสงนำทางแห่งสเตลลาร์ (Stellar Guidance)",
        "release_date": "2024-08-30",
        "logo_url": f"{IMG_BASE}/TH_SV7s_Booster.png",
    },
    "SV6-th": {
        "name": "หน้ากากจอมลวงตา (Mask of Deception)",
        "release_date": "2024-05-31",
        "logo_url": f"{IMG_BASE}/SV6_Booster_THA.png",
    },
    "SV5M-th": {
        "name": "ตุลาการไซเบอร์ (Cyber Judge)",
        "release_date": "2024-02-23",
        "logo_url": f"{IMG_BASE}/SV5M_Booster_THA.png",
    },
    "SV5K-th": {
        "name": "ไวลด์ฟอร์ซ (Wild Force)",
        "release_date": "2024-02-23",
        "logo_url": f"{IMG_BASE}/SV5K_Booster_THA.png",
    },
    "SV5a-th": {
        "name": "คริมซัน เฮซ (Crimson Haze)",
        "release_date": "2024-04-26",
        "logo_url": f"{IMG_BASE}/SV5a_Booster_THA.png",
    },
    "SV4a-th": {
        "name": "ไชนีเทรเชอร์ex (Shiny Treasure ex)",
        "release_date": "2024-01-26",
        "logo_url": f"{IMG_BASE}/Pkg_SV4a_THA.png",
    },
    "SV4M-th": {
        "name": "ประกายแสงจากอนาคต (Sparkle from the Future)",
        "release_date": "2023-12-15",
        "logo_url": f"{IMG_BASE}/SV4M_Booster_THA.png",
    },
    "SV4K-th": {
        "name": "เสียงคำรามจากอดีต (Roar from the Past)",
        "release_date": "2023-12-15",
        "logo_url": f"{IMG_BASE}/SV4K_Booster_THA.png",
    },
}


def main():
    print("Updating Thai sets with release dates, English names, and pack images...\n")

    for set_id, fields in UPDATES.items():
        print(f"  {set_id}: {fields['name']} ({fields['release_date']})")
        sb.table("sets").update(fields).eq("id", set_id).execute()

    print(f"\nUpdated {len(UPDATES)} sets. Done!")


if __name__ == "__main__":
    main()

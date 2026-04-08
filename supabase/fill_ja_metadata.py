"""
Fill missing metadata for Japanese cards using TCGdex API.
Updates: hp, rarity, supertype, subtypes, types, artist for all JA cards.
"""

import os
import sys
import time
import requests

sys.stdout.reconfigure(encoding='utf-8')

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

TCGDEX_BASE = "https://api.tcgdex.net/v2/ja"

session = requests.Session()

# Map TCGdex "category" / "stage" to our supertype
def get_supertype(card_data):
    cat = card_data.get("category", "").lower()
    if cat == "pokemon":
        return "Pokémon"
    elif cat == "trainer":
        return "Trainer"
    elif cat == "energy":
        return "Energy"
    return ""


def get_subtypes(card_data):
    """Extract subtypes from card data."""
    subtypes = []
    stage = card_data.get("stage", "")
    if stage:
        subtypes.append(stage)  # "Basic", "Stage1", "Stage2", etc.
    # Check for ex, V, VMAX, etc. in the name
    name = card_data.get("name", "")
    for suffix in ["ex", "EX", "GX", "V", "VSTAR", "VMAX", "BREAK"]:
        if suffix in name:
            subtypes.append(suffix)
            break
    # Trainer subtypes
    item = card_data.get("trainerType", "")
    if item:
        subtypes.append(item)  # "Item", "Supporter", "Stadium", "Tool"
    # Energy subtypes
    energy_type = card_data.get("energyType", "")
    if energy_type:
        subtypes.append(energy_type)
    return subtypes


def get_types(card_data):
    """Extract types list."""
    return card_data.get("types", []) or []


def main():
    # Get all JA sets
    sets_result = sb.table("sets").select("id").like("id", "%-ja").execute()
    all_sets = [s["id"] for s in (sets_result.data or [])]
    print(f"Found {len(all_sets)} JA sets\n")

    total_updated = 0
    total_skipped = 0
    total_failed = 0
    sets_done = 0

    for set_id in sorted(all_sets):
        # Extract the TCGdex set code: "SV7-ja" -> "SV7"
        tcgdex_set = set_id.replace("-ja", "")

        # Get cards from our DB for this set
        cards_result = sb.table("cards").select("id, number, hp").eq("set_id", set_id).execute()
        our_cards = cards_result.data or []
        if not our_cards:
            continue

        # Skip sets where cards already have HP data (already processed)
        filled = sum(1 for c in our_cards if c.get("hp"))
        if filled > len(our_cards) * 0.5:
            sets_done += 1
            print(f"  [{sets_done}/{len(all_sets)}] {set_id}: SKIP ({filled}/{len(our_cards)} already have HP)")
            continue

        # Fetch set card list from TCGdex
        try:
            resp = session.get(f"{TCGDEX_BASE}/sets/{tcgdex_set}", timeout=15)
            if resp.status_code != 200:
                print(f"  SKIP {set_id}: TCGdex set not found ({resp.status_code})")
                total_skipped += len(our_cards)
                continue
            tcgdex_set_data = resp.json()
        except Exception as e:
            print(f"  ERROR {set_id}: {e}")
            total_failed += len(our_cards)
            continue

        tcgdex_cards = tcgdex_set_data.get("cards", [])
        # Build lookup by localId
        tcgdex_map = {}
        for c in tcgdex_cards:
            local_id = c.get("localId", "")
            tcgdex_map[local_id] = c

        set_updated = 0
        set_need_detail = []

        # Match our cards to TCGdex cards
        for card in our_cards:
            number = card["number"]
            # Try different number formats
            tcg_card = (
                tcgdex_map.get(number) or
                tcgdex_map.get(number.zfill(3)) or
                tcgdex_map.get(number.lstrip("0") or "0")
            )
            if tcg_card:
                set_need_detail.append((card["id"], tcg_card["id"]))
            else:
                total_skipped += 1

        # Fetch individual card details and update
        for card_id, tcgdex_id in set_need_detail:
            try:
                resp = session.get(f"{TCGDEX_BASE}/cards/{tcgdex_id}", timeout=10)
                if resp.status_code != 200:
                    total_skipped += 1
                    continue
                detail = resp.json()
            except Exception:
                total_failed += 1
                continue

            hp = str(detail.get("hp", "")) if detail.get("hp") else ""
            rarity = detail.get("rarity", "") or ""
            supertype = get_supertype(detail)
            subtypes = get_subtypes(detail)
            types = get_types(detail)
            artist = detail.get("illustrator", "") or ""

            update_data = {}
            if hp:
                update_data["hp"] = hp
            if rarity:
                update_data["rarity"] = rarity
            if supertype:
                update_data["supertype"] = supertype
            if subtypes:
                update_data["subtypes"] = subtypes
            if types:
                update_data["types"] = types
            if artist:
                update_data["artist"] = artist

            if update_data:
                for attempt in range(3):
                    try:
                        sb.table("cards").update(update_data).eq("id", card_id).execute()
                        set_updated += 1
                        total_updated += 1
                        break
                    except Exception as e:
                        if attempt < 2:
                            time.sleep(5)  # Wait and retry on transient errors
                        else:
                            print(f"    FAIL {card_id}: {e}")
                            total_failed += 1
            else:
                total_skipped += 1

            # Rate limit: ~5 req/s to be nice
            time.sleep(0.2)

        sets_done += 1
        print(f"  [{sets_done}/{len(all_sets)}] {set_id}: {set_updated}/{len(our_cards)} cards updated")

    print(f"\nDone: {total_updated} updated, {total_skipped} skipped, {total_failed} failed")


if __name__ == "__main__":
    main()

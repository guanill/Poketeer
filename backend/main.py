"""
main.py — FastAPI backend for Pokémon card recognition.

Recognition pipeline (fully local, zero external API calls at scan time):
  1. OCR  — EasyOCR reads the card name from the top of the image,
             fuzzy-matched against the local card_names.json catalog.
  2. Visual — ResNet50 cosine similarity against card_index.npz.
  3. Merge — results are combined and deduplicated; OCR hits are boosted.

Endpoints
---------
POST /scan             Upload an image → returns top-N card matches
GET  /health           Server + index status
GET  /index/stats      Index / card catalog stats
POST /index/reload     Hot-reload indexes without restart
"""

import asyncio
import bisect
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import json
from pathlib import Path
import time
import urllib.parse

import numpy as np
import requests as _requests
import urllib.parse
import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from model import extract_features, prewarm as prewarm_model
    _MODEL_AVAILABLE = True
except Exception:
    _MODEL_AVAILABLE = False
    def extract_features(_bytes: bytes):  # type: ignore[misc]
        raise RuntimeError("ML model not available (torch/torchvision not installed)")
    def prewarm_model() -> None:  # type: ignore[misc]
        pass

import ocr_matcher
import card_detector
import image_preprocessing

# Thread pool for running blocking CPU work concurrently inside async endpoints
_EXECUTOR = ThreadPoolExecutor(max_workers=2)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    _load_visual_index()
    ocr_matcher.load_card_names()
    _load_sets()
    _build_search_index()
    _build_card_lookup()
    _load_prices_cache()
    # Pre-warm models if available
    if _MODEL_AVAILABLE:
        loop = asyncio.get_event_loop()
        await asyncio.gather(
            loop.run_in_executor(_EXECUTOR, prewarm_model),
            loop.run_in_executor(_EXECUTOR, ocr_matcher.prewarm),
        )
    yield


app = FastAPI(title="Poketeer Card Scanner API", version="2.0.0", lifespan=lifespan)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class OpenCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Max-Age": "600",
                },
            )
        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response


app.add_middleware(OpenCORSMiddleware)

INDEX_PATH = Path(__file__).parent / "card_index.npz"

# ---------------------------------------------------------------------------
# Visual index (lazy, cached)
# ---------------------------------------------------------------------------

_FEATURES: np.ndarray | None = None   # (N, 2048) float32, L2-normalised
_METADATA: list[dict] | None = None


def _load_visual_index() -> None:
    global _FEATURES, _METADATA
    if not INDEX_PATH.exists():
        print("[index] card_index.npz not found — visual matching disabled")
        return
    data = np.load(str(INDEX_PATH), allow_pickle=False)
    _FEATURES = data["features"]
    _METADATA = json.loads(data["metadata"].tobytes().decode("utf-8"))
    print(f"[index] Loaded {len(_METADATA)} visual features from {INDEX_PATH}")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class CardMatch(BaseModel):
    id: str
    name: str
    number: str
    set_id: str
    set_name: str
    rarity: str
    image_small: str
    image_large: str
    supertype: str
    subtypes: list[str]
    hp: str
    artist: str
    confidence: float
    method: str = "visual"   # "ocr" | "visual" | "ocr+visual"


class ScanResponse(BaseModel):
    matches: list[CardMatch]
    ocr_text: str             # raw text EasyOCR found (useful for debugging)
    method_used: str          # "ocr" | "visual" | "combined" | "none"
    visual_index_size: int
    catalog_size: int


class HealthResponse(BaseModel):
    status: str
    visual_index_loaded: bool
    ocr_catalog_loaded: bool
    card_detector_available: bool
    card_detector_mode: str
    visual_index_size: int
    catalog_size: int


class IndexStatsResponse(BaseModel):
    visual_index_size: int
    catalog_size: int
    index_path: str
    index_exists: bool


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _visual_matches(image_bytes: bytes, top_k: int, use_tta: bool = True) -> list[dict]:
    """
    Return top-k visual matches using ResNet50 cosine similarity.
    When use_tta=True, generates augmented versions of the image and
    averages their feature vectors for a more robust match.
    """
    if _FEATURES is None or _METADATA is None:
        return []

    try:
        if use_tta:
            # Test-time augmentation: extract features from multiple augmentations
            augmented = image_preprocessing.generate_augmentations(image_bytes, n=3)
            feature_list = []
            for aug_bytes in augmented:
                try:
                    f = extract_features(aug_bytes)
                    feature_list.append(f)
                except Exception:
                    pass
            if not feature_list:
                return []
            # Average the feature vectors and re-normalise
            qf = np.mean(feature_list, axis=0).astype(np.float32)
            norm = np.linalg.norm(qf)
            if norm > 0:
                qf = qf / norm
        else:
            qf = extract_features(image_bytes)
    except Exception:
        return []

    scores: np.ndarray = _FEATURES @ qf
    k = min(top_k, len(_METADATA))
    top_idx = np.argpartition(scores, -k)[-k:]
    top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]
    return [
        {**_METADATA[i], "confidence": float(np.clip(scores[i], 0.0, 1.0)),
         "method": "visual"}
        for i in top_idx
    ]


def _merge(
    ocr_hits: list[dict],
    visual_hits: list[dict],
    top_k: int,
) -> tuple[list[dict], str]:
    """
    Merge OCR and visual results.
    Cards that appear in both lists get their confidence boosted and
    are labelled 'ocr+visual'.  OCR-only hits rank above visual-only.
    """
    if not ocr_hits and not visual_hits:
        return [], "none"

    visual_by_id = {m["id"]: m for m in visual_hits}
    seen: set[str] = set()
    merged: list[dict] = []

    # OCR hits first (possibly boosted if also in visual)
    for hit in ocr_hits:
        cid = hit["id"]
        if cid in visual_by_id:
            combined_conf = min((hit["confidence"] + visual_by_id[cid]["confidence"]) / 2 * 1.2, 1.0)
            merged.append({**hit, "confidence": round(combined_conf, 4), "method": "ocr+visual"})
        else:
            merged.append({**hit, "method": "ocr"})
        seen.add(cid)

    # Remaining visual-only hits
    for hit in visual_hits:
        if hit["id"] not in seen:
            merged.append(hit)
            seen.add(hit["id"])

    merged.sort(key=lambda x: -x["confidence"])

    if ocr_hits and visual_hits:
        method = "combined"
    elif ocr_hits:
        method = "ocr"
    else:
        method = "visual"

    return merged[:top_k], method


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        visual_index_loaded=_FEATURES is not None,
        ocr_catalog_loaded=ocr_matcher.is_ready(),
        card_detector_available=card_detector.is_available(),
        card_detector_mode=card_detector.DETECTOR_MODE,
        visual_index_size=len(_METADATA) if _METADATA else 0,
        catalog_size=len(ocr_matcher._CARD_NAMES) if ocr_matcher._CARD_NAMES else 0,
    )


@app.get("/index/stats", response_model=IndexStatsResponse)
def index_stats():
    return IndexStatsResponse(
        visual_index_size=len(_METADATA) if _METADATA else 0,
        catalog_size=len(ocr_matcher._CARD_NAMES) if ocr_matcher._CARD_NAMES else 0,
        index_path=str(INDEX_PATH),
        index_exists=INDEX_PATH.exists(),
    )


class ScanRequest(BaseModel):
    """Query params for scan endpoint."""
    top_k: int = 5
    detect: bool = True     # use card detection to crop the card first
    preprocess: bool = True  # apply image preprocessing


@app.post("/scan", response_model=ScanResponse)
async def scan_card(
    image: UploadFile = File(...),
    top_k: int = 5,
    detect: bool = True,
    preprocess: bool = True,
):
    """
    Upload a card photo (JPEG / PNG / WEBP).

    Pipeline:
      1. (Optional) Card detection — detect and crop the card from the photo
         using a Roboflow-trained model, removing background clutter.
      2. (Optional) Image preprocessing — white-balance, contrast stretch,
         denoise, and sharpen for cleaner feature extraction.
      3. OCR — EasyOCR reads the card name, fuzzy-matched against catalog.
      4. Visual — ResNet50 cosine similarity with test-time augmentation.
      5. Merge — results are combined and deduplicated; OCR hits boosted.
    """
    if not ocr_matcher.is_ready() and (_FEATURES is None):
        raise HTTPException(
            status_code=503,
            detail="No card catalog or index loaded. Run `python build_index.py` first.",
        )

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    loop = asyncio.get_event_loop()

    # Step 1: Card detection — crop the card from the photo
    card_bytes = image_bytes
    if detect and card_detector.is_available():
        card_bytes = await loop.run_in_executor(
            _EXECUTOR, card_detector.crop_best_card, image_bytes
        )

    # Step 2: Preprocessing — separate paths for OCR vs visual
    if preprocess:
        ocr_bytes = image_preprocessing.preprocess_for_ocr(card_bytes)
        vis_bytes = image_preprocessing.preprocess_for_visual(card_bytes)
    else:
        ocr_bytes = card_bytes
        vis_bytes = card_bytes

    # Step 3 & 4: Run OCR and visual pipelines concurrently
    ocr_task = loop.run_in_executor(
        _EXECUTOR, ocr_matcher.ocr_matches, ocr_bytes, top_k * 2
    )
    vis_task = loop.run_in_executor(
        _EXECUTOR, _visual_matches, vis_bytes, top_k * 2
    )
    ocr_hits, visual_hits = await asyncio.gather(ocr_task, vis_task)

    # Step 5: Merge results
    matches, method = _merge(ocr_hits, visual_hits, top_k)

    # Extract the raw OCR text for debugging
    ocr_text = ""
    try:
        reader = ocr_matcher._get_reader()
        crop = ocr_matcher._crop_name_region(ocr_bytes)
        raw = reader.readtext(crop, detail=True, paragraph=False, beamWidth=1)
        ocr_text = " | ".join(t for (_, t, c) in raw if c > 0.2)
    except Exception:
        pass

    return ScanResponse(
        matches=[CardMatch(**m) for m in matches],
        ocr_text=ocr_text,
        method_used=method,
        visual_index_size=len(_METADATA) if _METADATA else 0,
        catalog_size=len(ocr_matcher._CARD_NAMES) if ocr_matcher._CARD_NAMES else 0,
    )


# ---------------------------------------------------------------------------
# Fast in-memory search index
# ---------------------------------------------------------------------------
# Sorted list of (name_lower, card_record) for O(log n) prefix lookup.
_SEARCH_SORTED: list[tuple[str, dict]] = []
_SEARCH_KEYS: list[str] = []   # parallel list of names for bisect


def _build_search_index() -> None:
    global _SEARCH_SORTED, _SEARCH_KEYS
    if not ocr_matcher._CARD_NAMES:
        return
    pairs = [(c["name"].lower(), c) for c in ocr_matcher._CARD_NAMES]
    pairs.sort(key=lambda x: x[0])
    _SEARCH_SORTED = pairs
    _SEARCH_KEYS = [p[0] for p in pairs]
    print(f"[search] Index built ({len(_SEARCH_SORTED)} cards)")


# ---------------------------------------------------------------------------
# Card-by-ID lookup (for batch fetch from Collection page)
# ---------------------------------------------------------------------------
_CARD_BY_ID: dict[str, dict] = {}


def _build_card_lookup() -> None:
    global _CARD_BY_ID
    if not ocr_matcher._CARD_NAMES:
        return
    _CARD_BY_ID = {c["id"]: c for c in ocr_matcher._CARD_NAMES}
    print(f"[lookup] Card-by-ID index built ({len(_CARD_BY_ID)} entries)")


@app.get("/batch-cards")
def get_cards_batch(ids: str = ""):
    """
    Fetch multiple cards by comma-separated IDs.
    Used by the Collection page to resolve scanned card IDs locally.
    """
    if not ids.strip():
        return []
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    return [
        _card_record_to_api(_CARD_BY_ID[cid])
        for cid in id_list
        if cid in _CARD_BY_ID
    ]


def _fast_search(q: str, page: int, page_size: int) -> dict:
    """Sub-millisecond card search: prefix via bisect, then substring scan."""
    q_lower = q.strip().lower()
    if not q_lower or not _SEARCH_SORTED:
        return {"data": [], "totalCount": 0, "page": page, "pageSize": page_size, "count": 0}

    # 1. Prefix matches via binary search (O(log n + k))
    lo = bisect.bisect_left(_SEARCH_KEYS, q_lower)
    prefix_ids: set[str] = set()
    results: list[dict] = []
    for i in range(lo, len(_SEARCH_SORTED)):
        name, card = _SEARCH_SORTED[i]
        if not name.startswith(q_lower):
            break
        prefix_ids.add(card["id"])
        results.append(card)

    # 2. Substring matches for non-prefix hits (linear, <1 ms for 20k cards)
    if len(q_lower) >= 2:
        for name, card in _SEARCH_SORTED:
            if card["id"] not in prefix_ids and q_lower in name:
                results.append(card)

    total = len(results)
    start = (page - 1) * page_size
    page_slice = results[start: start + page_size]

    return {
        "data": [_card_record_to_api(c) for c in page_slice],
        "totalCount": total,
        "page": page,
        "pageSize": page_size,
        "count": len(page_slice),
    }


@app.get("/search")
def search_cards_endpoint(q: str = "", page: int = 1, pageSize: int = 30):
    """Fast local card search — prefix-first, then substring, fully in-memory."""
    return _fast_search(q, page, pageSize)


SETS_PATH = Path(__file__).parent / "sets.json"
SETS_JA_PATH = Path(__file__).parent / "sets_ja.json"
SETS_TH_PATH = Path(__file__).parent / "sets_th.json"
PRICES_CACHE_PATH = Path(__file__).parent / "prices_cache.json"

# In-memory sets lookup (id → set dict) for building card responses
_SETS_BY_ID: dict[str, dict] = {}
_SETS_JA: list[dict] = []
_SETS_TH: list[dict] = []
_SETS_BY_ID_JA: dict[str, dict] = {}
_SETS_BY_ID_TH: dict[str, dict] = {}

# Disk + memory cache for tcgdex card responses
_INTL_CARDS_CACHE: dict[str, dict] = {}  # memory layer: "lang:set_id" → {cards, updated}
_INTL_CARDS_CACHE_DIR = Path(__file__).parent / "_intl_cards_cache"
_INTL_CARDS_TTL = 86_400  # 24 hours (survived restarts via disk)

_INTL_CARDS_CACHE_DIR.mkdir(exist_ok=True)


def _intl_cache_path(lang: str, set_id: str) -> Path:
    return _INTL_CARDS_CACHE_DIR / f"{lang}_{set_id}.json"


def _load_intl_cache(lang: str, set_id: str) -> list[dict] | None:
    """Load cards from disk cache if fresh enough."""
    key = f"{lang}:{set_id}"
    # Check memory first
    mem = _INTL_CARDS_CACHE.get(key)
    if mem and (time.time() - mem.get("updated", 0)) < _INTL_CARDS_TTL:
        return mem["cards"]
    # Check disk
    p = _intl_cache_path(lang, set_id)
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            if (time.time() - data.get("updated", 0)) < _INTL_CARDS_TTL:
                cards = data["cards"]
                _INTL_CARDS_CACHE[key] = {"cards": cards, "updated": data["updated"]}
                return cards
        except Exception:
            pass
    return None


def _save_intl_cache(lang: str, set_id: str, cards: list[dict]) -> None:
    """Persist cards to memory + disk cache."""
    key = f"{lang}:{set_id}"
    now = time.time()
    _INTL_CARDS_CACHE[key] = {"cards": cards, "updated": now}
    p = _intl_cache_path(lang, set_id)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"cards": cards, "updated": now}, f, ensure_ascii=False)
    except Exception as exc:
        print(f"[intl] Warning: could not write disk cache {p}: {exc}")

# ---------------------------------------------------------------------------
# Prices cache
# ---------------------------------------------------------------------------
_PRICES_CACHE: dict[str, dict] = {}  # { cardId: {"market": float|None, "updated": float, "failed"?: bool} }
_PRICES_TTL = 86_400      # 24 h for confirmed prices
_PRICES_NULL_TTL = 3_600  # 1 h retry for failed / null lookups


def _load_prices_cache() -> None:
    global _PRICES_CACHE
    if PRICES_CACHE_PATH.exists():
        with open(PRICES_CACHE_PATH, encoding="utf-8") as f:
            _PRICES_CACHE = json.load(f)
        print(f"[prices] Loaded {len(_PRICES_CACHE)} cached prices")


def _save_prices_cache() -> None:
    with open(PRICES_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(_PRICES_CACHE, f)


def _tcgplayer_market(tcgplayer: dict) -> float | None:
    prices = tcgplayer.get("prices") or {}
    for variant in ("holofoil", "normal", "reverseHolofoil",
                    "1stEditionHolofoil", "unlimited", "1stEdition"):
        market = (prices.get(variant) or {}).get("market")
        if market:
            return float(market)
    return None


def _fetch_prices_remote(card_ids: list[str]) -> dict[str, dict]:
    """
    Fetch TCGPlayer market prices from pokemontcg.io.
    Tries the batch search endpoint first; if that times out falls back to
    individual  GET /cards/{id}  requests (smaller response, more reliable).
    Failed entries are marked with "failed": True so they use a short retry TTL.
    """
    results: dict[str, dict] = {}
    now = time.time()
    BATCH = 50
    session = _requests.Session()
    session.headers["User-Agent"] = "poketeer/1.0"

    for i in range(0, len(card_ids), BATCH):
        batch = card_ids[i : i + BATCH]
        q = " OR ".join(f"id:{cid}" for cid in batch)
        batch_ok = False
        try:
            resp = session.get(
                "https://api.pokemontcg.io/v2/cards",
                params={"q": q, "select": "id,tcgplayer", "pageSize": BATCH},
                timeout=5,  # short — fall back to individual requests if slow
            )
            resp.raise_for_status()
            for card in resp.json().get("data", []):
                market = _tcgplayer_market(card.get("tcgplayer") or {})
                results[card["id"]] = {"market": market, "updated": now}
            batch_ok = True
        except Exception as exc:
            print(f"[prices] batch fetch failed (batch {i}): {exc} — trying individual lookups")

        if not batch_ok:
            # Fall back to individual /cards/{id} — smaller payload, faster response.
            # Run in parallel to avoid sequential blocking.
            def _fetch_one(cid: str) -> tuple[str, dict]:
                try:
                    r2 = session.get(
                        f"https://api.pokemontcg.io/v2/cards/{cid}",
                        params={"select": "id,tcgplayer"},
                        timeout=7,
                    )
                    r2.raise_for_status()
                    card_data = r2.json().get("data") or {}
                    market = _tcgplayer_market(card_data.get("tcgplayer") or {})
                    return cid, {"market": market, "updated": now}
                except Exception as e2:
                    print(f"[prices] individual fetch failed for {cid}: {e2}")
                    return cid, {"market": None, "updated": now, "failed": True}

            missing = [cid for cid in batch if cid not in results]
            from concurrent.futures import ThreadPoolExecutor as _TPE
            with _TPE(max_workers=min(len(missing), 10)) as pool:
                for cid, entry in pool.map(_fetch_one, missing):
                    results[cid] = entry

    return results


@app.get("/prices")
def get_prices_endpoint(ids: str = ""):
    """
    Return market prices for comma-separated card IDs.
    Stale / missing entries are fetched from pokemontcg.io and cached to disk.
    """
    if not ids.strip():
        return {}
    id_list = [x.strip() for x in ids.split(",") if x.strip()]
    now = time.time()

    def _entry_ttl(entry: dict) -> float:
        """Short TTL for failed/null entries so they are retried sooner."""
        return _PRICES_NULL_TTL if (entry.get("failed") or entry.get("market") is None) else _PRICES_TTL

    stale = [
        cid for cid in id_list
        if cid not in _PRICES_CACHE
        or (now - _PRICES_CACHE[cid].get("updated", 0)) > _entry_ttl(_PRICES_CACHE[cid])
    ]
    if stale:
        fetched = _fetch_prices_remote(stale)
        _PRICES_CACHE.update(fetched)
        _save_prices_cache()

    return {
        cid: (_PRICES_CACHE[cid]["market"] if cid in _PRICES_CACHE else None)
        for cid in id_list
    }



def _load_sets() -> None:
    global _SETS_BY_ID, _SETS_JA, _SETS_TH, _SETS_BY_ID_JA, _SETS_BY_ID_TH
    if SETS_PATH.exists():
        with open(SETS_PATH, encoding="utf-8") as f:
            sets_list = json.load(f)
        _SETS_BY_ID = {s["id"]: s for s in sets_list}
        print(f"[sets] Loaded {len(_SETS_BY_ID)} EN set records")
    if SETS_JA_PATH.exists():
        with open(SETS_JA_PATH, encoding="utf-8") as f:
            _SETS_JA = json.load(f)
        _SETS_BY_ID_JA = {s["id"]: s for s in _SETS_JA}
        print(f"[sets] Loaded {len(_SETS_JA)} JP set records")
    if SETS_TH_PATH.exists():
        with open(SETS_TH_PATH, encoding="utf-8") as f:
            _SETS_TH = json.load(f)
        _SETS_BY_ID_TH = {s["id"]: s for s in _SETS_TH}
        print(f"[sets] Loaded {len(_SETS_TH)} TH set records")


def _card_record_to_api(card: dict) -> dict:
    """Convert a card_names.json record to a PokemonCard-shaped dict."""
    set_info = _SETS_BY_ID.get(card.get("set_id", ""), {})
    return {
        "id": card["id"],
        "name": card["name"],
        "supertype": card.get("supertype", ""),
        "subtypes": card.get("subtypes") or [],
        "hp": card.get("hp", ""),
        "types": card.get("types") or [],
        "number": card.get("number", ""),
        "artist": card.get("artist", ""),
        "rarity": card.get("rarity", ""),
        "set": {
            "id": card.get("set_id", ""),
            "name": set_info.get("name") or card.get("set_name", ""),
            "series": set_info.get("series", ""),
            "images": set_info.get("images", {"symbol": "", "logo": ""}),
        },
        "images": {
            "small": card.get("image_small", ""),
            "large": card.get("image_large", ""),
        },
    }


@app.get("/sets")
def get_sets(lang: str = "en"):
    """
    Return Pokémon TCG sets with metadata + logo URLs.
    ?lang=en  → English sets (default)
    ?lang=ja  → Japanese sets (from sets_ja.json)
    ?lang=th  → Thai sets (from sets_th.json)
    """
    if lang == "ja":
        return _SETS_JA
    if lang == "th":
        return _SETS_TH

    # English — prefer the richer sets.json written by build_index.py
    if SETS_PATH.exists():
        with open(SETS_PATH, encoding="utf-8") as f:
            return json.load(f)

    # Fallback: derive unique sets from the card catalog
    if not ocr_matcher._CARD_NAMES:
        return []
    seen: dict[str, dict] = {}
    for card in ocr_matcher._CARD_NAMES:
        sid = card.get("set_id", "")
        if sid and sid not in seen:
            seen[sid] = {
                "id": sid,
                "name": card.get("set_name", sid),
                "series": "",
                "printedTotal": 0,
                "total": 0,
                "releaseDate": "",
                "images": {"symbol": "", "logo": ""},
            }
        if sid:
            seen[sid]["total"] += 1
    return list(seen.values())


@app.get("/sets/{set_id}")
def get_set(set_id: str, lang: str = ""):
    """Return metadata for a single set. Optional ?lang= to prefer a language."""
    if lang == "ja" and set_id in _SETS_BY_ID_JA:
        return _SETS_BY_ID_JA[set_id]
    if lang == "th" and set_id in _SETS_BY_ID_TH:
        return _SETS_BY_ID_TH[set_id]
    if set_id in _SETS_BY_ID:
        return _SETS_BY_ID[set_id]
    if set_id in _SETS_BY_ID_JA:
        return _SETS_BY_ID_JA[set_id]
    if set_id in _SETS_BY_ID_TH:
        return _SETS_BY_ID_TH[set_id]
    # Fallback: derive from card catalog
    if ocr_matcher._CARD_NAMES:
        for card in ocr_matcher._CARD_NAMES:
            if card.get("set_id") == set_id:
                return {"id": set_id, "name": card.get("set_name", set_id),
                        "series": "", "printedTotal": 0, "total": 0,
                        "releaseDate": "", "images": {"symbol": "", "logo": ""}}
    raise HTTPException(status_code=404, detail=f"Set {set_id!r} not found")


@app.get("/cards/{set_id}")
def get_cards_by_set(
    set_id: str,
    page: int = 1,
    pageSize: int = 60,
):
    """
    Return paginated cards for a set in PokemonCard-compatible shape.
    All data comes from the local card_names.json catalog.
    """
    if not ocr_matcher._CARD_NAMES:
        return {"data": [], "totalCount": 0, "page": page, "pageSize": pageSize, "count": 0}

    # Filter + sort by collector number
    set_cards = [
        c for c in ocr_matcher._CARD_NAMES
        if c.get("set_id") == set_id
    ]
    set_cards.sort(key=lambda c: int(c["number"]) if str(c.get("number", "")).isdigit() else 9999)

    total = len(set_cards)
    start = (page - 1) * pageSize
    page_cards = set_cards[start: start + pageSize]

    return {
        "data": [_card_record_to_api(c) for c in page_cards],
        "totalCount": total,
        "page": page,
        "pageSize": pageSize,
        "count": len(page_cards),
    }


def _tcgdex_card_to_api(card: dict, set_id: str, lang: str, set_info: dict,
                        serie_id: str = "") -> dict:
    """Convert a tcgdex card list item → PokemonCard-shaped dict."""
    local_id = card.get("localId", "")
    image_base = card.get("image", "")
    # Construct image URL from CDN pattern when the API doesn't include it
    if not image_base and serie_id and local_id:
        image_base = f"https://assets.tcgdex.net/{lang}/{serie_id}/{set_id}/{local_id}"
    return {
        "id": card["id"],
        "name": card.get("name") or "",
        "supertype": "Pokémon",
        "subtypes": [],
        "hp": "",
        "types": [],
        "number": local_id,
        "artist": "",
        "rarity": card.get("rarity") or "",
        "set": {
            "id": set_id,
            "name": set_info.get("name", set_id),
            "series": set_info.get("series", ""),
            "images": set_info.get("images", {"symbol": "", "logo": ""}),
        },
        "images": {
            "small": f"{image_base}/low.webp" if image_base else "",
            "large": f"{image_base}/high.webp" if image_base else "",
        },
        "language": lang,
    }


@app.get("/intl-cards-prefetch/{lang}")
def prefetch_intl_cards(lang: str, ids: str = ""):
    """
    Background-warm the card cache for a comma-separated list of set IDs.
    Called silently by the frontend when showing a JP/TH set list.
    Returns immediately — fetching runs in a daemon thread pool.
    """
    if lang not in ("ja", "th"):
        return {"status": "ok", "warmed": 0}
    set_ids = [s.strip() for s in ids.split(",") if s.strip()][:20]  # cap at 20

    def _warm(set_id: str):
        if _load_intl_cache(lang, set_id) is not None:
            return  # already cached
        try:
            resp = _requests.get(
                f"https://api.tcgdex.net/v2/{lang}/sets/{urllib.parse.quote(set_id, safe='')}",
                headers={"User-Agent": "poketeer/1.0"},
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()
            raw_cards = body.get("cards", [])
            serie_id = (body.get("serie") or {}).get("id", "")
            set_info = _SETS_BY_ID_JA.get(set_id) or _SETS_BY_ID_TH.get(set_id) or {}
            cards = [_tcgdex_card_to_api(c, set_id, lang, set_info, serie_id) for c in raw_cards]
            _save_intl_cache(lang, set_id, cards)
            print(f"[intl-prefetch] warmed {lang}/{set_id} ({len(cards)} cards)")
        except Exception as exc:
            print(f"[intl-prefetch] failed {lang}/{set_id}: {exc}")

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(_warm, set_ids))

    return {"status": "ok", "warmed": len(set_ids)}


@app.get("/intl-cards/{lang}/{set_id}")
def get_intl_cards(lang: str, set_id: str, page: int = 1, pageSize: int = 60):
    """
    Return paginated cards for a JP/TH set, fetched live from tcgdex.net
    and cached in memory for 1 hour.
    """
    if lang not in ("ja", "th"):
        raise HTTPException(status_code=400, detail="lang must be ja or th")

    all_cards: list[dict] | None = _load_intl_cache(lang, set_id)
    if all_cards is None:
        try:
            resp = _requests.get(
                f"https://api.tcgdex.net/v2/{lang}/sets/{urllib.parse.quote(set_id, safe='')}",
                headers={"User-Agent": "poketeer/1.0"},
                timeout=12,
            )
            resp.raise_for_status()
            body = resp.json()
            raw_cards = body.get("cards", [])
            serie_id = (body.get("serie") or {}).get("id", "")
            set_info = _SETS_BY_ID_JA.get(set_id) or _SETS_BY_ID_TH.get(set_id) or {}
            all_cards = [_tcgdex_card_to_api(c, set_id, lang, set_info, serie_id) for c in raw_cards]
            _save_intl_cache(lang, set_id, all_cards)
        except Exception as exc:
            print(f"[intl] Error fetching {lang}/{set_id}: {exc}")
            return {"data": [], "totalCount": 0, "page": page, "pageSize": pageSize, "count": 0}

    total = len(all_cards)
    start = (page - 1) * pageSize
    page_slice = all_cards[start: start + pageSize]
    return {
        "data": page_slice,
        "totalCount": total,
        "page": page,
        "pageSize": pageSize,
        "count": len(page_slice),
    }


@app.post("/index/reload")
def reload_index():
    """Hot-reload both indexes and set data from disk."""
    _load_visual_index()
    ocr_matcher.load_card_names()
    _load_sets()
    _build_card_lookup()
    return {
        "status": "reloaded",
        "visual_index_size": len(_METADATA) if _METADATA else 0,
        "catalog_size": len(ocr_matcher._CARD_NAMES) if ocr_matcher._CARD_NAMES else 0,
        "sets_en": len(_SETS_BY_ID),
        "sets_ja": len(_SETS_JA),
        "sets_th": len(_SETS_TH),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

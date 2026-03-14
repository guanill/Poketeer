# Poketeer — Card Scanner Backend

A FastAPI service that uses a pre-trained **ResNet50** model to identify
Pokémon cards from photos.  It compares visual features against a pre-built
index of card images fetched from the Pokémon TCG API.

## Quick start

```bash
cd backend

# 1. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Build the card index
#    This downloads card images and extracts ResNet50 features.
#    Full index (~17 000 cards) takes ~2-3 hours and ~400 MB disk space.
#    Use --limit for a quick smoke-test:
python build_index.py --limit 500

#    Index specific sets only:
python build_index.py --sets base1 base2 jungle fossil

#    Full index (all sets, no limit):
python build_index.py

# 4. Start the API server
python main.py
#    → http://localhost:8000
#    → Docs: http://localhost:8000/docs
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/scan` | Upload a card image (`multipart/form-data`, field `image`). Returns top-5 matches. |
| `GET`  | `/health` | Server + index status. |
| `GET`  | `/index/stats` | Number of indexed cards. |
| `POST` | `/index/reload` | Reload the index from disk without restarting. |

### `/scan` query params

| Param | Default | Description |
|-------|---------|-------------|
| `top_k` | `5` | Number of candidate matches to return. |

## How it works

1. **Feature extraction** — ResNet50 (ImageNet pre-trained, final FC layer removed)
   produces a 2048-D embedding for each image.
2. **Index** — All card embeddings are stored in a compressed NumPy file
   (`card_index.npz`) along with card metadata.
3. **Matching** — Query embedding is dot-multiplied against the index matrix
   (equivalent to cosine similarity because both sides are L2-normalised).
   The top-K results are returned ranked by similarity score.

## Tips for best accuracy

* Use good lighting and lay the card flat without glare.
* Crop the image to the card only when possible.
* The more cards in the index, the better — run `build_index.py` without
  `--limit` for the complete index.
* Adding your Pokémon TCG API key (`--api-key YOUR_KEY`) during indexing
  removes the free-tier rate limit and speeds up the process significantly.

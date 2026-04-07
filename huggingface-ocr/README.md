---
title: Poketeer Card OCR
emoji: 🔍
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
---

# Poketeer Card OCR

PaddleOCR-powered Pokemon card text recognition API.

## Endpoints

- `GET /` — Health check
- `GET /health` — Health check
- `POST /ocr?lang=en` — OCR a card image

## Usage

```bash
curl -X POST "https://YOUR-SPACE.hf.space/ocr?lang=en" \
  -F "file=@card.jpg"
```

Returns:
```json
{
  "name": "Pikachu",
  "number": "25",
  "set_code": "SV6",
  "all_text": [...]
}
```

FROM python:3.11-slim

# PaddleOCR needs libGL and other system libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download PaddleOCR models at build time so startup is fast
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(lang='en', use_gpu=False, show_log=False); PaddleOCR(lang='japan', use_gpu=False, show_log=False)"

COPY app.py .

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]

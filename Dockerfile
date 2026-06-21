# ── Stage 1: base image ───────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL maintainer="video-gen-v2"
LABEL description="AI English Learning Video Generator"

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── App directory ─────────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
COPY requirements.txt requirements_server.txt ./
RUN pip install --no-cache-dir \
    -r requirements.txt \
    -r requirements_server.txt

# ── App code ──────────────────────────────────────────────────────────────────
COPY . .

# ── Download English fonts ────────────────────────────────────────────────────
RUN python setup_fonts.py 2>/dev/null || true

# ── Output directory ──────────────────────────────────────────────────────────
RUN mkdir -p /app/output /app/cache /app/output/audio

# ── Environment defaults (override via docker-compose or -e flags) ────────────
ENV LLM_API_KEY=""
ENV LLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4/"
ENV LLM_MODEL="glm-4-flash"
ENV DEFAULT_TEMPLATE="english_learning"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# ── Default: API server  (override with: docker run ... python main.py ...) ───
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

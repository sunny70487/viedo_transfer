# ============================================================
# Qwen3-ASR 轉錄工具 — GPU-enabled Docker image
# Multi-stage: Node.js (React build) → CUDA + Python (backend)
# ============================================================

# ---- Stage 1: Build React frontend ----
FROM node:22-alpine AS frontend-build

WORKDIR /build

COPY frontend-react/package.json frontend-react/package-lock.json ./
RUN npm ci

COPY frontend-react/ ./
RUN npm run build

# ---- Stage 2: Python backend + React assets ----
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive

# ---- 系統依賴 ----
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3.11-dev \
        python3-pip \
        ffmpeg \
        git \
        curl \
        ca-certificates \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

# ---- Python 依賴（分層快取）----
COPY backend/requirements.txt .
RUN grep -v "pywin32" requirements.txt > /tmp/requirements_linux.txt \
    && pip install --no-cache-dir -r /tmp/requirements_linux.txt \
    && rm /tmp/requirements_linux.txt

# ---- 應用程式碼 ----
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# 從 Stage 1 複製 React 建置產物
COPY --from=frontend-build /build/dist/ ./frontend-react/dist/

# ---- 預設目錄 ----
RUN mkdir -p /app/outputs /app/uploads /app/temp /app/models

# ---- 環境變數 ----
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

ENV MODELSCOPE_CACHE=/app/models
ENV HF_HOME=/app/models
ENV HUGGINGFACE_HUB_CACHE=/app/models

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "5000"]

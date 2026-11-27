# syntax=docker/dockerfile:1
# ============================================================
# Qwen3-ASR 轉錄工具 — GPU-enabled Docker image
# Multi-stage: Node.js (React build) → CUDA + Python (backend)
# ============================================================

# ---- Stage 1: Build React frontend ----
FROM node:22-alpine AS frontend-build

WORKDIR /build

COPY frontend-react/package.json frontend-react/package-lock.json ./
# npm 下載快取保留在 BuildKit cache mount，lock 檔變動時不必重新下載全部套件
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline --no-audit --no-fund

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

# pip 下載快取放在 BuildKit cache mount（不進 image）：requirements.txt 變動
# 導致下列 layer 重跑時，torch / CUDA wheel（數 GB）直接從快取安裝，不重新下載。
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip setuptools wheel

WORKDIR /app

# ---- Python 依賴（分層快取）----
# torch / torchaudio 以 constraints 釘在 CUDA 12.1 版，第一次解析就裝對，
# 不必先裝 CPU/cu13 版再整包強制重裝（省約 5 分鐘與約 5GB image 空間）。
COPY backend/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v "pywin32" requirements.txt > /tmp/requirements_linux.txt \
    && printf 'torch==2.5.1+cu121\ntorchaudio==2.5.1+cu121\n' > /tmp/constraints.txt \
    && pip install -r /tmp/requirements_linux.txt -c /tmp/constraints.txt \
        --extra-index-url https://download.pytorch.org/whl/cu121 \
    && rm /tmp/requirements_linux.txt /tmp/constraints.txt

# FireRedVAD（語音活動檢測）；--no-deps 是必要的：其 pyproject.toml 釘死
# torch==2.10.0 / transformers==5.1.0，會覆蓋下方的 CUDA torch 並破壞 qwen-asr。
# 模型權重不打包進 image，首次使用時自動下載至 /app/models（volume）。
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps \
        git+https://github.com/FireRedTeam/FireRedASR2S.git

# ---- 應用程式碼 ----
COPY backend/ ./backend/

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

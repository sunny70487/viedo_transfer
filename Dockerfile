# ============================================================
# Qwen3-ASR 轉錄工具 — GPU-enabled Docker image
# Base: NVIDIA CUDA 12.1 + cuDNN 8 (matches PyTorch / Qwen3-ASR)
# ============================================================

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS base

# 避免 apt 互動式提示
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
        # yt-dlp 需要的 TLS / 證書
        ca-certificates \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 升級 pip
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# ---- 工作目錄 ----
WORKDIR /app

# ---- Python 依賴（分層快取）----
COPY backend/requirements.txt .
# 移除 Windows 專用依賴，安裝其餘所有套件
RUN grep -v "pywin32" requirements.txt > /tmp/requirements_linux.txt \
    && pip install --no-cache-dir -r /tmp/requirements_linux.txt \
    && rm /tmp/requirements_linux.txt

# ---- 應用程式碼 ----
# 後端核心檔案
COPY backend/ ./backend/

# 前端靜態資源與模板（舊版 Jinja2）
COPY frontend/ ./frontend/

# React 前端建置輸出（如存在）
COPY frontend-react/dist/ ./frontend-react/dist/

# ---- 預設目錄 ----
RUN mkdir -p /app/outputs /app/uploads /app/temp /app/models

# ---- 環境變數 ----
# NVIDIA Container Runtime 需要的變數
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# 應用設定
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Qwen3-ASR / HuggingFace / ModelScope 模型快取路徑（可掛載外部 volume 避免重複下載）
ENV MODELSCOPE_CACHE=/app/models
ENV HF_HOME=/app/models
ENV HUGGINGFACE_HUB_CACHE=/app/models

EXPOSE 5000

# ---- 健康檢查 ----
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# ---- 啟動 ----
# production 不用 --reload
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "5000"]

# Whisper Transfer — 語音轉錄工具

基於 **FastAPI** 和 **Qwen3-ASR** 的影片/音頻轉錄 Web 應用，支援多執行緒處理，可從 URL 下載或上傳本地音頻/影片檔案進行自動轉錄。

## 功能特點

- 美觀的 Web 界面，支援響應式設計與深色模式（多主題切換）
- 支援從 URL（YouTube、Bilibili 等）下載音頻/影片並轉錄
- 支援上傳本地音頻/影片檔案進行轉錄
- 多執行緒處理，不阻塞主執行緒
- 即時任務狀態更新與任務持久化（重啟不遺失）
- 多種輸出格式（txt, srt, vtt, json, ass, ssa）
- 多種 ASR 模型支援（Qwen3-ASR-1.7B、Qwen3-ASR-0.6B；舊版 FunASR 名稱自動對應）
- 自動語言檢測或指定語言
- 簡體中文自動轉繁體中文（OpenCC）
- GPU 加速轉錄（CUDA）
- 音頻分割處理大檔案
- 字幕編輯器（支援影片同步播放、搜尋、匯出、分割、合併）
- 選定片段重新轉錄（retranscribe）
- 影片自動轉換為 MP4（H.264 + AAC）以確保瀏覽器相容性
- Docker 部署支援（含 GPU）

## 專案結構

```
whisper_transfer/
├── backend/
│   ├── app.py                      # FastAPI 主應用
│   ├── qwen3_asr_transcribe.py     # Qwen3-ASR 轉錄引擎（主要）
│   ├── funasr_transcribe.py        # FunASR 轉錄引擎（備用 / 工具函數）
│   ├── faster_whisper_transcribe.py # Faster Whisper 轉錄引擎（備用）
│   ├── models.py                   # Pydantic 資料模型
│   ├── task_persistence.py         # 任務持久化
│   ├── requirements.txt            # Python 依賴
│   └── services/
│       ├── audio_segment_service.py  # 音頻分割服務
│       ├── retranscribe_service.py   # 重新轉錄服務
│       ├── subtitle_api.py           # 字幕 API
│       └── subtitle_converter.py     # 字幕格式轉換
├── frontend/
│   ├── templates/
│   │   ├── index.html              # 主頁面
│   │   └── subtitle_editor.html    # 字幕編輯器
│   └── static/
│       ├── css/                    # 樣式（含主題）
│       └── js/                     # 前端邏輯
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## 安裝

### 系統需求

- Python 3.11 或更高版本
- FFmpeg（用於音頻提取和影片轉換）
- 推薦使用 CUDA 相容的 NVIDIA GPU 以獲得更好的效能

### 本地安裝

```bash
git clone <repository-url>
cd whisper_transfer
pip install -r backend/requirements.txt
```

### Docker 部署（推薦）

需要 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) 以啟用 GPU 支援。

```bash
docker-compose up -d
```

Docker 配置說明：
- 基於 `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04`
- 自動掛載 `outputs/`、`uploads/`、`tasks_data.json` 至容器，資料不遺失
- 模型快取使用 Docker Volume（`whisper-model-cache`），避免每次重啟重新下載
- 可掛載本地微調模型目錄（如 `faster-whisper-large-v3-zh-TW/`）
- 內建健康檢查（每 30 秒）

## 使用方法

### Web 界面（推薦）

```bash
# 本地開發
python -m uvicorn backend.app:app --host 0.0.0.0 --port 5000

# 或使用 Docker
docker-compose up -d
```

應用將在 http://localhost:5000 啟動。

1. 打開瀏覽器訪問 http://localhost:5000
2. 選擇從 URL 轉錄或上傳音頻/影片檔案
3. 設定轉錄選項（模型、語言、輸出格式等）
4. 提交任務
5. 在任務列表中查看進度和結果
6. 完成後可下載轉錄結果或進入字幕編輯器進行編輯

## 轉錄選項說明

### 模型選擇

| 模型名稱 | 引擎 | 特點 |
|---------|------|------|
| `qwen3-asr-1.7b` | Qwen3-ASR | SOTA 精度，多語言，推薦 |
| `qwen3-asr-0.6b` | Qwen3-ASR | 輕量快速，適合低資源環境 |

> 舊版 FunASR / Faster Whisper 模型名稱（paraformer-zh, sensevoice, large-v3, tiny, base, small, medium 等）會自動對應到 Qwen3-ASR 模型。

### 基本選項

- **語言**：指定音頻語言，留空則自動檢測
- **任務**：轉錄（保持原始語言）或翻譯成英文
- **輸出格式**：txt, srt, vtt, json, ass, ssa
- **下載格式**：僅音頻 / 含影片

### 進階選項

- **運行設備**：自動 / CPU / GPU
- **計算類型**：float16, int8 等
- **束搜索大小**：影響準確性和速度
- **語音活動檢測（VAD）**：過濾無聲片段
- **詞級時間戳**：生成逐詞時間標記
- **音頻分割**：將長音頻分割為小片段處理

## 字幕編輯器

轉錄完成後，可進入內建字幕編輯器：

- 影片同步播放，點擊字幕即跳轉對應時間
- 編輯字幕文字與時間戳
- 分割 / 合併字幕段落
- 選定片段重新轉錄（使用不同模型參數）
- 搜尋字幕內容（支援正規表達式）
- 匯出為多種格式（srt, vtt, txt, json, ass, ssa）

## 注意事項

- `qwen3-asr-1.7b` 模型在多語言場景下品質最佳（SOTA），推薦優先使用
- GPU 轉錄速度遠快於 CPU
- 轉錄長影片時，建議啟用分割處理選項
- 非 MP4 格式的影片會自動轉換為 MP4 以確保瀏覽器播放相容性
- 任務資料會自動持久化至 `tasks_data.json`，重啟後自動恢復

## 授權

MIT
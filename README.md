# Faster Whisper 轉錄工具

基於 FastAPI 和 Faster Whisper 的影片/音頻轉錄 Web 應用，支援多執行緒處理，可從 URL 下載或上傳本地音頻/影片檔案進行自動轉錄。

## 功能特點

- 美觀的 Web 界面，支援響應式設計與深色模式
- 支援從 URL（YouTube、Bilibili 等）下載音頻/影片並轉錄
- 支援上傳本地音頻/影片檔案進行轉錄
- 多執行緒處理，不阻塞主執行緒
- 即時任務狀態更新
- 多種輸出格式（txt, srt, vtt, json, ass, ssa）
- 多種 Whisper 模型大小（tiny 到 large-v3）
- 自動語言檢測或指定語言
- GPU 加速轉錄（CUDA）
- 音頻分割處理大檔案
- 字幕編輯器（支援影片同步播放、搜尋、匯出）
- 影片自動轉換為 MP4（H.264 + AAC）以確保瀏覽器相容性
- Docker 部署支援（含 GPU）

## 安裝

### 系統需求

- Python 3.8 或更高版本
- FFmpeg（用於音頻提取和影片轉換）
- 推薦使用 CUDA 相容的 NVIDIA GPU 以獲得更好的效能

### 本地安裝

```bash
git clone <repository-url>
cd whisper_transfer
pip install -r requirements.txt
```

### Docker 部署

```bash
docker-compose up -d
```

## 使用方法

### Web 界面（推薦）

```bash
python app.py
```

應用將在 http://localhost:5000 啟動。

1. 打開瀏覽器訪問 http://localhost:5000
2. 選擇從 URL 轉錄或上傳音頻/影片檔案
3. 設定轉錄選項（模型大小、語言、輸出格式等）
4. 提交任務
5. 在任務列表中查看進度和結果
6. 完成後可下載轉錄結果或進入字幕編輯器

### 命令列模式

```bash
# 下載並轉錄 YouTube 影片
python faster_whisper_transcribe.py --url "https://www.youtube.com/watch?v=example"

# 指定輸出格式
python faster_whisper_transcribe.py --url "https://www.youtube.com/watch?v=example" --output_format all

# 使用較小的模型提高速度
python faster_whisper_transcribe.py --url "https://www.youtube.com/watch?v=example" --model small

# 查看所有可用選項
python faster_whisper_transcribe.py --help
```

## 轉錄選項說明

### 基本選項

- **模型大小**：tiny, base, small, medium, large-v1, large-v2, large-v3
- **語言**：指定音頻語言，留空則自動檢測
- **任務**：轉錄（保持原始語言）或翻譯成英文
- **輸出格式**：txt, srt, vtt, json, all

### 進階選項

- **運行設備**：CPU 或 GPU
- **計算類型**：float16, int8 等
- **束搜索大小**：影響準確性和速度
- **語音活動檢測（VAD）**：過濾無聲片段
- **詞級時間戳**：生成逐詞時間標記
- **音頻分割**：將長音頻分割為小片段處理

## 注意事項

- 大型模型（large-v3）提供最佳轉錄品質，但需要更多時間和記憶體
- GPU 轉錄速度遠快於 CPU
- 轉錄長影片時，建議啟用分割處理選項
- 非 MP4 格式的影片會自動轉換為 MP4 以確保瀏覽器播放相容性

## 授權

MIT
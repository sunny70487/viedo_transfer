# Whisper Transfer 優化 Roadmap

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 先建立最低限度的品質護欄，再逐步降低核心模組的耦合與重複邏輯，最後把專案演進成更容易維護、擴充與交接的架構。

**Architecture:** 這份 roadmap 採用「先穩、再拆、後演進」的順序。第一階段先補測試、lint、CI 等基本保護，避免後續重構在沒有安全網的情況下進行。中段優先處理轉錄引擎之間的重複邏輯、全域狀態與超大檔案。最後才進入中長期架構演進，避免過早設計。

**Tech Stack:** Python、FastAPI、Pydantic、Docker、vanilla JavaScript、Bootstrap、FFmpeg、ASR/transcription backends

---

## 為什麼需要這份 roadmap

目前的審閱結果指向四個會持續拖慢開發速度、也提高維護風險的核心問題：

1. **自動化驗證不足**：模型驗證、任務持久化、API 流程缺少足夠的回歸保護。
2. **轉錄流程重複邏輯偏多**：多個 engine 檔案之間有相似的下載、切段、格式轉換與 FFmpeg 處理。
3. **全域狀態與隱式耦合偏重**：task storage 與 singleton 式服務讓測試與推理都更困難。
4. **核心熱點檔案過大**：`backend/app.py`、多個 transcription module 與 `frontend/static/js/main.js` 都已經接近或進入高風險維護區。

這份 roadmap 的目的不是一次做大重構，而是把優化順序排對，讓每一步都能降低後續變更成本。

---

## 規劃原則

- **先補安全網，再重構**：沒有測試與 CI 的情況下，大改結構風險很高。
- **先做高槓桿項目**：優先處理重複邏輯、隱式耦合與核心熱點。
- **偏向漸進式抽離**：先抽共用邏輯與共享常數，再考慮更重的抽象。
- **避免為了整潔而重寫**：現階段應先整理既有前後端結構，而不是急著搬新框架。
- **每個 phase 都要可驗收**：不是只有「做了哪些事」，而是要能回答「風險是否真的下降」。

---

## Phase 0 — 基礎穩定化與品質護欄

**建議時程：** 1-3 天  
**主要目標：** 建立最低限度的測試、lint 與 CI 保護，讓後續結構調整可控且可驗證。

### 範圍

- 建立最小可用的測試基礎。
- 建立一致的本地品質檢查指令。
- 建立最小版 CI，讓專案能自動檢查。

### 主要目標檔案

- `backend/models.py`
- `backend/task_persistence.py`
- `backend/services/subtitle_api.py`
- 專案層級 Python 工具設定檔

### 預期交付物

1. 新增 `tests/` 目錄與第一批高價值測試。
2. 補上測試 / lint 的專案設定。
3. 建立最小 CI workflow。
4. 定義並寫進文件的本地開發驗證流程。

### Phase 0 執行任務分解

#### Task 0.1：建立 Python 品質工具基線

**目的：** 讓團隊有統一的測試與 lint 入口，不再依賴臨時指令。

**建議涉及檔案：**
- Create: `pyproject.toml` 或等效工具設定檔
- Modify: `backend/requirements.txt`
- Modify: `README.md`

**執行內容：**
1. 決定測試與 lint 工具最小組合，例如：`pytest` + `ruff`。
2. 把必要開發依賴納入文件化流程。
3. 在 README 或開發段落中加入本地驗證指令。

**驗收條件：**
- 新成員可以照文件執行 lint 與 tests。
- 專案內不再需要靠口頭說明才能知道怎麼驗證。

**風險提醒：**
- 這一步只建立基線，不要順便導入太多新工具。

#### Task 0.2：為 `backend/models.py` 補第一批單元測試

**目的：** 先保護最容易出現輸入邊界錯誤的資料模型層。

**建議涉及檔案：**
- Create: `tests/test_models.py`
- Read/Reference: `backend/models.py`

**優先測試主題：**
- 時間戳欄位的上下界或非法值
- 空字串 / 缺漏欄位
- subtitle segment / collection 的基本驗證邏輯
- 語言或格式欄位的有效值與無效值

**執行內容：**
1. 先寫 3-5 個最小但高價值的失敗案例。
2. 確認目前行為後，再補對應的正向案例。
3. 讓這批測試可單獨執行。

**驗收條件：**
- `backend/models.py` 的核心 validator 至少有一組正反向測試。
- 未來修改 model 時，能快速知道是否破壞既有驗證規則。

#### Task 0.3：為 `backend/task_persistence.py` 補 round-trip 測試

**目的：** 保護任務資料寫入、讀回、重建時的基本正確性。

**建議涉及檔案：**
- Create: `tests/test_task_persistence.py`
- Read/Reference: `backend/task_persistence.py`

**優先測試主題：**
- 任務資料存檔後可成功讀回
- 空資料或缺欄位時的穩定行為
- 重啟／重建任務資料時的基本一致性

**執行內容：**
1. 使用臨時檔案或暫存資料夾測試寫入與讀回。
2. 針對最關鍵的欄位做 round-trip 驗證。
3. 視目前實作狀態決定是否加入損壞資料的防禦性測試。

**驗收條件：**
- 任務持久化流程有最基本的回歸保護。
- 後續重構 task state 時，不容易無意間破壞落盤格式。

#### Task 0.4：補 1-2 個 `subtitle_api` smoke tests

**目的：** 先保護最核心、最容易被重構波及的 API 行為。

**建議涉及檔案：**
- Create: `tests/test_subtitle_api_smoke.py`
- Read/Reference: `backend/services/subtitle_api.py`
- Read/Reference: `backend/app.py`

**優先測試主題：**
- 一個成功路徑：能取回或更新基本字幕資料
- 一個失敗路徑：無效輸入、缺資料、找不到資源時的反應

**執行內容：**
1. 選最穩定、依賴最少的 API 做 smoke tests。
2. 先確認目前 response shape，再固定成測試期待。
3. 不追求完整 API coverage，只保護主流程。

**驗收條件：**
- 至少有一個成功路徑與一個失敗路徑可自動驗證。
- 後續拆 `subtitle_api.py` 時，有基本保護。

#### Task 0.5：建立最小 CI 檢查

**目的：** 讓 lint 與 tests 不只在本機跑，而是每次變更都能被自動驗證。

**建議涉及檔案：**
- Create: `.github/workflows/ci.yml`（若此 repo 使用 GitHub）
- 或建立等效 CI 設定檔

**執行內容：**
1. 建立最小 pipeline：安裝依賴 → 跑 lint → 跑 tests。
2. 確保指令與本地文件一致。
3. 保持 pipeline 輕量，先不要加入太多矩陣或耗時步驟。

**驗收條件：**
- CI 能在程式碼出現基本問題時失敗。
- 團隊不需要靠人工提醒才會做基本驗證。

#### Task 0.6：更新 README 的開發驗證說明

**目的：** 讓 roadmap 的第一階段不只存在於計畫書，也真正反映在團隊操作文件中。

**建議涉及檔案：**
- Modify: `README.md`

**執行內容：**
1. 補上開發模式下的測試與 lint 執行方式。
2. 如果有新增 CI 或工具設定，說明其目的與基本用法。
3. 保持 README 精簡，不把內部細節寫得過重。

**驗收條件：**
- 文件與實際驗證流程一致。
- 新成員不需要猜測如何驗證自己的修改。

### Phase 0 完成標準

- 可以在本地執行一組明確的 lint/test 指令。
- CI 能在基本錯誤出現時阻擋變更。
- `models`、`task_persistence`、`subtitle_api` 至少有第一批回歸保護。

### Phase 0 風險 / 注意事項

- 不要在這個階段順手大改業務邏輯。
- 不要追求高 coverage，先追求高風險區域的基本保護。
- 如果現有程式太難測，先從最小 smoke test 開始，而不是停在「等重構完再補」。

---

## Phase 1 — 移除高成本重複邏輯與隱式狀態

**建議時程：** 3-7 天  
**主要目標：** 把維護成本最高的重複邏輯與全域狀態收斂，減少未來每次修改都要多點同步的問題。

### 範圍

- 抽離轉錄引擎共用 helper。
- 整理最危險的全域狀態。
- 讓 service 邊界更清楚，但避免過度設計。

### 主要目標檔案

- `backend/funasr_transcribe.py`
- `backend/faster_whisper_transcribe.py`
- `backend/qwen3_asr_transcribe.py`
- `backend/app.py`
- `backend/services/subtitle_api.py`
- `backend/services/retranscribe_service.py`

### 建議交付物

1. 建立共用 backend utility module，集中處理：
   - 下載 helper
   - 音訊切段 helper
   - timestamp 相關 helper
   - FFmpeg 共用流程
   - 支援格式與共享常數
2. 把最零散的 task/state 存取改成明確的 manager/service object。
3. 釐清 retranscribe 與 task 相關 service 的生命週期。
4. 為抽出的共用 helper 補最小回歸測試。

### 完成標準

- 共用轉錄 / 媒體處理邏輯只保留單一主要來源。
- 一個 bugfix 不再需要同步改多個 engine 檔案。
- task 相關狀態更容易 mock、注入與測試。

### 風險 / 注意事項

- 不要太早引入很重的 abstraction layer。
- 除非重複已經非常穩定明確，否則先偏向實用抽離，而不是過早做抽象基底類。

---

## Phase 2 — 拆解最大熱點模組

**建議時程：** 1-2 週  
**主要目標：** 依照真實職責邊界拆解大檔案，降低閱讀與修改成本。

### 範圍

- 將大型 backend / frontend 檔案拆成更清楚的模組。
- 分離 HTTP handler、業務邏輯與共用工具。
- 在不破壞功能的前提下，降低認知負擔。

### 主要目標檔案

- `backend/app.py`
- `backend/services/subtitle_api.py`
- `frontend/static/js/main.js`
- `frontend/static/js/` 與 `frontend/templates/` 下相關支援檔案

### 建議交付物

1. 將 backend entrypoint 拆為更明確的 route / service 結構，例如：
   - task routes
   - subtitle routes
   - system/status routes
2. 把非 routing 邏輯從 `backend/app.py` 移出。
3. 將 `frontend/static/js/main.js` 依功能拆分，例如：
   - upload / transcription flow
   - task polling / progress UI
   - settings / state management
   - DOM / UI helper
4. 確保 Phase 0 建立的測試能覆蓋拆分後的主要路徑。

### 完成標準

- 核心流程不必透過單一超大檔案才能理解。
- 新功能可以落在更聚焦的小模組中。
- route handler 變薄、較容易測試。

### 風險 / 注意事項

- 只拆檔、不整理責任邊界，會造成「看起來模組化，但其實耦合還在」的假改善。
- 前端保持漸進式拆分即可，除非產品方向有明確改變，否則不要直接重寫。

---

## Phase 3 — 統一設定與品質流程

**建議時程：** 1-2 週  
**主要目標：** 建立前後端一致的設定來源，並讓品質流程成為日常開發的一部分。

### 範圍

- 收斂散落的常數與設定。
- 改善本地品質自動化。
- 提高可靠性基線，但避免工具過載。

### 主要目標

- 分散在 backend modules 與 templates 的格式 / 選項定義
- 專案層級工具設定
- commit-time 或 CI-time 的品質檢查

### 建議交付物

1. 建立單一事實來源，集中管理：
   - 支援副檔名
   - 音訊 / 影片轉換選項
   - 同時影響 UI 與 backend 的 engine 選項
2. 加入 pre-commit 或等效輕量自動化。
3. 逐步擴大對關鍵流程的測試覆蓋。
4. 在高價值核心模組中逐步補型別邊界，而不是一次全專案 strict typing。

### 完成標準

- UI 顯示的選項與 backend 實際支援能力保持一致。
- 工程師不再在多個地方重複宣告相同常數。
- 本地與 CI 驗證變成日常流程，而不是額外補救動作。

### 風險 / 注意事項

- 若共享常數模組就足夠，不要急著做很大的 config system。
- 型別強化要從高價值模組開始，不必一口氣做滿。

---

## Phase 4 — 中長期架構演進

**建議時程：** 1-3 個月  
**主要目標：** 讓專案從「可以維護」進一步走到「可以穩定擴充新能力」。

### 範圍

- 明確化 engine extensibility。
- 若併發與任務需求持續增加，改善 background job lifecycle。
- 依照真實產品需求持續演進前端模組化。

### 策略方向

1. **轉錄引擎架構整理**
   - 明確區分 engine setup、媒體準備、推論、後處理等共享 pipeline。
   - 將 engine-specific 行為留在各自模組，共用行為集中管理。

2. **Task / job lifecycle 模型明確化**
   - 若使用量增加，評估現行 in-process task handling 是否仍足夠。
   - 改善 task 建立、進度、重試、失敗狀態的可觀測性。

3. **前端持續演進**
   - 先延續現有 vanilla JS 的模組化。
   - 只有在未來產品明確需要更複雜的 client-side state 管理時，才評估框架遷移。

### 完成標準

- 新增 transcription engine 時，不需要再複製一個大型既有檔案。
- 長任務的 operational behavior 更容易觀察與除錯。
- 前端複雜度能以模組化方式被控制，而不是持續塞回單一檔案。

### 風險 / 注意事項

- 在 Phase 0-2 尚未有明顯進展前，不建議先做這一層架構演進。
- 不要為了「架構漂亮」而做沒有產品或維運壓力支撐的改造。

---

## 建議執行順序

若時間或人力有限，建議按照這個順序推進：

1. **Phase 0** — 基礎穩定化與品質護欄
2. **Phase 1** — 抽共用邏輯 + 收斂狀態管理
3. **Phase 2** — 拆解熱點模組
4. **Phase 3** — 統一設定與品質流程
5. **Phase 4** — 中長期架構演進

這個順序的重點是：先降低 silent regression 風險，再去做更大幅度的結構整理。

---

## 追蹤表格

可用下表持續追蹤每個 phase 的狀態：

| Phase | 狀態 | 負責人 | 目標時程 | 備註 |
|---|---|---|---|---|
| Phase 0 — 基礎穩定化與品質護欄 | Not Started | TBD | TBD | |
| Phase 1 — 移除高成本重複邏輯與隱式狀態 | Not Started | TBD | TBD | |
| Phase 2 — 拆解最大熱點模組 | Not Started | TBD | TBD | |
| Phase 3 — 統一設定與品質流程 | Not Started | TBD | TBD | |
| Phase 4 — 中長期架構演進 | Not Started | TBD | TBD | |

---

## 建議下一步

先從 **Phase 0** 開始，而且第一個 milestone 要刻意保持小而可完成：

- 建立第一批測試檔
- 建立 lint / test 指令
- 接上最小版 CI

等這個基線穩定後，再立刻進入 Phase 1，趁目前對架構熱點的理解還很新鮮時處理高成本重複邏輯與全域狀態。

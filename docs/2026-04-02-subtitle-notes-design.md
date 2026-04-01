# 字幕筆記生成功能 — 設計規格

> 日期：2026-04-02
> 分支：`feature/diarization-flow`
> 狀態：設計已確認，待實作

---

## 一、功能概述

### 目標

在字幕編輯器中新增「生成筆記」功能，將帶時間戳的字幕內容透過 LLM 整理為結構化筆記，並以可互動面板呈現（時間戳可點擊跳轉影片），同時支援匯出 Markdown 檔案。

### 使用情境

- **主要場景**：演講/課程 — 單一講者的教學內容，需提煉知識點、章節結構
- **兼顧場景**：會議紀錄、訪談摘要、Podcast 及通用摘要

### 使用流程

1. 使用者在字幕編輯器中校對完字幕
2. 點擊工具列「生成筆記」按鈕
3. 在 Dialog 中選擇筆記範本、確認 LLM 設定
4. 點擊「開始生成」，SSE 串流顯示進度
5. 生成完成後，筆記面板展開於影片下方
6. 使用者可點擊筆記中的時間戳跳轉影片，或匯出/複製 Markdown

---

## 二、技術架構

### 新增檔案

| 檔案 | 角色 |
|------|------|
| `backend/shared/note_generator.py` | 筆記生成核心（prompt 範本、分段、LLM 呼叫、組合） |
| `frontend-react/src/components/editor/NoteGeneratorDialog.tsx` | 生成設定 Dialog |
| `frontend-react/src/components/editor/NotePanel.tsx` | 筆記檢視面板 |

### 修改檔案

| 檔案 | 變動 |
|------|------|
| `backend/services/subtitle_api.py` | 新增 `POST /{task_id}/generate-notes` SSE 端點 |
| `frontend-react/src/api/client.ts` | 新增 `generateNotesStream()` |
| `frontend-react/src/pages/EditorPage.tsx` | 新增筆記按鈕 + NotePanel 區塊 |

### 前端新增依賴

| 套件 | 用途 | 大小 |
|------|------|------|
| `react-markdown` | Markdown 渲染（含 GFM 表格） | ~50KB |
| `remark-gfm` | GFM 語法支援（表格、刪除線等） | ~15KB |

### 設計原則

1. **遵循現有模式** — SSE 串流、LLM settings localStorage、Dialog 互動流程對齊 `LlmEnhanceDialog`
2. **不動既有程式碼** — `note_generator.py` 為獨立模組，復用 `llm_postprocess.py` 的底層函式但不修改它
3. **筆記不持久化** — 生成後在前端 state 保存，使用者可匯出。未來如需持久化，加一個存檔 API 即可

---

## 三、後端設計

### 3.1 筆記範本系統

4 種內建範本，每種有專屬 system prompt 和輸出結構：

| 範本 ID | 名稱 | 適用場景 | 輸出結構 |
|---------|------|---------|---------|
| `lecture` | 演講/課程筆記 | 單一講者教學 | 章節 → 知識點 → 關鍵術語表 |
| `meeting` | 會議紀錄 | 多人討論決策 | 議題 → 討論摘要 → 決議 → 行動項目 |
| `interview` | 訪談摘要 | 對談 / Podcast | 問答脈絡 → 各方觀點 → 核心主張 |
| `general` | 通用摘要 | 萬用 | 摘要 → 重點列表 → 關鍵詞 |

### 3.2 兩階段處理管線

```
階段 1：分段摘要（Chunk Summarization）
  字幕 [00:00-10:30] → LLM → 段落摘要 A
  字幕 [10:31-22:15] → LLM → 段落摘要 B
  字幕 [22:16-35:40] → LLM → 段落摘要 C
  ↓ SSE 進度

階段 2：全局綜合（Global Synthesis）
  段落摘要 A+B+C → LLM → 最終結構化筆記
  ↓ SSE 回傳結果
```

**分段策略**：復用 `_chunk_lines` 邏輯，以時間區間為單位：

```python
NOTE_CHUNK_MAX_LINES = 120
NOTE_CHUNK_MAX_CHARS = 8_000
NOTE_CHUNK_COOLDOWN = 1.0
```

**短內容優化**：若總字幕行數 ≤ `NOTE_CHUNK_MAX_LINES` 且總字元數 ≤ `NOTE_CHUNK_MAX_CHARS`，跳過階段 1，直接用單次 LLM 呼叫生成完整筆記。

### 3.3 Prompt 設計（lecture 範本）

**階段 1 — 分段摘要：**

```text
你是一位專業的學術筆記整理員。請根據以下演講字幕片段，整理出該片段的重點筆記。

## 規則
1. 識別該片段中的主要話題/章節
2. 每個話題列出 2-5 個關鍵知識點
3. 在重要知識點旁標註時間戳 [MM:SS]
4. 記錄重要的專業術語及其解釋
5. 保持客觀，不添加字幕中沒有的內容
6. 使用 Markdown 格式，章節用 ###，知識點用 - 列表

## 時間範圍
本段字幕時間範圍：{start_time} - {end_time}
{content_hint}
```

**階段 2 — 全局綜合：**

```text
你是一位專業的學術筆記整理員。以下是一場演講的分段摘要，
請將它們整合為一份完整的結構化筆記。

## 規則
1. 合併相關話題，建立清晰的章節結構
2. 保留所有時間戳標註 [MM:SS]
3. 在最後增加「關鍵術語」表格
4. 在開頭加上 2-3 句的總覽摘要
5. 不要遺漏任何分段中的重要資訊

## 輸出格式
## 總覽
（2-3 句總結）

### 第一章：... [MM:SS]
- ...

### 關鍵術語
| 術語 | 說明 |
|------|------|
```

**其他範本的 prompt 差異**：
- `meeting`：強調決議事項、行動項目、負責人
- `interview`：強調問答脈絡、各方觀點對比
- `general`：強調重點清單、關鍵詞提取

### 3.4 函式介面

```python
# backend/shared/note_generator.py

TEMPLATES = {
    "lecture": {"name": "演講/課程筆記", "chunk_prompt": "...", "synthesis_prompt": "..."},
    "meeting": {"name": "會議紀錄", "chunk_prompt": "...", "synthesis_prompt": "..."},
    "interview": {"name": "訪談摘要", "chunk_prompt": "...", "synthesis_prompt": "..."},
    "general": {"name": "通用摘要", "chunk_prompt": "...", "synthesis_prompt": "..."},
}

def get_available_templates() -> list[dict]:
    """回傳可用範本清單 [{id, name}]"""

def generate_notes(
    segments: list[dict],
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    template: str = "lecture",
    content_hint: str | None = None,
    progress_callback: Callable | None = None,
) -> str:
    """
    兩階段筆記生成。回傳 Markdown 字串。
    progress_callback(type, stage, batch, total, percent)
    """
```

**復用的底層函式**（從 `llm_postprocess.py` import）：
- `_call_llm()` — LLM 呼叫 + 重試
- `_chunk_lines()` — 分段邏輯
- `_friendly_error()` — 錯誤訊息格式化
- `_is_retryable()` — 判斷是否可重試

---

## 四、API 端點設計

### `POST /api/subtitles/{task_id}/generate-notes` (SSE)

```python
class GenerateNotesRequest(BaseModel):
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    template: str = "lecture"
    content_hint: Optional[str] = None
```

**SSE 事件流：**

```jsonc
// 資訊提示
data: {"type": "info", "message": "正在使用「演講筆記」範本分析 328 行字幕..."}

// 階段 1 進度
data: {"type": "progress", "stage": "chunk", "batch": 1, "total": 4, "percent": 25}

// 階段 2 進度
data: {"type": "progress", "stage": "synthesis", "batch": 1, "total": 1, "percent": 95}

// 最終結果
data: {"type": "result", "notes": "## 總覽\n...（完整 Markdown）"}

// 或錯誤
data: {"type": "error", "message": "LLM API 連線失敗"}
```

**端點內部流程：**
1. `SubtitleService.load_subtitle_data()` 載入字幕
2. 呼叫 `note_generator.generate_notes()` 並傳入 SSE progress callback
3. `StreamingResponse` 回傳

---

## 五、前端設計

### 5.1 設計系統（遵循現有 + UI/UX Pro Max 規範）

**現有 Theme tokens**（`index.css`）：
- Primary: `#6366F1`（Indigo）
- Surface: `#FFFFFF` / `#1E293B`
- Text: `#0F172A` / `#F1F5F9`
- Muted: `#64748B` / `#94A3B8`
- Border: `#E2E8F0` / `#334155`
- Font: Inter / JetBrains Mono

**UI/UX Pro Max 規範對照表**：

| 規範 | 實作 |
|------|------|
| `color-contrast` 4.5:1 | 使用 `text-text` / `text-text-dark`，不使用 muted 作為主要文字 |
| `touch-target-size` 44x44px | 按鈕最小 `h-10 w-10`（40px），實際點擊面積含 padding ≥ 44px |
| `focus-states` | 所有互動元素使用 `focus:ring-2 focus:ring-primary/50` |
| `cursor-pointer` | 所有可點擊元素加 `cursor-pointer` |
| `keyboard-nav` | Dialog Esc 關閉、Tab 順序正確 |
| `aria-labels` | icon-only 按鈕加 `aria-label` |
| `loading-buttons` | 生成中禁用按鈕 + loading spinner |
| `duration-timing` | 動畫 150-300ms，使用 `transition-colors duration-200` |
| `transform-performance` | 動畫僅用 `transform` / `opacity` |
| `reduced-motion` | 尊重 `prefers-reduced-motion` |
| `no-emoji-icons` | 使用 Lucide SVG icon，不用 emoji |
| `line-height` 1.5 | 筆記面板 body 使用 `leading-relaxed` |
| `line-length` 65-75ch | 筆記內容 `max-w-prose`（65ch） |

### 5.2 NoteGeneratorDialog.tsx

**行為模式**：完全對齊 `LlmEnhanceDialog`
- 共享 `LLM_STORAGE_KEY` 的 localStorage（API Key / Base URL / Model）
- 自動 debounce fetch 模型列表
- SSE 進度條（兩階段顯示）

**UI 結構**：

```
┌── Dialog ──────────────────────────────────────┐
│ Header: "生成筆記" + X 關閉                      │
│                                                 │
│ 說明文字                                        │
│ 範本選擇 <select>                               │
│ Base URL <input>                                │
│ API Key <input type="password">                 │
│ 模型 <select|input> + 連線狀態 icon              │
│ 內容描述 <textarea>（選填）                      │
│                                                 │
│ 進度區（生成中才顯示）                           │
│   info 訊息 + 進度條 + 百分比                    │
│                                                 │
│ Footer: [取消] [開始生成]                        │
└─────────────────────────────────────────────────┘
```

**範本選項**：
```tsx
const NOTE_TEMPLATES = [
  { value: 'lecture',   label: '演講/課程筆記',  icon: BookOpen },
  { value: 'meeting',   label: '會議紀錄',       icon: Users },
  { value: 'interview', label: '訪談摘要',       icon: MessageCircle },
  { value: 'general',   label: '通用摘要',       icon: FileText },
]
```

### 5.3 NotePanel.tsx

**位置**：`EditorPage` 左欄，影片 + 統計卡片下方。生成後展開，可收合。

**功能**：
- `react-markdown` + `remark-gfm` 渲染 Markdown
- 時間戳 `[MM:SS]` 轉為可點擊的 `<button>`，點擊呼叫 `videoRef.seek()`
- 「複製」按鈕：`navigator.clipboard.writeText(markdown)`
- 「匯出 .md」按鈕：`Blob` + `URL.createObjectURL` 下載
- 收合/展開切換

**時間戳解析邏輯**：
```tsx
// 將 Markdown 中的 [MM:SS] 或 [HH:MM:SS] 替換為可點擊按鈕
// 正規表達式：/\[(\d{1,2}:)?\d{2}:\d{2}\]/g
// 點擊事件：解析為秒數 → onSeek(seconds)
```

**UI 結構**：

```
┌── Card ────────────────────────────────────────┐
│ Header: FileText icon + "筆記"                  │
│         [複製] [匯出 .md] [收合 ▲]              │
├─────────────────────────────────────────────────┤
│                                                 │
│ (react-markdown 渲染區)                         │
│ max-w-prose leading-relaxed                     │
│                                                 │
│  ## 總覽                                        │
│  本演講深入介紹了...                             │
│                                                 │
│  ### 第一章：... [00:00] ← 可點擊              │
│  - 重點 A [01:15] ← 可點擊                     │
│  - 重點 B [04:22] ← 可點擊                     │
│                                                 │
│  ### 關鍵術語                                   │
│  | 術語 | 說明 |                                │
│  |------|------|                                │
│                                                 │
└─────────────────────────────────────────────────┘
```

**樣式細節**（UI/UX Pro Max 規範）：

```css
/* 筆記面板 Markdown 樣式 */
.note-content h2     { @apply text-lg font-semibold text-text dark:text-text-dark mt-6 mb-2; }
.note-content h3     { @apply text-base font-medium text-text dark:text-text-dark mt-4 mb-1.5; }
.note-content p      { @apply text-sm text-text dark:text-text-dark leading-relaxed mb-2; }
.note-content ul     { @apply text-sm space-y-1 pl-4 list-disc text-text dark:text-text-dark; }
.note-content table  { @apply w-full text-sm border-collapse mt-2; }
.note-content th     { @apply text-left px-3 py-1.5 bg-gray-50 dark:bg-gray-800
                               border border-border dark:border-border-dark
                               font-medium text-text dark:text-text-dark; }
.note-content td     { @apply px-3 py-1.5 border border-border dark:border-border-dark
                               text-text dark:text-text-dark; }

/* 時間戳按鈕 */
.timestamp-link      { @apply inline-flex items-center px-1.5 py-0.5 rounded
                               text-xs font-mono text-primary hover:text-primary-hover
                               bg-primary/10 hover:bg-primary/20
                               cursor-pointer transition-colors duration-200
                               focus:outline-none focus:ring-2 focus:ring-primary/50; }
```

### 5.4 EditorPage.tsx 變動

```tsx
// 新增 state
const [notesOpen, setNotesOpen] = useState(false)
const [notesContent, setNotesContent] = useState<string | null>(null)
const [notesDialogOpen, setNotesDialogOpen] = useState(false)

// SubtitleToolbar 新增 onNotes prop
<SubtitleToolbar
  ...
  onNotes={() => setNotesDialogOpen(true)}
/>

// Dialog
<NoteGeneratorDialog
  open={notesDialogOpen}
  onClose={() => setNotesDialogOpen(false)}
  taskId={taskId}
  onGenerated={(md) => { setNotesContent(md); setNotesOpen(true) }}
/>

// NotePanel（影片下方）
{notesContent && (
  <NotePanel
    content={notesContent}
    open={notesOpen}
    onToggle={() => setNotesOpen(!notesOpen)}
    onSeek={(t) => { videoRef.current?.seek(t); videoRef.current?.play() }}
  />
)}
```

### 5.5 api/client.ts 新增

```typescript
async *generateNotesStream(
  taskId: string,
  data: {
    api_key: string
    base_url: string
    model: string
    template: string
    content_hint?: string
  }
): AsyncGenerator<{
  type: string
  stage?: string
  batch?: number
  total?: number
  percent?: number
  notes?: string
  message?: string
}>
```

對齊 `enhanceSubtitlesStream` 的 SSE 讀取模式。

---

## 六、前端交付檢查清單（UI/UX Pro Max）

### 視覺品質
- [ ] 不使用 emoji 作為 icon（使用 Lucide SVG）
- [ ] Icon 來自一致的 icon set（Lucide React）
- [ ] hover 狀態不造成 layout shift
- [ ] 使用 theme color（`bg-primary`、`text-text` 等）

### 互動
- [ ] 所有可點擊元素加 `cursor-pointer`
- [ ] hover 提供清楚的視覺回饋
- [ ] transition 150-300ms
- [ ] focus state 可見（keyboard navigation）
- [ ] 生成中按鈕 disabled + loading spinner

### Light/Dark Mode
- [ ] 文字對比度 ≥ 4.5:1
- [ ] 兩種模式下邊框都可見
- [ ] 測試兩種模式

### Layout
- [ ] 筆記內容 `max-w-prose`（65ch 限制行寬）
- [ ] 筆記面板可收合，不佔用過多空間
- [ ] 行距 `leading-relaxed`（1.625）
- [ ] 響應式：手機上筆記面板全寬

### Accessibility
- [ ] icon-only 按鈕加 `aria-label`
- [ ] Dialog 有 `aria-modal` + `aria-label`
- [ ] 時間戳按鈕可用鍵盤觸發
- [ ] 尊重 `prefers-reduced-motion`

---

## 七、實作順序建議

| 步驟 | 內容 | 預估時間 |
|------|------|---------|
| 1 | `note_generator.py` — prompt 範本 + 分段 + 兩階段管線 | 1 天 |
| 2 | `subtitle_api.py` — SSE 端點 | 0.5 天 |
| 3 | `api/client.ts` — `generateNotesStream()` | 0.5 天 |
| 4 | `NoteGeneratorDialog.tsx` — 設定 Dialog | 0.5 天 |
| 5 | `NotePanel.tsx` — Markdown 渲染 + 時間戳跳轉 + 匯出 | 1 天 |
| 6 | `EditorPage.tsx` — 整合 + `SubtitleToolbar` 新增按鈕 | 0.5 天 |
| 7 | 測試 + 調整 | 1 天 |
| **合計** | | **5 天** |

---

## 八、未來擴展方向

1. **筆記持久化** — 加入 `POST /api/subtitles/{task_id}/notes` 存檔 + `GET` 讀取
2. **LLM 話題偵測分段** — 將機械分段升級為方案三的智慧話題邊界偵測
3. **筆記可編輯** — 在面板中加入 Markdown 編輯模式
4. **輕量版 Q&A** — 基於已生成的筆記，讓使用者追問細節
5. **批次筆記生成** — 多個任務一次生成，彙整為專案筆記

/**
 * 字幕編輯器 JavaScript 類別
 */

/**
 * 字幕編輯器主類別
 */
class SubtitleEditor {
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.options = {
            autoSync: true,
            syncTolerance: 0.5, // 同步容差（秒）
            enableVideoSubtitles: true, // 預設啟用影片內嵌字幕
            ...options
        };
        
        // DOM 元素引用
        this.container = null;
        this.videoPlayer = null;
        this.subtitleList = null;
        
        // 影片字幕同步管理器
        this.videoSubtitleSync = null;
        
        // 資料狀態
        this.subtitles = [];
        this.originalSubtitles = []; // 原始字幕資料（用於重置）
        this.metadata = null; // 原始元資料（儲存時帶回）
        this.currentSubtitleIndex = -1;
        this.isPlaying = false;
        this.isDirty = false; // 是否有未儲存的變更
        
        // 歷史記錄（用於復原/重做）
        this.history = [];
        this.historyIndex = -1;
        this.maxHistorySize = 50;
        
        // 行內編輯狀態
        this.inlineEditingIndex = -1;
        this._onInlineClickOutside = null;
        
        // 搜尋狀態
        this.searchTerm = '';
        this.filteredSubtitles = [];
        
        // 虛擬捲動狀態
        this._vsItemHeights = new Map();    // index → measured height
        this._vsEstimatedHeight = 72;       // default estimated item height (px)
        this._vsOffsets = [];               // cumulative offset array (top of each item)
        this._vsBuffer = 5;                 // buffer items above/below viewport
        this._vsScrollRAF = null;           // requestAnimationFrame id
        this._vsResizeObserver = null;      // ResizeObserver for measuring items
        this._vsRenderedRange = { start: -1, end: -1 }; // currently rendered range
        this._vsSpacer = null;              // spacer div for total height
        this._vsScrollContainer = null;     // #subtitle-list-container reference
        this._vsScrollHandler = null;       // bound scroll handler reference
        
        // 佈局狀態
        this.currentLayout = 'auto'; // 'auto', 'video', 'subtitle'
        
        // 事件監聽器
        this.eventListeners = new Map();
        
        // 初始化
        this.init();
    }
    
    /**
     * 初始化編輯器
     */
    init() {
        this.container = document.getElementById(this.containerId);
        if (!this.container) {
            throw new Error(`找不到容器元素: ${this.containerId}`);
        }
        
        this.initDOMReferences();
        this.initEventListeners();
        this.initThemeManager();
        
        console.log('字幕編輯器初始化完成');
    }
    
    /**
     * 初始化 DOM 元素引用
     */
    initDOMReferences() {
        this.videoPlayer = document.getElementById('video-player');
        this.subtitleList = document.getElementById('subtitle-list');
        this.loadingContainer = document.getElementById('loading-container');
        this.editorContainer = document.getElementById('subtitle-editor-container');
        this.errorContainer = document.getElementById('error-container');
        
        // 控制項元素
        this.playPauseBtn = document.getElementById('play-pause-btn');
        this.rewindBtn = document.getElementById('rewind-btn');
        this.forwardBtn = document.getElementById('forward-btn');
        this.videoProgress = document.getElementById('video-progress');
        this.volumeControl = document.getElementById('volume-control');
        this.playbackSpeed = document.getElementById('playback-speed');
        this.currentTimeDisplay = document.getElementById('current-time');
        this.totalTimeDisplay = document.getElementById('total-time');
        
        // 按鈕元素
        this.saveBtn = document.getElementById('save-subtitles');
        this.addSubtitleBtn = document.getElementById('add-subtitle-btn');
        this.syncToggleBtn = document.getElementById('sync-toggle-btn');
        this.themeToggleBtn = document.getElementById('theme-toggle');
        
        // 工具欄元素
        this.editingToolbar = document.getElementById('editing-toolbar');
        this.undoBtn = document.getElementById('undo-btn');
        this.redoBtn = document.getElementById('redo-btn');
        this.addSubtitleToolbarBtn = document.getElementById('add-subtitle-toolbar-btn');
        this.autoSyncBtn = document.getElementById('auto-sync-btn');
        this.resetBtn = document.getElementById('reset-btn');
        this.saveSubtitlesToolbar = document.getElementById('save-subtitles-toolbar');
        this.exportDropdownToolbar = document.getElementById('export-dropdown-toolbar');
        
        // 狀態顯示元素
        this.editStatus = document.getElementById('edit-status');
        this.syncStatus = document.getElementById('sync-status');
        this.saveStatus = document.getElementById('save-status');
        
        // 搜尋和計數元素
        this.subtitleSearch = document.getElementById('subtitle-search');
        this.clearSearchBtn = document.getElementById('clear-search-btn');
        this.subtitleCount = document.getElementById('subtitle-count');
        
        // 字幕顯示切換按鈕
        this.ccToggleBtn = document.getElementById('cc-toggle-btn');
        
        // 佈局切換元素
        this.layoutVideoBtn = document.getElementById('layout-video-btn');
        this.layoutSubtitleBtn = document.getElementById('layout-subtitle-btn');
        
        // 模態框元素
        this.editModal = document.getElementById('subtitle-edit-modal');
        this.editForm = document.getElementById('subtitle-edit-form');
        this.subtitleTextInput = document.getElementById('subtitle-text');
        this.startTimeInput = document.getElementById('start-time');
        this.endTimeInput = document.getElementById('end-time');
        this.saveSubtitleBtn = document.getElementById('save-subtitle-btn');
        this.deleteSubtitleBtn = document.getElementById('delete-subtitle-btn');
    }
    
    /**
     * 初始化事件監聽器
     */
    initEventListeners() {
        // 影片播放器事件
        if (this.videoPlayer) {
            this.addEventListener(this.videoPlayer, 'loadedmetadata', () => this.onVideoLoaded());
            this.addEventListener(this.videoPlayer, 'timeupdate', () => this.onTimeUpdate());
            this.addEventListener(this.videoPlayer, 'play', () => this.onPlayStateChange(true));
            this.addEventListener(this.videoPlayer, 'pause', () => this.onPlayStateChange(false));
            this.addEventListener(this.videoPlayer, 'error', (e) => this.onVideoError(e));
        }
        
        // 控制按鈕事件
        if (this.playPauseBtn) {
            this.addEventListener(this.playPauseBtn, 'click', () => this.togglePlayPause());
        }
        
        if (this.rewindBtn) {
            this.addEventListener(this.rewindBtn, 'click', () => this.rewind());
        }
        
        if (this.forwardBtn) {
            this.addEventListener(this.forwardBtn, 'click', () => this.forward());
        }
        
        // 進度條事件
        if (this.videoProgress) {
            this.addEventListener(this.videoProgress, 'input', () => this.onProgressChange());
        }
        
        // 音量控制事件
        if (this.volumeControl) {
            this.addEventListener(this.volumeControl, 'input', () => this.onVolumeChange());
        }
        
        // 播放速度事件
        if (this.playbackSpeed) {
            this.addEventListener(this.playbackSpeed, 'change', () => this.onSpeedChange());
        }
        
        // 功能按鈕事件
        if (this.saveBtn) {
            this.addEventListener(this.saveBtn, 'click', () => this.saveSubtitles());
        }
        
        if (this.addSubtitleBtn) {
            this.addEventListener(this.addSubtitleBtn, 'click', () => this.addNewSubtitle());
        }
        
        if (this.syncToggleBtn) {
            this.addEventListener(this.syncToggleBtn, 'click', () => this.toggleSync());
        }
        
        // 字幕顯示切換按鈕事件
        if (this.ccToggleBtn) {
            this.addEventListener(this.ccToggleBtn, 'click', () => this.toggleVideoSubtitles());
        }
        
        // 匯出按鈕事件
        document.querySelectorAll('[data-format]').forEach(btn => {
            this.addEventListener(btn, 'click', (e) => {
                e.preventDefault();
                const format = btn.dataset.format;
                this.exportSubtitles(format);
            });
        });
        
        // 進階匯出按鈕事件
        const advancedExportBtn = document.getElementById('advanced-export-btn');
        const advancedExportToolbarBtn = document.getElementById('advanced-export-toolbar-btn');
        
        if (advancedExportBtn) {
            this.addEventListener(advancedExportBtn, 'click', (e) => {
                e.preventDefault();
                this.showAdvancedExportModal();
            });
        }
        
        if (advancedExportToolbarBtn) {
            this.addEventListener(advancedExportToolbarBtn, 'click', (e) => {
                e.preventDefault();
                this.showAdvancedExportModal();
            });
        }
        
        // 進階匯出模態框事件
        const startAdvancedExportBtn = document.getElementById('start-advanced-export');
        if (startAdvancedExportBtn) {
            this.addEventListener(startAdvancedExportBtn, 'click', () => {
                this.startAdvancedExport();
            });
        }
        
        // 字幕編輯模態框事件
        if (this.saveSubtitleBtn) {
            this.addEventListener(this.saveSubtitleBtn, 'click', () => this.saveCurrentSubtitle());
        }
        
        if (this.deleteSubtitleBtn) {
            this.addEventListener(this.deleteSubtitleBtn, 'click', () => this.deleteCurrentSubtitle());
        }
        
        // 鍵盤快捷鍵
        this.addEventListener(document, 'keydown', (e) => this.onKeyDown(e));
        
        // 字幕列表事件委託
        if (this.subtitleList) {
            this.addEventListener(this.subtitleList, 'click', (e) => this.onSubtitleListClick(e));
            this.addEventListener(this.subtitleList, 'dblclick', (e) => this.onSubtitleListDblClick(e));
        }
        
        // 頁面離開前確認
        this.addEventListener(window, 'beforeunload', (e) => this.onBeforeUnload(e));
        
        // 工具欄事件
        if (this.undoBtn) {
            this.addEventListener(this.undoBtn, 'click', () => this.undo());
        }
        
        if (this.redoBtn) {
            this.addEventListener(this.redoBtn, 'click', () => this.redo());
        }
        
        if (this.addSubtitleToolbarBtn) {
            this.addEventListener(this.addSubtitleToolbarBtn, 'click', () => this.addNewSubtitle());
        }
        
        if (this.autoSyncBtn) {
            this.addEventListener(this.autoSyncBtn, 'click', () => this.toggleSync());
        }
        
        if (this.resetBtn) {
            this.addEventListener(this.resetBtn, 'click', () => this.resetSubtitles());
        }
        
        if (this.saveSubtitlesToolbar) {
            this.addEventListener(this.saveSubtitlesToolbar, 'click', () => this.saveSubtitles());
        }
        
        // 搜尋功能事件
        if (this.subtitleSearch) {
            this.addEventListener(this.subtitleSearch, 'input', () => this.onSearchInput());
        }
        
        if (this.clearSearchBtn) {
            this.addEventListener(this.clearSearchBtn, 'click', () => this.clearSearch());
        }
        
        // 佈局切換事件
        if (this.layoutVideoBtn) {
            this.addEventListener(this.layoutVideoBtn, 'click', () => this.showVideoLayout());
        }
        
        if (this.layoutSubtitleBtn) {
            this.addEventListener(this.layoutSubtitleBtn, 'click', () => this.showSubtitleLayout());
        }
        
        // 響應式佈局檢測
        this.addEventListener(window, 'resize', () => this.onWindowResize());
    }
    
    /**
     * 添加事件監聽器並記錄以便清理
     */
    addEventListener(element, event, handler) {
        element.addEventListener(event, handler);
        
        if (!this.eventListeners.has(element)) {
            this.eventListeners.set(element, []);
        }
        this.eventListeners.get(element).push({ event, handler });
    }
    
    /**
     * 初始化主題管理器
     */
    initThemeManager() {
        if (this.themeToggleBtn) {
            this.addEventListener(this.themeToggleBtn, 'click', () => this.toggleTheme());
        }
        
        // 載入儲存的主題
        this.loadTheme();
    }
    
    /**
     * 載入影片
     */
    loadVideo(videoUrl) {
        if (!this.videoPlayer) {
            console.error('[VideoPlayer] 影片播放器未初始化');
            return false;
        }
        
        if (!videoUrl) {
            console.warn('[VideoPlayer] 沒有提供影片 URL，編輯器將在無影片模式下運行');
            return false;
        }
        
        try {
            console.log('[VideoPlayer] 開始載入影片:', videoUrl);
            
            // 確保移除 crossorigin 屬性，避免 CORS 導致黑屏
            this.videoPlayer.removeAttribute('crossorigin');
            
            // 設置新的 src（不先清空，避免黑屏閃爍）
            this.videoPlayer.src = videoUrl;
            
            // 添加載入事件監聽器
            this.videoPlayer.addEventListener('loadedmetadata', () => {
                console.log('[VideoPlayer] 影片元資料已載入');
                console.log('[VideoPlayer] 影片時長:', this.videoPlayer.duration, '秒');
                this.showInfo('影片已載入');
                
                // 使用格式檢測器分析影片
                if (window.videoFormatDetector) {
                    window.videoFormatDetector.analyzeVideoElement(this.videoPlayer);
                }
            }, { once: true });
            
            this.videoPlayer.addEventListener('error', (e) => {
                console.error('[VideoPlayer] 影片載入錯誤:', e);
                console.error('[VideoPlayer] 錯誤詳情:', {
                    code: this.videoPlayer.error?.code,
                    message: this.videoPlayer.error?.message
                });
                
                // 使用格式檢測器進行診斷
                if (window.videoFormatDetector) {
                    const analysis = window.videoFormatDetector.analyzeVideoElement(this.videoPlayer);
                    
                    // 如果是格式不支持的錯誤，提供更詳細的建議
                    if (this.videoPlayer.error?.code === 4) {
                        const recommended = window.videoFormatDetector.getRecommendedFormats();
                        if (recommended.length > 0) {
                            console.log('[VideoPlayer] 建議使用的格式:', recommended.map(f => f.label).join(', '));
                            this.showError(`影片格式不支持。建議使用 ${recommended[0].label} 格式。字幕編輯功能仍可使用。`);
                        } else {
                            this.showError('影片格式不支持，且瀏覽器不支持任何推薦格式。字幕編輯功能仍可使用。');
                        }
                    } else {
                        this.showError('影片載入失敗，但字幕編輯功能仍可使用');
                    }
                } else {
                    this.showError('影片載入失敗，但字幕編輯功能仍可使用');
                }
            }, { once: true });
            
            this.videoPlayer.addEventListener('canplay', () => {
                console.log('[VideoPlayer] 影片可以開始播放');
            }, { once: true });
            
            // 開始載入
            this.videoPlayer.load();
            
            // 初始化影片字幕同步（如果啟用）
            // 延遲到影片元資料載入後再初始化，避免 track 干擾影片渲染
            if (this.options.enableVideoSubtitles && typeof VideoSubtitleSync !== 'undefined') {
                this.videoPlayer.addEventListener('loadeddata', () => {
                    this.videoSubtitleSync = new VideoSubtitleSync(this.videoPlayer, {
                        fontSize: '20px',
                        position: 'bottom'
                    });
                    
                    // 如果已經有字幕，載入到影片中
                    if (this.subtitles && this.subtitles.length > 0) {
                        this.videoSubtitleSync.loadSubtitles(this.subtitles);
                        console.log('[VideoPlayer] 影片字幕已同步');
                    }
                }, { once: true });
            }
            
            return true;
        } catch (error) {
            console.error('[VideoPlayer] 載入影片時發生錯誤:', error);
            this.showError('影片載入失敗');
            return false;
        }
    }
    
    /**
     * 載入字幕資料
     */
    loadSubtitles(subtitles) {
        if (!Array.isArray(subtitles)) {
            console.error('字幕資料格式錯誤');
            return false;
        }
        
        try {
            this.subtitles = subtitles.map((subtitle, index) => ({
                index: index,
                start_time: parseFloat(subtitle.start_time || 0),
                end_time: parseFloat(subtitle.end_time || 0),
                text: subtitle.text || '',
                confidence: subtitle.confidence || null,
                words: subtitle.words || null
            }));
            
            // 同步字幕到影片（如果啟用）
            if (this.videoSubtitleSync) {
                this.videoSubtitleSync.loadSubtitles(this.subtitles);
                console.log('[SubtitleEditor] 字幕已同步到影片');
            }
            
            // 保存原始資料
            this.originalSubtitles = JSON.parse(JSON.stringify(this.subtitles));
            
            // 初始化歷史記錄
            this.history = [JSON.parse(JSON.stringify(this.subtitles))];
            this.historyIndex = 0;
            
            this.renderSubtitleList();
            this.updateSubtitleCount();
            this.updateToolbarState();
            this.showEditingToolbar();
            this.isDirty = false;
            
            console.log(`載入了 ${this.subtitles.length} 個字幕項目`);
            return true;
        } catch (error) {
            console.error('載入字幕時發生錯誤:', error);
            this.showError('字幕載入失敗');
            return false;
        }
    }
    
    /**
     * 渲染字幕列表（虛擬捲動版）
     * 只渲染可視區域 + 緩衝區的項目，大幅改善 600+ 項目的效能
     */
    renderSubtitleList() {
        if (!this.subtitleList) return;
        
        // 初始化虛擬捲動（首次呼叫時）
        if (!this._vsScrollContainer) {
            this._vsInit();
        }
        
        // 清空已渲染的項目
        this._vsRemoveAllRenderedItems();
        this._vsRenderedRange = { start: -1, end: -1 };
        
        // 結構性變更（split/merge/delete/undo/redo）會重新索引所有字幕，
        // 此時舊的高度快取索引已無效，需要清除
        // 搜尋切換不需要清除，因為 subtitle.index 仍然有效
        this._vsItemHeights.clear();
        
        // 檢查是否有字幕
        const emptyState = document.getElementById('subtitle-empty-state');
        if (this.subtitles.length === 0) {
            if (emptyState) emptyState.style.display = 'block';
            if (this._vsSpacer) {
                this._vsSpacer.style.height = '0px';
            }
            return;
        }
        
        if (emptyState) emptyState.style.display = 'none';
        
        // 重建偏移量陣列
        this._vsRebuildOffsets();
        
        // 創建或更新 spacer（撐起總高度以獲得正確的捲動條）
        if (!this._vsSpacer) {
            this._vsSpacer = document.createElement('div');
            this._vsSpacer.className = 'vs-spacer';
            this._vsSpacer.style.cssText = 'width: 100%; pointer-events: none;';
            this.subtitleList.appendChild(this._vsSpacer);
        }
        this._vsSpacer.style.height = this._vsGetTotalHeight() + 'px';
        
        // 確保 spacer 始終在列表中
        if (!this._vsSpacer.parentNode) {
            this.subtitleList.appendChild(this._vsSpacer);
        }
        
        // 渲染可見項目
        this._vsRenderVisible();
        
        this.updateSubtitleCount();
    }
    
    /**
     * 顯示編輯工具欄
     */
    showEditingToolbar() {
        if (this.editingToolbar) {
            this.editingToolbar.style.display = 'block';
        }
    }
    
    /**
     * 更新字幕計數
     */
    updateSubtitleCount() {
        if (this.subtitleCount) {
            const total = this.subtitles.length;
            const filtered = this.searchTerm ? this.filteredSubtitles.length : total;
            
            if (this.searchTerm) {
                this.subtitleCount.textContent = `${filtered}/${total}`;
                this.subtitleCount.className = 'badge bg-warning ms-2';
            } else {
                this.subtitleCount.textContent = total;
                this.subtitleCount.className = 'badge bg-secondary ms-2';
            }
        }
    }
    
    /**
     * 更新工具欄狀態
     */
    updateToolbarState() {
        // 更新復原/重做按鈕狀態
        if (this.undoBtn) {
            this.undoBtn.disabled = this.historyIndex <= 0;
        }
        
        if (this.redoBtn) {
            this.redoBtn.disabled = this.historyIndex >= this.history.length - 1;
        }
        
        // 更新同步按鈕狀態
        if (this.autoSyncBtn) {
            if (this.options.autoSync) {
                this.autoSyncBtn.classList.remove('btn-outline-info');
                this.autoSyncBtn.classList.add('btn-info');
            } else {
                this.autoSyncBtn.classList.remove('btn-info');
                this.autoSyncBtn.classList.add('btn-outline-info');
            }
        }
        
        // 更新儲存狀態
        this.updateSaveStatus();
    }
    
    /**
     * 更新儲存狀態顯示
     */
    updateSaveStatus() {
        if (this.isDirty) {
            this.showStatus('edit', '有未儲存的變更');
            this.hideStatus('save');
        } else {
            this.hideStatus('edit');
        }
    }
    
    /**
     * 顯示狀態
     */
    showStatus(type, message = '') {
        const statusElement = this[`${type}Status`];
        if (statusElement) {
            statusElement.classList.remove('d-none');
            if (message) {
                statusElement.title = message;
            }
        }
    }
    
    /**
     * 隱藏狀態
     */
    hideStatus(type) {
        const statusElement = this[`${type}Status`];
        if (statusElement) {
            statusElement.classList.add('d-none');
        }
    }
    
    /**
     * 添加到歷史記錄
     */
    addToHistory() {
        // 移除當前位置之後的歷史記錄
        this.history = this.history.slice(0, this.historyIndex + 1);
        
        // 添加新的狀態
        this.history.push(JSON.parse(JSON.stringify(this.subtitles)));
        
        // 限制歷史記錄大小
        if (this.history.length > this.maxHistorySize) {
            this.history.shift();
        } else {
            this.historyIndex++;
        }
        
        this.updateToolbarState();
    }
    
    /**
     * 復原操作
     */
    undo() {
        if (this.historyIndex > 0) {
            this.historyIndex--;
            this.subtitles = JSON.parse(JSON.stringify(this.history[this.historyIndex]));
            this.renderSubtitleList();
            this.markDirty();
            this.syncVideoSubtitles();
            this.updateToolbarState();
            this.showSuccess('已復原');
        }
    }
    
    /**
     * 重做操作
     */
    redo() {
        if (this.historyIndex < this.history.length - 1) {
            this.historyIndex++;
            this.subtitles = JSON.parse(JSON.stringify(this.history[this.historyIndex]));
            this.renderSubtitleList();
            this.markDirty();
            this.syncVideoSubtitles();
            this.updateToolbarState();
            this.showSuccess('已重做');
        }
    }
    
    /**
     * 重置字幕到原始狀態
     */
    resetSubtitles() {
        if (confirm('確定要重置所有變更嗎？這將會失去所有未儲存的修改。')) {
            this.subtitles = JSON.parse(JSON.stringify(this.originalSubtitles));
            
            // 重置歷史記錄
            this.history = [JSON.parse(JSON.stringify(this.subtitles))];
            this.historyIndex = 0;
            
            this.renderSubtitleList();
            this.isDirty = false;
            this.syncVideoSubtitles();
            this.updateToolbarState();
            this.clearSearch();
            this.showSuccess('已重置到原始狀態');
        }
    }
    
    /**
     * 搜尋字幕
     */
    onSearchInput() {
        this.searchTerm = this.subtitleSearch.value.toLowerCase().trim();
        
        if (this.searchTerm) {
            this.filteredSubtitles = this.subtitles.filter(subtitle => 
                subtitle.text.toLowerCase().includes(this.searchTerm)
            );
        } else {
            this.filteredSubtitles = [];
        }
        
        this.renderSubtitleList();
    }
    
    /**
     * 清除搜尋
     */
    clearSearch() {
        if (this.subtitleSearch) {
            this.subtitleSearch.value = '';
        }
        this.searchTerm = '';
        this.filteredSubtitles = [];
        this.renderSubtitleList();
    }
    
    /**
     * 顯示影片佈局
     */
    showVideoLayout() {
        this.currentLayout = 'video';
        document.body.classList.add('layout-single-view');
        document.body.classList.remove('show-subtitles');
        
        // 更新按鈕狀態
        if (this.layoutVideoBtn) {
            this.layoutVideoBtn.classList.add('btn-secondary');
            this.layoutVideoBtn.classList.remove('btn-outline-secondary');
        }
        if (this.layoutSubtitleBtn) {
            this.layoutSubtitleBtn.classList.remove('btn-secondary');
            this.layoutSubtitleBtn.classList.add('btn-outline-secondary');
        }
    }
    
    /**
     * 顯示字幕佈局
     */
    showSubtitleLayout() {
        this.currentLayout = 'subtitle';
        document.body.classList.add('layout-single-view', 'show-subtitles');
        
        // 更新按鈕狀態
        if (this.layoutSubtitleBtn) {
            this.layoutSubtitleBtn.classList.add('btn-secondary');
            this.layoutSubtitleBtn.classList.remove('btn-outline-secondary');
        }
        if (this.layoutVideoBtn) {
            this.layoutVideoBtn.classList.remove('btn-secondary');
            this.layoutVideoBtn.classList.add('btn-outline-secondary');
        }
    }
    
    /**
     * 自動佈局
     */
    autoLayout() {
        this.currentLayout = 'auto';
        document.body.classList.remove('layout-single-view', 'show-subtitles');
        
        // 重置按鈕狀態
        if (this.layoutVideoBtn) {
            this.layoutVideoBtn.classList.remove('btn-secondary');
            this.layoutVideoBtn.classList.add('btn-outline-secondary');
        }
        if (this.layoutSubtitleBtn) {
            this.layoutSubtitleBtn.classList.remove('btn-secondary');
            this.layoutSubtitleBtn.classList.add('btn-outline-secondary');
        }
    }
    
    /**
     * 視窗大小變更處理
     */
    onWindowResize() {
        // 在大螢幕自動切換回自動佈局
        if (window.innerWidth >= 768 && this.currentLayout !== 'auto') {
            this.autoLayout();
        }
        
        // 視窗大小變更時重新計算可見項目
        if (this._vsScrollContainer) {
            this._vsRenderVisible();
        }
    }
    
    // ========== 虛擬捲動 (Virtual Scroll) 方法 ==========

    /**
     * 重建累積偏移量陣列
     * 每個項目的 top 位置 = 前面所有項目高度之和
     */
    _vsRebuildOffsets() {
        const items = this._vsGetItemList();
        const count = items.length;
        this._vsOffsets = new Array(count + 1);
        this._vsOffsets[0] = 0;
        
        for (let i = 0; i < count; i++) {
            // 使用原始 subtitle.index 作為 key 查詢快取高度
            const subtitleIndex = items[i].index;
            const h = this._vsItemHeights.get(subtitleIndex) || this._vsEstimatedHeight;
            this._vsOffsets[i + 1] = this._vsOffsets[i] + h;
        }
    }
    
    /**
     * 取得當前要渲染的字幕列表（考慮搜尋過濾）
     */
    _vsGetItemList() {
        return this.searchTerm ? this.filteredSubtitles : this.subtitles;
    }
    
    /**
     * 取得總高度
     */
    _vsGetTotalHeight() {
        const offsets = this._vsOffsets;
        return offsets.length > 0 ? offsets[offsets.length - 1] : 0;
    }
    
    /**
     * 根據捲動位置計算可見項目範圍
     * 使用二分搜尋找到第一個可見項目
     */
    _vsGetVisibleRange(scrollTop, viewportHeight) {
        const items = this._vsGetItemList();
        const count = items.length;
        if (count === 0) return { start: 0, end: 0 };
        
        const offsets = this._vsOffsets;
        
        // 二分搜尋：找到第一個 offset[i+1] > scrollTop 的 i
        let lo = 0, hi = count - 1;
        while (lo < hi) {
            const mid = (lo + hi) >>> 1;
            if (offsets[mid + 1] <= scrollTop) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }
        const startIndex = lo;
        
        // 從 startIndex 往後找到超出 viewport 的項目
        const scrollBottom = scrollTop + viewportHeight;
        let endIndex = startIndex;
        while (endIndex < count && offsets[endIndex] < scrollBottom) {
            endIndex++;
        }
        
        // 加入緩衝區
        const bufferedStart = Math.max(0, startIndex - this._vsBuffer);
        const bufferedEnd = Math.min(count, endIndex + this._vsBuffer);
        
        return { start: bufferedStart, end: bufferedEnd };
    }
    
    /**
     * 渲染可見項目（差異更新）
     * 只添加/移除變化的 DOM 元素
     */
    _vsRenderVisible() {
        if (!this.subtitleList || !this._vsScrollContainer) return;
        
        const scrollTop = this._vsScrollContainer.scrollTop;
        const viewportHeight = this._vsScrollContainer.clientHeight;
        const { start, end } = this._vsGetVisibleRange(scrollTop, viewportHeight);
        
        const prevStart = this._vsRenderedRange.start;
        const prevEnd = this._vsRenderedRange.end;
        
        // 如果範圍沒變，不做任何事
        if (start === prevStart && end === prevEnd) return;
        
        const items = this._vsGetItemList();
        const offsets = this._vsOffsets;
        
        // 策略：如果範圍重疊，做差異更新；否則全量替換
        const hasOverlap = prevStart >= 0 && start < prevEnd && end > prevStart;
        
        if (hasOverlap) {
            // 移除不再可見的頂部項目
            for (let i = prevStart; i < start; i++) {
                const el = this.subtitleList.querySelector(`[data-index="${items[i].index}"]`);
                if (el) {
                    this._vsResizeObserver?.unobserve(el);
                    el.remove();
                }
            }
            // 移除不再可見的底部項目
            for (let i = end; i < prevEnd; i++) {
                const el = this.subtitleList.querySelector(`[data-index="${items[i].index}"]`);
                if (el) {
                    this._vsResizeObserver?.unobserve(el);
                    el.remove();
                }
            }
            // 添加新出現的頂部項目
            const firstExistingIndex = Math.max(start, prevStart);
            const firstExistingEl = firstExistingIndex < items.length
                ? this.subtitleList.querySelector(`[data-index="${items[firstExistingIndex].index}"]`)
                : null;
            for (let i = start; i < prevStart && i < end; i++) {
                const el = this._vsCreatePositionedElement(items[i], items[i].index, offsets[i]);
                if (firstExistingEl) {
                    this.subtitleList.insertBefore(el, firstExistingEl);
                } else {
                    this.subtitleList.appendChild(el);
                }
            }
            // 添加新出現的底部項目
            for (let i = Math.max(prevEnd, start); i < end; i++) {
                const el = this._vsCreatePositionedElement(items[i], items[i].index, offsets[i]);
                this.subtitleList.appendChild(el);
            }
        } else {
            // 完全替換：移除所有已渲染項目
            this._vsRemoveAllRenderedItems();
            
            // 渲染新範圍
            for (let i = start; i < end; i++) {
                const el = this._vsCreatePositionedElement(items[i], items[i].index, offsets[i]);
                this.subtitleList.appendChild(el);
            }
        }
        
        // 對新加入的項目啟動觀察
        this._vsObserveRenderedItems(start, end, items);
        
        // 標記當前高亮
        if (this.currentSubtitleIndex >= 0) {
            const currentEl = this.subtitleList.querySelector(`[data-index="${this.currentSubtitleIndex}"]`);
            if (currentEl) {
                currentEl.classList.add('current');
            }
        }
        
        this._vsRenderedRange = { start, end };
    }
    
    /**
     * 創建一個絕對定位的字幕元素
     */
    _vsCreatePositionedElement(subtitle, index, topOffset) {
        const fragment = this.createSubtitleElement(subtitle, index);
        // createSubtitleElement 返回 DocumentFragment，取出第一個 Element
        const container = fragment.querySelector
            ? fragment.querySelector('.subtitle-item')
            : fragment.firstElementChild;
        
        // 因為 DocumentFragment 插入後會清空，我們需要先設定樣式
        // 但 fragment 中的 container 引用在 append 後仍有效
        if (container) {
            container.style.position = 'absolute';
            container.style.top = topOffset + 'px';
            container.style.left = '0';
            container.style.right = '0';
        }
        
        return fragment;
    }
    
    /**
     * 移除所有已渲染的字幕項目（保留 spacer）
     */
    _vsRemoveAllRenderedItems() {
        if (!this.subtitleList) return;
        
        // 取消觀察
        if (this._vsResizeObserver) {
            this._vsResizeObserver.disconnect();
        }
        
        const items = this.subtitleList.querySelectorAll('.subtitle-item');
        items.forEach(el => el.remove());
    }
    
    /**
     * 觀察已渲染項目的尺寸變化
     */
    _vsObserveRenderedItems(start, end, items) {
        if (!this._vsResizeObserver) return;
        
        for (let i = start; i < end; i++) {
            const el = this.subtitleList.querySelector(`[data-index="${items[i].index}"]`);
            if (el) {
                this._vsResizeObserver.observe(el);
            }
        }
    }
    
    /**
     * 捲動事件處理（RAF 節流）
     */
    _vsOnScroll() {
        if (this._vsScrollRAF) return;
        
        this._vsScrollRAF = requestAnimationFrame(() => {
            this._vsScrollRAF = null;
            this._vsRenderVisible();
        });
    }
    
    /**
     * 設置 ResizeObserver 測量實際項目高度
     */
    _vsSetupResizeObserver() {
        if (this._vsResizeObserver) {
            this._vsResizeObserver.disconnect();
        }
        
        this._vsResizeObserver = new ResizeObserver((entries) => {
            let offsetsChanged = false;
            
            for (const entry of entries) {
                const el = entry.target;
                const index = parseInt(el.dataset.index, 10);
                if (isNaN(index)) continue;
                
                // 使用 borderBoxSize 或 offsetHeight
                const measuredHeight = el.offsetHeight;
                const currentHeight = this._vsItemHeights.get(index) || this._vsEstimatedHeight;
                
                if (Math.abs(measuredHeight - currentHeight) > 2) {
                    this._vsItemHeights.set(index, measuredHeight);
                    offsetsChanged = true;
                }
            }
            
            if (offsetsChanged) {
                this._vsRebuildOffsets();
                
                // 更新 spacer 高度
                if (this._vsSpacer) {
                    this._vsSpacer.style.height = this._vsGetTotalHeight() + 'px';
                }
                
                // 重新定位已渲染的項目
                this._vsRepositionRenderedItems();
            }
        });
    }
    
    /**
     * 重新定位已渲染的項目（偏移量變化後）
     */
    _vsRepositionRenderedItems() {
        const items = this._vsGetItemList();
        const offsets = this._vsOffsets;
        const { start, end } = this._vsRenderedRange;
        
        for (let i = start; i < end && i < items.length; i++) {
            const el = this.subtitleList.querySelector(`[data-index="${items[i].index}"]`);
            if (el) {
                el.style.top = offsets[i] + 'px';
            }
        }
    }
    
    /**
     * 初始化虛擬捲動（綁定捲動容器和事件）
     */
    _vsInit() {
        this._vsScrollContainer = document.getElementById('subtitle-list-container');
        if (!this._vsScrollContainer || !this.subtitleList) return;
        
        // 設定列表容器為 relative 定位
        this.subtitleList.style.position = 'relative';
        
        // 設置 ResizeObserver
        this._vsSetupResizeObserver();
        
        // 綁定捲動事件
        this._vsScrollHandler = () => this._vsOnScroll();
        this._vsScrollContainer.addEventListener('scroll', this._vsScrollHandler, { passive: true });
    }
    
    /**
     * 銷毀虛擬捲動資源
     */
    _vsDestroy() {
        if (this._vsScrollRAF) {
            cancelAnimationFrame(this._vsScrollRAF);
            this._vsScrollRAF = null;
        }
        
        if (this._vsResizeObserver) {
            this._vsResizeObserver.disconnect();
            this._vsResizeObserver = null;
        }
        
        if (this._vsScrollContainer && this._vsScrollHandler) {
            this._vsScrollContainer.removeEventListener('scroll', this._vsScrollHandler);
            this._vsScrollHandler = null;
        }
        
        this._vsRenderedRange = { start: -1, end: -1 };
        this._vsSpacer = null;
    }
    
    /**
     * 捲動到指定項目索引位置
     * @param {number} itemListIndex - 在 _vsGetItemList() 中的索引
     */
    scrollToItem(itemListIndex) {
        if (!this._vsScrollContainer) return;
        
        const offsets = this._vsOffsets;
        const items = this._vsGetItemList();
        if (itemListIndex < 0 || itemListIndex >= items.length) return;
        
        const targetTop = offsets[itemListIndex];
        const viewportHeight = this._vsScrollContainer.clientHeight;
        const subtitleIndex = items[itemListIndex].index;
        const itemHeight = this._vsItemHeights.get(subtitleIndex) || this._vsEstimatedHeight;
        
        // 捲動到使項目居中的位置
        const scrollTarget = targetTop - (viewportHeight - itemHeight) / 2;
        
        this._vsScrollContainer.scrollTo({
            top: Math.max(0, scrollTarget),
            behavior: 'smooth'
        });
    }

    // ========== 結束虛擬捲動方法 ==========

    /**
     * 創建字幕元素
     */
    createSubtitleElement(subtitle, index) {
        const template = document.getElementById('subtitle-item-template');
        const element = template.content.cloneNode(true);
        const container = element.querySelector('.subtitle-item');
        
        // 設置資料屬性
        container.dataset.index = index;
        
        // 設置時間顯示
        const timingElement = element.querySelector('.subtitle-timing');
        timingElement.textContent = `${this.formatTime(subtitle.start_time)} → ${this.formatTime(subtitle.end_time)}`;
        
        // 設置字幕文字
        const textElement = element.querySelector('.subtitle-text');
        textElement.textContent = subtitle.text;
        
        // 設置按鈕事件
        const editBtn = element.querySelector('.edit-btn');
        const splitBtn = element.querySelector('.split-btn');
        const mergeBtn = element.querySelector('.merge-btn');
        const deleteBtn = element.querySelector('.delete-btn');
        
        editBtn.onclick = () => this.editSubtitle(index);
        splitBtn.onclick = (e) => {
            e.stopPropagation();
            this.splitSubtitle(index);
        };
        mergeBtn.onclick = (e) => {
            e.stopPropagation();
            this.mergeSubtitle(index);
        };
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            this.deleteSubtitle(index);
        };
        
        // 點擊跳轉到對應時間
        container.onclick = () => this.seekToSubtitle(index);
        
        return element;
    }
    
    /**
     * 同步字幕資料到影片字幕軌道（編輯後即時更新影片中顯示的字幕）
     */
    syncVideoSubtitles() {
        if (this.videoSubtitleSync) {
            this.videoSubtitleSync.updateSubtitles(this.subtitles);
            console.log('[SubtitleEditor] 影片字幕已即時同步');
        }
    }
    
    /**
     * 同步影片與字幕
     */
    syncVideoWithSubtitles() {
        if (!this.videoPlayer || !this.options.autoSync) return;
        
        const currentTime = this.videoPlayer.currentTime;
        let foundIndex = -1;
        
        // 尋找當前時間對應的字幕
        for (let i = 0; i < this.subtitles.length; i++) {
            const subtitle = this.subtitles[i];
            if (currentTime >= subtitle.start_time - this.options.syncTolerance && 
                currentTime <= subtitle.end_time + this.options.syncTolerance) {
                foundIndex = i;
                break;
            }
        }
        
        // 更新當前字幕高亮
        this.setCurrentSubtitle(foundIndex);
    }
    
    /**
     * 設置當前字幕（虛擬捲動版）
     * 如果目標項目不在 DOM 中，先捲動到其位置觸發渲染
     */
    setCurrentSubtitle(index) {
        // 移除之前的高亮
        const previousCurrent = this.subtitleList?.querySelector('.subtitle-item.current');
        if (previousCurrent) {
            previousCurrent.classList.remove('current');
        }
        
        this.currentSubtitleIndex = index;
        
        // 添加新的高亮
        if (index >= 0 && this.subtitleList) {
            let currentElement = this.subtitleList.querySelector(`[data-index="${index}"]`);
            
            if (currentElement) {
                currentElement.classList.add('current');
                
                // 使用原生 scrollIntoView，但要確認在可視範圍內
                currentElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'nearest'
                });
            } else {
                // 項目不在 DOM 中 → 先找到它在 itemList 中的位置索引，然後捲動過去
                const items = this._vsGetItemList();
                const itemListIndex = items.findIndex(s => s.index === index);
                
                if (itemListIndex >= 0 && this._vsOffsets.length > itemListIndex) {
                    // 直接設定 scrollTop 以觸發捲動事件和重新渲染
                    const targetTop = this._vsOffsets[itemListIndex];
                    const viewportHeight = this._vsScrollContainer?.clientHeight || 400;
                    const itemHeight = this._vsItemHeights.get(index) || this._vsEstimatedHeight;
                    const scrollTarget = targetTop - (viewportHeight - itemHeight) / 2;
                    
                    if (this._vsScrollContainer) {
                        this._vsScrollContainer.scrollTop = Math.max(0, scrollTarget);
                    }
                    
                    // 強制立即渲染（而非等待 RAF）
                    this._vsRenderVisible();
                    
                    // 現在元素應該在 DOM 中了
                    currentElement = this.subtitleList.querySelector(`[data-index="${index}"]`);
                    if (currentElement) {
                        currentElement.classList.add('current');
                    }
                }
            }
        }
    }
    
    /**
     * 編輯字幕
     */
    editSubtitle(index) {
        if (index < 0 || index >= this.subtitles.length) return;
        
        const subtitle = this.subtitles[index];
        this.currentEditingIndex = index;
        
        // 填充表單
        this.subtitleTextInput.value = subtitle.text;
        this.startTimeInput.value = this.formatTime(subtitle.start_time);
        this.endTimeInput.value = this.formatTime(subtitle.end_time);
        
        // 顯示模態框
        const modal = new bootstrap.Modal(this.editModal);
        modal.show();
    }
    
    /**
     * 儲存當前編輯的字幕
     */
    saveCurrentSubtitle() {
        if (this.currentEditingIndex < 0) return;
        
        try {
            const text = this.subtitleTextInput.value.trim();
            const startTime = this.parseTime(this.startTimeInput.value);
            const endTime = this.parseTime(this.endTimeInput.value);
            
            // 驗證輸入
            if (!text) {
                this.showError('字幕文字不能為空');
                return;
            }
            
            if (startTime >= endTime) {
                this.showError('開始時間必須小於結束時間');
                return;
            }
            
            // 更新字幕資料
            const subtitle = this.subtitles[this.currentEditingIndex];
            subtitle.text = text;
            subtitle.start_time = startTime;
            subtitle.end_time = endTime;
            
            // 添加到歷史記錄
            this.addToHistory();
            
            // 重新渲染列表
            this.renderSubtitleList();
            this.markDirty();
            
            // 同步更新影片字幕
            this.syncVideoSubtitles();
            
            // 關閉模態框
            const modal = bootstrap.Modal.getInstance(this.editModal);
            modal.hide();
            
            this.showSuccess('字幕已更新');
        } catch (error) {
            console.error('儲存字幕時發生錯誤:', error);
            this.showError('儲存字幕失敗');
        }
    }
    
    /**
     * 刪除當前編輯的字幕
     */
    deleteCurrentSubtitle() {
        if (this.currentEditingIndex < 0) return;
        
        if (confirm('確定要刪除這個字幕嗎？')) {
            this.subtitles.splice(this.currentEditingIndex, 1);
            
            // 重新索引
            this.subtitles.forEach((subtitle, index) => {
                subtitle.index = index;
            });
            
            this.addToHistory();
            this.renderSubtitleList();
            this.markDirty();
            
            // 同步更新影片字幕
            this.syncVideoSubtitles();
            
            // 關閉模態框
            const modal = bootstrap.Modal.getInstance(this.editModal);
            modal.hide();
            
            this.showSuccess('字幕已刪除');
        }
    }
    
    /**
     * 分割字幕
     */
    splitSubtitle(index) {
        if (index < 0 || index >= this.subtitles.length) return;
        
        const subtitle = this.subtitles[index];
        const midTime = (subtitle.start_time + subtitle.end_time) / 2;
        
        // 創建新的字幕項目
        const newSubtitle = {
            index: index + 1,
            start_time: midTime,
            end_time: subtitle.end_time,
            text: subtitle.text,
            confidence: subtitle.confidence,
            words: null
        };
        
        // 更新原字幕的結束時間
        subtitle.end_time = midTime;
        
        // 插入新字幕
        this.subtitles.splice(index + 1, 0, newSubtitle);
        
        // 重新索引
        this.subtitles.forEach((sub, idx) => {
            sub.index = idx;
        });
        
        this.addToHistory();
        this.renderSubtitleList();
        this.markDirty();
        
        // 同步更新影片字幕
        this.syncVideoSubtitles();
        
        this.showSuccess('字幕已分割');
    }
    
    /**
     * 合併字幕
     */
    mergeSubtitle(index) {
        if (index < 0 || index >= this.subtitles.length - 1) return;
        
        const currentSubtitle = this.subtitles[index];
        const nextSubtitle = this.subtitles[index + 1];
        
        // 合併文字和時間
        currentSubtitle.text += ' ' + nextSubtitle.text;
        currentSubtitle.end_time = nextSubtitle.end_time;
        
        // 刪除下一個字幕
        this.subtitles.splice(index + 1, 1);
        
        // 重新索引
        this.subtitles.forEach((subtitle, idx) => {
            subtitle.index = idx;
        });
        
        this.addToHistory();
        this.renderSubtitleList();
        this.markDirty();
        
        // 同步更新影片字幕
        this.syncVideoSubtitles();
        
        this.showSuccess('字幕已合併');
    }
    
    /**
     * 刪除字幕
     */
    deleteSubtitle(index) {
        if (index < 0 || index >= this.subtitles.length) return;
        
        if (!confirm('確定要刪除這個字幕嗎？')) return;
        
        // 取得被刪除字幕的時間範圍
        const deleted = this.subtitles[index];
        const deletedStart = deleted.start_time;
        const deletedEnd = deleted.end_time;
        const gap = deletedEnd - deletedStart;
        
        // 移除字幕
        this.subtitles.splice(index, 1);
        
        // 重新計算後續字幕的時間（將被刪除片段的時間間隔扣除）
        for (let i = index; i < this.subtitles.length; i++) {
            this.subtitles[i].start_time = Math.max(0, this.subtitles[i].start_time - gap);
            this.subtitles[i].end_time = Math.max(0, this.subtitles[i].end_time - gap);
            // 更新詞級時間戳
            if (this.subtitles[i].words) {
                for (const w of this.subtitles[i].words) {
                    w.start = Math.max(0, w.start - gap);
                    w.end = Math.max(0, w.end - gap);
                }
            }
        }
        
        // 重新索引
        this.subtitles.forEach((subtitle, idx) => {
            subtitle.index = idx;
        });
        
        this.addToHistory();
        this.renderSubtitleList();
        this.markDirty();
        
        // 同步更新影片字幕
        this.syncVideoSubtitles();
        
        this.showSuccess('字幕已刪除');
    }
    
    /**
     * 跳轉到指定字幕
     */
    seekToSubtitle(index) {
        if (index < 0 || index >= this.subtitles.length || !this.videoPlayer) return;
        
        const subtitle = this.subtitles[index];
        this.videoPlayer.currentTime = subtitle.start_time;
        this.setCurrentSubtitle(index);
    }
    
    /**
     * 新增字幕
     */
    addNewSubtitle() {
        if (!this.videoPlayer) {
            this.showError('請先載入影片');
            return;
        }
        
        const currentTime = this.videoPlayer.currentTime;
        const duration = Math.min(3.0, this.videoPlayer.duration - currentTime); // 預設3秒長度
        
        const newSubtitle = {
            index: this.subtitles.length,
            start_time: currentTime,
            end_time: currentTime + duration,
            text: '新字幕',
            confidence: null,
            words: null
        };
        
        this.subtitles.push(newSubtitle);
        
        // 按時間排序
        this.subtitles.sort((a, b) => a.start_time - b.start_time);
        
        // 重新索引
        this.subtitles.forEach((subtitle, index) => {
            subtitle.index = index;
        });
        
        this.addToHistory();
        this.renderSubtitleList();
        this.markDirty();
        
        // 同步更新影片字幕
        this.syncVideoSubtitles();
        
        // 自動編輯新字幕
        const newIndex = this.subtitles.findIndex(sub => sub.start_time === currentTime);
        if (newIndex >= 0) {
            setTimeout(() => this.editSubtitle(newIndex), 100);
        }
        
        this.showSuccess('已新增字幕');
    }
    
    /**
     * 切換同步模式
     */
    toggleSync() {
        this.options.autoSync = !this.options.autoSync;
        
        if (this.syncToggleBtn) {
            const icon = this.syncToggleBtn.querySelector('i');
            if (this.options.autoSync) {
                this.syncToggleBtn.classList.remove('btn-outline-secondary');
                this.syncToggleBtn.classList.add('btn-outline-primary');
                icon.className = 'bi bi-arrow-repeat';
                this.showSuccess('已開啟自動同步');
            } else {
                this.syncToggleBtn.classList.remove('btn-outline-primary');
                this.syncToggleBtn.classList.add('btn-outline-secondary');
                icon.className = 'bi bi-pause';
                this.showSuccess('已關閉自動同步');
            }
        }
    }
    
    /**
     * 切換影片字幕顯示（CC 按鈕）
     */
    toggleVideoSubtitles() {
        if (!this.videoSubtitleSync) {
            this.showError('字幕尚未載入');
            return;
        }
        
        const isCurrentlyVisible = this.videoSubtitleSync.isVisible();
        this.videoSubtitleSync.setVisible(!isCurrentlyVisible);
        
        if (this.ccToggleBtn) {
            if (!isCurrentlyVisible) {
                this.ccToggleBtn.classList.add('active');
                this.ccToggleBtn.title = '關閉字幕';
                this.showSuccess('已開啟影片字幕');
            } else {
                this.ccToggleBtn.classList.remove('active');
                this.ccToggleBtn.title = '開啟字幕';
                this.showSuccess('已關閉影片字幕');
            }
        }
    }
    
    /**
     * 切換播放/暫停
     */
    togglePlayPause() {
        if (!this.videoPlayer) return;
        
        if (this.videoPlayer.paused) {
            this.videoPlayer.play();
        } else {
            this.videoPlayer.pause();
        }
    }
    
    /**
     * 後退
     */
    rewind() {
        if (!this.videoPlayer) return;
        this.videoPlayer.currentTime = Math.max(0, this.videoPlayer.currentTime - 10);
    }
    
    /**
     * 快進
     */
    forward() {
        if (!this.videoPlayer) return;
        this.videoPlayer.currentTime = Math.min(this.videoPlayer.duration, this.videoPlayer.currentTime + 10);
    }
    
    /**
     * 儲存字幕
     */
    async saveSubtitles() {
        if (!this.taskId) {
            this.showError('缺少任務 ID');
            return;
        }
        
        try {
            this.showLoading('正在儲存字幕...');
            
            // 同步更新影片字幕
            if (this.videoSubtitleSync) {
                this.videoSubtitleSync.updateSubtitles(this.subtitles);
                console.log('[SubtitleEditor] 影片字幕已更新');
            }
            
            // 準備字幕資料（帶回原始 metadata，更新 last_modified）
            const metadata = Object.assign({}, this.metadata || {}, {
                last_modified: Date.now() / 1000
            });
            const subtitleCollection = {
                task_id: this.taskId,
                subtitles: this.subtitles,
                metadata: metadata
            };
            
            const response = await fetch(`/api/subtitles/${this.taskId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(subtitleCollection)
            });
            
            if (!response.ok) {
                const error = await response.json();
                // FastAPI 422 returns {detail: [...]}, other errors may use {error: "..."}
                let errorMsg = '儲存失敗';
                if (error.detail) {
                    if (Array.isArray(error.detail)) {
                        errorMsg = error.detail.map(d => d.msg || JSON.stringify(d)).join('; ');
                    } else {
                        errorMsg = String(error.detail);
                    }
                } else if (error.error) {
                    errorMsg = error.error;
                }
                throw new Error(errorMsg);
            }
            
            const result = await response.json();
            
            this.isDirty = false;
            this.hideLoading();
            this.showStatus('save', '字幕已儲存');
            this.updateToolbarState();
            this.showSuccess('字幕已儲存');
            
            // 3秒後隱藏儲存狀態
            setTimeout(() => {
                this.hideStatus('save');
            }, 3000);
            
            console.log('字幕儲存成功:', result);
        } catch (error) {
            this.hideLoading();
            console.error('儲存字幕時發生錯誤:', error);
            this.showError(`儲存字幕失敗: ${error.message}`);
        }
    }
    
    /**
     * 匯出字幕
     */
    async exportSubtitles(format) {
        if (!this.downloadManager) {
            // 回退到原始實現
            return this.legacyExportSubtitles(format);
        }
        
        // 使用下載管理器
        return this.downloadManager.downloadSubtitle(format);
    }
    
    /**
     * 原始匯出實現（回退用）
     */
    async legacyExportSubtitles(format) {
        if (!this.taskId) {
            this.showError('缺少任務 ID');
            return;
        }
        
        try {
            this.showLoading(`正在匯出 ${format.toUpperCase()} 格式...`);
            
            const response = await fetch(`/api/subtitles/${this.taskId}/download/${format}`);
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || '匯出失敗');
            }
            
            // 下載文件
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `subtitles_${this.taskId}.${format}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            this.hideLoading();
            this.showSuccess(`${format.toUpperCase()} 格式匯出完成`);
        } catch (error) {
            this.hideLoading();
            console.error('匯出字幕時發生錯誤:', error);
            this.showError(`匯出字幕失敗: ${error.message}`);
        }
    }
    
    /**
     * 顯示進階匯出模態框
     */
    showAdvancedExportModal() {
        const modal = document.getElementById('advanced-export-modal');
        if (!modal) {
            this.showError('找不到進階匯出模態框');
            return;
        }
        
        // 初始化格式選擇器
        if (this.downloadManager) {
            this.downloadManager.createFormatSelector('format-selector-container', {
                title: '選擇匯出格式',
                multiple: true,
                showDescription: true
            });
        }
        
        // 顯示模態框
        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();
    }
    
    /**
     * 開始進階匯出
     */
    async startAdvancedExport() {
        if (!this.downloadManager) {
            this.showError('下載管理器未初始化');
            return;
        }
        
        const modal = document.getElementById('advanced-export-modal');
        const container = document.getElementById('format-selector-container');
        
        // 獲取選中的格式
        const selectedFormats = this.downloadManager.getSelectedFormats(container, true);
        
        if (selectedFormats.length === 0) {
            this.showError('請選擇至少一種格式');
            return;
        }
        
        // 獲取匯出選項
        const options = this.getExportOptions();
        
        // 關閉模態框
        const bootstrapModal = bootstrap.Modal.getInstance(modal);
        if (bootstrapModal) {
            bootstrapModal.hide();
        }
        
        try {
            // 檢查是否批次下載
            if (options.batchDownload && selectedFormats.length > 1) {
                await this.downloadManager.downloadMultipleFormats(selectedFormats);
            } else {
                // 逐個下載
                for (const format of selectedFormats) {
                    await this.downloadManager.downloadSubtitle(format);
                    
                    // 批次下載間隔
                    if (selectedFormats.length > 1) {
                        await new Promise(resolve => setTimeout(resolve, 1000));
                    }
                }
            }
        } catch (error) {
            console.error('進階匯出時發生錯誤:', error);
            this.showError(`進階匯出失敗: ${error.message}`);
        }
    }
    
    /**
     * 獲取匯出選項
     */
    getExportOptions() {
        return {
            includeTimestamps: document.getElementById('include-timestamps')?.checked || false,
            includeMetadata: document.getElementById('include-metadata')?.checked || false,
            includeConfidence: document.getElementById('include-confidence')?.checked || false,
            encoding: document.getElementById('encoding-select')?.value || 'utf-8',
            lineEnding: document.getElementById('line-ending-select')?.value || 'lf',
            batchDownload: document.getElementById('batch-download')?.checked || false
        };
    }
    
    /**
     * 切換主題
     */
    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-bs-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        document.documentElement.setAttribute('data-bs-theme', newTheme);
        localStorage.setItem('subtitle-editor-theme', newTheme);
        
        // 更新按鈕圖標
        const icon = this.themeToggleBtn.querySelector('i');
        if (newTheme === 'dark') {
            icon.className = 'bi bi-sun-fill';
        } else {
            icon.className = 'bi bi-moon-fill';
        }
    }
    
    /**
     * 載入主題
     */
    loadTheme() {
        const savedTheme = localStorage.getItem('subtitle-editor-theme') || 'light';
        document.documentElement.setAttribute('data-bs-theme', savedTheme);
        
        // 更新按鈕圖標
        if (this.themeToggleBtn) {
            const icon = this.themeToggleBtn.querySelector('i');
            if (savedTheme === 'dark') {
                icon.className = 'bi bi-sun-fill';
            } else {
                icon.className = 'bi bi-moon-fill';
            }
        }
    }
    
    /**
     * 格式化時間
     */
    formatTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        const ms = Math.floor((seconds % 1) * 1000);
        
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
    }
    
    /**
     * 解析時間字串
     */
    parseTime(timeString) {
        const parts = timeString.split(':');
        if (parts.length !== 3) throw new Error('時間格式錯誤');
        
        const hours = parseInt(parts[0]);
        const minutes = parseInt(parts[1]);
        const secondsParts = parts[2].split('.');
        const seconds = parseInt(secondsParts[0]);
        const ms = secondsParts.length > 1 ? parseInt(secondsParts[1].padEnd(3, '0')) : 0;
        
        return hours * 3600 + minutes * 60 + seconds + ms / 1000;
    }
    
    /**
     * 標記為已修改
     */
    markDirty() {
        this.isDirty = true;
        this.updateToolbarState();
    }
    
    /**
     * 顯示載入狀態
     */
    showLoading(message = '載入中...') {
        // 移除現有的載入提示
        this.hideLoading();
        
        // 創建載入提示元素
        const loadingEl = document.createElement('div');
        loadingEl.id = 'subtitle-loading-indicator';
        loadingEl.className = 'position-fixed top-0 start-0 w-100 h-100 d-flex justify-content-center align-items-center';
        loadingEl.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
        loadingEl.style.zIndex = '9999';
        
        loadingEl.innerHTML = `
            <div class="bg-white p-4 rounded shadow-lg text-center">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">載入中...</span>
                </div>
                <p class="mb-0">${message}</p>
            </div>
        `;
        
        document.body.appendChild(loadingEl);
    }
    
    /**
     * 隱藏載入狀態
     */
    hideLoading() {
        const loadingEl = document.getElementById('subtitle-loading-indicator');
        if (loadingEl) {
            loadingEl.remove();
        }
    }
    
    /**
     * 顯示成功訊息
     */
    showSuccess(message) {
        this.showToast(message, 'success');
    }
    
    /**
     * 顯示錯誤訊息
     */
    showError(message) {
        this.showToast(message, 'danger');
    }
    
    /**
     * 顯示資訊訊息
     */
    showInfo(message) {
        this.showToast(message, 'info');
    }
    
    /**
     * 顯示提示訊息
     */
    showToast(message, type = 'info') {
        // 創建 Toast 容器（如果不存在）
        let toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            toastContainer.style.zIndex = '9998';
            document.body.appendChild(toastContainer);
        }
        
        // 創建 Toast 元素
        const toastId = `toast-${Date.now()}`;
        const toast = document.createElement('div');
        toast.className = `toast fade-in border-${type}`;
        toast.id = toastId;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
        toast.setAttribute('aria-atomic', 'true');
        
        const typeText = type === 'success' ? '成功' : type === 'danger' ? '錯誤' : '提示';
        
        toast.innerHTML = `
            <div class="toast-header">
                <strong class="me-auto text-${type}">${typeText}</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        `;
        
        // 添加到容器
        toastContainer.appendChild(toast);
        
        // 初始化 Bootstrap Toast
        const bsToast = new bootstrap.Toast(toast, {
            autohide: true,
            delay: 5000
        });
        
        // 顯示 Toast
        bsToast.show();
        
        // 監聽隱藏事件，移除元素
        toast.addEventListener('hidden.bs.toast', function() {
            toast.remove();
        });
    }
    
    /**
     * 事件處理器
     */
    onVideoLoaded() {
        if (this.totalTimeDisplay) {
            this.totalTimeDisplay.textContent = this.formatTime(this.videoPlayer.duration);
        }
        
        if (this.videoProgress) {
            this.videoProgress.max = this.videoPlayer.duration;
        }
    }
    
    onTimeUpdate() {
        const currentTime = this.videoPlayer.currentTime;
        
        if (this.currentTimeDisplay) {
            this.currentTimeDisplay.textContent = this.formatTime(currentTime);
        }
        
        if (this.videoProgress) {
            this.videoProgress.value = currentTime;
        }
        
        this.syncVideoWithSubtitles();
    }
    
    onPlayStateChange(isPlaying) {
        this.isPlaying = isPlaying;
        
        if (this.playPauseBtn) {
            const icon = this.playPauseBtn.querySelector('i');
            if (isPlaying) {
                icon.className = 'bi bi-pause-fill';
            } else {
                icon.className = 'bi bi-play-fill';
            }
        }
    }
    
    onVideoError(error) {
        console.error('影片播放錯誤:', error);
        this.showError('影片播放發生錯誤');
    }
    
    onProgressChange() {
        if (this.videoPlayer) {
            this.videoPlayer.currentTime = this.videoProgress.value;
        }
    }
    
    onVolumeChange() {
        if (this.videoPlayer) {
            this.videoPlayer.volume = this.volumeControl.value / 100;
        }
    }
    
    onSpeedChange() {
        if (this.videoPlayer) {
            this.videoPlayer.playbackRate = parseFloat(this.playbackSpeed.value);
        }
    }
    
    onKeyDown(event) {
        // 鍵盤快捷鍵處理
        if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
            return; // 在輸入框中不處理快捷鍵
        }
        
        switch (event.code) {
            case 'Space':
                event.preventDefault();
                this.togglePlayPause();
                break;
            case 'ArrowLeft':
                event.preventDefault();
                this.rewind();
                break;
            case 'ArrowRight':
                event.preventDefault();
                this.forward();
                break;
        }
    }
    
    onSubtitleListClick(event) {
        // 如果正在行內編輯，點擊非編輯區域則提交編輯
        if (this.inlineEditingIndex >= 0) {
            const editingTextarea = this.subtitleList.querySelector('.subtitle-inline-edit');
            if (editingTextarea && !editingTextarea.contains(event.target)) {
                this.commitInlineEdit();
            }
            return;
        }
        
        const subtitleItem = event.target.closest('.subtitle-item');
        if (subtitleItem && !event.target.closest('.btn')) {
            const index = parseInt(subtitleItem.dataset.index);
            this.seekToSubtitle(index);
        }
    }
    
    onSubtitleListDblClick(event) {
        const subtitleItem = event.target.closest('.subtitle-item');
        if (subtitleItem && !event.target.closest('.btn')) {
            event.preventDefault();
            event.stopPropagation();
            const index = parseInt(subtitleItem.dataset.index);
            this.startInlineEdit(index);
        }
    }
    
    /**
     * 開始行內編輯字幕文字
     */
    startInlineEdit(index) {
        // 如果已在編輯其他項目，先提交
        if (this.inlineEditingIndex >= 0) {
            this.commitInlineEdit();
        }
        
        if (index < 0 || index >= this.subtitles.length) return;
        
        const subtitleItem = this.subtitleList.querySelector(`[data-index="${index}"]`);
        if (!subtitleItem) return;
        
        const textElement = subtitleItem.querySelector('.subtitle-text');
        if (!textElement) return;
        
        this.inlineEditingIndex = index;
        const originalText = this.subtitles[index].text;
        
        // 將 <p> 替換為 <textarea>
        const textarea = document.createElement('textarea');
        textarea.className = 'subtitle-inline-edit';
        textarea.value = originalText;
        textarea.dataset.originalText = originalText;
        textarea.rows = Math.max(1, Math.ceil(originalText.length / 40));
        
        // 鍵盤事件
        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                this.cancelInlineEdit();
            } else if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                e.stopPropagation();
                this.commitInlineEdit();
            }
        });
        
        // 阻止 textarea 上的 click 冒泡，避免觸發 seekToSubtitle
        textarea.addEventListener('click', (e) => e.stopPropagation());
        textarea.addEventListener('dblclick', (e) => e.stopPropagation());
        
        // 替換元素
        textElement.style.display = 'none';
        textElement.parentNode.insertBefore(textarea, textElement.nextSibling);
        
        // 標記編輯狀態
        subtitleItem.classList.add('inline-editing');
        
        // 聚焦並選中全部
        textarea.focus();
        textarea.select();
        
        // 全域點擊監聽（點擊編輯區域外部則提交）
        this._onInlineClickOutside = (e) => {
            if (!textarea.contains(e.target) && !subtitleItem.contains(e.target)) {
                this.commitInlineEdit();
            }
        };
        // 延遲綁定，避免同一次 dblclick 立刻觸發
        setTimeout(() => {
            document.addEventListener('mousedown', this._onInlineClickOutside);
        }, 0);
    }
    
    /**
     * 提交行內編輯
     */
    commitInlineEdit() {
        if (this.inlineEditingIndex < 0) return;
        
        const index = this.inlineEditingIndex;
        const subtitleItem = this.subtitleList.querySelector(`[data-index="${index}"]`);
        if (!subtitleItem) {
            this._cleanupInlineEdit();
            return;
        }
        
        const textarea = subtitleItem.querySelector('.subtitle-inline-edit');
        const textElement = subtitleItem.querySelector('.subtitle-text');
        if (!textarea || !textElement) {
            this._cleanupInlineEdit();
            return;
        }
        
        const newText = textarea.value.trim();
        const originalText = textarea.dataset.originalText;
        
        // 只有內容有變更才更新
        if (newText && newText !== originalText) {
            const originalSubtitle = { ...this.subtitles[index] };
            this.subtitles[index].text = newText;
            
            this.addToHistory();
            this.markDirty();
            this.syncVideoSubtitles();
        }
        
        // 還原 DOM
        textElement.textContent = this.subtitles[index].text;
        textElement.style.display = '';
        textarea.remove();
        subtitleItem.classList.remove('inline-editing');
        
        this._cleanupInlineEdit();
    }
    
    /**
     * 取消行內編輯
     */
    cancelInlineEdit() {
        if (this.inlineEditingIndex < 0) return;
        
        const index = this.inlineEditingIndex;
        const subtitleItem = this.subtitleList.querySelector(`[data-index="${index}"]`);
        if (subtitleItem) {
            const textarea = subtitleItem.querySelector('.subtitle-inline-edit');
            const textElement = subtitleItem.querySelector('.subtitle-text');
            
            if (textarea) textarea.remove();
            if (textElement) textElement.style.display = '';
            subtitleItem.classList.remove('inline-editing');
        }
        
        this._cleanupInlineEdit();
    }
    
    /**
     * 清理行內編輯狀態
     */
    _cleanupInlineEdit() {
        if (this._onInlineClickOutside) {
            document.removeEventListener('mousedown', this._onInlineClickOutside);
            this._onInlineClickOutside = null;
        }
        this.inlineEditingIndex = -1;
    }
    
    onBeforeUnload(event) {
        if (this.isDirty) {
            event.preventDefault();
            event.returnValue = '您有未儲存的變更，確定要離開嗎？';
            return event.returnValue;
        }
    }
    
    /**
     * 清理資源
     */
    destroy() {
        // 清理虛擬捲動資源
        this._vsDestroy();
        
        // 移除所有事件監聯器
        this.eventListeners.forEach((listeners, element) => {
            listeners.forEach(({ event, handler }) => {
                element.removeEventListener(event, handler);
            });
        });
        
        this.eventListeners.clear();
        
        // 清理其他資源
        this.subtitles = [];
        this.currentSubtitleIndex = -1;
        
        console.log('字幕編輯器已清理');
    }
}

/**
 * 頁面載入完成後初始化
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('[SubtitleEditor] DOMContentLoaded 事件觸發');
    
    // 確保所有依賴都已載入
    if (typeof SubtitleEditor === 'undefined') {
        console.error('[SubtitleEditor] SubtitleEditor 類別未定義');
        showEditorError('字幕編輯器載入失敗：缺少必要組件');
        return;
    }
    
    let taskId = null;

    // 1) 模板可能提前設定全域變數
    if (typeof window !== 'undefined' && window.SUBTITLE_EDITOR_TASK_ID) {
        taskId = window.SUBTITLE_EDITOR_TASK_ID;
    }

    // 2) 嘗試從查詢參數讀取
    if (!taskId) {
        const urlParams = new URLSearchParams(window.location.search);
        taskId = urlParams.get('task_id');
    }

    // 3) 支援 RESTful 路徑 /subtitle-editor/<taskId>
    if (!taskId) {
        const pathMatch = window.location.pathname.match(/\/subtitle-editor\/([^\/?#]+)/);
        if (pathMatch && pathMatch[1]) {
            try {
                taskId = decodeURIComponent(pathMatch[1]);
            } catch (e) {
                taskId = pathMatch[1];
            }
        }
    }

    if (!taskId) {
        console.error('[SubtitleEditor] 缺少任務 ID');
        showEditorError('缺少任務 ID 參數');
        return;
    }

    console.log('[SubtitleEditor] 任務 ID:', taskId);

    // 將解析出的任務 ID 暴露給其他腳本使用
    window.SUBTITLE_EDITOR_TASK_ID = taskId;

    // 使用 setTimeout 確保 DOM 完全準備好
    setTimeout(() => {
        try {
            console.log('[SubtitleEditor] 開始初始化編輯器');
            
            // 確保載入遮罩已隱藏
            if (window.globalLoadingManager) {
                window.globalLoadingManager.hideAllLoaders();
            }
            
            const editor = new SubtitleEditor('subtitle-editor-container', {
                autoSync: true,
                syncTolerance: 0.5
            });

            // 載入任務資料
            loadTaskData(taskId, editor);

            // 將編輯器實例存儲到全域變數
            window.subtitleEditor = editor;
            
            console.log('[SubtitleEditor] 編輯器初始化完成');
        } catch (error) {
            console.error('[SubtitleEditor] 初始化失敗:', error);
            showEditorError('初始化字幕編輯器失敗: ' + error.message);
        }
    }, 100); // 短暫延遲確保 DOM 和其他腳本都準備好
});

/**
 * 顯示編輯器錯誤
 */
function showEditorError(message) {
    const loadingContainer = document.getElementById('loading-container');
    const errorContainer = document.getElementById('error-container');
    const errorMessage = document.getElementById('error-message');
    const editorContainer = document.getElementById('subtitle-editor-container');
    const toolbar = document.getElementById('editing-toolbar');
    
    if (loadingContainer) loadingContainer.style.display = 'none';
    if (editorContainer) editorContainer.style.display = 'none';
    if (toolbar) toolbar.style.display = 'none';
    
    if (errorContainer && errorMessage) {
        errorMessage.textContent = message;
        errorContainer.style.display = 'block';
    }
}

/**
 * 載入任務資料
 */
async function loadTaskData(taskId, editor) {
    try {
        console.log('[SubtitleEditor] 開始載入任務資料:', taskId);
        
        // 載入字幕資料
        const subtitleResponse = await fetch(`/api/subtitles/${taskId}`);
        if (!subtitleResponse.ok) {
            throw new Error(`載入字幕資料失敗: ${subtitleResponse.status}`);
        }
        
        const subtitleData = await subtitleResponse.json();
        console.log('[SubtitleEditor] 字幕資料已載入:', subtitleData.subtitles?.length, '個項目');
        
        // 儲存原始元資料（儲存時帶回）
        editor.metadata = subtitleData.metadata || null;
        
        // 載入字幕到編輯器
        const loadSuccess = editor.loadSubtitles(subtitleData.subtitles);
        if (!loadSuccess) {
            throw new Error('載入字幕到編輯器失敗');
        }
        
        // 如果有影片 URL，載入影片
        if (subtitleData.metadata && subtitleData.metadata.video_info && subtitleData.metadata.video_info.video_url) {
            console.log('[SubtitleEditor] 發現影片資訊:', {
                url: subtitleData.metadata.video_info.video_url,
                format: subtitleData.metadata.video_info.format,
                size: subtitleData.metadata.video_info.file_size
            });
            
            const videoLoaded = editor.loadVideo(subtitleData.metadata.video_info.video_url);
            if (videoLoaded) {
                console.log('[SubtitleEditor] 影片載入請求已發送');
            } else {
                console.warn('[SubtitleEditor] 影片載入失敗，但字幕編輯器仍可正常使用');
            }
        } else {
            console.warn('[SubtitleEditor] 沒有找到影片資訊，編輯器將在無影片模式下運行');
            console.log('[SubtitleEditor] 元資料:', subtitleData.metadata);
        }
        
        // 儲存任務 ID 到編輯器
        editor.taskId = taskId;
        
        // 確保所有遮罩層都已隱藏
        const loadingContainer = document.getElementById('loading-container');
        const editorContainer = document.getElementById('subtitle-editor-container');
        const toolbar = document.getElementById('editing-toolbar');
        
        if (loadingContainer) {
            loadingContainer.style.display = 'none';
        }
        
        if (editorContainer) {
            editorContainer.style.display = 'flex';
            editorContainer.style.pointerEvents = 'auto';
        }
        
        if (toolbar) {
            toolbar.style.display = 'block';
            toolbar.style.pointerEvents = 'auto';
        }
        
        // 確保全域載入管理器的遮罩都已隱藏
        if (window.globalLoadingManager) {
            window.globalLoadingManager.hideAllLoaders();
        }
        
        console.log('[SubtitleEditor] 字幕編輯器載入完成');
        
        // 觸發載入完成事件
        document.dispatchEvent(new CustomEvent('subtitleEditorLoadComplete', {
            detail: { taskId, editor }
        }));
        
    } catch (error) {
        console.error('[SubtitleEditor] 載入任務資料失敗:', error);
        showEditorError(`載入任務資料失敗: ${error.message}`);
    }
}
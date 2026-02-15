/**
 * 載入狀態和進度提示管理器
 * 提供字幕編輯器載入骨架屏、重新轉錄進度條和檔案下載進度顯示
 */

class LoadingManager {
    constructor(options = {}) {
        this.options = {
            skeletonAnimationDuration: 1500, // 骨架屏動畫持續時間
            progressUpdateInterval: 100, // 進度更新間隔
            autoHideDelay: 3000, // 自動隱藏延遲
            showPercentage: true,
            showETA: true, // 顯示預估完成時間
            ...options
        };
        
        // 狀態管理
        this.activeLoaders = new Map(); // 活躍的載入器
        this.progressTrackers = new Map(); // 進度追蹤器
        
        // DOM 元素
        this.skeletonContainer = null;
        this.progressContainer = null;
        
        this.init();
    }
    
    /**
     * 初始化載入管理器
     */
    init() {
        this.createSkeletonContainer();
        this.createProgressContainer();
        
        console.log('LoadingManager 初始化完成');
    }
    
    /**
     * 創建骨架屏容器
     */
    createSkeletonContainer() {
        const containerHtml = `
            <div id="skeleton-container" class="position-fixed top-0 start-0 w-100 h-100 theme-aware-bg" 
                 style="z-index: 9998; display: none; pointer-events: none;">
                <div class="container-fluid h-100">
                    <!-- 頁首骨架 -->
                    <div class="skeleton-header py-3 mb-4 border-bottom theme-aware-border">
                        <div class="container d-flex justify-content-between align-items-center">
                            <div class="d-flex align-items-center">
                                <div class="skeleton-item skeleton-icon me-2" style="width: 32px; height: 32px;"></div>
                                <div class="skeleton-item skeleton-text" style="width: 120px; height: 28px;"></div>
                            </div>
                            <div class="d-flex gap-2">
                                <div class="skeleton-item skeleton-button" style="width: 80px; height: 38px;"></div>
                                <div class="skeleton-item skeleton-button" style="width: 100px; height: 38px;"></div>
                                <div class="skeleton-item skeleton-button" style="width: 80px; height: 38px;"></div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="row h-100">
                        <!-- 字幕編輯器骨架屏 -->
                        <div id="subtitle-editor-skeleton" class="skeleton-screen" style="display: none;">
                            <!-- 工具欄骨架 -->
                            <div class="row mb-3">
                                <div class="col-12">
                                    <div class="card theme-card">
                                        <div class="card-body py-2">
                                            <div class="d-flex justify-content-between align-items-center">
                                                <div class="d-flex gap-2">
                                                    <div class="skeleton-item skeleton-button" style="width: 60px; height: 32px;"></div>
                                                    <div class="skeleton-item skeleton-button" style="width: 60px; height: 32px;"></div>
                                                    <div class="skeleton-item skeleton-button" style="width: 80px; height: 32px;"></div>
                                                </div>
                                                <div class="skeleton-item skeleton-badge" style="width: 80px; height: 24px;"></div>
                                                <div class="d-flex gap-2">
                                                    <div class="skeleton-item skeleton-button" style="width: 70px; height: 32px;"></div>
                                                    <div class="skeleton-item skeleton-button" style="width: 80px; height: 32px;"></div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="row h-75">
                                <!-- 影片播放器骨架 -->
                                <div class="col-xl-6 col-lg-12 mb-4">
                                    <div class="card h-100 theme-card">
                                        <div class="card-header">
                                            <div class="d-flex justify-content-between align-items-center">
                                                <div class="skeleton-item skeleton-text" style="width: 120px; height: 20px;"></div>
                                                <div class="d-flex gap-2">
                                                    <div class="skeleton-item skeleton-button" style="width: 40px; height: 32px;"></div>
                                                    <div class="skeleton-item skeleton-button" style="width: 40px; height: 32px;"></div>
                                                    <div class="skeleton-item skeleton-button" style="width: 40px; height: 32px;"></div>
                                                </div>
                                            </div>
                                        </div>
                                        <div class="card-body p-0">
                                            <div class="skeleton-video-player">
                                                <div class="skeleton-item skeleton-video" style="height: 300px; background-color: var(--theme-bg-tertiary);"></div>
                                                <div class="skeleton-controls p-3 border-top theme-aware-border">
                                                    <div class="d-flex align-items-center gap-3 mb-2">
                                                        <div class="skeleton-item skeleton-text" style="width: 50px; height: 16px;"></div>
                                                        <div class="flex-grow-1">
                                                            <div class="skeleton-item skeleton-progress-bar" style="height: 8px;"></div>
                                                        </div>
                                                        <div class="skeleton-item skeleton-text" style="width: 50px; height: 16px;"></div>
                                                    </div>
                                                    <div class="d-flex justify-content-between align-items-center">
                                                        <div class="d-flex align-items-center gap-2">
                                                            <div class="skeleton-item skeleton-icon" style="width: 20px; height: 20px;"></div>
                                                            <div class="skeleton-item skeleton-slider" style="width: 100px; height: 8px;"></div>
                                                        </div>
                                                        <div class="d-flex align-items-center gap-2">
                                                            <div class="skeleton-item skeleton-text" style="width: 40px; height: 16px;"></div>
                                                            <div class="skeleton-item skeleton-select" style="width: 80px; height: 32px;"></div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- 字幕列表骨架 -->
                                <div class="col-xl-6 col-lg-12 mb-4">
                                    <div class="card h-100 theme-card">
                                        <div class="card-header">
                                            <div class="d-flex justify-content-between align-items-center">
                                                <div class="d-flex align-items-center gap-2">
                                                    <div class="skeleton-item skeleton-text" style="width: 80px; height: 20px;"></div>
                                                    <div class="skeleton-item skeleton-badge" style="width: 30px; height: 20px;"></div>
                                                </div>
                                                <div class="d-flex align-items-center gap-2">
                                                    <div class="skeleton-item skeleton-search" style="width: 150px; height: 32px;"></div>
                                                    <div class="skeleton-item skeleton-button" style="width: 60px; height: 32px;"></div>
                                                    <div class="skeleton-item skeleton-button" style="width: 60px; height: 32px;"></div>
                                                </div>
                                            </div>
                                        </div>
                                        <div class="card-body p-0">
                                            <div class="skeleton-subtitle-list" style="max-height: 400px; overflow-y: auto;">
                                                ${this.generateSubtitleSkeletonItems(12)}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- 通用載入骨架屏 -->
                        <div id="generic-skeleton" class="skeleton-screen d-flex align-items-center justify-content-center" style="display: none;">
                            <div class="text-center">
                                <div class="skeleton-spinner mb-4">
                                    <div class="spinner-border text-primary" style="width: 3rem; height: 3rem;" role="status">
                                        <span class="visually-hidden">載入中...</span>
                                    </div>
                                </div>
                                <div class="skeleton-item skeleton-text mx-auto mb-2" style="width: 200px; height: 24px;"></div>
                                <div class="skeleton-item skeleton-text mx-auto" style="width: 150px; height: 16px;"></div>
                            </div>
                        </div>
                        
                        <!-- 檔案載入骨架屏 -->
                        <div id="file-loading-skeleton" class="skeleton-screen d-flex align-items-center justify-content-center" style="display: none;">
                            <div class="text-center">
                                <div class="skeleton-file-icon mb-4">
                                    <div class="skeleton-item" style="width: 80px; height: 100px; border-radius: 8px;"></div>
                                </div>
                                <div class="skeleton-item skeleton-text mx-auto mb-2" style="width: 180px; height: 20px;"></div>
                                <div class="skeleton-item skeleton-text mx-auto mb-3" style="width: 120px; height: 16px;"></div>
                                <div class="skeleton-item skeleton-progress-bar mx-auto" style="width: 250px; height: 8px;"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', containerHtml);
        this.skeletonContainer = document.getElementById('skeleton-container');
    }
    
    /**
     * 生成字幕列表骨架項目
     */
    generateSubtitleSkeletonItems(count) {
        let html = '';
        for (let i = 0; i < count; i++) {
            const randomWidth1 = 85 + Math.random() * 15; // 85-100%
            const randomWidth2 = 60 + Math.random() * 25; // 60-85%
            const randomTimeWidth = 70 + Math.random() * 20; // 70-90px
            
            html += `
                <div class="skeleton-subtitle-item list-group-item theme-aware-bg theme-aware-border">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div class="skeleton-item skeleton-text" style="width: ${randomTimeWidth}px; height: 12px;"></div>
                        <div class="d-flex gap-1">
                            <div class="skeleton-item skeleton-button-sm" style="width: 28px; height: 28px;"></div>
                            <div class="skeleton-item skeleton-button-sm" style="width: 28px; height: 28px;"></div>
                            <div class="skeleton-item skeleton-button-sm" style="width: 28px; height: 28px;"></div>
                            <div class="skeleton-item skeleton-button-sm" style="width: 28px; height: 28px;"></div>
                        </div>
                    </div>
                    <div class="skeleton-item skeleton-text mb-1" style="width: ${randomWidth1}%; height: 16px;"></div>
                    <div class="skeleton-item skeleton-text" style="width: ${randomWidth2}%; height: 16px;"></div>
                </div>
            `;
        }
        return html;
    }
    
    /**
     * 創建進度提示容器
     */
    createProgressContainer() {
        const containerHtml = `
            <div id="progress-container" class="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center" 
                 style="z-index: 9999; background: rgba(0,0,0,0.5); display: none; pointer-events: none;">
                
                <!-- 重新轉錄進度 -->
                <div id="retranscribe-progress" class="progress-modal" style="display: none;">
                    <div class="card theme-card" style="min-width: 450px; max-width: 500px;">
                        <div class="card-header bg-primary text-white">
                            <div class="d-flex align-items-center">
                                <div class="spinner-border spinner-border-sm me-2" role="status">
                                    <span class="visually-hidden">處理中...</span>
                                </div>
                                <h5 class="mb-0">重新轉錄進行中</h5>
                            </div>
                        </div>
                        <div class="card-body">
                            <!-- 進度環形指示器 -->
                            <div class="text-center mb-4">
                                <div class="position-relative d-inline-block">
                                    <svg width="80" height="80" class="progress-ring">
                                        <circle cx="40" cy="40" r="35" stroke="var(--theme-bg-tertiary)" stroke-width="6" fill="transparent"/>
                                        <circle id="retranscribe-progress-ring" cx="40" cy="40" r="35" stroke="var(--theme-primary)" 
                                                stroke-width="6" fill="transparent" stroke-linecap="round"
                                                stroke-dasharray="220" stroke-dashoffset="220"
                                                style="transition: stroke-dashoffset 0.3s ease;"/>
                                    </svg>
                                    <div class="position-absolute top-50 start-50 translate-middle">
                                        <div id="retranscribe-percentage" class="h4 mb-0 text-primary fw-bold">0%</div>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- 線性進度條 -->
                            <div class="mb-3">
                                <div class="progress" style="height: 12px;">
                                    <div id="retranscribe-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" 
                                         role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                                    </div>
                                </div>
                            </div>
                            
                            <!-- 狀態資訊 -->
                            <div class="row mb-3">
                                <div class="col-6">
                                    <div class="text-muted small">當前狀態</div>
                                    <div id="retranscribe-status" class="fw-bold text-truncate">正在初始化...</div>
                                </div>
                                <div class="col-6" id="retranscribe-eta-container" style="display: none;">
                                    <div class="text-muted small">預估剩餘時間</div>
                                    <div id="retranscribe-eta" class="fw-bold">計算中...</div>
                                </div>
                            </div>
                            
                            <!-- 處理階段指示器 -->
                            <div class="mb-3">
                                <div class="d-flex justify-content-between small text-muted mb-2">
                                    <span>處理階段</span>
                                    <span id="retranscribe-stage">1/4</span>
                                </div>
                                <div class="progress" style="height: 4px;">
                                    <div id="retranscribe-stage-bar" class="progress-bar bg-info" 
                                         role="progressbar" style="width: 25%"></div>
                                </div>
                                <div class="d-flex justify-content-between mt-1">
                                    <small class="stage-label active" data-stage="1">初始化</small>
                                    <small class="stage-label" data-stage="2">音頻處理</small>
                                    <small class="stage-label" data-stage="3">轉錄中</small>
                                    <small class="stage-label" data-stage="4">完成</small>
                                </div>
                            </div>
                            
                            <!-- 提示訊息 -->
                            <div class="alert alert-info py-2 mb-0">
                                <div class="d-flex align-items-center">
                                    <i class="bi bi-info-circle me-2"></i>
                                    <small>重新轉錄可能需要幾分鐘時間，請保持頁面開啟</small>
                                </div>
                            </div>
                        </div>
                        <div class="card-footer d-flex justify-content-between align-items-center">
                            <div class="text-muted small">
                                <i class="bi bi-clock me-1"></i>
                                <span id="retranscribe-elapsed">00:00</span>
                            </div>
                            <button type="button" class="btn btn-outline-danger btn-sm" id="cancel-retranscribe-progress">
                                <i class="bi bi-x-circle"></i> 取消
                            </button>
                        </div>
                    </div>
                </div>
                
                <!-- 檔案下載進度 -->
                <div id="download-progress" class="progress-modal" style="display: none;">
                    <div class="card theme-card" style="min-width: 420px; max-width: 480px;">
                        <div class="card-header bg-success text-white">
                            <div class="d-flex align-items-center">
                                <i class="bi bi-download me-2"></i>
                                <h5 class="mb-0">檔案下載中</h5>
                            </div>
                        </div>
                        <div class="card-body">
                            <!-- 下載圖示和檔案資訊 -->
                            <div class="text-center mb-4">
                                <div class="download-icon-container mb-3">
                                    <i class="bi bi-file-earmark-arrow-down display-4 text-success download-icon"></i>
                                    <div class="download-animation-overlay"></div>
                                </div>
                                <div id="download-filename" class="fw-bold text-truncate">準備下載...</div>
                                <div id="download-format" class="text-muted small">--</div>
                            </div>
                            
                            <!-- 進度條 -->
                            <div class="mb-3">
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <span class="text-muted small">下載進度</span>
                                    <span id="download-percentage" class="fw-bold text-success">0%</span>
                                </div>
                                <div class="progress" style="height: 10px;">
                                    <div id="download-progress-bar" class="progress-bar bg-success progress-bar-striped" 
                                         role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                                    </div>
                                </div>
                            </div>
                            
                            <!-- 檔案大小和速度資訊 -->
                            <div class="row mb-3">
                                <div class="col-6" id="download-size-container" style="display: none;">
                                    <div class="text-muted small">檔案大小</div>
                                    <div id="download-size" class="fw-bold">-- / --</div>
                                </div>
                                <div class="col-6" id="download-speed-container" style="display: none;">
                                    <div class="text-muted small">下載速度</div>
                                    <div id="download-speed" class="fw-bold">--</div>
                                </div>
                            </div>
                            
                            <!-- 狀態訊息 -->
                            <div class="d-flex align-items-center">
                                <div class="spinner-border spinner-border-sm text-success me-2" role="status">
                                    <span class="visually-hidden">下載中...</span>
                                </div>
                                <small id="download-status-message" class="text-muted">正在準備檔案...</small>
                            </div>
                        </div>
                        <div class="card-footer d-flex justify-content-between align-items-center">
                            <div class="text-muted small">
                                <i class="bi bi-clock me-1"></i>
                                <span id="download-elapsed">00:00</span>
                            </div>
                            <button type="button" class="btn btn-outline-danger btn-sm" id="cancel-download-progress">
                                <i class="bi bi-x-circle"></i> 取消
                            </button>
                        </div>
                    </div>
                </div>
                
                <!-- 通用進度 -->
                <div id="generic-progress" class="progress-modal" style="display: none;">
                    <div class="card theme-card" style="min-width: 380px; max-width: 450px;">
                        <div class="card-body text-center">
                            <!-- 載入動畫 -->
                            <div class="mb-4">
                                <div class="loading-animation-container">
                                    <div class="spinner-border text-primary" style="width: 3rem; height: 3rem;" role="status">
                                        <span class="visually-hidden">載入中...</span>
                                    </div>
                                    <div class="loading-dots mt-2">
                                        <span class="dot"></span>
                                        <span class="dot"></span>
                                        <span class="dot"></span>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- 標題和訊息 -->
                            <div id="generic-progress-title" class="h5 mb-2 text-primary">處理中...</div>
                            <div id="generic-progress-message" class="text-muted mb-3">請稍候</div>
                            
                            <!-- 進度條（可選） -->
                            <div class="mt-3" id="generic-progress-bar-container" style="display: none;">
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <span class="text-muted small">進度</span>
                                    <span id="generic-progress-percentage" class="fw-bold">0%</span>
                                </div>
                                <div class="progress" style="height: 8px;">
                                    <div id="generic-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated" 
                                         role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                                    </div>
                                </div>
                            </div>
                            
                            <!-- 額外資訊 -->
                            <div class="mt-3" id="generic-progress-info" style="display: none;">
                                <div class="text-muted small" id="generic-progress-details">--</div>
                            </div>
                        </div>
                        <div class="card-footer text-center" id="generic-progress-footer" style="display: none;">
                            <button type="button" class="btn btn-outline-secondary btn-sm" id="cancel-generic-progress">
                                <i class="bi bi-x-circle"></i> 取消
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', containerHtml);
        this.progressContainer = document.getElementById('progress-container');
        
        // 綁定取消按鈕
        document.getElementById('cancel-retranscribe-progress').addEventListener('click', () => {
            this.cancelProgress('retranscribe');
        });
    }
    
    /**
     * 顯示字幕編輯器載入骨架屏
     */
    showSubtitleEditorSkeleton() {
        const loaderId = 'subtitle-editor-skeleton';
        
        if (this.activeLoaders.has(loaderId)) {
            return this.activeLoaders.get(loaderId);
        }
        
        const loader = {
            id: loaderId,
            type: 'skeleton',
            startTime: Date.now()
        };
        
        this.activeLoaders.set(loaderId, loader);
        
        // 顯示骨架屏
        this.skeletonContainer.style.display = 'block';
        this.skeletonContainer.style.pointerEvents = 'auto';
        document.getElementById('subtitle-editor-skeleton').style.display = 'block';
        
        // 添加 CSS 動畫
        this.addSkeletonAnimation();
        
        return loader;
    }
    
    /**
     * 隱藏字幕編輯器骨架屏
     */
    hideSubtitleEditorSkeleton() {
        const loaderId = 'subtitle-editor-skeleton';
        
        if (!this.activeLoaders.has(loaderId)) {
            return;
        }
        
        this.activeLoaders.delete(loaderId);
        
        // 淡出動畫
        const skeletonElement = document.getElementById('subtitle-editor-skeleton');
        skeletonElement.style.opacity = '0';
        skeletonElement.style.transition = 'opacity 0.3s ease-out';
        
        setTimeout(() => {
            this.skeletonContainer.style.display = 'none';
            this.skeletonContainer.style.pointerEvents = 'none';
            skeletonElement.style.display = 'none';
            skeletonElement.style.opacity = '1';
            skeletonElement.style.transition = '';
        }, 300);
    }
    
    /**
     * 顯示檔案載入骨架屏
     */
    showFileLoadingSkeleton(filename = '載入檔案中...') {
        const loaderId = 'file-loading-skeleton';
        
        if (this.activeLoaders.has(loaderId)) {
            return this.activeLoaders.get(loaderId);
        }
        
        const loader = {
            id: loaderId,
            type: 'skeleton',
            startTime: Date.now(),
            filename
        };
        
        this.activeLoaders.set(loaderId, loader);
        
        // 顯示骨架屏
        this.skeletonContainer.style.display = 'block';
        this.skeletonContainer.style.pointerEvents = 'auto';
        document.getElementById('file-loading-skeleton').style.display = 'block';
        
        // 更新檔案名稱顯示
        const filenameElements = document.querySelectorAll('#file-loading-skeleton .skeleton-text');
        if (filenameElements.length > 0) {
            filenameElements[0].setAttribute('data-filename', filename);
        }
        
        // 添加 CSS 動畫
        this.addSkeletonAnimation();
        
        return loader;
    }
    
    /**
     * 隱藏檔案載入骨架屏
     */
    hideFileLoadingSkeleton() {
        const loaderId = 'file-loading-skeleton';
        
        if (!this.activeLoaders.has(loaderId)) {
            return;
        }
        
        this.activeLoaders.delete(loaderId);
        
        // 淡出動畫
        const skeletonElement = document.getElementById('file-loading-skeleton');
        skeletonElement.style.opacity = '0';
        skeletonElement.style.transition = 'opacity 0.3s ease-out';
        
        setTimeout(() => {
            if (this.activeLoaders.size === 0) {
                this.skeletonContainer.style.display = 'none';
                this.skeletonContainer.style.pointerEvents = 'none';
            }
            skeletonElement.style.display = 'none';
            skeletonElement.style.opacity = '1';
            skeletonElement.style.transition = '';
        }, 300);
    }
    
    /**
     * 顯示通用骨架屏
     */
    showGenericSkeleton(message = '載入中...') {
        const loaderId = 'generic-skeleton';
        
        if (this.activeLoaders.has(loaderId)) {
            return this.activeLoaders.get(loaderId);
        }
        
        const loader = {
            id: loaderId,
            type: 'skeleton',
            startTime: Date.now(),
            message
        };
        
        this.activeLoaders.set(loaderId, loader);
        
        // 顯示骨架屏
        this.skeletonContainer.style.display = 'block';
        this.skeletonContainer.style.pointerEvents = 'auto';
        document.getElementById('generic-skeleton').style.display = 'block';
        
        // 更新訊息顯示
        const messageElements = document.querySelectorAll('#generic-skeleton .skeleton-text');
        if (messageElements.length > 0) {
            messageElements[0].setAttribute('data-message', message);
        }
        
        // 添加 CSS 動畫
        this.addSkeletonAnimation();
        
        return loader;
    }
    
    /**
     * 隱藏通用骨架屏
     */
    hideGenericSkeleton() {
        const loaderId = 'generic-skeleton';
        
        if (!this.activeLoaders.has(loaderId)) {
            return;
        }
        
        this.activeLoaders.delete(loaderId);
        
        // 淡出動畫
        const skeletonElement = document.getElementById('generic-skeleton');
        skeletonElement.style.opacity = '0';
        skeletonElement.style.transition = 'opacity 0.3s ease-out';
        
        setTimeout(() => {
            if (this.activeLoaders.size === 0) {
                this.skeletonContainer.style.display = 'none';
                this.skeletonContainer.style.pointerEvents = 'none';
            }
            skeletonElement.style.display = 'none';
            skeletonElement.style.opacity = '1';
            skeletonElement.style.transition = '';
        }, 300);
    }
    
    /**
     * 顯示重新轉錄進度
     */
    showRetranscribeProgress(taskInfo = {}) {
        const progressId = 'retranscribe';
        
        const tracker = {
            id: progressId,
            type: 'retranscribe',
            startTime: Date.now(),
            progress: 0,
            status: '正在初始化...',
            taskInfo
        };
        
        this.progressTrackers.set(progressId, tracker);
        
        // 顯示進度模態框
        this.progressContainer.style.display = 'flex';
        this.progressContainer.style.pointerEvents = 'auto';
        document.getElementById('retranscribe-progress').style.display = 'block';
        
        // 初始化顯示
        this.updateRetranscribeProgress(0, '正在初始化...');
        
        return tracker;
    }
    
    /**
     * 更新重新轉錄進度
     */
    updateRetranscribeProgress(percentage, status, estimatedTime = null, stage = null) {
        const progressId = 'retranscribe';
        const tracker = this.progressTrackers.get(progressId);
        
        if (!tracker) return;
        
        tracker.progress = percentage;
        tracker.status = status;
        tracker.lastUpdate = Date.now();
        
        // 更新百分比顯示
        const percentageElement = document.getElementById('retranscribe-percentage');
        if (percentageElement) {
            percentageElement.textContent = `${Math.round(percentage)}%`;
        }
        
        // 更新線性進度條
        const progressBar = document.getElementById('retranscribe-progress-bar');
        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
        }
        
        // 更新環形進度條
        const progressRing = document.getElementById('retranscribe-progress-ring');
        if (progressRing) {
            const circumference = 2 * Math.PI * 35; // r=35
            const offset = circumference - (percentage / 100) * circumference;
            progressRing.style.strokeDashoffset = offset;
        }
        
        // 更新狀態文字
        const statusElement = document.getElementById('retranscribe-status');
        if (statusElement) {
            statusElement.textContent = status;
        }
        
        // 更新處理階段
        if (stage) {
            this.updateRetranscribeStage(stage);
        }
        
        // 更新預估時間
        if (this.options.showETA && percentage > 0) {
            const eta = this.calculateETA(tracker, percentage);
            if (eta) {
                const etaContainer = document.getElementById('retranscribe-eta-container');
                const etaElement = document.getElementById('retranscribe-eta');
                if (etaContainer && etaElement) {
                    etaContainer.style.display = 'block';
                    etaElement.textContent = eta;
                }
            }
        }
        
        // 更新經過時間
        this.updateElapsedTime('retranscribe-elapsed', tracker.startTime);
    }
    
    /**
     * 更新重新轉錄處理階段
     */
    updateRetranscribeStage(stage) {
        const stageElement = document.getElementById('retranscribe-stage');
        const stageBar = document.getElementById('retranscribe-stage-bar');
        const stageLabels = document.querySelectorAll('.stage-label');
        
        if (stageElement) {
            stageElement.textContent = `${stage}/4`;
        }
        
        if (stageBar) {
            const stagePercentage = (stage / 4) * 100;
            stageBar.style.width = `${stagePercentage}%`;
        }
        
        // 更新階段標籤狀態
        stageLabels.forEach((label, index) => {
            label.classList.remove('active', 'completed');
            if (index + 1 < stage) {
                label.classList.add('completed');
            } else if (index + 1 === stage) {
                label.classList.add('active');
            }
        });
    }
    
    /**
     * 隱藏重新轉錄進度
     */
    hideRetranscribeProgress() {
        const progressId = 'retranscribe';
        
        if (!this.progressTrackers.has(progressId)) {
            return;
        }
        
        this.progressTrackers.delete(progressId);
        
        // 隱藏進度模態框
        document.getElementById('retranscribe-progress').style.display = 'none';
        
        // 檢查是否還有其他進度
        if (this.progressTrackers.size === 0) {
            this.progressContainer.style.display = 'none';
            this.progressContainer.style.pointerEvents = 'none';
        }
    }
    
    /**
     * 顯示檔案下載進度
     */
    showDownloadProgress(filename, fileSize = null) {
        const progressId = 'download';
        
        const tracker = {
            id: progressId,
            type: 'download',
            startTime: Date.now(),
            progress: 0,
            filename,
            fileSize,
            downloadedSize: 0
        };
        
        this.progressTrackers.set(progressId, tracker);
        
        // 顯示進度模態框
        this.progressContainer.style.display = 'flex';
        this.progressContainer.style.pointerEvents = 'auto';
        document.getElementById('download-progress').style.display = 'block';
        
        // 初始化顯示
        document.getElementById('download-filename').textContent = filename;
        
        if (fileSize) {
            document.getElementById('download-size-container').style.display = 'block';
            document.getElementById('download-size').textContent = `0 / ${this.formatFileSize(fileSize)}`;
        }
        
        return tracker;
    }
    
    /**
     * 更新檔案下載進度
     */
    updateDownloadProgress(percentage, downloadedSize = null, downloadSpeed = null) {
        const progressId = 'download';
        const tracker = this.progressTrackers.get(progressId);
        
        if (!tracker) return;
        
        tracker.progress = percentage;
        tracker.downloadedSize = downloadedSize || tracker.downloadedSize;
        tracker.lastUpdate = Date.now();
        
        // 更新百分比顯示
        const percentageElement = document.getElementById('download-percentage');
        if (percentageElement) {
            percentageElement.textContent = `${Math.round(percentage)}%`;
        }
        
        // 更新進度條
        const progressBar = document.getElementById('download-progress-bar');
        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
            
            // 根據進度改變進度條動畫
            if (percentage >= 100) {
                progressBar.classList.remove('progress-bar-striped');
                progressBar.classList.add('bg-success');
            }
        }
        
        // 更新檔案大小顯示
        if (tracker.fileSize) {
            const sizeContainer = document.getElementById('download-size-container');
            const sizeElement = document.getElementById('download-size');
            
            if (sizeContainer && sizeElement) {
                sizeContainer.style.display = 'block';
                const downloaded = downloadedSize || (tracker.fileSize * percentage / 100);
                const sizeText = `${this.formatFileSize(downloaded)} / ${this.formatFileSize(tracker.fileSize)}`;
                sizeElement.textContent = sizeText;
            }
        }
        
        // 更新下載速度
        if (downloadSpeed) {
            const speedContainer = document.getElementById('download-speed-container');
            const speedElement = document.getElementById('download-speed');
            
            if (speedContainer && speedElement) {
                speedContainer.style.display = 'block';
                speedElement.textContent = `${this.formatFileSize(downloadSpeed)}/s`;
            }
        }
        
        // 更新狀態訊息
        const statusMessage = document.getElementById('download-status-message');
        if (statusMessage) {
            if (percentage >= 100) {
                statusMessage.textContent = '下載完成！';
            } else if (percentage >= 80) {
                statusMessage.textContent = '即將完成...';
            } else if (percentage >= 50) {
                statusMessage.textContent = '下載進行中...';
            } else {
                statusMessage.textContent = '正在下載檔案...';
            }
        }
        
        // 更新下載圖示動畫
        this.updateDownloadAnimation(percentage);
        
        // 更新經過時間
        this.updateElapsedTime('download-elapsed', tracker.startTime);
    }
    
    /**
     * 更新下載動畫
     */
    updateDownloadAnimation(percentage) {
        const downloadIcon = document.querySelector('.download-icon');
        const animationOverlay = document.querySelector('.download-animation-overlay');
        
        if (downloadIcon) {
            // 根據進度改變圖示
            if (percentage >= 100) {
                downloadIcon.className = 'bi bi-check-circle-fill display-4 text-success download-icon';
            } else if (percentage >= 50) {
                downloadIcon.className = 'bi bi-arrow-down-circle display-4 text-success download-icon';
            }
        }
        
        if (animationOverlay) {
            animationOverlay.style.height = `${100 - percentage}%`;
        }
    }
    
    /**
     * 隱藏檔案下載進度
     */
    hideDownloadProgress() {
        const progressId = 'download';
        
        if (!this.progressTrackers.has(progressId)) {
            return;
        }
        
        this.progressTrackers.delete(progressId);
        
        // 隱藏進度模態框
        document.getElementById('download-progress').style.display = 'none';
        
        // 檢查是否還有其他進度
        if (this.progressTrackers.size === 0) {
            this.progressContainer.style.display = 'none';
            this.progressContainer.style.pointerEvents = 'none';
        }
    }
    
    /**
     * 顯示通用進度
     */
    showGenericProgress(title, message, showProgressBar = false) {
        const progressId = 'generic';
        
        const tracker = {
            id: progressId,
            type: 'generic',
            startTime: Date.now(),
            progress: 0,
            title,
            message,
            showProgressBar
        };
        
        this.progressTrackers.set(progressId, tracker);
        
        // 顯示進度模態框
        this.progressContainer.style.display = 'flex';
        this.progressContainer.style.pointerEvents = 'auto';
        document.getElementById('generic-progress').style.display = 'block';
        
        // 初始化顯示
        document.getElementById('generic-progress-title').textContent = title;
        document.getElementById('generic-progress-message').textContent = message;
        
        if (showProgressBar) {
            document.getElementById('generic-progress-bar-container').style.display = 'block';
        }
        
        return tracker;
    }
    
    /**
     * 更新通用進度
     */
    updateGenericProgress(percentage, message, details = null) {
        const progressId = 'generic';
        const tracker = this.progressTrackers.get(progressId);
        
        if (!tracker) return;
        
        tracker.progress = percentage;
        tracker.message = message;
        tracker.lastUpdate = Date.now();
        
        // 更新訊息
        const messageElement = document.getElementById('generic-progress-message');
        if (messageElement) {
            messageElement.textContent = message;
        }
        
        // 更新進度條（如果啟用）
        if (tracker.showProgressBar) {
            const progressBar = document.getElementById('generic-progress-bar');
            const percentageElement = document.getElementById('generic-progress-percentage');
            
            if (progressBar) {
                progressBar.style.width = `${percentage}%`;
                progressBar.setAttribute('aria-valuenow', percentage);
            }
            
            if (percentageElement) {
                percentageElement.textContent = `${Math.round(percentage)}%`;
            }
        }
        
        // 更新詳細資訊
        if (details) {
            const infoContainer = document.getElementById('generic-progress-info');
            const detailsElement = document.getElementById('generic-progress-details');
            
            if (infoContainer && detailsElement) {
                infoContainer.style.display = 'block';
                detailsElement.textContent = details;
            }
        }
    }
    
    /**
     * 更新經過時間顯示
     */
    updateElapsedTime(elementId, startTime) {
        const element = document.getElementById(elementId);
        if (!element || !startTime) return;
        
        const elapsed = Date.now() - startTime;
        const minutes = Math.floor(elapsed / 60000);
        const seconds = Math.floor((elapsed % 60000) / 1000);
        
        element.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }
    
    /**
     * 隱藏通用進度
     */
    hideGenericProgress() {
        const progressId = 'generic';
        
        if (!this.progressTrackers.has(progressId)) {
            return;
        }
        
        this.progressTrackers.delete(progressId);
        
        // 隱藏進度模態框
        document.getElementById('generic-progress').style.display = 'none';
        
        // 檢查是否還有其他進度
        if (this.progressTrackers.size === 0) {
            this.progressContainer.style.display = 'none';
            this.progressContainer.style.pointerEvents = 'none';
        }
    }
    
    /**
     * 取消進度
     */
    cancelProgress(progressId) {
        const tracker = this.progressTrackers.get(progressId);
        if (!tracker) return;
        
        // 觸發取消事件
        const event = new CustomEvent('progressCancelled', {
            detail: { progressId, tracker }
        });
        document.dispatchEvent(event);
        
        // 隱藏對應的進度
        switch (progressId) {
            case 'retranscribe':
                this.hideRetranscribeProgress();
                break;
            case 'download':
                this.hideDownloadProgress();
                break;
            case 'generic':
                this.hideGenericProgress();
                break;
        }
    }
    
    /**
     * 添加骨架屏動畫
     */
    addSkeletonAnimation() {
        if (document.getElementById('skeleton-animation-style')) {
            return;
        }
        
        const style = document.createElement('style');
        style.id = 'skeleton-animation-style';
        style.textContent = `
            /* 骨架屏基礎樣式 */
            .skeleton-item {
                background: linear-gradient(90deg, 
                    var(--theme-bg-tertiary) 25%, 
                    var(--theme-bg-accent) 50%, 
                    var(--theme-bg-tertiary) 75%);
                background-size: 200% 100%;
                animation: skeleton-loading ${this.options.skeletonAnimationDuration}ms ease-in-out infinite;
                border-radius: var(--theme-border-radius-sm);
                position: relative;
                overflow: hidden;
            }
            
            /* 深色模式下的骨架屏 */
            [data-bs-theme="dark"] .skeleton-item {
                background: linear-gradient(90deg, 
                    var(--theme-bg-secondary) 25%, 
                    var(--theme-bg-tertiary) 50%, 
                    var(--theme-bg-secondary) 75%);
                background-size: 200% 100%;
            }
            
            @keyframes skeleton-loading {
                0% {
                    background-position: 200% 0;
                }
                100% {
                    background-position: -200% 0;
                }
            }
            
            /* 骨架屏元素變體 */
            .skeleton-video {
                background-color: var(--theme-bg-tertiary);
                border-radius: var(--theme-border-radius-lg);
                position: relative;
            }
            
            .skeleton-video::before {
                content: '';
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background-color: var(--theme-bg-accent);
                opacity: 0.7;
            }
            
            .skeleton-video::after {
                content: '▶';
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-45%, -50%);
                font-size: 24px;
                color: var(--theme-text-muted);
                opacity: 0.5;
            }
            
            .skeleton-button {
                border-radius: var(--theme-border-radius);
            }
            
            .skeleton-button-sm {
                border-radius: var(--theme-border-radius-sm);
            }
            
            .skeleton-icon {
                border-radius: 50%;
            }
            
            .skeleton-progress-bar {
                border-radius: 10px;
            }
            
            .skeleton-slider {
                border-radius: 10px;
            }
            
            .skeleton-text {
                border-radius: var(--theme-border-radius-sm);
            }
            
            .skeleton-badge {
                border-radius: 12px;
            }
            
            .skeleton-search {
                border-radius: var(--theme-border-radius);
                border: 1px solid var(--theme-border-primary);
            }
            
            .skeleton-select {
                border-radius: var(--theme-border-radius);
                border: 1px solid var(--theme-border-primary);
            }
            
            /* 骨架屏容器樣式 */
            .skeleton-screen {
                opacity: 0;
                animation: skeleton-fade-in 0.3s ease-out forwards;
            }
            
            @keyframes skeleton-fade-in {
                from {
                    opacity: 0;
                    transform: translateY(10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            .skeleton-subtitle-item {
                transition: background-color 0.2s ease;
                border-color: var(--theme-border-primary);
            }
            
            .skeleton-subtitle-item:hover {
                background-color: var(--theme-bg-accent);
            }
            
            /* 骨架屏頁首樣式 */
            .skeleton-header {
                background-color: var(--theme-navbar-bg);
                border-color: var(--theme-navbar-border);
            }
            
            /* 脈衝動畫變體 */
            .skeleton-pulse {
                animation: skeleton-pulse 2s ease-in-out infinite;
            }
            
            @keyframes skeleton-pulse {
                0%, 100% {
                    opacity: 1;
                }
                50% {
                    opacity: 0.6;
                }
            }
            
            /* 波浪動畫變體 */
            .skeleton-wave {
                position: relative;
                overflow: hidden;
            }
            
            .skeleton-wave::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, 
                    transparent, 
                    rgba(255, 255, 255, 0.4), 
                    transparent);
                animation: skeleton-wave-animation 2s infinite;
            }
            
            [data-bs-theme="dark"] .skeleton-wave::before {
                background: linear-gradient(90deg, 
                    transparent, 
                    rgba(255, 255, 255, 0.1), 
                    transparent);
            }
            
            @keyframes skeleton-wave-animation {
                0% {
                    left: -100%;
                }
                100% {
                    left: 100%;
                }
            }
            
            /* 減少動畫偏好支援 */
            @media (prefers-reduced-motion: reduce) {
                .skeleton-item {
                    animation: none;
                    background: var(--theme-bg-tertiary);
                }
                
                .skeleton-screen {
                    animation: none;
                    opacity: 1;
                    transform: none;
                }
                
                .skeleton-pulse {
                    animation: none;
                }
                
                .skeleton-wave::before {
                    animation: none;
                    display: none;
                }
            }
            
            /* 高對比度模式支援 */
            @media (prefers-contrast: high) {
                .skeleton-item {
                    border: 2px solid var(--theme-border-primary);
                    background: var(--theme-bg-secondary);
                }
                
                .skeleton-video {
                    border: 3px solid var(--theme-border-primary);
                }
            }
            
            /* 進度指示器增強樣式 */
            .progress-ring {
                transform: rotate(-90deg);
            }
            
            .progress-ring circle {
                transition: stroke-dashoffset 0.3s ease;
            }
            
            /* 處理階段指示器 */
            .stage-label {
                color: var(--theme-text-muted);
                transition: color 0.3s ease;
                font-size: 0.75rem;
            }
            
            .stage-label.active {
                color: var(--theme-primary);
                font-weight: 600;
            }
            
            .stage-label.completed {
                color: var(--theme-success);
            }
            
            .stage-label.completed::before {
                content: '✓ ';
                font-weight: bold;
            }
            
            /* 下載動畫 */
            .download-icon-container {
                position: relative;
                display: inline-block;
            }
            
            .download-animation-overlay {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                background: linear-gradient(to bottom, 
                    var(--theme-bg-primary) 0%, 
                    var(--theme-bg-primary) 50%, 
                    transparent 50%);
                height: 100%;
                transition: height 0.3s ease;
                pointer-events: none;
            }
            
            .download-icon {
                transition: all 0.3s ease;
            }
            
            /* 載入點動畫 */
            .loading-dots {
                display: flex;
                justify-content: center;
                gap: 4px;
            }
            
            .loading-dots .dot {
                width: 6px;
                height: 6px;
                border-radius: 50%;
                background-color: var(--theme-primary);
                animation: loading-dots-bounce 1.4s ease-in-out infinite both;
            }
            
            .loading-dots .dot:nth-child(1) { animation-delay: -0.32s; }
            .loading-dots .dot:nth-child(2) { animation-delay: -0.16s; }
            .loading-dots .dot:nth-child(3) { animation-delay: 0s; }
            
            @keyframes loading-dots-bounce {
                0%, 80%, 100% {
                    transform: scale(0.8);
                    opacity: 0.5;
                }
                40% {
                    transform: scale(1);
                    opacity: 1;
                }
            }
            
            /* 進度模態框動畫 */
            .progress-modal {
                animation: progress-modal-fade-in 0.3s ease-out;
            }
            
            @keyframes progress-modal-fade-in {
                from {
                    opacity: 0;
                    transform: scale(0.9) translateY(-20px);
                }
                to {
                    opacity: 1;
                    transform: scale(1) translateY(0);
                }
            }
            
            /* 進度條增強動畫 */
            .progress-bar-enhanced {
                position: relative;
                overflow: hidden;
            }
            
            .progress-bar-enhanced::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, 
                    transparent, 
                    rgba(255, 255, 255, 0.3), 
                    transparent);
                animation: progress-shine 2s infinite;
            }
            
            @keyframes progress-shine {
                0% { left: -100%; }
                100% { left: 100%; }
            }
            
            /* 成功狀態動畫 */
            .success-pulse {
                animation: success-pulse 0.6s ease-out;
            }
            
            @keyframes success-pulse {
                0% {
                    transform: scale(1);
                }
                50% {
                    transform: scale(1.1);
                }
                100% {
                    transform: scale(1);
                }
            }
            
            /* 錯誤狀態動畫 */
            .error-shake {
                animation: error-shake 0.5s ease-in-out;
            }
            
            @keyframes error-shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-5px); }
                75% { transform: translateX(5px); }
            }
            
            /* 響應式調整 */
            @media (max-width: 576px) {
                .progress-modal .card {
                    min-width: 300px !important;
                    max-width: 90vw !important;
                }
                
                .progress-ring {
                    width: 60px;
                    height: 60px;
                }
                
                .progress-ring circle {
                    r: 25;
                    cx: 30;
                    cy: 30;
                }
                
                .stage-label {
                    font-size: 0.65rem;
                }
            }
        `;
        
        document.head.appendChild(style);
    }
    
    /**
     * 計算預估完成時間
     */
    calculateETA(tracker, currentProgress) {
        if (!tracker.startTime || currentProgress <= 0) {
            return null;
        }
        
        const elapsed = Date.now() - tracker.startTime;
        const rate = currentProgress / elapsed; // 進度/毫秒
        const remaining = (100 - currentProgress) / rate;
        
        if (remaining < 60000) { // 小於1分鐘
            return `約 ${Math.round(remaining / 1000)} 秒`;
        } else if (remaining < 3600000) { // 小於1小時
            return `約 ${Math.round(remaining / 60000)} 分鐘`;
        } else {
            return `約 ${Math.round(remaining / 3600000)} 小時`;
        }
    }
    
    /**
     * 格式化檔案大小
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    /**
     * 獲取載入狀態
     */
    getLoadingState() {
        return {
            activeLoaders: Array.from(this.activeLoaders.keys()),
            progressTrackers: Array.from(this.progressTrackers.keys()),
            totalActiveOperations: this.activeLoaders.size + this.progressTrackers.size
        };
    }
    
    /**
     * 隱藏所有載入指示器
     */
    hideAllLoaders() {
        // 隱藏所有骨架屏
        this.activeLoaders.forEach((loader, id) => {
            if (loader.type === 'skeleton') {
                if (id === 'subtitle-editor-skeleton') {
                    this.hideSubtitleEditorSkeleton();
                }
            }
        });
        
        // 隱藏所有進度指示器
        this.progressTrackers.forEach((tracker, id) => {
            switch (id) {
                case 'retranscribe':
                    this.hideRetranscribeProgress();
                    break;
                case 'download':
                    this.hideDownloadProgress();
                    break;
                case 'generic':
                    this.hideGenericProgress();
                    break;
            }
        });
    }
    
    /**
     * 顯示載入狀態提示
     */
    showLoadingToast(message, duration = 3000) {
        // 創建 Toast 容器（如果不存在）
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = '1055';
            document.body.appendChild(toastContainer);
        }
        
        // 創建載入 Toast
        const toastId = `loading-toast-${Date.now()}`;
        const toastHtml = `
            <div class="toast" id="${toastId}" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="toast-header">
                    <div class="spinner-border spinner-border-sm text-primary me-2" role="status">
                        <span class="visually-hidden">載入中...</span>
                    </div>
                    <strong class="me-auto">載入中</strong>
                    <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
                <div class="toast-body">
                    ${message}
                </div>
            </div>
        `;
        
        toastContainer.insertAdjacentHTML('beforeend', toastHtml);
        
        const toastElement = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastElement, {
            autohide: true,
            delay: duration
        });
        
        toast.show();
        
        // 自動清理
        setTimeout(() => {
            if (toastElement) {
                toastElement.remove();
            }
        }, duration + 1000);
        
        return toastId;
    }
    
    /**
     * 隱藏載入狀態提示
     */
    hideLoadingToast(toastId) {
        const toastElement = document.getElementById(toastId);
        if (toastElement) {
            const toast = bootstrap.Toast.getInstance(toastElement);
            if (toast) {
                toast.hide();
            }
        }
    }
    
    /**
     * 顯示成功完成動畫
     */
    showSuccessAnimation(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.classList.add('success-pulse');
            setTimeout(() => {
                element.classList.remove('success-pulse');
            }, 600);
        }
    }
    
    /**
     * 顯示錯誤動畫
     */
    showErrorAnimation(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.classList.add('error-shake');
            setTimeout(() => {
                element.classList.remove('error-shake');
            }, 500);
        }
    }
    
    /**
     * 創建內聯載入指示器
     */
    createInlineLoader(containerId, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return null;
        
        const loaderOptions = {
            size: 'sm',
            message: '載入中...',
            showSpinner: true,
            showMessage: true,
            ...options
        };
        
        const loaderId = `inline-loader-${Date.now()}`;
        const sizeClass = loaderOptions.size === 'lg' ? '' : 'spinner-border-sm';
        
        const loaderHtml = `
            <div id="${loaderId}" class="inline-loader text-center py-3">
                ${loaderOptions.showSpinner ? `
                    <div class="spinner-border ${sizeClass} text-primary mb-2" role="status">
                        <span class="visually-hidden">載入中...</span>
                    </div>
                ` : ''}
                ${loaderOptions.showMessage ? `
                    <div class="loader-message text-muted">${loaderOptions.message}</div>
                ` : ''}
            </div>
        `;
        
        container.innerHTML = loaderHtml;
        return loaderId;
    }
    
    /**
     * 移除內聯載入指示器
     */
    removeInlineLoader(loaderId) {
        const loader = document.getElementById(loaderId);
        if (loader) {
            loader.remove();
        }
    }
    
    /**
     * 更新內聯載入指示器訊息
     */
    updateInlineLoader(loaderId, message) {
        const loader = document.getElementById(loaderId);
        if (loader) {
            const messageElement = loader.querySelector('.loader-message');
            if (messageElement) {
                messageElement.textContent = message;
            }
        }
    }
    
    /**
     * 獲取所有活躍的載入狀態
     */
    getAllActiveStates() {
        return {
            skeletonLoaders: Array.from(this.activeLoaders.entries()).map(([id, loader]) => ({
                id,
                type: loader.type,
                startTime: loader.startTime,
                duration: Date.now() - loader.startTime
            })),
            progressTrackers: Array.from(this.progressTrackers.entries()).map(([id, tracker]) => ({
                id,
                type: tracker.type,
                progress: tracker.progress,
                startTime: tracker.startTime,
                duration: Date.now() - tracker.startTime,
                status: tracker.status || tracker.message
            }))
        };
    }
    
    /**
     * 檢查是否有活躍的載入狀態
     */
    hasActiveLoading() {
        return this.activeLoaders.size > 0 || this.progressTrackers.size > 0;
    }
    
    /**
     * 清理資源
     */
    destroy() {
        // 隱藏所有載入器
        this.hideAllLoaders();
        
        // 清理狀態
        this.activeLoaders.clear();
        this.progressTrackers.clear();
        
        // 移除 DOM 元素
        if (this.skeletonContainer) {
            this.skeletonContainer.remove();
        }
        
        if (this.progressContainer) {
            this.progressContainer.remove();
        }
        
        // 移除樣式
        const style = document.getElementById('skeleton-animation-style');
        if (style) {
            style.remove();
        }
        
        // 清理 Toast 容器
        const toastContainer = document.getElementById('toast-container');
        if (toastContainer && toastContainer.children.length === 0) {
            toastContainer.remove();
        }
        
        console.log('LoadingManager 已銷毀');
    }
}

// 導出類別
window.LoadingManager = LoadingManager;

// 創建全域實例
window.globalLoadingManager = new LoadingManager();
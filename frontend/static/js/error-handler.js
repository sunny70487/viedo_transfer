/**
 * 全面的錯誤處理機制
 * 提供網路錯誤重試、離線提示、檔案載入失敗處理和編輯衝突樂觀鎖定
 */

class ErrorHandler {
    constructor(options = {}) {
        this.options = {
            maxRetries: 3,
            retryDelay: 1000, // 基礎重試延遲（毫秒）
            retryBackoff: 2, // 退避倍數
            offlineCheckInterval: 5000, // 離線檢查間隔
            conflictRetryDelay: 2000, // 衝突重試延遲
            showToasts: true,
            logErrors: true,
            ...options
        };
        
        // 狀態管理
        this.isOnline = navigator.onLine;
        this.retryQueue = new Map(); // 重試隊列
        this.conflictLocks = new Map(); // 樂觀鎖定
        this.errorHistory = []; // 錯誤歷史
        this.offlineQueue = []; // 離線操作隊列
        
        // DOM 元素
        this.offlineIndicator = null;
        this.errorToastContainer = null;
        
        this.init();
    }
    
    /**
     * 初始化錯誤處理器
     */
    init() {
        this.createOfflineIndicator();
        this.createErrorToastContainer();
        this.bindNetworkEvents();
        this.startOfflineCheck();
        
        // 全域錯誤捕獲
        this.setupGlobalErrorHandling();
        
        console.log('ErrorHandler 初始化完成');
    }
    
    /**
     * 創建離線指示器
     */
    createOfflineIndicator() {
        const indicatorHtml = `
            <div id="offline-indicator" class="alert alert-warning position-fixed top-0 start-50 translate-middle-x" 
                 style="z-index: 9999; display: none; margin-top: 20px;">
                <div class="d-flex align-items-center">
                    <i class="bi bi-wifi-off me-2"></i>
                    <div class="flex-grow-1">
                        <strong>網路連線中斷</strong>
                        <div class="small">正在嘗試重新連線...</div>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-warning ms-2" id="retry-connection-btn">
                        <i class="bi bi-arrow-clockwise"></i> 重試
                    </button>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', indicatorHtml);
        this.offlineIndicator = document.getElementById('offline-indicator');
        
        // 綁定重試按鈕
        document.getElementById('retry-connection-btn').addEventListener('click', () => {
            this.checkConnection();
        });
    }
    
    /**
     * 創建錯誤提示容器
     */
    createErrorToastContainer() {
        let container = document.getElementById('error-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'error-toast-container';
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            container.style.zIndex = '1055';
            document.body.appendChild(container);
        }
        this.errorToastContainer = container;
    }
    
    /**
     * 綁定網路事件
     */
    bindNetworkEvents() {
        window.addEventListener('online', () => {
            this.handleOnline();
        });
        
        window.addEventListener('offline', () => {
            this.handleOffline();
        });
    }
    
    /**
     * 設置全域錯誤處理
     */
    setupGlobalErrorHandling() {
        // 捕獲未處理的 Promise 拒絕
        window.addEventListener('unhandledrejection', (event) => {
            this.logError('Unhandled Promise Rejection', event.reason);
            
            // 如果是網路錯誤，嘗試處理
            if (this.isNetworkError(event.reason)) {
                event.preventDefault(); // 防止控制台錯誤
                this.handleNetworkError(event.reason);
            }
        });
        
        // 捕獲 JavaScript 錯誤
        window.addEventListener('error', (event) => {
            this.logError('JavaScript Error', {
                message: event.message,
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno,
                error: event.error
            });
        });
        
        // 捕獲資源載入錯誤
        window.addEventListener('error', (event) => {
            if (event.target !== window) {
                this.handleResourceError(event.target);
            }
        }, true);
    }
    
    /**
     * 處理網路錯誤
     */
    async handleNetworkError(error, requestInfo = {}) {
        if (!this.isOnline) {
            this.queueOfflineRequest(requestInfo);
            return null;
        }
        
        const errorKey = this.generateErrorKey(requestInfo);
        
        // 檢查是否已在重試隊列中
        if (this.retryQueue.has(errorKey)) {
            return this.retryQueue.get(errorKey);
        }
        
        // 創建重試 Promise
        const retryPromise = this.retryWithBackoff(requestInfo);
        this.retryQueue.set(errorKey, retryPromise);
        
        try {
            const result = await retryPromise;
            this.retryQueue.delete(errorKey);
            return result;
        } catch (finalError) {
            this.retryQueue.delete(errorKey);
            this.showNetworkErrorToast(finalError, requestInfo);
            throw finalError;
        }
    }
    
    /**
     * 帶退避的重試機制
     */
    async retryWithBackoff(requestInfo, attempt = 1) {
        if (attempt > this.options.maxRetries) {
            throw new Error(`網路請求失敗，已重試 ${this.options.maxRetries} 次`);
        }
        
        // 計算延遲時間
        const delay = this.options.retryDelay * Math.pow(this.options.retryBackoff, attempt - 1);
        
        // 顯示重試提示
        if (attempt > 1) {
            this.showRetryToast(attempt, this.options.maxRetries);
        }
        
        await this.sleep(delay);
        
        try {
            // 檢查網路狀態
            if (!this.isOnline) {
                throw new Error('網路連線中斷');
            }
            
            // 重新執行請求
            const result = await this.executeRequest(requestInfo);
            
            // 成功後隱藏重試提示
            if (attempt > 1) {
                this.showSuccessToast('網路連線已恢復');
            }
            
            return result;
        } catch (error) {
            if (this.isNetworkError(error)) {
                return this.retryWithBackoff(requestInfo, attempt + 1);
            }
            throw error;
        }
    }
    
    /**
     * 執行網路請求
     */
    async executeRequest(requestInfo) {
        const { url, options = {} } = requestInfo;
        
        // 添加超時控制
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000); // 30秒超時
        
        try {
            const response = await fetch(url, {
                ...options,
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            return response;
        } catch (error) {
            clearTimeout(timeoutId);
            throw error;
        }
    }
    
    /**
     * 處理檔案載入錯誤
     */
    handleFileLoadError(fileInfo, error) {
        this.logError('File Load Error', { fileInfo, error });
        
        // 提供替代方案
        const alternatives = this.generateFileAlternatives(fileInfo);
        
        this.showFileErrorToast(fileInfo, error, alternatives);
        
        return alternatives;
    }
    
    /**
     * 生成檔案替代方案
     */
    generateFileAlternatives(fileInfo) {
        const alternatives = [];
        
        if (fileInfo.type === 'video') {
            alternatives.push({
                type: 'reload',
                description: '重新載入影片',
                action: () => this.reloadFile(fileInfo)
            });
            
            alternatives.push({
                type: 'fallback',
                description: '使用音頻模式',
                action: () => this.switchToAudioMode(fileInfo)
            });
        } else if (fileInfo.type === 'subtitle') {
            alternatives.push({
                type: 'reload',
                description: '重新載入字幕',
                action: () => this.reloadFile(fileInfo)
            });
            
            alternatives.push({
                type: 'regenerate',
                description: '重新生成字幕',
                action: () => this.regenerateSubtitle(fileInfo)
            });
        }
        
        alternatives.push({
            type: 'report',
            description: '回報問題',
            action: () => this.reportError(fileInfo, error)
        });
        
        return alternatives;
    }
    
    /**
     * 樂觀鎖定機制
     */
    acquireOptimisticLock(resourceId, version) {
        const lockKey = `${resourceId}:${version}`;
        
        if (this.conflictLocks.has(resourceId)) {
            const existingLock = this.conflictLocks.get(resourceId);
            if (existingLock.version !== version) {
                throw new ConflictError('資源已被其他使用者修改', {
                    resourceId,
                    currentVersion: existingLock.version,
                    requestedVersion: version
                });
            }
        }
        
        const lock = {
            resourceId,
            version,
            timestamp: Date.now(),
            lockId: this.generateLockId()
        };
        
        this.conflictLocks.set(resourceId, lock);
        return lock;
    }
    
    /**
     * 釋放樂觀鎖定
     */
    releaseOptimisticLock(resourceId, lockId) {
        const lock = this.conflictLocks.get(resourceId);
        if (lock && lock.lockId === lockId) {
            this.conflictLocks.delete(resourceId);
            return true;
        }
        return false;
    }
    
    /**
     * 處理編輯衝突
     */
    async handleEditConflict(conflictError) {
        const { resourceId, currentVersion, requestedVersion } = conflictError.details;
        
        // 顯示衝突解決對話框
        const resolution = await this.showConflictResolutionDialog(conflictError);
        
        switch (resolution.action) {
            case 'merge':
                return this.attemptAutoMerge(resourceId, currentVersion, requestedVersion);
            case 'overwrite':
                return this.forceOverwrite(resourceId, requestedVersion);
            case 'reload':
                return this.reloadResource(resourceId);
            case 'cancel':
                throw new Error('使用者取消操作');
            default:
                throw conflictError;
        }
    }
    
    /**
     * 顯示衝突解決對話框
     */
    async showConflictResolutionDialog(conflictError) {
        return new Promise((resolve) => {
            const modalHtml = `
                <div class="modal fade" id="conflict-resolution-modal" tabindex="-1" aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">
                                    <i class="bi bi-exclamation-triangle text-warning"></i>
                                    編輯衝突
                                </h5>
                            </div>
                            <div class="modal-body">
                                <div class="alert alert-warning">
                                    <strong>檢測到編輯衝突！</strong><br>
                                    此資源已被其他使用者或會話修改。請選擇如何處理：
                                </div>
                                <div class="d-grid gap-2">
                                    <button type="button" class="btn btn-primary" data-action="merge">
                                        <i class="bi bi-arrow-down-up"></i> 嘗試自動合併
                                    </button>
                                    <button type="button" class="btn btn-warning" data-action="overwrite">
                                        <i class="bi bi-arrow-clockwise"></i> 覆蓋現有版本
                                    </button>
                                    <button type="button" class="btn btn-info" data-action="reload">
                                        <i class="bi bi-arrow-clockwise"></i> 重新載入最新版本
                                    </button>
                                    <button type="button" class="btn btn-secondary" data-action="cancel">
                                        <i class="bi bi-x-circle"></i> 取消操作
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            const modal = new bootstrap.Modal(document.getElementById('conflict-resolution-modal'));
            
            // 綁定按鈕事件
            document.querySelectorAll('[data-action]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const action = btn.dataset.action;
                    modal.hide();
                    document.getElementById('conflict-resolution-modal').remove();
                    resolve({ action });
                });
            });
            
            modal.show();
        });
    }
    
    /**
     * 處理離線狀態
     */
    handleOffline() {
        this.isOnline = false;
        this.showOfflineIndicator();
        this.logError('Network Status', 'Gone offline');
    }
    
    /**
     * 處理上線狀態
     */
    handleOnline() {
        this.isOnline = true;
        this.hideOfflineIndicator();
        this.processOfflineQueue();
        this.logError('Network Status', 'Back online');
    }
    
    /**
     * 顯示離線指示器
     */
    showOfflineIndicator() {
        if (this.offlineIndicator) {
            this.offlineIndicator.style.display = 'block';
        }
    }
    
    /**
     * 隱藏離線指示器
     */
    hideOfflineIndicator() {
        if (this.offlineIndicator) {
            this.offlineIndicator.style.display = 'none';
        }
    }
    
    /**
     * 離線操作隊列
     */
    queueOfflineRequest(requestInfo) {
        this.offlineQueue.push({
            ...requestInfo,
            timestamp: Date.now()
        });
        
        this.showOfflineQueueToast(this.offlineQueue.length);
    }
    
    /**
     * 處理離線隊列
     */
    async processOfflineQueue() {
        if (this.offlineQueue.length === 0) return;
        
        this.showProcessingQueueToast(this.offlineQueue.length);
        
        const results = [];
        
        for (const request of this.offlineQueue) {
            try {
                const result = await this.executeRequest(request);
                results.push({ success: true, result });
            } catch (error) {
                results.push({ success: false, error });
            }
        }
        
        this.offlineQueue = [];
        
        const successCount = results.filter(r => r.success).length;
        this.showQueueProcessedToast(successCount, results.length);
    }
    
    /**
     * 檢查連線狀態
     */
    async checkConnection() {
        try {
            const response = await fetch('/api/health', {
                method: 'HEAD',
                cache: 'no-cache'
            });
            
            if (response.ok) {
                if (!this.isOnline) {
                    this.handleOnline();
                }
                return true;
            }
        } catch (error) {
            if (this.isOnline) {
                this.handleOffline();
            }
        }
        
        return false;
    }
    
    /**
     * 開始離線檢查
     */
    startOfflineCheck() {
        setInterval(() => {
            if (!this.isOnline) {
                this.checkConnection();
            }
        }, this.options.offlineCheckInterval);
    }
    
    /**
     * 顯示各種錯誤提示
     */
    showNetworkErrorToast(error, requestInfo) {
        if (!this.options.showToasts) return;
        
        this.showErrorToast('網路錯誤', `請求失敗: ${error.message}`, [
            {
                text: '重試',
                action: () => this.handleNetworkError(error, requestInfo)
            }
        ]);
    }
    
    showFileErrorToast(fileInfo, error, alternatives) {
        if (!this.options.showToasts) return;
        
        const actions = alternatives.map(alt => ({
            text: alt.description,
            action: alt.action
        }));
        
        this.showErrorToast('檔案載入錯誤', `無法載入 ${fileInfo.name}: ${error.message}`, actions);
    }
    
    showRetryToast(attempt, maxAttempts) {
        if (!this.options.showToasts) return;
        
        this.showInfoToast('重試中', `正在重試 (${attempt}/${maxAttempts})...`);
    }
    
    showSuccessToast(message) {
        if (!this.options.showToasts) return;
        
        this.showToast('success', '成功', message);
    }
    
    showOfflineQueueToast(queueLength) {
        if (!this.options.showToasts) return;
        
        this.showInfoToast('離線模式', `操作已加入隊列 (${queueLength} 個待處理)`);
    }
    
    showProcessingQueueToast(queueLength) {
        if (!this.options.showToasts) return;
        
        this.showInfoToast('處理隊列', `正在處理 ${queueLength} 個離線操作...`);
    }
    
    showQueueProcessedToast(successCount, totalCount) {
        if (!this.options.showToasts) return;
        
        const message = `已處理 ${successCount}/${totalCount} 個操作`;
        if (successCount === totalCount) {
            this.showSuccessToast(message);
        } else {
            this.showErrorToast('部分失敗', message);
        }
    }
    
    /**
     * 通用 Toast 顯示方法
     */
    showToast(type, title, message, actions = []) {
        const toastId = `toast-${Date.now()}`;
        const iconClass = {
            success: 'bi-check-circle-fill text-success',
            error: 'bi-exclamation-triangle-fill text-danger',
            warning: 'bi-exclamation-triangle-fill text-warning',
            info: 'bi-info-circle-fill text-info'
        }[type] || 'bi-info-circle-fill text-info';
        
        const actionsHtml = actions.length > 0 ? `
            <div class="mt-2 d-flex gap-2">
                ${actions.map((action, index) => `
                    <button type="button" class="btn btn-sm btn-outline-primary" data-action="${index}">
                        ${action.text}
                    </button>
                `).join('')}
            </div>
        ` : '';
        
        const toastHtml = `
            <div class="toast" id="${toastId}" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="toast-header">
                    <i class="bi ${iconClass} me-2"></i>
                    <strong class="me-auto">${title}</strong>
                    <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
                <div class="toast-body">
                    ${message}
                    ${actionsHtml}
                </div>
            </div>
        `;
        
        this.errorToastContainer.insertAdjacentHTML('beforeend', toastHtml);
        
        const toastElement = document.getElementById(toastId);
        
        // 綁定動作按鈕
        actions.forEach((action, index) => {
            const btn = toastElement.querySelector(`[data-action="${index}"]`);
            if (btn) {
                btn.addEventListener('click', () => {
                    action.action();
                    bootstrap.Toast.getInstance(toastElement)?.hide();
                });
            }
        });
        
        const toast = new bootstrap.Toast(toastElement, {
            autohide: type === 'success' || type === 'info',
            delay: type === 'success' ? 3000 : 5000
        });
        
        toast.show();
        
        // 清理
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }
    
    showErrorToast(title, message, actions = []) {
        this.showToast('error', title, message, actions);
    }
    
    showInfoToast(title, message, actions = []) {
        this.showToast('info', title, message, actions);
    }
    
    /**
     * 工具方法
     */
    isNetworkError(error) {
        return error instanceof TypeError && error.message.includes('fetch') ||
               error.name === 'NetworkError' ||
               error.message.includes('網路') ||
               error.message.includes('network') ||
               error.message.includes('timeout');
    }
    
    generateErrorKey(requestInfo) {
        return `${requestInfo.url || 'unknown'}_${requestInfo.method || 'GET'}`;
    }
    
    generateLockId() {
        return `lock_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }
    
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    logError(type, details) {
        if (!this.options.logErrors) return;
        
        const errorEntry = {
            type,
            details,
            timestamp: new Date().toISOString(),
            userAgent: navigator.userAgent,
            url: window.location.href
        };
        
        this.errorHistory.push(errorEntry);
        
        // 限制錯誤歷史長度
        if (this.errorHistory.length > 100) {
            this.errorHistory = this.errorHistory.slice(-50);
        }
        
        console.error(`[ErrorHandler] ${type}:`, details);
    }
    
    /**
     * 獲取錯誤統計
     */
    getErrorStatistics() {
        const stats = {
            totalErrors: this.errorHistory.length,
            networkErrors: 0,
            fileErrors: 0,
            conflictErrors: 0,
            otherErrors: 0,
            recentErrors: []
        };
        
        const recentTime = Date.now() - (24 * 60 * 60 * 1000); // 24小時內
        
        this.errorHistory.forEach(error => {
            const errorTime = new Date(error.timestamp).getTime();
            
            if (errorTime > recentTime) {
                stats.recentErrors.push(error);
            }
            
            if (error.type.includes('Network')) {
                stats.networkErrors++;
            } else if (error.type.includes('File')) {
                stats.fileErrors++;
            } else if (error.type.includes('Conflict')) {
                stats.conflictErrors++;
            } else {
                stats.otherErrors++;
            }
        });
        
        return stats;
    }
    
    /**
     * 清理資源
     */
    destroy() {
        // 清理重試隊列
        this.retryQueue.clear();
        
        // 清理衝突鎖定
        this.conflictLocks.clear();
        
        // 清理離線隊列
        this.offlineQueue = [];
        
        // 移除 DOM 元素
        if (this.offlineIndicator) {
            this.offlineIndicator.remove();
        }
        
        if (this.errorToastContainer) {
            this.errorToastContainer.remove();
        }
        
        console.log('ErrorHandler 已銷毀');
    }
}

/**
 * 自定義錯誤類型
 */
class ConflictError extends Error {
    constructor(message, details = {}) {
        super(message);
        this.name = 'ConflictError';
        this.details = details;
    }
}

class FileLoadError extends Error {
    constructor(message, fileInfo = {}) {
        super(message);
        this.name = 'FileLoadError';
        this.fileInfo = fileInfo;
    }
}

class NetworkError extends Error {
    constructor(message, requestInfo = {}) {
        super(message);
        this.name = 'NetworkError';
        this.requestInfo = requestInfo;
    }
}

// 導出類別
window.ErrorHandler = ErrorHandler;
window.ConflictError = ConflictError;
window.FileLoadError = FileLoadError;
window.NetworkError = NetworkError;

// 創建全域實例
window.globalErrorHandler = new ErrorHandler();
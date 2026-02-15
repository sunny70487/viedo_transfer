/**
 * 字幕下載管理器
 * 處理字幕匯出格式選擇、下載進度提示和成功訊息
 */

class SubtitleDownloadManager {
    constructor(options = {}) {
        this.options = {
            baseUrl: '/api/subtitles',
            supportedFormats: ['srt', 'vtt', 'txt', 'json'],
            showProgress: true,
            showSuccessMessage: true,
            autoCloseDelay: 3000, // 成功訊息自動關閉延遲（毫秒）
            ...options
        };
        
        // 狀態管理
        this.isDownloading = false;
        this.currentTaskId = null;
        this.downloadQueue = [];
        
        // DOM 元素引用
        this.progressModal = null;
        this.progressBar = null;
        this.progressText = null;
        this.successToast = null;
        
        // 事件監聽器管理
        this.eventListeners = new Map();
        this.callbacks = new Map();
        
        // 初始化
        this.init();
    }
    
    /**
     * 初始化下載管理器
     */
    init() {
        this.createProgressModal();
        this.createSuccessToast();
        this.initEventListeners();
        
        console.log('SubtitleDownloadManager 初始化完成');
    }
    
    /**
     * 創建進度模態框
     */
    createProgressModal() {
        // 檢查是否已存在
        this.progressModal = document.getElementById('download-progress-modal');
        if (this.progressModal) return;
        
        // 創建進度模態框 HTML
        const modalHtml = `
            <div class="modal fade" id="download-progress-modal" tabindex="-1" aria-labelledby="download-progress-label" aria-hidden="true" data-bs-backdrop="static">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="download-progress-label">
                                <i class="bi bi-download"></i> 正在下載字幕
                            </h5>
                        </div>
                        <div class="modal-body">
                            <div class="d-flex align-items-center mb-3">
                                <div class="spinner-border spinner-border-sm text-primary me-3" role="status">
                                    <span class="visually-hidden">載入中...</span>
                                </div>
                                <div class="flex-grow-1">
                                    <div class="progress">
                                        <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                             id="download-progress-bar" 
                                             role="progressbar" 
                                             style="width: 0%" 
                                             aria-valuenow="0" 
                                             aria-valuemin="0" 
                                             aria-valuemax="100">
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <p class="mb-0 text-muted" id="download-progress-text">準備下載...</p>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" id="cancel-download-btn">取消</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // 添加到頁面
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // 獲取元素引用
        this.progressModal = document.getElementById('download-progress-modal');
        this.progressBar = document.getElementById('download-progress-bar');
        this.progressText = document.getElementById('download-progress-text');
        
        // 綁定取消按鈕事件
        const cancelBtn = document.getElementById('cancel-download-btn');
        if (cancelBtn) {
            this.addEventListener(cancelBtn, 'click', () => this.cancelDownload());
        }
    }
    
    /**
     * 創建成功提示 Toast
     */
    createSuccessToast() {
        // 檢查是否已存在
        this.successToast = document.getElementById('download-success-toast');
        if (this.successToast) return;
        
        // 創建 Toast 容器（如果不存在）
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = '1055';
            document.body.appendChild(toastContainer);
        }
        
        // 創建成功 Toast HTML
        const toastHtml = `
            <div class="toast" id="download-success-toast" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="toast-header">
                    <i class="bi bi-check-circle-fill text-success me-2"></i>
                    <strong class="me-auto">下載完成</strong>
                    <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
                <div class="toast-body" id="download-success-message">
                    字幕檔案已成功下載
                </div>
            </div>
        `;
        
        // 添加到容器
        toastContainer.insertAdjacentHTML('beforeend', toastHtml);
        
        // 獲取元素引用
        this.successToast = document.getElementById('download-success-toast');
    }
    
    /**
     * 初始化事件監聽器
     */
    initEventListeners() {
        // 監聽匯出按鈕點擊事件
        document.addEventListener('click', (e) => {
            const exportBtn = e.target.closest('[data-format]');
            if (exportBtn) {
                e.preventDefault();
                const format = exportBtn.dataset.format;
                this.downloadSubtitle(format);
            }
        });
        
        // 監聽鍵盤快捷鍵
        this.addEventListener(document, 'keydown', (e) => this.onKeyDown(e));
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
     * 設置當前任務 ID
     */
    setTaskId(taskId) {
        this.currentTaskId = taskId;
    }
    
    /**
     * 下載字幕
     */
    async downloadSubtitle(format, taskId = null) {
        const actualTaskId = taskId || this.currentTaskId;
        
        if (!actualTaskId) {
            this.showError('未指定任務 ID');
            return false;
        }
        
        if (!this.options.supportedFormats.includes(format)) {
            this.showError(`不支援的格式: ${format}`);
            return false;
        }
        
        if (this.isDownloading) {
            this.showError('已有下載任務進行中，請稍候');
            return false;
        }
        
        try {
            this.isDownloading = true;
            
            // 使用全域載入管理器顯示下載進度
            const filename = `subtitles_${actualTaskId}.${format}`;
            if (window.globalLoadingManager) {
                window.globalLoadingManager.showDownloadProgress(filename);
            } else if (this.options.showProgress) {
                this.showProgress();
            }
            
            // 更新進度文字
            this.updateProgress(10, `正在準備 ${format.toUpperCase()} 格式...`);
            
            // 觸發下載開始回調
            this.triggerCallback('downloadStart', {
                taskId: actualTaskId,
                format: format
            });
            
            // 構建下載 URL
            const downloadUrl = `${this.options.baseUrl}/${actualTaskId}/download/${format}`;
            
            // 更新進度
            this.updateProgress(30, '正在生成字幕檔案...');
            if (window.globalLoadingManager) {
                window.globalLoadingManager.updateDownloadProgress(30);
            }
            
            // 使用錯誤處理器發送請求
            let response;
            if (window.globalErrorHandler) {
                const requestInfo = {
                    url: downloadUrl,
                    options: {
                        method: 'GET',
                        headers: {
                            'Accept': 'application/octet-stream'
                        }
                    }
                };
                
                try {
                    response = await window.globalErrorHandler.executeRequest(requestInfo);
                } catch (networkError) {
                    // 如果是網路錯誤，嘗試錯誤處理
                    response = await window.globalErrorHandler.handleNetworkError(networkError, requestInfo);
                    if (!response) {
                        throw networkError;
                    }
                }
            } else {
                // 發送下載請求
                response = await fetch(downloadUrl, {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/octet-stream'
                    }
                });
            }
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `下載失敗: ${response.status}`);
            }
            
            // 更新進度
            this.updateProgress(60, '正在處理檔案...');
            if (window.globalLoadingManager) {
                window.globalLoadingManager.updateDownloadProgress(60);
            }
            
            // 獲取檔案資料
            const blob = await response.blob();
            
            // 更新進度
            this.updateProgress(80, '正在準備下載...');
            if (window.globalLoadingManager) {
                window.globalLoadingManager.updateDownloadProgress(80);
            }
            
            // 獲取檔案名稱
            const contentDisposition = response.headers.get('Content-Disposition');
            let actualFilename = filename;
            
            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                if (filenameMatch && filenameMatch[1]) {
                    actualFilename = filenameMatch[1].replace(/['"]/g, '');
                }
            }
            
            // 創建下載連結
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = actualFilename;
            a.style.display = 'none';
            
            // 觸發下載
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            
            // 清理 URL
            window.URL.revokeObjectURL(url);
            
            // 更新進度
            this.updateProgress(100, '下載完成！');
            if (window.globalLoadingManager) {
                window.globalLoadingManager.updateDownloadProgress(100);
            }
            
            // 延遲隱藏進度
            setTimeout(() => {
                if (window.globalLoadingManager) {
                    window.globalLoadingManager.hideDownloadProgress();
                } else {
                    this.hideProgress();
                }
                
                // 顯示成功訊息
                if (this.options.showSuccessMessage) {
                    this.showSuccess(`${format.toUpperCase()} 格式字幕已成功下載`, actualFilename);
                }
            }, 500);
            
            // 觸發下載完成回調
            this.triggerCallback('downloadComplete', {
                taskId: actualTaskId,
                format: format,
                filename: actualFilename,
                size: blob.size
            });
            
            return true;
            
        } catch (error) {
            console.error('下載字幕時發生錯誤:', error);
            
            // 隱藏進度
            if (window.globalLoadingManager) {
                window.globalLoadingManager.hideDownloadProgress();
            } else {
                this.hideProgress();
            }
            
            // 使用錯誤處理器處理檔案載入錯誤
            if (window.globalErrorHandler) {
                const fileInfo = {
                    name: `subtitles_${actualTaskId}.${format}`,
                    type: 'subtitle',
                    url: `${this.options.baseUrl}/${actualTaskId}/download/${format}`
                };
                window.globalErrorHandler.handleFileLoadError(fileInfo, error);
            } else {
                this.showError(`下載失敗: ${error.message}`);
            }
            
            // 觸發下載錯誤回調
            this.triggerCallback('downloadError', {
                taskId: actualTaskId,
                format: format,
                error: error.message
            });
            
            return false;
        } finally {
            this.isDownloading = false;
        }
    }
    
    /**
     * 批次下載多種格式
     */
    async downloadMultipleFormats(formats, taskId = null) {
        const actualTaskId = taskId || this.currentTaskId;
        
        if (!actualTaskId) {
            this.showError('未指定任務 ID');
            return false;
        }
        
        if (this.isDownloading) {
            this.showError('已有下載任務進行中，請稍候');
            return false;
        }
        
        const results = [];
        const totalFormats = formats.length;
        
        try {
            this.isDownloading = true;
            
            if (this.options.showProgress) {
                this.showProgress();
            }
            
            for (let i = 0; i < formats.length; i++) {
                const format = formats[i];
                const progress = Math.round(((i + 1) / totalFormats) * 100);
                
                this.updateProgress(progress, `正在下載 ${format.toUpperCase()} 格式 (${i + 1}/${totalFormats})...`);
                
                const success = await this.downloadSubtitle(format, actualTaskId);
                results.push({ format, success });
                
                // 批次下載間隔
                if (i < formats.length - 1) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }
            
            this.hideProgress();
            
            const successCount = results.filter(r => r.success).length;
            if (successCount === totalFormats) {
                this.showSuccess(`所有 ${totalFormats} 種格式已成功下載`);
            } else {
                this.showError(`${successCount}/${totalFormats} 種格式下載成功`);
            }
            
            return results;
            
        } catch (error) {
            console.error('批次下載時發生錯誤:', error);
            this.hideProgress();
            this.showError(`批次下載失敗: ${error.message}`);
            return results;
        } finally {
            this.isDownloading = false;
        }
    }
    
    /**
     * 取消下載
     */
    cancelDownload() {
        if (!this.isDownloading) return;
        
        this.isDownloading = false;
        this.hideProgress();
        
        this.triggerCallback('downloadCancel');
        
        console.log('下載已取消');
    }
    
    /**
     * 顯示進度模態框
     */
    showProgress() {
        if (!this.progressModal) return;
        
        const modal = new bootstrap.Modal(this.progressModal);
        modal.show();
        
        // 重置進度
        this.updateProgress(0, '準備下載...');
    }
    
    /**
     * 隱藏進度模態框
     */
    hideProgress() {
        if (!this.progressModal) return;
        
        const modal = bootstrap.Modal.getInstance(this.progressModal);
        if (modal) {
            modal.hide();
        }
    }
    
    /**
     * 更新進度
     */
    updateProgress(percentage, message = '') {
        if (this.progressBar) {
            this.progressBar.style.width = `${percentage}%`;
            this.progressBar.setAttribute('aria-valuenow', percentage);
        }
        
        if (this.progressText && message) {
            this.progressText.textContent = message;
        }
    }
    
    /**
     * 顯示成功訊息
     */
    showSuccess(message, filename = '') {
        if (!this.successToast) return;
        
        const messageElement = document.getElementById('download-success-message');
        if (messageElement) {
            let fullMessage = message;
            if (filename) {
                fullMessage += `\n檔案名稱: ${filename}`;
            }
            messageElement.textContent = fullMessage;
        }
        
        const toast = new bootstrap.Toast(this.successToast, {
            autohide: true,
            delay: this.options.autoCloseDelay
        });
        toast.show();
    }
    
    /**
     * 顯示錯誤訊息
     */
    showError(message) {
        // 創建錯誤 Toast（如果不存在）
        let errorToast = document.getElementById('download-error-toast');
        if (!errorToast) {
            const toastContainer = document.getElementById('toast-container') || document.body;
            
            const errorToastHtml = `
                <div class="toast" id="download-error-toast" role="alert" aria-live="assertive" aria-atomic="true">
                    <div class="toast-header">
                        <i class="bi bi-exclamation-triangle-fill text-danger me-2"></i>
                        <strong class="me-auto">下載錯誤</strong>
                        <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
                    </div>
                    <div class="toast-body" id="download-error-message">
                        下載時發生錯誤
                    </div>
                </div>
            `;
            
            toastContainer.insertAdjacentHTML('beforeend', errorToastHtml);
            errorToast = document.getElementById('download-error-toast');
        }
        
        const messageElement = document.getElementById('download-error-message');
        if (messageElement) {
            messageElement.textContent = message;
        }
        
        const toast = new bootstrap.Toast(errorToast, {
            autohide: true,
            delay: 5000 // 錯誤訊息顯示較長時間
        });
        toast.show();
        
        console.error('下載錯誤:', message);
    }
    
    /**
     * 獲取支援的格式列表
     */
    getSupportedFormats() {
        return [...this.options.supportedFormats];
    }
    
    /**
     * 檢查格式是否支援
     */
    isFormatSupported(format) {
        return this.options.supportedFormats.includes(format.toLowerCase());
    }
    
    /**
     * 獲取格式資訊
     */
    getFormatInfo(format) {
        const formatInfo = {
            srt: {
                name: 'SRT',
                description: 'SubRip 字幕格式',
                extension: 'srt',
                mimeType: 'text/plain',
                icon: 'bi-file-text'
            },
            vtt: {
                name: 'VTT',
                description: 'WebVTT 字幕格式',
                extension: 'vtt',
                mimeType: 'text/vtt',
                icon: 'bi-file-code'
            },
            txt: {
                name: 'TXT',
                description: '純文字格式',
                extension: 'txt',
                mimeType: 'text/plain',
                icon: 'bi-file-earmark-text'
            },
            json: {
                name: 'JSON',
                description: 'JSON 資料格式',
                extension: 'json',
                mimeType: 'application/json',
                icon: 'bi-file-earmark-code'
            }
        };
        
        return formatInfo[format.toLowerCase()] || null;
    }
    
    /**
     * 創建格式選擇界面
     */
    createFormatSelector(containerId, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`找不到容器元素: ${containerId}`);
            return false;
        }
        
        const selectorOptions = {
            title: '選擇匯出格式',
            multiple: false,
            showDescription: true,
            ...options
        };
        
        let html = `<div class="format-selector">`;
        
        if (selectorOptions.title) {
            html += `<h6 class="mb-3">${selectorOptions.title}</h6>`;
        }
        
        html += `<div class="row g-2">`;
        
        this.options.supportedFormats.forEach(format => {
            const info = this.getFormatInfo(format);
            if (!info) return;
            
            const inputType = selectorOptions.multiple ? 'checkbox' : 'radio';
            const inputName = selectorOptions.multiple ? 'formats[]' : 'format';
            
            html += `
                <div class="col-md-6">
                    <div class="card format-option" data-format="${format}">
                        <div class="card-body p-3">
                            <div class="form-check">
                                <input class="form-check-input" type="${inputType}" name="${inputName}" value="${format}" id="format-${format}">
                                <label class="form-check-label w-100" for="format-${format}">
                                    <div class="d-flex align-items-center">
                                        <i class="bi ${info.icon} fs-4 me-3 text-primary"></i>
                                        <div>
                                            <div class="fw-bold">${info.name}</div>
                                            ${selectorOptions.showDescription ? `<small class="text-muted">${info.description}</small>` : ''}
                                        </div>
                                    </div>
                                </label>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        html += `</div>`;
        
        // 添加操作按鈕
        html += `
            <div class="mt-3 d-flex justify-content-end gap-2">
                <button type="button" class="btn btn-secondary" id="cancel-format-btn">取消</button>
                <button type="button" class="btn btn-primary" id="download-selected-btn">
                    <i class="bi bi-download"></i> 下載
                </button>
            </div>
        `;
        
        html += `</div>`;
        
        container.innerHTML = html;
        
        // 綁定事件
        const downloadBtn = container.querySelector('#download-selected-btn');
        const cancelBtn = container.querySelector('#cancel-format-btn');
        
        if (downloadBtn) {
            downloadBtn.addEventListener('click', () => {
                const selectedFormats = this.getSelectedFormats(container, selectorOptions.multiple);
                if (selectedFormats.length === 0) {
                    this.showError('請選擇至少一種格式');
                    return;
                }
                
                if (selectorOptions.multiple && selectedFormats.length > 1) {
                    this.downloadMultipleFormats(selectedFormats);
                } else {
                    this.downloadSubtitle(selectedFormats[0]);
                }
                
                // 觸發選擇完成回調
                this.triggerCallback('formatSelected', {
                    formats: selectedFormats,
                    multiple: selectorOptions.multiple
                });
            });
        }
        
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                this.triggerCallback('formatCancel');
            });
        }
        
        // 卡片點擊選中
        container.querySelectorAll('.format-option').forEach(card => {
            card.addEventListener('click', (e) => {
                if (e.target.type !== 'radio' && e.target.type !== 'checkbox') {
                    const input = card.querySelector('input');
                    if (input) {
                        if (input.type === 'radio') {
                            input.checked = true;
                        } else {
                            input.checked = !input.checked;
                        }
                    }
                }
            });
        });
        
        return true;
    }
    
    /**
     * 獲取選中的格式
     */
    getSelectedFormats(container, multiple = false) {
        const inputs = container.querySelectorAll('input[name="format"], input[name="formats[]"]');
        const selected = [];
        
        inputs.forEach(input => {
            if (input.checked) {
                selected.push(input.value);
            }
        });
        
        return selected;
    }
    
    /**
     * 鍵盤事件處理
     */
    onKeyDown(event) {
        // Ctrl+D 快速下載 SRT 格式
        if ((event.ctrlKey || event.metaKey) && event.key === 'd') {
            event.preventDefault();
            this.downloadSubtitle('srt');
        }
        
        // ESC 取消下載
        if (event.key === 'Escape' && this.isDownloading) {
            this.cancelDownload();
        }
    }
    
    /**
     * 註冊回調函數
     */
    on(event, callback) {
        if (!this.callbacks.has(event)) {
            this.callbacks.set(event, []);
        }
        this.callbacks.get(event).push(callback);
    }
    
    /**
     * 移除回調函數
     */
    off(event, callback) {
        if (!this.callbacks.has(event)) return;
        
        const callbacks = this.callbacks.get(event);
        const index = callbacks.indexOf(callback);
        if (index > -1) {
            callbacks.splice(index, 1);
        }
    }
    
    /**
     * 觸發回調函數
     */
    triggerCallback(event, data = {}) {
        if (!this.callbacks.has(event)) return;
        
        const callbacks = this.callbacks.get(event);
        callbacks.forEach(callback => {
            try {
                callback(data);
            } catch (error) {
                console.error(`回調函數執行錯誤 (${event}):`, error);
            }
        });
    }
    
    /**
     * 獲取下載狀態
     */
    getDownloadState() {
        return {
            isDownloading: this.isDownloading,
            currentTaskId: this.currentTaskId,
            queueLength: this.downloadQueue.length
        };
    }
    
    /**
     * 銷毀下載管理器
     */
    destroy() {
        // 取消進行中的下載
        if (this.isDownloading) {
            this.cancelDownload();
        }
        
        // 清理事件監聽器
        this.eventListeners.forEach((listeners, element) => {
            listeners.forEach(({ event, handler }) => {
                element.removeEventListener(event, handler);
            });
        });
        this.eventListeners.clear();
        
        // 清理回調函數
        this.callbacks.clear();
        
        // 移除 DOM 元素
        if (this.progressModal) {
            this.progressModal.remove();
        }
        if (this.successToast) {
            this.successToast.remove();
        }
        
        console.log('SubtitleDownloadManager 已銷毀');
    }
}

// 全域實例（可選）
window.SubtitleDownloadManager = SubtitleDownloadManager;
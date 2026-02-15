/**
 * 錯誤處理和載入管理整合腳本
 * 初始化全域錯誤處理器和載入管理器，並整合到現有組件中
 */

(function() {
    'use strict';
    
    /**
     * 初始化錯誤處理和載入管理系統
     */
    function initializeErrorAndLoadingManagement() {
        console.log('初始化錯誤處理和載入管理系統...');
        
        // 檢查依賴
        if (typeof ErrorHandler === 'undefined') {
            console.error('ErrorHandler 未載入');
            return false;
        }
        
        if (typeof LoadingManager === 'undefined') {
            console.error('LoadingManager 未載入');
            return false;
        }
        
        // 初始化全域錯誤處理器（如果尚未初始化）
        if (!window.globalErrorHandler) {
            window.globalErrorHandler = new ErrorHandler({
                maxRetries: 3,
                retryDelay: 1000,
                retryBackoff: 2,
                offlineCheckInterval: 5000,
                conflictRetryDelay: 2000,
                showToasts: true,
                logErrors: true
            });
            
            console.log('全域錯誤處理器已初始化');
        }
        
        // 初始化全域載入管理器（如果尚未初始化）
        if (!window.globalLoadingManager) {
            window.globalLoadingManager = new LoadingManager({
                skeletonAnimationDuration: 1500,
                progressUpdateInterval: 100,
                autoHideDelay: 3000,
                showPercentage: true,
                showETA: true
            });
            
            console.log('全域載入管理器已初始化');
        }
        
        return true;
    }
    
    /**
     * 整合字幕編輯器載入狀態
     */
    function integrateSubtitleEditorLoading() {
        // 監聽字幕編輯器載入事件
        document.addEventListener('subtitleEditorLoadStart', () => {
            if (window.globalLoadingManager) {
                window.globalLoadingManager.showSubtitleEditorSkeleton();
            }
        });
        
        document.addEventListener('subtitleEditorLoadComplete', () => {
            if (window.globalLoadingManager) {
                setTimeout(() => {
                    window.globalLoadingManager.hideSubtitleEditorSkeleton();
                }, 500); // 短暫延遲以確保內容已渲染
            }
        });
        
        // 監聽字幕資料載入
        document.addEventListener('subtitleDataLoadStart', (event) => {
            if (window.globalLoadingManager) {
                window.globalLoadingManager.showGenericProgress(
                    '載入字幕資料',
                    '正在從伺服器載入字幕資料...',
                    true
                );
            }
        });
        
        document.addEventListener('subtitleDataLoadProgress', (event) => {
            if (window.globalLoadingManager && event.detail) {
                window.globalLoadingManager.updateGenericProgress(
                    event.detail.percentage || 0,
                    event.detail.message || '載入中...'
                );
            }
        });
        
        document.addEventListener('subtitleDataLoadComplete', () => {
            if (window.globalLoadingManager) {
                window.globalLoadingManager.hideGenericProgress();
            }
        });
        
        document.addEventListener('subtitleDataLoadError', (event) => {
            if (window.globalLoadingManager) {
                window.globalLoadingManager.hideGenericProgress();
            }
            
            if (window.globalErrorHandler && event.detail) {
                const fileInfo = {
                    name: '字幕資料',
                    type: 'subtitle',
                    url: event.detail.url || 'unknown'
                };
                window.globalErrorHandler.handleFileLoadError(fileInfo, event.detail.error);
            }
        });
    }
    
    /**
     * 整合影片播放器錯誤處理
     */
    function integrateVideoPlayerErrorHandling() {
        // 監聽影片載入錯誤
        document.addEventListener('videoLoadError', (event) => {
            if (window.globalErrorHandler && event.detail) {
                const fileInfo = {
                    name: event.detail.filename || '影片檔案',
                    type: 'video',
                    url: event.detail.url || 'unknown',
                    size: event.detail.size
                };
                
                const alternatives = window.globalErrorHandler.handleFileLoadError(fileInfo, event.detail.error);
                
                // 觸發影片錯誤處理完成事件
                document.dispatchEvent(new CustomEvent('videoErrorHandled', {
                    detail: { alternatives, fileInfo }
                }));
            }
        });
        
        // 監聽影片載入開始
        document.addEventListener('videoLoadStart', (event) => {
            if (window.globalLoadingManager && event.detail) {
                window.globalLoadingManager.showGenericProgress(
                    '載入影片',
                    `正在載入 ${event.detail.filename || '影片檔案'}...`,
                    false
                );
            }
        });
        
        document.addEventListener('videoLoadComplete', () => {
            if (window.globalLoadingManager) {
                window.globalLoadingManager.hideGenericProgress();
            }
        });
    }
    
    /**
     * 整合樂觀鎖定機制到字幕編輯
     */
    function integrateOptimisticLocking() {
        // 字幕編輯開始時獲取鎖定
        document.addEventListener('subtitleEditStart', (event) => {
            if (window.globalErrorHandler && event.detail) {
                try {
                    const lock = window.globalErrorHandler.acquireOptimisticLock(
                        event.detail.resourceId,
                        event.detail.version
                    );
                    
                    // 儲存鎖定資訊到事件目標
                    if (event.detail.element) {
                        event.detail.element.dataset.lockId = lock.lockId;
                    }
                    
                    console.log('獲取樂觀鎖定:', lock);
                } catch (error) {
                    if (error instanceof ConflictError) {
                        // 處理編輯衝突
                        window.globalErrorHandler.handleEditConflict(error).catch(console.error);
                    } else {
                        console.error('獲取樂觀鎖定失敗:', error);
                    }
                }
            }
        });
        
        // 字幕編輯完成時釋放鎖定
        document.addEventListener('subtitleEditComplete', (event) => {
            if (window.globalErrorHandler && event.detail) {
                const released = window.globalErrorHandler.releaseOptimisticLock(
                    event.detail.resourceId,
                    event.detail.lockId
                );
                
                if (released) {
                    console.log('釋放樂觀鎖定:', event.detail.resourceId);
                } else {
                    console.warn('釋放樂觀鎖定失敗:', event.detail.resourceId);
                }
            }
        });
        
        // 字幕編輯取消時釋放鎖定
        document.addEventListener('subtitleEditCancel', (event) => {
            if (window.globalErrorHandler && event.detail) {
                window.globalErrorHandler.releaseOptimisticLock(
                    event.detail.resourceId,
                    event.detail.lockId
                );
            }
        });
    }
    
    /**
     * 整合進度取消處理
     */
    function integrateProgressCancellation() {
        // 監聽進度取消事件
        document.addEventListener('progressCancelled', (event) => {
            if (event.detail) {
                const { progressId, tracker } = event.detail;
                
                console.log('進度已取消:', progressId, tracker);
                
                // 根據進度類型執行相應的取消邏輯
                switch (tracker.type) {
                    case 'retranscribe':
                        // 取消重新轉錄任務
                        document.dispatchEvent(new CustomEvent('retranscribeCancelRequested', {
                            detail: { taskId: tracker.taskInfo?.taskId }
                        }));
                        break;
                        
                    case 'download':
                        // 取消下載任務
                        document.dispatchEvent(new CustomEvent('downloadCancelRequested', {
                            detail: { filename: tracker.filename }
                        }));
                        break;
                        
                    case 'generic':
                        // 通用取消
                        document.dispatchEvent(new CustomEvent('genericProgressCancelRequested', {
                            detail: { title: tracker.title }
                        }));
                        break;
                }
            }
        });
    }
    
    /**
     * 設置全域錯誤監聽器
     */
    function setupGlobalErrorListeners() {
        // 監聽 fetch 錯誤
        const originalFetch = window.fetch;
        window.fetch = async function(...args) {
            try {
                const response = await originalFetch.apply(this, args);
                
                // 檢查響應狀態
                if (!response.ok && window.globalErrorHandler) {
                    const requestInfo = {
                        url: args[0],
                        options: args[1] || {}
                    };
                    
                    // 如果是網路相關錯誤，使用錯誤處理器
                    if (response.status >= 500 || response.status === 0) {
                        const error = new Error(`HTTP ${response.status}: ${response.statusText}`);
                        return window.globalErrorHandler.handleNetworkError(error, requestInfo);
                    }
                }
                
                return response;
            } catch (error) {
                // 如果是網路錯誤且有錯誤處理器，使用錯誤處理器
                if (window.globalErrorHandler && window.globalErrorHandler.isNetworkError(error)) {
                    const requestInfo = {
                        url: args[0],
                        options: args[1] || {}
                    };
                    return window.globalErrorHandler.handleNetworkError(error, requestInfo);
                }
                
                throw error;
            }
        };
    }
    
    /**
     * 創建錯誤和載入狀態的調試工具
     */
    function createDebugTools() {
        // 只在開發環境中創建調試工具
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            window.debugErrorHandling = {
                getErrorStats: () => {
                    return window.globalErrorHandler ? window.globalErrorHandler.getErrorStatistics() : null;
                },
                
                getLoadingState: () => {
                    return window.globalLoadingManager ? window.globalLoadingManager.getLoadingState() : null;
                },
                
                simulateNetworkError: () => {
                    const error = new TypeError('Simulated network error');
                    window.globalErrorHandler?.handleNetworkError(error, { url: '/api/test' });
                },
                
                simulateFileError: () => {
                    const fileInfo = { name: 'test.mp4', type: 'video' };
                    const error = new Error('Simulated file error');
                    window.globalErrorHandler?.handleFileLoadError(fileInfo, error);
                },
                
                showTestSkeleton: () => {
                    window.globalLoadingManager?.showSubtitleEditorSkeleton();
                    setTimeout(() => {
                        window.globalLoadingManager?.hideSubtitleEditorSkeleton();
                    }, 3000);
                },
                
                showTestProgress: () => {
                    window.globalLoadingManager?.showRetranscribeProgress();
                    let progress = 0;
                    const interval = setInterval(() => {
                        progress += 10;
                        window.globalLoadingManager?.updateRetranscribeProgress(progress, `測試進度 ${progress}%`);
                        if (progress >= 100) {
                            clearInterval(interval);
                            setTimeout(() => {
                                window.globalLoadingManager?.hideRetranscribeProgress();
                            }, 1000);
                        }
                    }, 500);
                }
            };
            
            console.log('錯誤處理調試工具已載入，使用 window.debugErrorHandling 存取');
        }
    }
    
    /**
     * 主初始化函數
     */
    function initialize() {
        // 等待 DOM 載入完成
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initialize);
            return;
        }
        
        try {
            // 初始化核心系統
            if (!initializeErrorAndLoadingManagement()) {
                console.error('錯誤處理和載入管理系統初始化失敗');
                return;
            }
            
            // 整合各個組件
            integrateSubtitleEditorLoading();
            integrateVideoPlayerErrorHandling();
            integrateOptimisticLocking();
            integrateProgressCancellation();
            
            // 設置全域監聽器
            setupGlobalErrorListeners();
            
            // 創建調試工具
            createDebugTools();
            
            console.log('錯誤處理和載入管理整合完成');
            
            // 觸發初始化完成事件
            document.dispatchEvent(new CustomEvent('errorLoadingIntegrationComplete'));
            
        } catch (error) {
            console.error('錯誤處理和載入管理整合失敗:', error);
        }
    }
    
    // 開始初始化
    initialize();
    
})();
/**
 * 重新轉錄管理器
 * 處理字幕片段重新轉錄的前端邏輯
 */

class RetranscribeManager {
    constructor(options = {}) {
        this.options = {
            baseUrl: '/api/subtitles',
            pollInterval: 2000, // 輪詢間隔（毫秒）
            maxRetries: 3,
            ...options
        };
        
        // 狀態管理
        this.activeTasks = new Map(); // 活躍的重新轉錄任務
        this.taskId = null; // 當前字幕任務 ID
        this.eventListeners = new Map();
        
        // DOM 元素
        this.modal = null;
        this.progressModal = null;
        this.comparisonModal = null;
        
        this.init();
    }
    
    /**
     * 初始化重新轉錄管理器
     */
    init() {
        this.createModals();
        this.bindEvents();
        console.log('重新轉錄管理器初始化完成');
    }
    
    /**
     * 設置任務 ID
     */
    setTaskId(taskId) {
        this.taskId = taskId;
    }
    
    /**
     * 創建模態框
     */
    createModals() {
        this.createRetranscribeModal();
        this.createProgressModal();
        this.createComparisonModal();
    }
    
    /**
     * 創建重新轉錄設定模態框
     */
    createRetranscribeModal() {
        const modalHtml = `
            <div class="modal fade" id="retranscribe-modal" tabindex="-1" aria-labelledby="retranscribe-modal-label" aria-hidden="true">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="retranscribe-modal-label">
                                <i class="bi bi-arrow-repeat"></i> 重新轉錄字幕片段
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div class="alert alert-info">
                                <i class="bi bi-info-circle"></i>
                                <strong>提示：</strong>重新轉錄將使用 Whisper 模型重新處理選定的音頻片段，可能會得到更準確的結果。
                            </div>
                            
                            <!-- 字幕資訊 -->
                            <div class="mb-4">
                                <h6 class="mb-3">選定的字幕片段</h6>
                                <div class="card bg-light">
                                    <div class="card-body">
                                        <div class="row">
                                            <div class="col-md-6">
                                                <small class="text-muted">時間範圍</small>
                                                <div id="selected-time-range" class="fw-bold">--:-- ~ --:--</div>
                                            </div>
                                            <div class="col-md-6">
                                                <small class="text-muted">片段長度</small>
                                                <div id="selected-duration" class="fw-bold">-- 秒</div>
                                            </div>
                                        </div>
                                        <div class="mt-2">
                                            <small class="text-muted">當前文字</small>
                                            <div id="selected-text" class="border rounded p-2 mt-1 bg-white">--</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- 模型設定 -->
                            <div class="mb-4">
                                <h6 class="mb-3">轉錄設定</h6>
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label for="retranscribe-model" class="form-label">模型大小</label>
                                            <select class="form-select" id="retranscribe-model">
                                                <option value="large-v3" selected>Large-v3 (推薦)</option>
                                                <option value="large-v2">Large-v2</option>
                                                <option value="medium">Medium</option>
                                                <option value="small">Small</option>
                                                <option value="base">Base</option>
                                            </select>
                                        </div>
                                        <div class="mb-3">
                                            <label for="retranscribe-language" class="form-label">語言</label>
                                            <select class="form-select" id="retranscribe-language">
                                                <option value="">自動檢測</option>
                                                <option value="zh">中文</option>
                                                <option value="en">英文</option>
                                                <option value="ja">日文</option>
                                                <option value="ko">韓文</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label for="retranscribe-device" class="form-label">運算設備</label>
                                            <select class="form-select" id="retranscribe-device">
                                                <option value="auto" selected>自動選擇</option>
                                                <option value="cuda">GPU (CUDA)</option>
                                                <option value="cpu">CPU</option>
                                            </select>
                                        </div>
                                        <div class="mb-3">
                                            <label for="retranscribe-beam-size" class="form-label">束搜索大小</label>
                                            <select class="form-select" id="retranscribe-beam-size">
                                                <option value="1">1 (最快)</option>
                                                <option value="3">3</option>
                                                <option value="5" selected>5 (推薦)</option>
                                                <option value="10">10 (最準確)</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- 進階選項 -->
                                <div class="form-check mb-2">
                                    <input class="form-check-input" type="checkbox" id="retranscribe-vad" checked>
                                    <label class="form-check-label" for="retranscribe-vad">
                                        啟用語音活動檢測 (VAD)
                                    </label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="checkbox" id="retranscribe-word-timestamps" checked>
                                    <label class="form-check-label" for="retranscribe-word-timestamps">
                                        生成詞級時間戳
                                    </label>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" id="start-retranscribe-btn">
                                <i class="bi bi-arrow-repeat"></i> 開始重新轉錄
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        this.modal = new bootstrap.Modal(document.getElementById('retranscribe-modal'));
    }
    
    /**
     * 創建進度顯示模態框
     */
    createProgressModal() {
        const modalHtml = `
            <div class="modal fade" id="retranscribe-progress-modal" tabindex="-1" aria-labelledby="retranscribe-progress-modal-label" aria-hidden="true" data-bs-backdrop="static" data-bs-keyboard="false">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="retranscribe-progress-modal-label">
                                <i class="bi bi-arrow-repeat"></i> 重新轉錄進行中
                            </h5>
                        </div>
                        <div class="modal-body">
                            <div class="text-center mb-3">
                                <div class="spinner-border text-primary" role="status">
                                    <span class="visually-hidden">處理中...</span>
                                </div>
                            </div>
                            
                            <div class="mb-3">
                                <div class="d-flex justify-content-between align-items-center mb-1">
                                    <small class="text-muted">進度</small>
                                    <small id="progress-percentage" class="text-muted">0%</small>
                                </div>
                                <div class="progress">
                                    <div id="progress-bar" class="progress-bar" role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                                </div>
                            </div>
                            
                            <div class="mb-3">
                                <small class="text-muted">狀態</small>
                                <div id="progress-message" class="fw-bold">正在初始化...</div>
                            </div>
                            
                            <div class="alert alert-info">
                                <i class="bi bi-info-circle"></i>
                                <small>重新轉錄可能需要幾分鐘時間，請耐心等待。</small>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-danger" id="cancel-retranscribe-btn">
                                <i class="bi bi-x-circle"></i> 取消
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        this.progressModal = new bootstrap.Modal(document.getElementById('retranscribe-progress-modal'));
    }
    
    /**
     * 創建結果比較模態框
     */
    createComparisonModal() {
        const modalHtml = `
            <div class="modal fade" id="retranscribe-comparison-modal" tabindex="-1" aria-labelledby="retranscribe-comparison-modal-label" aria-hidden="true">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="retranscribe-comparison-modal-label">
                                <i class="bi bi-compare"></i> 轉錄結果比較
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div class="alert alert-success">
                                <i class="bi bi-check-circle"></i>
                                <strong>重新轉錄完成！</strong>請比較新舊結果並選擇要使用的版本。
                            </div>
                            
                            <div class="row">
                                <!-- 原始結果 -->
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-header bg-light">
                                            <h6 class="mb-0">
                                                <i class="bi bi-file-text"></i> 原始結果
                                            </h6>
                                        </div>
                                        <div class="card-body">
                                            <div class="mb-2">
                                                <small class="text-muted">時間範圍</small>
                                                <div id="original-time-range" class="fw-bold">--:-- ~ --:--</div>
                                            </div>
                                            <div class="mb-2">
                                                <small class="text-muted">信心度</small>
                                                <div id="original-confidence" class="fw-bold">--</div>
                                            </div>
                                            <div>
                                                <small class="text-muted">文字內容</small>
                                                <div id="original-text" class="border rounded p-3 mt-1 bg-light" style="min-height: 100px;">--</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- 新結果 -->
                                <div class="col-md-6">
                                    <div class="card border-primary">
                                        <div class="card-header bg-primary text-white">
                                            <h6 class="mb-0">
                                                <i class="bi bi-stars"></i> 重新轉錄結果
                                            </h6>
                                        </div>
                                        <div class="card-body">
                                            <div class="mb-2">
                                                <small class="text-muted">時間範圍</small>
                                                <div id="new-time-range" class="fw-bold">--:-- ~ --:--</div>
                                            </div>
                                            <div class="mb-2">
                                                <small class="text-muted">信心度</small>
                                                <div id="new-confidence" class="fw-bold">--</div>
                                            </div>
                                            <div>
                                                <small class="text-muted">文字內容</small>
                                                <div id="new-text" class="border rounded p-3 mt-1 bg-white" style="min-height: 100px;">--</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- 差異分析 -->
                            <div class="mt-4">
                                <h6 class="mb-3">
                                    <i class="bi bi-graph-up"></i> 差異分析
                                </h6>
                                <div class="row">
                                    <div class="col-md-4">
                                        <div class="text-center">
                                            <div id="text-similarity" class="h4 text-primary">--%</div>
                                            <small class="text-muted">文字相似度</small>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="text-center">
                                            <div id="confidence-change" class="h4">--</div>
                                            <small class="text-muted">信心度變化</small>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="text-center">
                                            <div id="word-count-change" class="h4">--</div>
                                            <small class="text-muted">字數變化</small>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-outline-primary" id="keep-original-btn">
                                <i class="bi bi-arrow-left"></i> 保留原始結果
                            </button>
                            <button type="button" class="btn btn-primary" id="apply-new-result-btn">
                                <i class="bi bi-check-circle"></i> 使用新結果
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        this.comparisonModal = new bootstrap.Modal(document.getElementById('retranscribe-comparison-modal'));
    }
    
    /**
     * 綁定事件監聽器
     */
    bindEvents() {
        // 開始重新轉錄按鈕
        document.getElementById('start-retranscribe-btn').addEventListener('click', () => {
            this.startRetranscribe();
        });
        
        // 取消重新轉錄按鈕
        document.getElementById('cancel-retranscribe-btn').addEventListener('click', () => {
            this.cancelRetranscribe();
        });
        
        // 保留原始結果按鈕
        document.getElementById('keep-original-btn').addEventListener('click', () => {
            this.keepOriginalResult();
        });
        
        // 應用新結果按鈕
        document.getElementById('apply-new-result-btn').addEventListener('click', () => {
            this.applyNewResult();
        });
    }
    
    /**
     * 顯示重新轉錄對話框
     */
    showRetranscribeDialog(subtitleIndex, subtitle) {
        this.currentSubtitleIndex = subtitleIndex;
        this.currentSubtitle = subtitle;
        
        // 更新對話框內容
        this.updateRetranscribeDialog(subtitle);
        
        // 顯示模態框
        this.modal.show();
    }
    
    /**
     * 更新重新轉錄對話框內容
     */
    updateRetranscribeDialog(subtitle) {
        // 格式化時間
        const startTime = this.formatTime(subtitle.start_time);
        const endTime = this.formatTime(subtitle.end_time);
        const duration = (subtitle.end_time - subtitle.start_time).toFixed(1);
        
        // 更新顯示
        document.getElementById('selected-time-range').textContent = `${startTime} ~ ${endTime}`;
        document.getElementById('selected-duration').textContent = `${duration} 秒`;
        document.getElementById('selected-text').textContent = subtitle.text || '(無文字)';
    }
    
    /**
     * 開始重新轉錄
     */
    async startRetranscribe() {
        try {
            // 收集設定
            const settings = this.collectRetranscribeSettings();
            
            // 準備請求資料
            const requestData = {
                task_id: this.taskId,
                start_time: this.currentSubtitle.start_time,
                end_time: this.currentSubtitle.end_time,
                subtitle_index: this.currentSubtitleIndex,
                model_settings: settings
            };
            
            // 隱藏設定對話框
            this.modal.hide();
            
            // 使用全域載入管理器顯示進度
            if (window.globalLoadingManager) {
                window.globalLoadingManager.showRetranscribeProgress({
                    taskId: this.taskId,
                    subtitleIndex: this.currentSubtitleIndex
                });
            } else {
                this.showProgressDialog();
            }
            
            // 使用錯誤處理器發送請求
            let response;
            if (window.globalErrorHandler) {
                const requestInfo = {
                    url: `${this.options.baseUrl}/${this.taskId}/retranscribe`,
                    options: {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(requestData)
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
                // 發送重新轉錄請求
                response = await fetch(`${this.options.baseUrl}/${this.taskId}/retranscribe`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
            }
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '創建重新轉錄任務失敗');
            }
            
            const result = await response.json();
            this.currentRetranscribeTaskId = result.retranscribe_task_id;
            
            // 開始輪詢任務狀態
            this.startPolling(result.retranscribe_task_id);
            
            // 觸發事件
            this.emit('retranscribeStart', {
                taskId: result.retranscribe_task_id,
                subtitleIndex: this.currentSubtitleIndex
            });
            
        } catch (error) {
            console.error('開始重新轉錄時出錯:', error);
            
            // 隱藏進度
            if (window.globalLoadingManager) {
                window.globalLoadingManager.hideRetranscribeProgress();
            } else {
                this.hideProgressDialog();
            }
            
            // 使用錯誤處理器處理錯誤
            if (window.globalErrorHandler) {
                const fileInfo = {
                    name: `重新轉錄任務 ${this.taskId}`,
                    type: 'retranscribe',
                    url: `${this.options.baseUrl}/${this.taskId}/retranscribe`
                };
                window.globalErrorHandler.handleFileLoadError(fileInfo, error);
            }
            
            this.emit('retranscribeError', { error: error.message });
        }
    }
    
    /**
     * 收集重新轉錄設定
     */
    collectRetranscribeSettings() {
        return {
            model_size: document.getElementById('retranscribe-model').value,
            language: document.getElementById('retranscribe-language').value || null,
            device: document.getElementById('retranscribe-device').value,
            beam_size: parseInt(document.getElementById('retranscribe-beam-size').value),
            vad_filter: document.getElementById('retranscribe-vad').checked,
            word_timestamps: document.getElementById('retranscribe-word-timestamps').checked
        };
    }
    
    /**
     * 顯示進度對話框
     */
    showProgressDialog() {
        this.updateProgress(0, '正在初始化...');
        this.progressModal.show();
    }
    
    /**
     * 隱藏進度對話框
     */
    hideProgressDialog() {
        this.progressModal.hide();
    }
    
    /**
     * 更新進度顯示
     */
    updateProgress(percentage, message) {
        // 優先使用全域載入管理器
        if (window.globalLoadingManager) {
            window.globalLoadingManager.updateRetranscribeProgress(percentage, message);
        }
        
        // 同時更新本地進度顯示（向後相容）
        const progressBar = document.getElementById('progress-bar');
        const progressPercentage = document.getElementById('progress-percentage');
        const progressMessage = document.getElementById('progress-message');
        
        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
        }
        if (progressPercentage) {
            progressPercentage.textContent = `${Math.round(percentage)}%`;
        }
        if (progressMessage) {
            progressMessage.textContent = message;
        }
    }
    
    /**
     * 開始輪詢任務狀態
     */
    startPolling(taskId) {
        this.activeTasks.set(taskId, {
            id: taskId,
            startTime: Date.now(),
            retryCount: 0
        });
        
        this.pollTaskStatus(taskId);
    }
    
    /**
     * 輪詢任務狀態
     */
    async pollTaskStatus(taskId) {
        try {
            const response = await fetch(`${this.options.baseUrl}/retranscribe/${taskId}`);
            
            if (!response.ok) {
                throw new Error('獲取任務狀態失敗');
            }
            
            const task = await response.json();
            
            // 更新進度
            this.updateProgress(task.progress || 0, task.message || '處理中...');
            
            if (task.status === 'completed') {
                // 任務完成
                this.handleRetranscribeComplete(task);
            } else if (task.status === 'failed') {
                // 任務失敗
                this.handleRetranscribeError(task.error || '重新轉錄失敗');
            } else {
                // 繼續輪詢
                setTimeout(() => {
                    if (this.activeTasks.has(taskId)) {
                        this.pollTaskStatus(taskId);
                    }
                }, this.options.pollInterval);
            }
            
        } catch (error) {
            console.error('輪詢任務狀態時出錯:', error);
            
            const taskInfo = this.activeTasks.get(taskId);
            if (taskInfo && taskInfo.retryCount < this.options.maxRetries) {
                taskInfo.retryCount++;
                setTimeout(() => {
                    if (this.activeTasks.has(taskId)) {
                        this.pollTaskStatus(taskId);
                    }
                }, this.options.pollInterval * 2);
            } else {
                this.handleRetranscribeError('網路錯誤，請稍後重試');
            }
        }
    }
    
    /**
     * 處理重新轉錄完成
     */
    handleRetranscribeComplete(task) {
        this.activeTasks.delete(task.id);
        
        // 隱藏進度
        if (window.globalLoadingManager) {
            window.globalLoadingManager.hideRetranscribeProgress();
        } else {
            this.hideProgressDialog();
        }
        
        // 顯示結果比較
        this.showComparisonDialog(this.currentSubtitle, task.result);
        
        // 觸發事件
        this.emit('retranscribeComplete', {
            taskId: task.id,
            result: task.result
        });
    }
    
    /**
     * 處理重新轉錄錯誤
     */
    handleRetranscribeError(errorMessage) {
        if (this.currentRetranscribeTaskId) {
            this.activeTasks.delete(this.currentRetranscribeTaskId);
        }
        
        // 隱藏進度
        if (window.globalLoadingManager) {
            window.globalLoadingManager.hideRetranscribeProgress();
        } else {
            this.hideProgressDialog();
        }
        
        // 使用錯誤處理器顯示錯誤
        if (window.globalErrorHandler) {
            const fileInfo = {
                name: `重新轉錄任務 ${this.currentRetranscribeTaskId}`,
                type: 'retranscribe'
            };
            const error = new Error(errorMessage);
            window.globalErrorHandler.handleFileLoadError(fileInfo, error);
        }
        
        // 觸發事件
        this.emit('retranscribeError', { error: errorMessage });
    }
    
    /**
     * 顯示結果比較對話框
     */
    showComparisonDialog(originalSubtitle, newSubtitle) {
        this.originalSubtitle = originalSubtitle;
        this.newSubtitle = newSubtitle;
        
        // 更新比較內容
        this.updateComparisonDialog(originalSubtitle, newSubtitle);
        
        // 顯示模態框
        this.comparisonModal.show();
    }
    
    /**
     * 更新比較對話框內容
     */
    updateComparisonDialog(originalSubtitle, newSubtitle) {
        // 原始結果
        const originalStartTime = this.formatTime(originalSubtitle.start_time);
        const originalEndTime = this.formatTime(originalSubtitle.end_time);
        document.getElementById('original-time-range').textContent = `${originalStartTime} ~ ${originalEndTime}`;
        document.getElementById('original-confidence').textContent = this.formatConfidence(originalSubtitle.confidence);
        document.getElementById('original-text').textContent = originalSubtitle.text || '(無文字)';
        
        // 新結果
        const newStartTime = this.formatTime(newSubtitle.start_time);
        const newEndTime = this.formatTime(newSubtitle.end_time);
        document.getElementById('new-time-range').textContent = `${newStartTime} ~ ${newEndTime}`;
        document.getElementById('new-confidence').textContent = this.formatConfidence(newSubtitle.confidence);
        document.getElementById('new-text').textContent = newSubtitle.text || '(無文字)';
        
        // 差異分析
        this.updateDifferenceAnalysis(originalSubtitle, newSubtitle);
    }
    
    /**
     * 更新差異分析
     */
    updateDifferenceAnalysis(originalSubtitle, newSubtitle) {
        // 計算文字相似度
        const similarity = this.calculateTextSimilarity(originalSubtitle.text, newSubtitle.text);
        document.getElementById('text-similarity').textContent = `${Math.round(similarity * 100)}%`;
        
        // 信心度變化
        const originalConf = originalSubtitle.confidence || 0;
        const newConf = newSubtitle.confidence || 0;
        const confChange = newConf - originalConf;
        const confChangeElement = document.getElementById('confidence-change');
        confChangeElement.textContent = confChange >= 0 ? `+${confChange.toFixed(2)}` : confChange.toFixed(2);
        confChangeElement.className = `h4 ${confChange >= 0 ? 'text-success' : 'text-danger'}`;
        
        // 字數變化
        const originalWordCount = (originalSubtitle.text || '').length;
        const newWordCount = (newSubtitle.text || '').length;
        const wordChange = newWordCount - originalWordCount;
        const wordChangeElement = document.getElementById('word-count-change');
        wordChangeElement.textContent = wordChange >= 0 ? `+${wordChange}` : `${wordChange}`;
        wordChangeElement.className = `h4 ${wordChange >= 0 ? 'text-success' : 'text-warning'}`;
    }
    
    /**
     * 計算文字相似度
     */
    calculateTextSimilarity(text1, text2) {
        if (!text1 && !text2) return 1;
        if (!text1 || !text2) return 0;
        
        // 簡單的字符相似度計算
        const maxLength = Math.max(text1.length, text2.length);
        let matches = 0;
        
        for (let i = 0; i < Math.min(text1.length, text2.length); i++) {
            if (text1[i] === text2[i]) {
                matches++;
            }
        }
        
        return matches / maxLength;
    }
    
    /**
     * 保留原始結果
     */
    keepOriginalResult() {
        this.comparisonModal.hide();
        
        // 觸發事件
        this.emit('retranscribeKeepOriginal', {
            subtitleIndex: this.currentSubtitleIndex
        });
    }
    
    /**
     * 應用新結果
     */
    async applyNewResult() {
        try {
            // 發送應用請求
            const response = await fetch(
                `${this.options.baseUrl}/${this.taskId}/retranscribe/${this.currentRetranscribeTaskId}/apply`,
                { method: 'POST' }
            );
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '應用新結果失敗');
            }
            
            const result = await response.json();
            
            this.comparisonModal.hide();
            
            // 觸發事件
            this.emit('retranscribeApplied', {
                subtitleIndex: this.currentSubtitleIndex,
                newSubtitle: this.newSubtitle,
                result: result
            });
            
        } catch (error) {
            console.error('應用新結果時出錯:', error);
            this.emit('retranscribeError', { error: error.message });
        }
    }
    
    /**
     * 取消重新轉錄
     */
    cancelRetranscribe() {
        if (this.currentRetranscribeTaskId) {
            this.activeTasks.delete(this.currentRetranscribeTaskId);
        }
        this.hideProgressDialog();
        
        // 觸發事件
        this.emit('retranscribeCancel', {
            taskId: this.currentRetranscribeTaskId
        });
    }
    
    /**
     * 格式化時間
     */
    formatTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        const ms = Math.floor((seconds % 1) * 1000);
        
        if (hours > 0) {
            return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
        } else {
            return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
        }
    }
    
    /**
     * 格式化信心度
     */
    formatConfidence(confidence) {
        if (confidence === null || confidence === undefined) {
            return '未知';
        }
        return `${(confidence * 100).toFixed(1)}%`;
    }
    
    /**
     * 事件監聽器管理
     */
    on(event, callback) {
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, []);
        }
        this.eventListeners.get(event).push(callback);
    }
    
    off(event, callback) {
        if (this.eventListeners.has(event)) {
            const listeners = this.eventListeners.get(event);
            const index = listeners.indexOf(callback);
            if (index > -1) {
                listeners.splice(index, 1);
            }
        }
    }
    
    emit(event, data) {
        if (this.eventListeners.has(event)) {
            this.eventListeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`事件處理器錯誤 (${event}):`, error);
                }
            });
        }
    }
    
    /**
     * 清理資源
     */
    destroy() {
        // 停止所有活躍任務
        this.activeTasks.clear();
        
        // 清理事件監聽器
        this.eventListeners.clear();
        
        // 移除模態框
        if (this.modal) {
            this.modal.dispose();
        }
        if (this.progressModal) {
            this.progressModal.dispose();
        }
        if (this.comparisonModal) {
            this.comparisonModal.dispose();
        }
    }
}
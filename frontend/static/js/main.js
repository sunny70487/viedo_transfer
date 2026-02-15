/**
 * Whisper 轉錄應用前端 JavaScript
 */

// 防重複提交標誌
let isSubmitting = false;

// 當 DOM 加載完成後執行
document.addEventListener('DOMContentLoaded', function() {
    // 初始化表單和事件監聯器
    initForms();
    initEventListeners();
    
    // 載入任務列表
    loadTasks();
    
    // 設置定時刷新任務狀態
    setInterval(updateTasksStatus, 5000);
});

/**
 * 初始化表單提交事件
 */
function initForms() {
    // URL 轉錄表單
    const urlForm = document.getElementById('url-form');
    if (urlForm) {
        urlForm.addEventListener('submit', function(e) {
            e.preventDefault();
            submitUrlForm();
        });
        
        // 監聽下載格式變更，以顯示/隱藏影片畫質選項
        const downloadFormatSelect = document.getElementById('download-format');
        const videoQualityContainer = document.getElementById('video-quality-container');
        
        if (downloadFormatSelect && videoQualityContainer) {
            downloadFormatSelect.addEventListener('change', function() {
                // 如果選擇了視頻或兩者，顯示畫質選擇
                if (this.value === 'video' || this.value === 'both') {
                    videoQualityContainer.style.display = 'block';
                } else {
                    videoQualityContainer.style.display = 'none';
                }
            });
        }
    }
    
    // 上傳音頻/影片表單
    const uploadForm = document.getElementById('upload-form');
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();
            submitUploadForm();
        });
    }
}

/**
 * 初始化其他事件監聽器
 */
function initEventListeners() {
    // GPU 信息按鈕
    const gpuInfoBtn = document.getElementById('gpu-info-btn');
    if (gpuInfoBtn) {
        gpuInfoBtn.addEventListener('click', function() {
            showGpuInfo();
        });
    }
    
    // 刷新任務按鈕
    const refreshTasksBtn = document.getElementById('refresh-tasks');
    if (refreshTasksBtn) {
        refreshTasksBtn.addEventListener('click', function() {
            loadTasks();
        });
    }
    
    // 任務詳情按鈕事件委託
    document.addEventListener('click', function(e) {
        if (e.target && e.target.classList.contains('task-details-btn')) {
            const taskItem = e.target.closest('.task-item');
            if (taskItem) {
                const taskId = taskItem.dataset.taskId;
                showTaskDetails(taskId);
            }
        }
    });

    // 任務刪除按鈕事件委託
    document.addEventListener('click', function(e) {
        const deleteBtn = e.target.closest('.task-delete-btn');
        if (deleteBtn) {
            e.stopPropagation();
            const taskItem = deleteBtn.closest('.task-item');
            if (taskItem) {
                const taskId = taskItem.dataset.taskId;
                deleteTask(taskId, taskItem);
            }
        }
    });
    
    // 目錄選擇按鈕
    const selectDirBtn = document.getElementById('select-dir-btn');
    if (selectDirBtn) {
        selectDirBtn.addEventListener('click', selectOutputDirectory);
    }
}

/**
 * 提交 URL 轉錄表單
 */
async function submitUrlForm() {
    if (isSubmitting) return;
    isSubmitting = true;
    try {
        // 獲取表單數據
        const formData = getFormData();
        const url = document.getElementById('url').value;
        const downloadFormat = document.getElementById('download-format').value;
        
        // 添加 URL 特定參數
        formData.url = url;
        formData.download_format = downloadFormat;
        
        // 如果選擇了視頻格式，添加畫質參數
        if (downloadFormat === 'video' || downloadFormat === 'both') {
            const videoQuality = document.getElementById('video-quality').value;
            formData.video_quality = videoQuality;
        }
        
        // 禁用表單
        setFormDisabled(true);
        showLoading('正在提交轉錄請求...');
        
        // 發送請求
        const response = await fetch('/transcribe/url', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        // 處理響應
        if (response.ok) {
            const data = await response.json();
            showSuccess(`轉錄任務已創建，任務 ID: ${data.task_id}`);
            loadTasks();
        } else {
            const error = await response.json();
            showError(`轉錄請求失敗: ${error.error || '未知錯誤'}`);
        }
    } catch (error) {
        console.error('提交 URL 表單時出錯:', error);
        showError(`提交請求時出錯: ${error.message}`);
    } finally {
        // 啟用表單
        setFormDisabled(false);
        hideLoading();
        isSubmitting = false;
    }
}

/**
 * 提交上傳音頻表單
 */
async function submitUploadForm() {
    if (isSubmitting) return;
    isSubmitting = true;
    try {
        // 獲取文件
        const fileInput = document.getElementById('audio-file');
        if (!fileInput.files || fileInput.files.length === 0) {
            showError('請選擇要上傳的音頻文件');
            return;
        }
        
        // 創建 FormData 對象
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        
        // 添加其他參數
        appendFormDataParams(formData);
        
        // 禁用表單
        setFormDisabled(true);
        showLoading('正在上傳音頻文件...');
        
        // 發送請求
        const response = await fetch('/transcribe/upload', {
            method: 'POST',
            body: formData
        });
        
        // 處理響應
        if (response.ok) {
            const data = await response.json();
            showSuccess(`音頻文件已上傳，轉錄任務已創建，任務 ID: ${data.task_id}`);
            loadTasks();
        } else {
            const error = await response.json();
            showError(`上傳失敗: ${error.error || '未知錯誤'}`);
        }
    } catch (error) {
        console.error('提交上傳表單時出錯:', error);
        showError(`上傳文件時出錯: ${error.message}`);
    } finally {
        // 啟用表單
        setFormDisabled(false);
        hideLoading();
        isSubmitting = false;
    }
}

/**
 * 獲取表單數據
 */
function getFormData() {
    const formData = {
        model_size: document.getElementById('model-size').value,
        device: document.getElementById('device').value,
        compute_type: document.getElementById('compute-type').value,
        language: document.getElementById('language').value || null,
        task: document.getElementById('task').value,
        beam_size: parseInt(document.getElementById('beam-size').value),
        vad_filter: document.getElementById('vad-filter').checked,
        word_timestamps: document.getElementById('word-timestamps').checked,
        output_format: document.getElementById('output-format').value,
        split_segments: document.getElementById('split-segments').checked,
        segment_duration: parseInt(document.getElementById('segment-duration').value),
        output_dir: document.getElementById('output-dir').value || null
    };
    
    return formData;
}

/**
 * 將表單參數添加到 FormData 對象
 */
function appendFormDataParams(formData) {
    formData.append('model_size', document.getElementById('model-size').value);
    formData.append('device', document.getElementById('device').value);
    formData.append('compute_type', document.getElementById('compute-type').value);
    
    const language = document.getElementById('language').value;
    if (language) {
        formData.append('language', language);
    }
    
    formData.append('task', document.getElementById('task').value);
    formData.append('beam_size', document.getElementById('beam-size').value);
    formData.append('vad_filter', document.getElementById('vad-filter').checked);
    formData.append('word_timestamps', document.getElementById('word-timestamps').checked);
    formData.append('output_format', document.getElementById('output-format').value);
    formData.append('split_segments', document.getElementById('split-segments').checked);
    formData.append('segment_duration', document.getElementById('segment-duration').value);
    
    const outputDir = document.getElementById('output-dir').value;
    if (outputDir) {
        formData.append('output_dir', outputDir);
    }
}

/**
 * 設置表單禁用狀態
 */
function setFormDisabled(disabled) {
    // 禁用所有表單元素
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        const elements = form.elements;
        for (let i = 0; i < elements.length; i++) {
            elements[i].disabled = disabled;
        }
    });
    
    // 禁用選項卡
    const tabs = document.querySelectorAll('.nav-link');
    tabs.forEach(tab => {
        tab.classList.toggle('disabled', disabled);
    });
}

/**
 * 顯示加載提示
 */
function showLoading(message) {
    // 創建加載提示元素
    const loadingEl = document.createElement('div');
    loadingEl.id = 'loading-indicator';
    loadingEl.className = 'position-fixed top-0 start-0 w-100 h-100 d-flex justify-content-center align-items-center';
    loadingEl.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
    loadingEl.style.zIndex = '9999';
    
    loadingEl.innerHTML = `
        <div class="p-4 rounded shadow-lg text-center" style="background-color: var(--theme-card-bg); color: var(--theme-text-primary);">
            <div class="spinner-border text-primary mb-3" role="status">
                <span class="visually-hidden">載入中...</span>
            </div>
            <p class="mb-0">${message || '請稍候...'}</p>
        </div>
    `;
    
    document.body.appendChild(loadingEl);
}

/**
 * 隱藏加載提示
 */
function hideLoading() {
    const loadingEl = document.getElementById('loading-indicator');
    if (loadingEl) {
        loadingEl.remove();
    }
}

/**
 * 顯示成功提示
 */
function showSuccess(message) {
    showToast(message, 'success');
}

/**
 * 顯示錯誤提示
 */
function showError(message) {
    showToast(message, 'danger');
}

/**
 * 顯示提示消息
 */
function showToast(message, type = 'info') {
    // 創建 Toast 容器（如果不存在）
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }
    
    // 創建 Toast 元素
    const toastId = `toast-${Date.now()}`;
    const toast = document.createElement('div');
    toast.className = `toast fade-in border-${type}`;
    toast.id = toastId;
    toast.setAttribute('role', type === 'danger' ? 'alert' : 'status');
    toast.setAttribute('aria-live', type === 'danger' ? 'assertive' : 'polite');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="toast-header">
            <strong class="me-auto text-${type}">${type === 'success' ? '成功' : type === 'danger' ? '錯誤' : '提示'}</strong>
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
 * 載入任務列表
 */
async function loadTasks() {
    try {
        const response = await fetch('/tasks');
        if (response.ok) {
            const tasks = await response.json();
            renderTasks(tasks);
        } else {
            console.error('獲取任務列表失敗');
        }
    } catch (error) {
        console.error('載入任務時出錯:', error);
    }
}

/**
 * 渲染任務列表
 */
function renderTasks(tasks) {
    const tasksContainer = document.getElementById('tasks-container');
    if (!tasksContainer) return;
    
    // 清空容器
    tasksContainer.innerHTML = '';
    
    // 檢查是否有任務
    const taskIds = Object.keys(tasks);
    if (taskIds.length === 0) {
        tasksContainer.innerHTML = `
            <div class="text-center py-4 text-muted">
                <i class="bi bi-inbox fs-1"></i>
                <p class="mt-2">尚無任務</p>
                <p class="small">提交 URL 或上傳檔案以開始轉錄</p>
            </div>
        `;
        return;
    }
    
    // 按開始時間排序（最新的在前面）
    taskIds.sort((a, b) => tasks[b].start_time - tasks[a].start_time);
    
    // 創建任務項目
    taskIds.forEach(taskId => {
        const task = tasks[taskId];
        if (!task.id) task.id = taskId;
        const taskElement = createTaskElement(task);
        tasksContainer.appendChild(taskElement);
    });
}

/**
 * 創建任務元素
 */
function createTaskElement(task) {
    const template = document.getElementById('task-template');
    const taskElement = template.content.cloneNode(true).querySelector('.task-item');
    
    // 設置任務 ID
    taskElement.dataset.taskId = task.id;
    taskElement.dataset.status = task.status;
    taskElement.querySelector('.task-id').textContent = task.source_name || (task.id.substring(0, 8) + '...');
    taskElement.querySelector('.task-id').title = task.source_name || task.id;
    
    // 設置狀態
    const statusBadge = taskElement.querySelector('.task-status');
    statusBadge.textContent = getStatusText(task.status);
    statusBadge.classList.add(task.status);
    
    // 設置消息
    taskElement.querySelector('.task-message').textContent = task.message;
    
    // 設置進度條
    const progressBar = taskElement.querySelector('.progress-bar');
    progressBar.style.width = `${task.progress}%`;
    progressBar.setAttribute('aria-valuenow', task.progress);
    
    // 設置進度文本
    const progressText = taskElement.querySelector('.progress-text');
    if (progressText) {
        progressText.textContent = `${task.progress.toFixed(1)}%`;
    }
    
    // 設置時間
    const timeElement = taskElement.querySelector('.task-time');
    if (task.status === 'completed' || task.status === 'failed') {
        const duration = task.end_time - task.start_time;
        timeElement.textContent = `耗時: ${formatDuration(duration)}`;
    } else {
        const startTime = new Date(task.start_time * 1000);
        timeElement.textContent = `開始: ${formatDateTime(startTime)}`;
    }

    // 已完成或失敗的任務顯示刪除按鈕
    const deleteBtn = taskElement.querySelector('.task-delete-btn');
    if (deleteBtn && (task.status === 'completed' || task.status === 'failed')) {
        deleteBtn.style.display = '';
    }
    
    return taskElement;
}

/**
 * 更新任務狀態
 */
async function updateTasksStatus() {
    try {
        // 獲取所有任務元素
        const taskElements = document.querySelectorAll('.task-item');
        
        // 如果沒有任務，不需要更新
        if (taskElements.length === 0) {
            return;
        }
        
        // 獲取所有任務的最新狀態
        const response = await fetch('/tasks');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const tasksData = await response.json();
        
        // 更新每個任務的狀態
        taskElements.forEach(taskElement => {
            const taskId = taskElement.dataset.taskId;
            if (taskId in tasksData) {
                const task = tasksData[taskId];
                
                // 確保完成的任務顯示100%進度
                if (task.status === 'completed' && task.progress < 100) {
                    task.progress = 100.0;
                }
                
                updateTaskElement(taskElement, task);
                
                // 如果此任務的 inline 詳情當前展開，也更新詳情
                const inlineDetails = taskElement.querySelector('.task-details-inline');
                if (inlineDetails && inlineDetails.classList.contains('show')) {
                    // 確保詳情頁面的任務完成時也顯示100%
                    if (task.status === 'completed' && task.progress < 100) {
                        task.progress = 100.0;
                    }
                    // 確保 task.id 存在（/tasks API 的 key 即為 id）
                    if (!task.id) task.id = taskId;
                    renderTaskDetails(task);
                }
            }
        });
    } catch (error) {
        console.error('更新任務狀態時出錯:', error);
    }
}

/**
 * 更新任務元素
 */
function updateTaskElement(taskElement, task) {
    // 更新任務標題（來源名稱）
    if (task.source_name) {
        const taskIdEl = taskElement.querySelector('.task-id');
        taskIdEl.textContent = task.source_name;
        taskIdEl.title = task.source_name;
    }

    // 更新狀態徽章
    const statusBadge = taskElement.querySelector('.task-status');
    statusBadge.textContent = getStatusText(task.status);
    statusBadge.className = `badge task-status ${task.status}`;
    
    // 更新任務消息
    const messageElement = taskElement.querySelector('.task-message');
    messageElement.textContent = task.message;
    
    // 更新進度條
    const progressBar = taskElement.querySelector('.progress-bar');
    progressBar.style.width = `${task.progress}%`;
    progressBar.setAttribute('aria-valuenow', task.progress);
    
    // 更新進度文本
    const progressText = taskElement.querySelector('.progress-text');
    if (progressText) {
        progressText.textContent = `${task.progress.toFixed(1)}%`;
    }
    
    // 如果任務已完成或失敗，更新時間
    if (task.status === 'completed' || task.status === 'failed') {
        const timeElement = taskElement.querySelector('.task-time');
        const duration = task.end_time - task.start_time;
        timeElement.textContent = `耗時: ${formatDuration(duration)}`;
    }
    
    // 更新刪除按鈕顯示狀態
    const deleteBtn = taskElement.querySelector('.task-delete-btn');
    if (deleteBtn) {
        deleteBtn.style.display = (task.status === 'completed' || task.status === 'failed') ? '' : 'none';
    }

    // 更新任務項目的狀態屬性
    taskElement.dataset.status = task.status;
}

/**
 * 刪除任務
 */
async function deleteTask(taskId, taskElement) {
    if (!confirm('確定要刪除這個任務嗎？')) {
        return;
    }

    try {
        const response = await fetch(`/tasks/${taskId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            // 淡出動畫後移除元素
            taskElement.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            taskElement.style.opacity = '0';
            taskElement.style.transform = 'translateX(20px)';
            setTimeout(() => {
                taskElement.remove();
                // 如果沒有任何任務了，顯示空狀態
                const tasksContainer = document.getElementById('tasks-container');
                if (tasksContainer && tasksContainer.querySelectorAll('.task-item').length === 0) {
                    tasksContainer.innerHTML = `
                        <div class="text-center py-4 text-muted">
                            <i class="bi bi-inbox fs-1"></i>
                            <p class="mt-2">尚無任務</p>
                            <p class="small">提交 URL 或上傳檔案以開始轉錄</p>
                        </div>
                    `;
                }
            }, 300);
            showToast('任務已刪除', 'success');
        } else {
            const data = await response.json();
            showToast(data.error || '刪除失敗', 'danger');
        }
    } catch (error) {
        console.error('刪除任務時出錯:', error);
        showToast('刪除任務時出錯', 'danger');
    }
}

/**
 * 顯示任務詳情（inline accordion）
 */
async function showTaskDetails(taskId) {
    try {
        // 重新查詢 DOM（避免 stale reference）
        let taskCard = document.querySelector(`.task-item[data-task-id="${taskId}"]`);
        if (!taskCard) {
            console.warn('[showTaskDetails] taskCard not found for:', taskId);
            return;
        }

        let inlineContainer = taskCard.querySelector('.task-details-inline');
        let detailBtn = taskCard.querySelector('.task-details-btn');

        if (!inlineContainer || !detailBtn) {
            console.warn('[showTaskDetails] missing inlineContainer or detailBtn');
            return;
        }

        // If already expanded, collapse it
        if (inlineContainer.classList.contains('show')) {
            inlineContainer.classList.remove('show');
            taskCard.classList.remove('task-expanded');
            detailBtn.textContent = '詳情';
            detailBtn.classList.remove('active');
            return;
        }

        // Collapse any other expanded task
        const prevExpanded = document.querySelector('.task-details-inline.show');
        if (prevExpanded) {
            prevExpanded.classList.remove('show');
            const prevCard = prevExpanded.closest('.task-item');
            if (prevCard) {
                prevCard.classList.remove('task-expanded');
                const prevBtn = prevCard.querySelector('.task-details-btn');
                if (prevBtn) {
                    prevBtn.textContent = '詳情';
                    prevBtn.classList.remove('active');
                }
            }
        }

        // Fetch task data
        const response = await fetch(`/tasks/${taskId}`);
        if (!response.ok) {
            showError('獲取任務詳情失敗');
            return;
        }

        const task = await response.json();
        if (!task.id) task.id = taskId;

        // 在 await 之後重新查詢 DOM（防止 DOM 在 await 期間被重建）
        taskCard = document.querySelector(`.task-item[data-task-id="${taskId}"]`);
        if (!taskCard) {
            console.warn('[showTaskDetails] taskCard lost after fetch for:', taskId);
            return;
        }
        inlineContainer = taskCard.querySelector('.task-details-inline');
        detailBtn = taskCard.querySelector('.task-details-btn');
        if (!inlineContainer || !detailBtn) {
            console.warn('[showTaskDetails] DOM elements lost after fetch');
            return;
        }

        // Render into inline container
        renderTaskDetails(task);

        // Expand
        inlineContainer.classList.add('show');
        taskCard.classList.add('task-expanded');
        detailBtn.textContent = '收起';
        detailBtn.classList.add('active');

        // Smooth scroll to the task card
        taskCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (error) {
        console.error('顯示任務詳情時出錯:', error);
        console.error('Error stack:', error.stack);
        showError(`獲取任務詳情時出錯: ${error.message}`);
    }
}

/**
 * 渲染任務詳情（插入到對應 task card 的 inline container）
 */
function renderTaskDetails(task) {
    // Find the inline container inside the matching task card
    const taskCard = document.querySelector(`.task-item[data-task-id="${task.id}"]`);
    if (!taskCard) return;

    const container = taskCard.querySelector('.task-details-inline > .card-body');
    if (!container) return;

    // 確保進度值正確
    if (task.status === 'completed') {
        task.progress = 100.0;
    }

    // 構建詳情 HTML
    const startTime = new Date(task.start_time * 1000);
    let html = `<div class="task-details">`;

    // 來源名稱
    if (task.source_name) {
        html += `<div class="mb-3"><h6>來源</h6><p>${escapeHtml(task.source_name)}</p></div>`;
    }

    // 任務 ID
    html += `<div class="mb-3"><h6>任務 ID</h6><p>${escapeHtml(task.id)}</p></div>`;

    // 狀態
    html += `<div class="mb-3"><h6>狀態</h6><p><span class="badge task-status ${task.status}">${getStatusText(task.status)}</span></p></div>`;

    // 消息
    html += `<div class="mb-3"><h6>消息</h6><p>${escapeHtml(task.message)}</p></div>`;

    // 進度條（處理中的任務）
    if (task.status === 'processing' || task.status === 'uploading' || task.status === 'queued') {
        html += `<div class="mb-3"><h6>進度</h6>
            <div class="progress" style="height: 10px;">
                <div class="progress-bar" role="progressbar" style="width: ${task.progress}%;" 
                     aria-valuenow="${task.progress}" aria-valuemin="0" aria-valuemax="100"></div>
            </div>
            <p class="text-end mt-1"><small>${task.progress.toFixed(1)}%</small></p></div>`;
    }

    // 開始時間
    html += `<div class="mb-3"><h6>開始時間</h6><p>${formatDateTime(startTime)}</p></div>`;

    // 結束時間和處理時間
    if (task.end_time) {
        const endTime = new Date(task.end_time * 1000);
        const duration = task.end_time - task.start_time;
        html += `<div class="mb-3"><h6>完成時間</h6><p>${formatDateTime(endTime)}</p></div>`;
        html += `<div class="mb-3"><h6>處理時間</h6><p>${formatDuration(duration)}</p></div>`;
    }

    // 錯誤信息
    if (task.error) {
        html += `<div class="mb-3"><h6>錯誤</h6><div class="alert alert-danger">${escapeHtml(task.error)}</div></div>`;
    }

    // 結果文件
    if (task.result && task.result.files) {
        html += `<div class="mb-3"><h6>結果文件</h6><div class="list-group task-results">`;

        // 字幕編輯器按鈕
        const hasEditableSubtitles = task.result.files.json || task.result.files.updated_json;
        if (hasEditableSubtitles) {
            html += `<div class="list-group-item list-group-item-action d-flex justify-content-between align-items-center bg-light">
                <span><i class="bi bi-pencil-square text-primary"></i> 字幕編輯器</span>
                <button class="btn btn-sm btn-primary subtitle-editor-btn" data-task-id="${escapeHtml(task.id)}" onclick="openSubtitleEditor('${escapeHtml(task.id)}')">
                    <i class="bi bi-box-arrow-up-right"></i> 開啟
                </button>
            </div>`;
        }

        // 文件列表
        const typeNames = {
            txt: '純文本 (TXT)', srt: '字幕 (SRT)', vtt: '網頁字幕 (VTT)',
            json: '詳細數據 (JSON)', segments_txt: '分段文本 (TXT)'
        };
        Object.entries(task.result.files).forEach(([type, path]) => {
            const typeName = typeNames[type] || type;
            html += `<a href="/download/${encodeURIComponent(task.id)}/${encodeURIComponent(type)}" 
                class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" download>
                <span>${typeName}</span>
                <button class="btn btn-sm btn-outline-primary"><i class="bi bi-download"></i> 下載</button>
            </a>`;
        });

        html += `</div></div>`;
    }

    html += `</div>`;

    container.innerHTML = html;
}

/**
 * HTML 轉義（防止 XSS）
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 顯示 GPU 信息
 */
async function showGpuInfo() {
    try {
        // 顯示模態框
        const modal = new bootstrap.Modal(document.getElementById('gpu-info-modal'));
        modal.show();
        
        // 獲取 GPU 信息
        const response = await fetch('/gpu-info');
        if (!response.ok) {
            document.getElementById('gpu-info-content').innerHTML = `
                <div class="alert alert-danger">
                    獲取 GPU 信息失敗
                </div>
            `;
            return;
        }
        
        const gpuInfo = await response.json();
        
        // 渲染 GPU 信息
        renderGpuInfo(gpuInfo);
    } catch (error) {
        console.error('顯示 GPU 信息時出錯:', error);
        document.getElementById('gpu-info-content').innerHTML = `
            <div class="alert alert-danger">
                獲取 GPU 信息時出錯: ${error.message}
            </div>
        `;
    }
}

/**
 * 渲染 GPU 信息
 */
function renderGpuInfo(gpuInfo) {
    const container = document.getElementById('gpu-info-content');
    if (!container) return;
    
    let html = '';
    
    if (gpuInfo.available) {
        html += `
            <div class="alert alert-success">
                <i class="bi bi-check-circle-fill me-2"></i>
                檢測到 ${gpuInfo.device_count} 個 GPU 設備
            </div>
            <table class="table table-sm">
                <thead>
                    <tr>
                        <th>設備</th>
                        <th>名稱</th>
                        <th>已分配</th>
                        <th>已保留</th>
                        <th>總記憶體</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        gpuInfo.devices.forEach((device, index) => {
            html += `
                <tr>
                    <td>${index}</td>
                    <td>${device.name}</td>
                    <td>${device.memory_allocated}</td>
                    <td>${device.memory_reserved}</td>
                    <td>${device.max_memory}</td>
                </tr>
            `;
        });
        
        html += `
                </tbody>
            </table>
        `;
    } else {
        html += `
            <div class="alert alert-warning">
                <i class="bi bi-exclamation-triangle-fill me-2"></i>
                未檢測到可用的 GPU 設備，將使用 CPU 進行處理
            </div>
        `;
    }
    
    container.innerHTML = html;
}

/**
 * 獲取狀態文本
 */
function getStatusText(status) {
    switch (status) {
        case 'queued':
            return '排隊中';
        case 'uploading':
            return '上傳中';
        case 'processing':
            return '處理中';
        case 'completed':
            return '已完成';
        case 'failed':
            return '失敗';
        default:
            return status;
    }
}

/**
 * 格式化日期時間
 */
function formatDateTime(date) {
    return date.toLocaleString('zh-TW', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

/**
 * 格式化持續時間
 */
function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    let result = '';
    if (hours > 0) {
        result += `${hours} 小時 `;
    }
    if (minutes > 0 || hours > 0) {
        result += `${minutes} 分鐘 `;
    }
    result += `${secs} 秒`;
    
    return result;
}

/**
 * 選擇本地音頻/視頻檔案
 */
async function selectLocalFile() {
    try {
        // 創建模態框實例
        const directoryModal = new bootstrap.Modal(document.getElementById('directory-picker-modal'));
        
        // 設置模態框標題
        document.querySelector('#directory-picker-modal-label .modal-title-text').textContent = '選擇音頻/視頻檔案';
        document.querySelector('.directory-mode-icon').style.display = 'none';
        document.querySelector('.file-mode-icon').style.display = 'inline-block';
        
        // 清空已選擇的路徑
        document.getElementById('selected-directory').value = '';
        
        // 清空麵包屑
        document.getElementById('directory-breadcrumb').innerHTML = `
            <li class="breadcrumb-item active" aria-current="page">根目錄</li>
        `;
        
        // 清空子目錄區域
        document.getElementById('subdirectories-container').innerHTML = `
            <div class="text-center py-3">
                <p>請從左側選擇一個目錄</p>
            </div>
        `;
        
        // 設置模態框為檔案選擇模式
        document.getElementById('directory-picker-modal').dataset.mode = 'file';
        
        // 顯示檔案選擇模式提示，隱藏目錄選擇模式提示
        document.querySelector('.file-mode-hint').style.display = 'block';
        document.querySelector('.directory-mode-hint').style.display = 'none';
        
        // 載入系統目錄
        await loadSystemDirectories();
        
        // 顯示模態框
        directoryModal.show();
        
        // 設置確認按鈕事件
        document.getElementById('confirm-directory-btn').onclick = function() {
            const selectedPath = document.getElementById('selected-directory').value;
            if (selectedPath) {
                // 確認是否選擇了檔案
                const isFile = document.querySelector('.file-card.selected') !== null;
                
                if (isFile || confirm('您選擇的似乎是一個目錄而不是檔案，是否確認使用？')) {
                    // 設置輸入框值
                    document.getElementById('local-file-path').value = selectedPath;
                    
                    // 關閉模態框
                    directoryModal.hide();
                    
                    // 顯示成功消息
                    showSuccess(`已選擇${isFile ? '檔案' : '目錄'}: ${selectedPath}`);
                }
            } else {
                showError('請選擇一個檔案');
            }
        };
    } catch (error) {
        console.error('選擇本地檔案時出錯:', error);
        showError(`選擇檔案時出錯: ${error.message}`);
    }
}

/**
 * 選擇輸出目錄
 */
async function selectOutputDirectory() {
    try {
        // 創建模態框實例
        const directoryModal = new bootstrap.Modal(document.getElementById('directory-picker-modal'));
        
        // 清空已選擇的路徑
        document.getElementById('selected-directory').value = '';
        
        // 清空麵包屑
        document.getElementById('directory-breadcrumb').innerHTML = `
            <li class="breadcrumb-item active" aria-current="page">根目錄</li>
        `;
        
        // 清空子目錄區域
        document.getElementById('subdirectories-container').innerHTML = `
            <div class="text-center py-3">
                <p>請從左側選擇一個目錄</p>
            </div>
        `;
        
        // 載入系統目錄
        await loadSystemDirectories();
        
        // 顯示模態框
        directoryModal.show();
        
        // 設置確認按鈕事件
        document.getElementById('confirm-directory-btn').onclick = function() {
            const selectedDir = document.getElementById('selected-directory').value;
            if (selectedDir) {
                document.getElementById('output-dir').value = selectedDir;
                directoryModal.hide();
                showSuccess(`已選擇目錄: ${selectedDir}`);
            } else {
                showError('請選擇一個目錄');
            }
        };
    } catch (error) {
        console.error('選擇輸出目錄時出錯:', error);
        showError(`選擇目錄時出錯: ${error.message}`);
    }
}

// 載入系統目錄
async function loadSystemDirectories() {
    try {
        const response = await fetch('/system/directories');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        renderDirectoryTree(data.directories);
    } catch (error) {
        console.error('載入系統目錄時出錯:', error);
        document.getElementById('directory-tree').innerHTML = `
            <div class="alert alert-danger">
                載入目錄失敗: ${error.message}
            </div>
        `;
    }
}

// 渲染目錄樹
function renderDirectoryTree(directories) {
    const treeContainer = document.getElementById('directory-tree');
    treeContainer.innerHTML = '';
    
    directories.forEach(dir => {
        const item = document.createElement('a');
        item.href = '#';
        item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
        
        // 顯示目錄名稱（取最後一部分）
        const dirName = dir.split(/[\/\\]/).filter(Boolean).pop() || dir;
        
        item.innerHTML = `
            <span><i class="bi bi-folder"></i> ${dirName}</span>
            <i class="bi bi-chevron-right"></i>
        `;
        
        item.onclick = function(e) {
            e.preventDefault();
            loadSubdirectories(dir);
            
            // 清空麵包屑並添加當前項目
            updateBreadcrumb([{ name: dirName, path: dir }]);
            
            // 更新選擇的目錄（如果是目錄選擇模式）
            const pickerMode = document.getElementById('directory-picker-modal').dataset.mode || 'directory';
            if (pickerMode === 'directory') {
                document.getElementById('selected-directory').value = dir;
            } else {
                // 在文件選擇模式下，清空選擇
                document.getElementById('selected-directory').value = '';
                // 移除任何已選中的文件
                document.querySelectorAll('.file-card.selected').forEach(card => {
                    card.classList.remove('selected');
                });
            }
        };
        
        treeContainer.appendChild(item);
    });
}

// 載入子目錄
async function loadSubdirectories(path) {
    try {
        const response = await fetch(`/system/subdirectories?path=${encodeURIComponent(path)}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        renderSubdirectories(data, path);
    } catch (error) {
        console.error('載入子目錄時出錯:', error);
        document.getElementById('subdirectories-container').innerHTML = `
            <div class="alert alert-danger">
                載入子目錄失敗: ${error.message}
            </div>
        `;
    }
}

// 渲染子目錄和檔案
function renderSubdirectories(data, parentPath) {
    // 獲取DOM元素
    const container = document.getElementById('subdirectories-container');
    
    // 獲取選擇器模式
    const pickerMode = document.getElementById('directory-picker-modal').dataset.mode || 'directory';
    const isFilePicker = pickerMode === 'file';
    
    // 清空容器內容
    container.innerHTML = '';
    
    // 檢查是否有內容
    if (!data || ((!data.subdirectories || data.subdirectories.length === 0) && 
                 (!data.files || data.files.length === 0))) {
        container.innerHTML = `
            <div class="alert alert-info">
                此目錄下沒有內容
            </div>
        `;
        return;
    }
    
    // 顯示子目錄
    if (data.subdirectories && data.subdirectories.length > 0) {
        // 添加標題
        const dirTitle = document.createElement('h6');
        dirTitle.className = 'mb-3';
        dirTitle.innerHTML = '<i class="bi bi-folder"></i> 子目錄';
        container.appendChild(dirTitle);
        
        // 創建目錄行
        const dirRow = document.createElement('div');
        dirRow.className = 'row g-3 mb-4';
        
        // 處理每個子目錄
        data.subdirectories.forEach(subdir => {
            // 創建列
            const col = document.createElement('div');
            col.className = 'col-md-4 mb-3';
            
            // 創建卡片
            const card = document.createElement('div');
            card.className = 'card h-100 directory-card';
            
            // 設置卡片內容
            card.innerHTML = `
                <div class="card-body">
                    <h6 class="card-title"><i class="bi bi-folder2"></i> ${subdir.name}</h6>
                </div>
            `;
            
            // 設置點擊事件
            card.onclick = function() {
                // 加載子目錄
                loadSubdirectories(subdir.path);
                
                // 更新麵包屑
                // 獲取當前麵包屑路徑
                const breadcrumb = document.getElementById('directory-breadcrumb');
                const items = Array.from(breadcrumb.querySelectorAll('li'))
                    .map(li => {
                        return {
                            name: li.textContent,
                            path: li.dataset.path || ''
                        };
                    });
                
                // 如果當前項為活動項，則替換，否則添加
                if (items.length > 0 && items[items.length - 1].name === '根目錄') {
                    items.pop();
                }
                
                // 添加新項
                items.push({
                    name: subdir.name,
                    path: subdir.path
                });
                
                // 更新麵包屑
                updateBreadcrumb(items);
                
                // 更新選擇的目錄
                document.getElementById('selected-directory').value = subdir.path;
            };
            
            // 添加到容器
            col.appendChild(card);
            dirRow.appendChild(col);
        });
        
        container.appendChild(dirRow);
    }
    
    // 顯示檔案（如果有）
    if (data.files && data.files.length > 0) {
        // 添加標題
        const fileTitle = document.createElement('h6');
        fileTitle.className = 'mb-3';
        fileTitle.innerHTML = '<i class="bi bi-file-earmark-music"></i> 音頻/視頻檔案';
        container.appendChild(fileTitle);
        
        // 創建檔案行
        const fileRow = document.createElement('div');
        fileRow.className = 'row g-3';
        
        // 處理每個檔案
        data.files.forEach(file => {
            // 創建列
            const col = document.createElement('div');
            col.className = 'col-md-4 mb-3';
            
            // 選擇圖標
            let fileIcon = 'bi-file-earmark';
            if (['.mp3', '.wav', '.ogg', '.flac', '.aac'].includes(file.extension)) {
                fileIcon = 'bi-file-earmark-music';
            } else if (['.mp4', '.avi', '.mov', '.mkv', '.webm'].includes(file.extension)) {
                fileIcon = 'bi-file-earmark-play';
            }
            
            // 創建卡片
            const card = document.createElement('div');
            card.className = 'card h-100 file-card';
            
            // 設置卡片內容
            card.innerHTML = `
                <div class="card-body">
                    <h6 class="card-title"><i class="bi ${fileIcon}"></i> ${file.name}</h6>
                    <p class="card-text small text-muted">${file.size || ''}</p>
                </div>
            `;
            
            // 添加到容器
            col.appendChild(card);
            fileRow.appendChild(col);
        });
        
        container.appendChild(fileRow);
    }
}

// 更新麵包屑
function updateBreadcrumb(items) {
    const breadcrumb = document.getElementById('directory-breadcrumb');
    breadcrumb.innerHTML = '';
    
    // 如果沒有項目，顯示根目錄
    if (!items || items.length === 0) {
        const rootLi = document.createElement('li');
        rootLi.className = 'breadcrumb-item active';
        rootLi.setAttribute('aria-current', 'page');
        rootLi.textContent = '根目錄';
        breadcrumb.appendChild(rootLi);
        return;
    }
    
    // 渲染所有麵包屑項目
    items.forEach((item, index) => {
        const li = document.createElement('li');
        li.className = 'breadcrumb-item';
        li.dataset.path = item.path || '';
        
        if (index === items.length - 1) {
            // 最後一個項目為當前活動項
            li.className += ' active';
            li.setAttribute('aria-current', 'page');
            li.textContent = item.name;
        } else {
            // 其他項目為可點擊的鏈接
            const a = document.createElement('a');
            a.href = '#';
            a.textContent = item.name;
            
            // 設置點擊事件
            a.onclick = function(e) {
                e.preventDefault();
                
                // 如果點擊的是根目錄，重置並載入系統目錄
                if (index === 0 && item.name === '根目錄') {
                    loadSystemDirectories();
                    updateBreadcrumb([{name: '根目錄', path: ''}]);
                    return;
                }
                
                // 載入對應的目錄
                if (item.path) {
                    loadSubdirectories(item.path);
                    
                    // 截取麵包屑導航
                    const newItems = items.slice(0, index + 1);
                    updateBreadcrumb(newItems);
                    
                    // 設置選定目錄
                    document.getElementById('selected-directory').value = item.path;
                }
            };
            
            li.appendChild(a);
        }
        
        breadcrumb.appendChild(li);
    });
} 
/**

 * 開啟字幕編輯器
 */
async function openSubtitleEditor(taskId) {
    try {
        // 顯示載入提示
        showLoading('正在開啟字幕編輯器...');
        
        // 檢查任務狀態
        const taskResponse = await fetch(`/tasks/${taskId}`);
        if (!taskResponse.ok) {
            throw new Error('無法獲取任務資訊');
        }
        
        const taskData = await taskResponse.json();
        
        // 確認任務已完成
        if (taskData.status !== 'completed') {
            throw new Error('任務尚未完成，無法開啟字幕編輯器');
        }
        
        // 檢查是否有字幕資料
        if (!taskData.result || !taskData.result.files || 
            (!taskData.result.files.srt && !taskData.result.files.json)) {
            throw new Error('找不到字幕資料');
        }
        
        // 檢查字幕 API 是否可用
        const subtitleResponse = await fetch(`/api/subtitles/${taskId}`, {
            method: 'HEAD'
        });
        
        if (!subtitleResponse.ok && subtitleResponse.status !== 404) {
            throw new Error('字幕 API 服務不可用');
        }
        
        // 隱藏載入提示
        hideLoading();
        
        // 開啟字幕編輯器頁面
        const editorUrl = `/subtitle-editor/${taskId}`;
        const editorWindow = window.open(editorUrl, '_blank', 'width=1200,height=800,scrollbars=yes,resizable=yes');
        
        if (!editorWindow) {
            throw new Error('無法開啟字幕編輯器視窗，請檢查瀏覽器的彈出視窗設定');
        }
        
        // 監聽視窗載入完成
        const checkWindow = setInterval(() => {
            try {
                if (editorWindow.closed) {
                    clearInterval(checkWindow);
                    console.log('字幕編輯器視窗已關閉');
                    return;
                }
                
                // 檢查視窗是否載入完成
                if (editorWindow.document && editorWindow.document.readyState === 'complete') {
                    clearInterval(checkWindow);
                    console.log('字幕編輯器已成功開啟');
                    
                    // 顯示成功提示
                    showSuccess('字幕編輯器已開啟');
                }
            } catch (e) {
                // 跨域錯誤是正常的，忽略
                if (e.name === 'SecurityError') {
                    clearInterval(checkWindow);
                    showSuccess('字幕編輯器已開啟');
                }
            }
        }, 500);
        
        // 5秒後停止檢查
        setTimeout(() => {
            clearInterval(checkWindow);
        }, 5000);
        
    } catch (error) {
        hideLoading();
        console.error('開啟字幕編輯器時發生錯誤:', error);
        showError(`開啟字幕編輯器失敗: ${error.message}`);
    }
}

/**
 * 檢查字幕編輯器可用性
 */
async function checkSubtitleEditorAvailability(taskId) {
    try {
        // 檢查任務是否存在且已完成
        const taskResponse = await fetch(`/tasks/${taskId}`);
        if (!taskResponse.ok) {
            return { available: false, reason: '任務不存在' };
        }
        
        const taskData = await taskResponse.json();
        
        if (taskData.status !== 'completed') {
            return { available: false, reason: '任務尚未完成' };
        }
        
        // 檢查是否有字幕檔案
        if (!taskData.result || !taskData.result.files) {
            return { available: false, reason: '沒有結果檔案' };
        }
        
        if (!taskData.result.files.srt && !taskData.result.files.json) {
            return { available: false, reason: '沒有字幕檔案' };
        }
        
        return { available: true };
        
    } catch (error) {
        console.error('檢查字幕編輯器可用性時發生錯誤:', error);
        return { available: false, reason: '檢查失敗' };
    }
}

/**
 * 更新字幕編輯器按鈕狀態
 */
function updateSubtitleEditorButton(button, taskId) {
    checkSubtitleEditorAvailability(taskId).then(result => {
        if (result.available) {
            button.disabled = false;
            button.title = '開啟字幕編輯器';
            button.classList.remove('btn-secondary');
            button.classList.add('btn-primary');
        } else {
            button.disabled = true;
            button.title = `無法開啟字幕編輯器: ${result.reason}`;
            button.classList.remove('btn-primary');
            button.classList.add('btn-secondary');
        }
    });
}
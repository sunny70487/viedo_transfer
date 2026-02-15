/**
 * 主題設定界面組件
 * 提供主題偏好設定的使用者界面
 */
class ThemeSettings {
    constructor(options = {}) {
        this.options = {
            modalId: 'theme-settings-modal',
            storageKey: 'whisper-app-theme-settings',
            ...options
        };
        
        this.themeManager = window.themeManager;
        this.settings = this.loadSettings();
        
        this.init();
    }
    
    /**
     * 初始化主題設定界面
     */
    init() {
        this.createModal();
        this.setupEventListeners();
        this.updateUI();
        
        console.log('ThemeSettings initialized');
    }
    
    /**
     * 創建主題設定模態框
     */
    createModal() {
        // 檢查是否已存在模態框
        if (document.getElementById(this.options.modalId)) {
            return;
        }
        
        const modalHTML = `
            <div class="modal fade" id="${this.options.modalId}" tabindex="-1" aria-labelledby="${this.options.modalId}-label" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="${this.options.modalId}-label">
                                <i class="bi bi-palette"></i> 主題設定
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <!-- 主題選擇 -->
                            <div class="mb-4">
                                <h6 class="mb-3">主題模式</h6>
                                <div class="row g-3">
                                    <div class="col-4">
                                        <div class="theme-option" data-theme="light">
                                            <div class="theme-preview theme-preview-light">
                                                <i class="bi bi-sun-fill fs-4"></i>
                                                <div class="mt-2">淺色模式</div>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="col-4">
                                        <div class="theme-option" data-theme="dark">
                                            <div class="theme-preview theme-preview-dark">
                                                <i class="bi bi-moon-fill fs-4"></i>
                                                <div class="mt-2">深色模式</div>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="col-4">
                                        <div class="theme-option" data-theme="auto">
                                            <div class="theme-preview">
                                                <i class="bi bi-circle-half fs-4"></i>
                                                <div class="mt-2">跟隨系統</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- 進階設定 -->
                            <div class="mb-4">
                                <h6 class="mb-3">進階設定</h6>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="auto-detect-checkbox">
                                    <label class="form-check-label" for="auto-detect-checkbox">
                                        自動檢測系統主題偏好
                                    </label>
                                    <div class="form-text">
                                        當系統主題變更時自動切換應用主題
                                    </div>
                                </div>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="smooth-transition-checkbox">
                                    <label class="form-check-label" for="smooth-transition-checkbox">
                                        啟用平滑過渡動畫
                                    </label>
                                    <div class="form-text">
                                        主題切換時使用動畫效果
                                    </div>
                                </div>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="remember-preference-checkbox">
                                    <label class="form-check-label" for="remember-preference-checkbox">
                                        記住主題偏好
                                    </label>
                                    <div class="form-text">
                                        在瀏覽器中儲存主題設定
                                    </div>
                                </div>
                            </div>
                            
                            <!-- 系統資訊 -->
                            <div class="mb-4">
                                <h6 class="mb-3">系統資訊</h6>
                                <div class="row">
                                    <div class="col-6">
                                        <small class="text-muted">當前主題:</small>
                                        <div id="current-theme-display" class="fw-bold"></div>
                                    </div>
                                    <div class="col-6">
                                        <small class="text-muted">系統主題:</small>
                                        <div id="system-theme-display" class="fw-bold"></div>
                                    </div>
                                </div>
                                <div class="row mt-2">
                                    <div class="col-6">
                                        <small class="text-muted">支援深色模式:</small>
                                        <div id="dark-mode-support" class="fw-bold"></div>
                                    </div>
                                    <div class="col-6">
                                        <small class="text-muted">已儲存偏好:</small>
                                        <div id="stored-preference" class="fw-bold"></div>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- 重置選項 -->
                            <div class="mb-3">
                                <h6 class="mb-3">重置選項</h6>
                                <button type="button" class="btn btn-outline-warning btn-sm" id="reset-theme-settings">
                                    <i class="bi bi-arrow-clockwise"></i> 重置為預設值
                                </button>
                                <button type="button" class="btn btn-outline-danger btn-sm ms-2" id="clear-theme-data">
                                    <i class="bi bi-trash"></i> 清除所有資料
                                </button>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" id="save-theme-settings">
                                <i class="bi bi-check"></i> 儲存設定
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        
        // 添加主題選項樣式
        const style = document.createElement('style');
        style.textContent = `
            .theme-option {
                cursor: pointer;
                border-radius: var(--theme-border-radius);
                transition: all 0.2s ease;
            }
            
            .theme-option:hover {
                transform: translateY(-2px);
                box-shadow: var(--theme-shadow);
            }
            
            .theme-option.selected {
                transform: translateY(-2px);
                box-shadow: var(--theme-shadow);
                border: 2px solid var(--theme-primary);
            }
            
            .theme-preview {
                padding: 1rem;
                text-align: center;
                border-radius: var(--theme-border-radius);
                border: 1px solid var(--theme-border-primary);
                background: var(--theme-bg-primary);
                color: var(--theme-text-primary);
                transition: all 0.2s ease;
            }
            
            .theme-preview-light {
                background: #ffffff;
                color: #212529;
                border-color: #dee2e6;
            }
            
            .theme-preview-dark {
                background: #1a1a1a;
                color: #ffffff;
                border-color: #404040;
            }
        `;
        document.head.appendChild(style);
    }
    
    /**
     * 設置事件監聽器
     */
    setupEventListeners() {
        const modal = document.getElementById(this.options.modalId);
        if (!modal) return;
        
        // 主題選項點擊
        modal.querySelectorAll('.theme-option').forEach(option => {
            option.addEventListener('click', (e) => {
                const theme = option.dataset.theme;
                this.selectTheme(theme);
            });
        });
        
        // 設定變更
        const autoDetectCheckbox = modal.querySelector('#auto-detect-checkbox');
        const smoothTransitionCheckbox = modal.querySelector('#smooth-transition-checkbox');
        const rememberPreferenceCheckbox = modal.querySelector('#remember-preference-checkbox');
        
        if (autoDetectCheckbox) {
            autoDetectCheckbox.addEventListener('change', (e) => {
                this.settings.autoDetect = e.target.checked;
                this.updateThemeManager();
            });
        }
        
        if (smoothTransitionCheckbox) {
            smoothTransitionCheckbox.addEventListener('change', (e) => {
                this.settings.smoothTransition = e.target.checked;
            });
        }
        
        if (rememberPreferenceCheckbox) {
            rememberPreferenceCheckbox.addEventListener('change', (e) => {
                this.settings.rememberPreference = e.target.checked;
            });
        }
        
        // 重置按鈕
        const resetButton = modal.querySelector('#reset-theme-settings');
        if (resetButton) {
            resetButton.addEventListener('click', () => {
                this.resetSettings();
            });
        }
        
        // 清除資料按鈕
        const clearButton = modal.querySelector('#clear-theme-data');
        if (clearButton) {
            clearButton.addEventListener('click', () => {
                this.clearAllData();
            });
        }
        
        // 儲存按鈕
        const saveButton = modal.querySelector('#save-theme-settings');
        if (saveButton) {
            saveButton.addEventListener('click', () => {
                this.saveSettings();
                bootstrap.Modal.getInstance(modal).hide();
            });
        }
        
        // 模態框顯示時更新 UI
        modal.addEventListener('show.bs.modal', () => {
            this.updateUI();
        });
    }
    
    /**
     * 選擇主題
     */
    selectTheme(theme) {
        const modal = document.getElementById(this.options.modalId);
        if (!modal) return;
        
        // 更新選中狀態
        modal.querySelectorAll('.theme-option').forEach(option => {
            option.classList.remove('selected');
        });
        
        const selectedOption = modal.querySelector(`[data-theme="${theme}"]`);
        if (selectedOption) {
            selectedOption.classList.add('selected');
        }
        
        // 更新設定
        this.settings.selectedTheme = theme;
        
        // 應用主題
        if (theme === 'auto') {
            this.settings.autoDetect = true;
            if (this.themeManager) {
                this.themeManager.options.autoDetect = true;
                this.themeManager.setTheme(this.themeManager.systemTheme);
            }
        } else {
            this.settings.autoDetect = false;
            if (this.themeManager) {
                this.themeManager.options.autoDetect = false;
                this.themeManager.setTheme(theme);
            }
        }
        
        this.updateThemeManager();
        this.updateSystemInfo();
    }
    
    /**
     * 更新主題管理器設定
     */
    updateThemeManager() {
        if (!this.themeManager) return;
        
        this.themeManager.options.autoDetect = this.settings.autoDetect;
        this.themeManager.options.animationDuration = this.settings.smoothTransition ? 300 : 0;
    }
    
    /**
     * 更新 UI 顯示
     */
    updateUI() {
        const modal = document.getElementById(this.options.modalId);
        if (!modal) return;
        
        // 更新主題選擇
        modal.querySelectorAll('.theme-option').forEach(option => {
            option.classList.remove('selected');
        });
        
        const selectedOption = modal.querySelector(`[data-theme="${this.settings.selectedTheme}"]`);
        if (selectedOption) {
            selectedOption.classList.add('selected');
        }
        
        // 更新複選框
        const autoDetectCheckbox = modal.querySelector('#auto-detect-checkbox');
        const smoothTransitionCheckbox = modal.querySelector('#smooth-transition-checkbox');
        const rememberPreferenceCheckbox = modal.querySelector('#remember-preference-checkbox');
        
        if (autoDetectCheckbox) {
            autoDetectCheckbox.checked = this.settings.autoDetect;
        }
        
        if (smoothTransitionCheckbox) {
            smoothTransitionCheckbox.checked = this.settings.smoothTransition;
        }
        
        if (rememberPreferenceCheckbox) {
            rememberPreferenceCheckbox.checked = this.settings.rememberPreference;
        }
        
        // 更新系統資訊
        this.updateSystemInfo();
    }
    
    /**
     * 更新系統資訊顯示
     */
    updateSystemInfo() {
        const modal = document.getElementById(this.options.modalId);
        if (!modal || !this.themeManager) return;
        
        const stats = this.themeManager.getThemeStats();
        
        const currentThemeDisplay = modal.querySelector('#current-theme-display');
        const systemThemeDisplay = modal.querySelector('#system-theme-display');
        const darkModeSupportDisplay = modal.querySelector('#dark-mode-support');
        const storedPreferenceDisplay = modal.querySelector('#stored-preference');
        
        if (currentThemeDisplay) {
            currentThemeDisplay.textContent = stats.currentTheme === 'dark' ? '深色模式' : '淺色模式';
        }
        
        if (systemThemeDisplay) {
            systemThemeDisplay.textContent = stats.systemTheme === 'dark' ? '深色模式' : '淺色模式';
        }
        
        if (darkModeSupportDisplay) {
            darkModeSupportDisplay.textContent = stats.supportsDarkMode ? '是' : '否';
        }
        
        if (storedPreferenceDisplay) {
            storedPreferenceDisplay.textContent = stats.hasStoredPreference ? '是' : '否';
        }
    }
    
    /**
     * 載入設定
     */
    loadSettings() {
        const defaultSettings = {
            selectedTheme: 'auto',
            autoDetect: true,
            smoothTransition: true,
            rememberPreference: true
        };
        
        try {
            const stored = localStorage.getItem(this.options.storageKey);
            if (stored) {
                return { ...defaultSettings, ...JSON.parse(stored) };
            }
        } catch (error) {
            console.warn('Failed to load theme settings:', error);
        }
        
        return defaultSettings;
    }
    
    /**
     * 儲存設定
     */
    saveSettings() {
        if (!this.settings.rememberPreference) {
            this.clearSettings();
            return;
        }
        
        try {
            const settingsData = {
                ...this.settings,
                timestamp: Date.now()
            };
            
            localStorage.setItem(this.options.storageKey, JSON.stringify(settingsData));
            
            // 顯示成功訊息
            this.showMessage('設定已儲存', 'success');
            
        } catch (error) {
            console.error('Failed to save theme settings:', error);
            this.showMessage('儲存設定失敗', 'error');
        }
    }
    
    /**
     * 清除設定
     */
    clearSettings() {
        try {
            localStorage.removeItem(this.options.storageKey);
        } catch (error) {
            console.warn('Failed to clear theme settings:', error);
        }
    }
    
    /**
     * 重置設定為預設值
     */
    resetSettings() {
        this.settings = {
            selectedTheme: 'auto',
            autoDetect: true,
            smoothTransition: true,
            rememberPreference: true
        };
        
        this.selectTheme('auto');
        this.updateUI();
        this.showMessage('設定已重置為預設值', 'info');
    }
    
    /**
     * 清除所有資料
     */
    clearAllData() {
        if (confirm('確定要清除所有主題資料嗎？此操作無法復原。')) {
            this.clearSettings();
            
            if (this.themeManager) {
                this.themeManager.clearThemePreference();
            }
            
            this.resetSettings();
            this.showMessage('所有主題資料已清除', 'warning');
        }
    }
    
    /**
     * 顯示訊息
     */
    showMessage(message, type = 'info') {
        // 創建訊息元素
        const messageEl = document.createElement('div');
        messageEl.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
        messageEl.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        messageEl.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(messageEl);
        
        // 自動移除
        setTimeout(() => {
            if (messageEl.parentNode) {
                messageEl.remove();
            }
        }, 5000);
    }
    
    /**
     * 顯示主題設定模態框
     */
    show() {
        const modal = document.getElementById(this.options.modalId);
        if (modal) {
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();
        }
    }
    
    /**
     * 隱藏主題設定模態框
     */
    hide() {
        const modal = document.getElementById(this.options.modalId);
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) {
                bsModal.hide();
            }
        }
    }
    
    /**
     * 銷毀主題設定組件
     */
    destroy() {
        const modal = document.getElementById(this.options.modalId);
        if (modal) {
            modal.remove();
        }
    }
}

// 全域主題設定實例
window.themeSettings = null;

// DOM 載入完成後自動初始化
document.addEventListener('DOMContentLoaded', function() {
    // 等待主題管理器初始化完成
    setTimeout(() => {
        if (!window.themeSettings && window.themeManager) {
            window.themeSettings = new ThemeSettings();
        }
    }, 100);
});
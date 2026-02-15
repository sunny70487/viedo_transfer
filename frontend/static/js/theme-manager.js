/**
 * 主題管理系統
 * 負責處理深色/淺色模式的切換、持久化和自動檢測
 */
class ThemeManager {
    constructor(options = {}) {
        this.options = {
            storageKey: 'whisper-app-theme',
            defaultTheme: 'light',
            autoDetect: true,
            animationDuration: 300,
            ...options
        };
        
        this.currentTheme = null;
        this.systemTheme = null;
        this.listeners = new Map();
        
        this.init();
    }
    
    /**
     * 初始化主題管理器
     */
    init() {
        // 檢測系統主題偏好
        this.detectSystemTheme();
        
        // 監聽系統主題變化
        this.watchSystemTheme();
        
        // 載入儲存的主題偏好
        const savedTheme = this.loadThemePreference();
        
        // 決定初始主題
        const initialTheme = savedTheme || (this.options.autoDetect ? this.systemTheme : this.options.defaultTheme);
        
        // 應用初始主題
        this.setTheme(initialTheme, false);
        
        // 設置主題切換按鈕事件
        this.setupThemeToggle();
        
        console.log('ThemeManager initialized:', {
            currentTheme: this.currentTheme,
            systemTheme: this.systemTheme,
            autoDetect: this.options.autoDetect
        });
    }
    
    /**
     * 檢測系統主題偏好
     */
    detectSystemTheme() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            this.systemTheme = 'dark';
        } else {
            this.systemTheme = 'light';
        }
    }
    
    /**
     * 監聽系統主題變化
     */
    watchSystemTheme() {
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            
            // 使用新的 addEventListener 方法
            if (mediaQuery.addEventListener) {
                mediaQuery.addEventListener('change', (e) => {
                    this.systemTheme = e.matches ? 'dark' : 'light';
                    this.emit('systemThemeChanged', { theme: this.systemTheme });
                    
                    // 如果啟用自動檢測且沒有手動設置過主題，則跟隨系統主題
                    if (this.options.autoDetect && !this.loadThemePreference()) {
                        this.setTheme(this.systemTheme);
                    }
                });
            } else {
                // 舊版瀏覽器的兼容性處理
                mediaQuery.addListener((e) => {
                    this.systemTheme = e.matches ? 'dark' : 'light';
                    this.emit('systemThemeChanged', { theme: this.systemTheme });
                    
                    if (this.options.autoDetect && !this.loadThemePreference()) {
                        this.setTheme(this.systemTheme);
                    }
                });
            }
        }
    }
    
    /**
     * 獲取當前主題
     * @returns {string} 當前主題名稱
     */
    getCurrentTheme() {
        return this.currentTheme;
    }
    
    /**
     * 設置主題
     * @param {string} theme - 主題名稱 ('light' 或 'dark')
     * @param {boolean} animate - 是否使用動畫效果
     */
    setTheme(theme, animate = true) {
        if (!theme || (theme !== 'light' && theme !== 'dark')) {
            console.warn('Invalid theme:', theme);
            return;
        }
        
        const previousTheme = this.currentTheme;
        this.currentTheme = theme;
        
        // 應用主題
        this.applyTheme(theme, animate);
        
        // 儲存主題偏好
        this.saveThemePreference(theme);
        
        // 更新主題切換按鈕
        this.updateThemeToggleButton();
        
        // 觸發主題變更事件
        this.emit('themeChanged', {
            theme: theme,
            previousTheme: previousTheme
        });
        
        console.log('Theme changed:', { from: previousTheme, to: theme });
    }
    
    /**
     * 切換主題
     */
    toggleTheme() {
        const newTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.setTheme(newTheme);
    }
    
    /**
     * 應用主題到 DOM
     * @param {string} theme - 主題名稱
     * @param {boolean} animate - 是否使用動畫效果
     */
    applyTheme(theme, animate = true) {
        const html = document.documentElement;
        const body = document.body;
        
        // 如果需要動畫效果，添加過渡類
        if (animate) {
            body.classList.add('theme-transition');
            
            // 動畫結束後移除過渡類
            setTimeout(() => {
                body.classList.remove('theme-transition');
            }, this.options.animationDuration);
        }
        
        // 設置 Bootstrap 主題屬性
        html.setAttribute('data-bs-theme', theme);
        
        // 設置自定義主題類
        body.classList.remove('theme-light', 'theme-dark');
        body.classList.add(`theme-${theme}`);
        
        // 更新 meta theme-color (用於移動設備)
        this.updateMetaThemeColor(theme);
        
        // 觸發主題應用事件
        this.emit('themeApplied', { theme: theme });
    }
    
    /**
     * 更新 meta theme-color
     * @param {string} theme - 主題名稱
     */
    updateMetaThemeColor(theme) {
        let metaThemeColor = document.querySelector('meta[name="theme-color"]');
        
        if (!metaThemeColor) {
            metaThemeColor = document.createElement('meta');
            metaThemeColor.name = 'theme-color';
            document.head.appendChild(metaThemeColor);
        }
        
        // 設置主題顏色
        const colors = {
            light: '#ffffff',
            dark: '#1a1a1a'
        };
        
        metaThemeColor.content = colors[theme] || colors.light;
    }
    
    /**
     * 設置主題切換按鈕事件
     */
    setupThemeToggle() {
        const toggleButtons = document.querySelectorAll('#theme-toggle, [data-theme-toggle]');
        
        toggleButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                this.toggleTheme();
            });
        });
    }
    
    /**
     * 更新主題切換按鈕圖標
     */
    updateThemeToggleButton() {
        const toggleButtons = document.querySelectorAll('#theme-toggle, [data-theme-toggle]');
        
        toggleButtons.forEach(button => {
            const icon = button.querySelector('i');
            if (icon) {
                // 移除所有主題圖標類
                icon.classList.remove('bi-sun-fill', 'bi-moon-fill', 'bi-circle-half');
                
                // 根據當前主題設置圖標
                if (this.currentTheme === 'dark') {
                    icon.classList.add('bi-sun-fill');
                    button.title = '切換到淺色模式';
                } else {
                    icon.classList.add('bi-moon-fill');
                    button.title = '切換到深色模式';
                }
            }
        });
    }
    
    /**
     * 儲存主題偏好到 localStorage
     * @param {string} theme - 主題名稱
     */
    saveThemePreference(theme) {
        try {
            const themeData = {
                theme: theme,
                timestamp: Date.now(),
                autoDetect: this.options.autoDetect
            };
            
            localStorage.setItem(this.options.storageKey, JSON.stringify(themeData));
        } catch (error) {
            console.warn('Failed to save theme preference:', error);
        }
    }
    
    /**
     * 從 localStorage 載入主題偏好
     * @returns {string|null} 儲存的主題名稱
     */
    loadThemePreference() {
        try {
            const stored = localStorage.getItem(this.options.storageKey);
            if (stored) {
                const themeData = JSON.parse(stored);
                return themeData.theme;
            }
        } catch (error) {
            console.warn('Failed to load theme preference:', error);
        }
        
        return null;
    }
    
    /**
     * 清除儲存的主題偏好
     */
    clearThemePreference() {
        try {
            localStorage.removeItem(this.options.storageKey);
        } catch (error) {
            console.warn('Failed to clear theme preference:', error);
        }
    }
    
    /**
     * 獲取主題統計信息
     * @returns {Object} 主題統計信息
     */
    getThemeStats() {
        return {
            currentTheme: this.currentTheme,
            systemTheme: this.systemTheme,
            hasStoredPreference: !!this.loadThemePreference(),
            autoDetect: this.options.autoDetect,
            supportsDarkMode: window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
        };
    }
    
    /**
     * 事件監聽器管理
     */
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }
    
    off(event, callback) {
        if (this.listeners.has(event)) {
            const callbacks = this.listeners.get(event);
            const index = callbacks.indexOf(callback);
            if (index > -1) {
                callbacks.splice(index, 1);
            }
        }
    }
    
    emit(event, data) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error('Error in theme event listener:', error);
                }
            });
        }
    }
    
    /**
     * 銷毀主題管理器
     */
    destroy() {
        this.listeners.clear();
        
        // 移除事件監聽器
        const toggleButtons = document.querySelectorAll('#theme-toggle, [data-theme-toggle]');
        toggleButtons.forEach(button => {
            button.removeEventListener('click', this.toggleTheme);
        });
    }
}

// 全域主題管理器實例
window.themeManager = null;

// DOM 載入完成後自動初始化
document.addEventListener('DOMContentLoaded', function() {
    if (!window.themeManager) {
        window.themeManager = new ThemeManager();
    }
    if (window.themeManager) {
        const initialTheme = window.themeManager.getCurrentTheme() || 'light';
        const root = document.documentElement;
        root.setAttribute('data-bs-theme', initialTheme);
        root.classList.remove('theme-light', 'theme-dark');
        root.classList.add(`theme-${initialTheme}`);
    }
});
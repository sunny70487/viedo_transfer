/**
 * VideoPlayer 組件 - 封裝 HTML5 video 元素
 * 提供播放控制、時間跳轉和進度顯示功能
 * 支援鍵盤快捷鍵操作
 */

class VideoPlayer {
    constructor(videoElementId, options = {}) {
        this.videoElementId = videoElementId;
        this.options = {
            rewindStep: 10, // 後退步長（秒）
            forwardStep: 10, // 快進步長（秒）
            volumeStep: 0.1, // 音量調整步長
            enableKeyboardShortcuts: true,
            autoPlay: false,
            ...options
        };
        
        // DOM 元素引用
        this.videoElement = null;
        this.progressBar = null;
        this.volumeControl = null;
        this.playPauseBtn = null;
        this.rewindBtn = null;
        this.forwardBtn = null;
        this.currentTimeDisplay = null;
        this.totalTimeDisplay = null;
        this.playbackSpeedSelect = null;
        
        // 狀態管理
        this.isPlaying = false;
        this.currentTime = 0;
        this.duration = 0;
        this.volume = 1;
        this.playbackRate = 1;
        this.isLoaded = false;
        
        // 事件監聽器管理
        this.eventListeners = new Map();
        this.callbacks = new Map();
        
        // 初始化
        this.init();
    }
    
    /**
     * 初始化播放器
     */
    init() {
        this.videoElement = document.getElementById(this.videoElementId);
        if (!this.videoElement) {
            throw new Error(`找不到影片元素: ${this.videoElementId}`);
        }
        
        this.initControlElements();
        this.initEventListeners();
        this.initKeyboardShortcuts();
        
        console.log('VideoPlayer 初始化完成');
    }
    
    /**
     * 初始化控制元素
     */
    initControlElements() {
        // 查找控制元素
        this.progressBar = document.getElementById('video-progress');
        this.volumeControl = document.getElementById('volume-control');
        this.playPauseBtn = document.getElementById('play-pause-btn');
        this.rewindBtn = document.getElementById('rewind-btn');
        this.forwardBtn = document.getElementById('forward-btn');
        this.currentTimeDisplay = document.getElementById('current-time');
        this.totalTimeDisplay = document.getElementById('total-time');
        this.playbackSpeedSelect = document.getElementById('playback-speed');
        
        // 設置初始值
        if (this.volumeControl) {
            this.volumeControl.value = this.volume * 100;
        }
        
        if (this.playbackSpeedSelect) {
            this.playbackSpeedSelect.value = this.playbackRate.toString();
        }
    }
    
    /**
     * 初始化事件監聽器
     */
    initEventListeners() {
        // 影片元素事件
        this.addEventListener(this.videoElement, 'loadedmetadata', () => this.onLoadedMetadata());
        this.addEventListener(this.videoElement, 'timeupdate', () => this.onTimeUpdate());
        this.addEventListener(this.videoElement, 'play', () => this.onPlay());
        this.addEventListener(this.videoElement, 'pause', () => this.onPause());
        this.addEventListener(this.videoElement, 'ended', () => this.onEnded());
        this.addEventListener(this.videoElement, 'error', (e) => this.onError(e));
        this.addEventListener(this.videoElement, 'loadstart', () => this.onLoadStart());
        this.addEventListener(this.videoElement, 'canplay', () => this.onCanPlay());
        this.addEventListener(this.videoElement, 'waiting', () => this.onWaiting());
        this.addEventListener(this.videoElement, 'playing', () => this.onPlaying());
        
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
        if (this.progressBar) {
            this.addEventListener(this.progressBar, 'input', () => this.onProgressChange());
            this.addEventListener(this.progressBar, 'mousedown', () => this.onProgressMouseDown());
            this.addEventListener(this.progressBar, 'mouseup', () => this.onProgressMouseUp());
        }
        
        // 音量控制事件
        if (this.volumeControl) {
            this.addEventListener(this.volumeControl, 'input', () => this.onVolumeChange());
        }
        
        // 播放速度事件
        if (this.playbackSpeedSelect) {
            this.addEventListener(this.playbackSpeedSelect, 'change', () => this.onSpeedChange());
        }
    }
    
    /**
     * 初始化鍵盤快捷鍵
     */
    initKeyboardShortcuts() {
        if (!this.options.enableKeyboardShortcuts) return;
        
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
     * 載入影片
     */
    loadVideo(videoUrl) {
        if (!videoUrl) {
            console.error('影片 URL 不能為空');
            return false;
        }
        
        try {
            this.videoElement.src = videoUrl;
            this.videoElement.load();
            this.isLoaded = false;
            
            this.triggerCallback('loadstart', { url: videoUrl });
            return true;
        } catch (error) {
            console.error('載入影片時發生錯誤:', error);
            this.triggerCallback('error', { error, message: '影片載入失敗' });
            return false;
        }
    }
    
    /**
     * 播放影片
     */
    async play() {
        if (!this.videoElement) return false;
        
        try {
            await this.videoElement.play();
            return true;
        } catch (error) {
            console.error('播放影片時發生錯誤:', error);
            this.triggerCallback('error', { error, message: '影片播放失敗' });
            return false;
        }
    }
    
    /**
     * 暫停影片
     */
    pause() {
        if (!this.videoElement) return false;
        
        try {
            this.videoElement.pause();
            return true;
        } catch (error) {
            console.error('暫停影片時發生錯誤:', error);
            return false;
        }
    }
    
    /**
     * 切換播放/暫停
     */
    async togglePlayPause() {
        if (!this.videoElement) return false;
        
        if (this.isPlaying) {
            return this.pause();
        } else {
            return await this.play();
        }
    }
    
    /**
     * 跳轉到指定時間
     */
    seekTo(time) {
        if (!this.videoElement || !this.isLoaded) return false;
        
        try {
            const clampedTime = Math.max(0, Math.min(time, this.duration));
            this.videoElement.currentTime = clampedTime;
            this.triggerCallback('seek', { time: clampedTime });
            return true;
        } catch (error) {
            console.error('跳轉時間時發生錯誤:', error);
            return false;
        }
    }
    
    /**
     * 後退
     */
    rewind(step = null) {
        const rewindStep = step || this.options.rewindStep;
        const newTime = this.currentTime - rewindStep;
        return this.seekTo(newTime);
    }
    
    /**
     * 快進
     */
    forward(step = null) {
        const forwardStep = step || this.options.forwardStep;
        const newTime = this.currentTime + forwardStep;
        return this.seekTo(newTime);
    }
    
    /**
     * 設置音量
     */
    setVolume(volume) {
        if (!this.videoElement) return false;
        
        try {
            const clampedVolume = Math.max(0, Math.min(1, volume));
            this.videoElement.volume = clampedVolume;
            this.volume = clampedVolume;
            
            if (this.volumeControl) {
                this.volumeControl.value = clampedVolume * 100;
            }
            
            this.triggerCallback('volumechange', { volume: clampedVolume });
            return true;
        } catch (error) {
            console.error('設置音量時發生錯誤:', error);
            return false;
        }
    }
    
    /**
     * 設置播放速度
     */
    setPlaybackRate(rate) {
        if (!this.videoElement) return false;
        
        try {
            const clampedRate = Math.max(0.25, Math.min(4, rate));
            this.videoElement.playbackRate = clampedRate;
            this.playbackRate = clampedRate;
            
            if (this.playbackSpeedSelect) {
                this.playbackSpeedSelect.value = clampedRate.toString();
            }
            
            this.triggerCallback('ratechange', { rate: clampedRate });
            return true;
        } catch (error) {
            console.error('設置播放速度時發生錯誤:', error);
            return false;
        }
    }
    
    /**
     * 獲取當前播放狀態
     */
    getState() {
        return {
            isPlaying: this.isPlaying,
            currentTime: this.currentTime,
            duration: this.duration,
            volume: this.volume,
            playbackRate: this.playbackRate,
            isLoaded: this.isLoaded
        };
    }
    
    /**
     * 格式化時間顯示
     */
    formatTime(seconds) {
        if (!seconds || isNaN(seconds)) return '00:00:00';
        
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        if (hours > 0) {
            return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        } else {
            return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
    }
    
    /**
     * 更新進度顯示
     */
    updateProgress() {
        if (this.progressBar && this.duration > 0) {
            const progress = (this.currentTime / this.duration) * 100;
            this.progressBar.value = this.currentTime;
            this.progressBar.max = this.duration;
        }
        
        if (this.currentTimeDisplay) {
            this.currentTimeDisplay.textContent = this.formatTime(this.currentTime);
        }
        
        if (this.totalTimeDisplay) {
            this.totalTimeDisplay.textContent = this.formatTime(this.duration);
        }
    }
    
    /**
     * 更新播放按鈕狀態
     */
    updatePlayButton() {
        if (!this.playPauseBtn) return;
        
        const icon = this.playPauseBtn.querySelector('i');
        if (icon) {
            if (this.isPlaying) {
                icon.className = 'bi bi-pause-fill';
                this.playPauseBtn.title = '暫停';
            } else {
                icon.className = 'bi bi-play-fill';
                this.playPauseBtn.title = '播放';
            }
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
     * 事件處理器
     */
    onLoadedMetadata() {
        this.duration = this.videoElement.duration;
        this.isLoaded = true;
        this.updateProgress();
        
        this.triggerCallback('loadedmetadata', {
            duration: this.duration
        });
        
        console.log('影片元數據載入完成，時長:', this.formatTime(this.duration));
    }
    
    onTimeUpdate() {
        this.currentTime = this.videoElement.currentTime;
        this.updateProgress();
        
        this.triggerCallback('timeupdate', {
            currentTime: this.currentTime,
            duration: this.duration
        });
    }
    
    onPlay() {
        this.isPlaying = true;
        this.updatePlayButton();
        
        this.triggerCallback('play', {
            currentTime: this.currentTime
        });
    }
    
    onPause() {
        this.isPlaying = false;
        this.updatePlayButton();
        
        this.triggerCallback('pause', {
            currentTime: this.currentTime
        });
    }
    
    onEnded() {
        this.isPlaying = false;
        this.updatePlayButton();
        
        this.triggerCallback('ended', {
            duration: this.duration
        });
    }
    
    onError(event) {
        const error = this.videoElement.error;
        console.error('影片播放錯誤:', error);
        
        this.triggerCallback('error', {
            error: error,
            message: this.getErrorMessage(error)
        });
    }
    
    onLoadStart() {
        this.triggerCallback('loadstart');
    }
    
    onCanPlay() {
        this.triggerCallback('canplay');
    }
    
    onWaiting() {
        this.triggerCallback('waiting');
    }
    
    onPlaying() {
        this.triggerCallback('playing');
    }
    
    onProgressChange() {
        if (!this.progressBar || !this.isLoaded) return;
        
        const newTime = parseFloat(this.progressBar.value);
        this.seekTo(newTime);
    }
    
    onProgressMouseDown() {
        this.wasPlayingBeforeSeek = this.isPlaying;
        if (this.isPlaying) {
            this.pause();
        }
    }
    
    onProgressMouseUp() {
        if (this.wasPlayingBeforeSeek) {
            this.play();
        }
    }
    
    onVolumeChange() {
        if (!this.volumeControl) return;
        
        const newVolume = parseFloat(this.volumeControl.value) / 100;
        this.setVolume(newVolume);
    }
    
    onSpeedChange() {
        if (!this.playbackSpeedSelect) return;
        
        const newRate = parseFloat(this.playbackSpeedSelect.value);
        this.setPlaybackRate(newRate);
    }
    
    onKeyDown(event) {
        // 如果焦點在輸入框中，不處理快捷鍵
        if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
            return;
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
            case 'ArrowUp':
                event.preventDefault();
                this.setVolume(Math.min(1, this.volume + this.options.volumeStep));
                break;
            case 'ArrowDown':
                event.preventDefault();
                this.setVolume(Math.max(0, this.volume - this.options.volumeStep));
                break;
            case 'KeyM':
                event.preventDefault();
                this.toggleMute();
                break;
            case 'KeyF':
                event.preventDefault();
                this.toggleFullscreen();
                break;
        }
    }
    
    /**
     * 切換靜音
     */
    toggleMute() {
        if (!this.videoElement) return false;
        
        if (this.videoElement.muted) {
            this.videoElement.muted = false;
            this.setVolume(this.volume);
        } else {
            this.videoElement.muted = true;
            this.setVolume(0);
        }
        
        this.triggerCallback('mutechange', {
            muted: this.videoElement.muted
        });
        
        return true;
    }
    
    /**
     * 切換全螢幕
     */
    toggleFullscreen() {
        if (!this.videoElement) return false;
        
        try {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                this.videoElement.requestFullscreen();
            }
            return true;
        } catch (error) {
            console.error('切換全螢幕時發生錯誤:', error);
            return false;
        }
    }
    
    /**
     * 獲取錯誤訊息
     */
    getErrorMessage(error) {
        if (!error) return '未知錯誤';
        
        switch (error.code) {
            case error.MEDIA_ERR_ABORTED:
                return '影片載入被中止';
            case error.MEDIA_ERR_NETWORK:
                return '網路錯誤導致影片載入失敗';
            case error.MEDIA_ERR_DECODE:
                return '影片解碼錯誤';
            case error.MEDIA_ERR_SRC_NOT_SUPPORTED:
                return '不支援的影片格式';
            default:
                return '影片播放錯誤';
        }
    }
    
    /**
     * 銷毀播放器
     */
    destroy() {
        // 清理事件監聽器
        this.eventListeners.forEach((listeners, element) => {
            listeners.forEach(({ event, handler }) => {
                element.removeEventListener(event, handler);
            });
        });
        
        // 清理回調函數
        this.callbacks.clear();
        
        // 停止播放
        if (this.videoElement) {
            this.pause();
            this.videoElement.src = '';
            this.videoElement.load();
        }
        
        console.log('VideoPlayer 已銷毀');
    }
}

// 導出類別供其他模組使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = VideoPlayer;
}
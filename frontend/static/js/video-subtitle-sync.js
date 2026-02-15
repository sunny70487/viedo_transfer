/**
 * 影片字幕同步管理器
 * 負責將字幕嵌入到影片中，並實現實時更新
 */

class VideoSubtitleSync {
    constructor(videoElement, options = {}) {
        this.videoElement = videoElement;
        this.options = {
            fontSize: '20px',
            fontColor: '#FFFFFF',
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            position: 'bottom',
            ...options
        };
        
        this.subtitles = [];
        this.textTrack = null;
        
        this.init();
    }
    
    /**
     * 初始化字幕軌道
     */
    init() {
        if (!this.videoElement) {
            console.error('[VideoSubtitleSync] 影片元素不存在');
            return;
        }
        
        // 移除任何已有的字幕 track，避免 CORS 污染問題
        const existingTracks = this.videoElement.querySelectorAll('track');
        existingTracks.forEach(track => track.remove());
        
        // 使用 JavaScript API 建立 TextTrack，而非 <track> 元素
        // 這種方式不需要 src 屬性，不會觸發 CORS 檢查，避免影片黑屏
        this.textTrack = this.videoElement.addTextTrack('subtitles', '字幕', 'zh');
        this.textTrack.mode = 'showing';
        
        console.log('[VideoSubtitleSync] 字幕軌道已初始化（使用 addTextTrack API）');
    }
    
    /**
     * 載入字幕資料
     */
    loadSubtitles(subtitles) {
        if (!Array.isArray(subtitles)) {
            console.error('[VideoSubtitleSync] 字幕資料格式錯誤');
            return false;
        }
        
        this.subtitles = subtitles;
        this.updateTrack();
        
        console.log('[VideoSubtitleSync] 已載入', subtitles.length, '條字幕');
        return true;
    }
    
    /**
     * 更新字幕軌道
     */
    updateTrack() {
        if (!this.textTrack) {
            console.warn('[VideoSubtitleSync] textTrack 不存在，跳過更新');
            return;
        }
        
        // 清除所有現有的 cues
        while (this.textTrack.cues && this.textTrack.cues.length > 0) {
            this.textTrack.removeCue(this.textTrack.cues[0]);
        }
        
        // 使用 VTTCue API 直接添加字幕 cues（不需要 Blob URL，不觸發 CORS）
        this.subtitles.forEach((subtitle, index) => {
            try {
                const cue = new VTTCue(
                    subtitle.start_time,
                    subtitle.end_time,
                    subtitle.text
                );
                cue.id = String(index + 1);
                cue.line = -2;
                cue.size = 80;
                cue.align = 'center';
                this.textTrack.addCue(cue);
            } catch (e) {
                console.warn('[VideoSubtitleSync] 無法添加字幕 cue:', index, e);
            }
        });
        
        this.textTrack.mode = 'showing';
        console.log('[VideoSubtitleSync] 字幕軌道已更新，共', this.subtitles.length, '條字幕');
    }
    
    /**
     * 生成 WebVTT 格式內容
     */
    generateVTT() {
        let vtt = 'WEBVTT\n\n';
        
        this.subtitles.forEach((subtitle, index) => {
            // 格式化時間戳（WebVTT 格式：HH:MM:SS.mmm）
            const startTime = this.formatVTTTimestamp(subtitle.start_time);
            const endTime = this.formatVTTTimestamp(subtitle.end_time);
            
            // 清理字幕文字（移除 VTT 特殊字符）
            const text = subtitle.text
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/-->/g, '→');
            
            // 添加字幕條目
            vtt += `${index + 1}\n`;
            vtt += `${startTime} --> ${endTime}\n`;
            vtt += `${text}\n\n`;
        });
        
        return vtt;
    }
    
    /**
     * 格式化時間戳為 WebVTT 格式 (HH:MM:SS.mmm)
     */
    formatVTTTimestamp(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        const ms = Math.floor((seconds % 1) * 1000);
        
        return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
    }
    
    /**
     * 更新所有字幕（重新載入字幕軌道）
     */
    updateSubtitles(subtitles) {
        if (!Array.isArray(subtitles)) {
            console.error('[VideoSubtitleSync] 字幕資料格式錯誤');
            return false;
        }
        
        this.subtitles = subtitles;
        this.updateTrack();
        
        console.log('[VideoSubtitleSync] 字幕已更新，共', subtitles.length, '條');
        return true;
    }
    
    /**
     * 更新單條字幕
     */
    updateSubtitle(index, newSubtitle) {
        if (index >= 0 && index < this.subtitles.length) {
            this.subtitles[index] = { ...this.subtitles[index], ...newSubtitle };
            this.updateTrack();
            console.log('[VideoSubtitleSync] 字幕', index, '已更新');
        }
    }
    
    /**
     * 批量更新字幕
     */
    updateSubtitles(newSubtitles) {
        this.subtitles = newSubtitles;
        this.updateTrack();
        console.log('[VideoSubtitleSync] 字幕已批量更新');
    }
    
    /**
     * 啟用/禁用字幕顯示
     */
    setVisible(visible) {
        if (this.textTrack) {
            this.textTrack.mode = visible ? 'showing' : 'hidden';
            console.log('[VideoSubtitleSync] 字幕顯示:', visible);
        }
    }
    
    /**
     * 獲取當前字幕狀態
     */
    isVisible() {
        return this.textTrack && this.textTrack.mode === 'showing';
    }
    
    /**
     * 設置字幕樣式
     */
    setStyle(styleOptions) {
        this.options = { ...this.options, ...styleOptions };
        
        // 應用自定義樣式到字幕軌道
        if (this.textTrack && this.textTrack.cues) {
            for (let i = 0; i < this.textTrack.cues.length; i++) {
                const cue = this.textTrack.cues[i];
                if (cue) {
                    // WebVTT 支持的樣式選項
                    cue.line = this.options.position === 'top' ? 0 : -2;
                    cue.size = 80; // 字幕寬度百分比
                    cue.align = 'center';
                }
            }
        }
        
        console.log('[VideoSubtitleSync] 字幕樣式已更新:', this.options);
    }
    
    /**
     * 清理資源
     */
    destroy() {
        // 清除所有 cues
        if (this.textTrack && this.textTrack.cues) {
            while (this.textTrack.cues.length > 0) {
                this.textTrack.removeCue(this.textTrack.cues[0]);
            }
            this.textTrack.mode = 'hidden';
        }
        
        this.textTrack = null;
        
        console.log('[VideoSubtitleSync] 資源已清理');
    }
}

// 暴露到全域
window.VideoSubtitleSync = VideoSubtitleSync;


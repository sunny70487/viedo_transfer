/**
 * 影片格式檢測工具
 * 檢測瀏覽器對不同影片格式的支持情況
 */

class VideoFormatDetector {
    constructor() {
        this.testVideo = document.createElement('video');
        this.supportCache = null;
    }
    
    /**
     * 檢測所有常見格式的支持情況
     */
    detectSupport() {
        if (this.supportCache) {
            return this.supportCache;
        }
        
        const formats = {
            // MP4 (H.264 + AAC)
            mp4_h264: {
                type: 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"',
                label: 'MP4 (H.264)',
                recommended: true
            },
            // WebM (VP8 + Vorbis)
            webm_vp8: {
                type: 'video/webm; codecs="vp8, vorbis"',
                label: 'WebM (VP8)',
                recommended: false
            },
            // WebM (VP9 + Opus)
            webm_vp9: {
                type: 'video/webm; codecs="vp9, opus"',
                label: 'WebM (VP9)',
                recommended: false
            },
            // MKV (H.264 + AAC)
            mkv_h264: {
                type: 'video/x-matroska; codecs="avc1.42E01E, mp4a.40.2"',
                label: 'MKV (H.264)',
                recommended: false
            },
            // MKV (通用)
            mkv: {
                type: 'video/x-matroska',
                label: 'MKV (通用)',
                recommended: false
            },
            // OGG
            ogg: {
                type: 'video/ogg; codecs="theora, vorbis"',
                label: 'OGG',
                recommended: false
            }
        };
        
        const support = {};
        
        for (const [key, format] of Object.entries(formats)) {
            const canPlay = this.testVideo.canPlayType(format.type);
            support[key] = {
                ...format,
                support: this.interpretSupport(canPlay),
                raw: canPlay
            };
        }
        
        this.supportCache = support;
        return support;
    }
    
    /**
     * 解釋瀏覽器的支持級別
     */
    interpretSupport(canPlayResult) {
        switch (canPlayResult) {
            case 'probably':
                return 'full';
            case 'maybe':
                return 'partial';
            default:
                return 'none';
        }
    }
    
    /**
     * 檢查特定格式是否支持
     */
    canPlay(format) {
        const support = this.detectSupport();
        return support[format] && support[format].support !== 'none';
    }
    
    /**
     * 獲取推薦格式（按優先級排序）
     */
    getRecommendedFormats() {
        const support = this.detectSupport();
        return Object.entries(support)
            .filter(([_, info]) => info.support === 'full')
            .sort((a, b) => {
                // 推薦格式優先
                if (a[1].recommended && !b[1].recommended) return -1;
                if (!a[1].recommended && b[1].recommended) return 1;
                return 0;
            })
            .map(([key, info]) => ({
                format: key,
                label: info.label,
                type: info.type
            }));
    }
    
    /**
     * 顯示詳細的支持報告
     */
    generateReport() {
        const support = this.detectSupport();
        const browserInfo = this.getBrowserInfo();
        
        console.group('🎬 影片格式支持報告');
        console.log('瀏覽器:', browserInfo.name, browserInfo.version);
        console.log('作業系統:', browserInfo.os);
        console.log('');
        
        console.table(
            Object.entries(support).map(([key, info]) => ({
                格式: info.label,
                支持級別: info.support,
                MIME類型: info.type,
                推薦: info.recommended ? '✅' : '❌'
            }))
        );
        
        const recommended = this.getRecommendedFormats();
        if (recommended.length > 0) {
            console.log('✅ 推薦使用的格式:', recommended.map(f => f.label).join(', '));
        } else {
            console.warn('⚠️ 沒有完全支持的格式！');
        }
        
        console.groupEnd();
        
        return {
            browser: browserInfo,
            support,
            recommended
        };
    }
    
    /**
     * 獲取瀏覽器信息
     */
    getBrowserInfo() {
        const ua = navigator.userAgent;
        let name = 'Unknown';
        let version = 'Unknown';
        let os = 'Unknown';
        
        // 檢測瀏覽器
        if (ua.indexOf('Firefox') > -1) {
            name = 'Firefox';
            version = ua.match(/Firefox\/(\d+\.\d+)/)?.[1];
        } else if (ua.indexOf('Edg') > -1) {
            name = 'Edge';
            version = ua.match(/Edg\/(\d+\.\d+)/)?.[1];
        } else if (ua.indexOf('Chrome') > -1) {
            name = 'Chrome';
            version = ua.match(/Chrome\/(\d+\.\d+)/)?.[1];
        } else if (ua.indexOf('Safari') > -1) {
            name = 'Safari';
            version = ua.match(/Version\/(\d+\.\d+)/)?.[1];
        }
        
        // 檢測作業系統
        if (ua.indexOf('Windows') > -1) os = 'Windows';
        else if (ua.indexOf('Mac') > -1) os = 'macOS';
        else if (ua.indexOf('Linux') > -1) os = 'Linux';
        else if (ua.indexOf('Android') > -1) os = 'Android';
        else if (ua.indexOf('iOS') > -1) os = 'iOS';
        
        return { name, version, os };
    }
    
    /**
     * 檢查當前影片元素並提供建議
     */
    analyzeVideoElement(videoElement) {
        if (!videoElement || !videoElement.src) {
            console.warn('沒有提供有效的影片元素');
            return null;
        }
        
        const src = videoElement.src;
        const ext = src.split('.').pop().toLowerCase().split('?')[0];
        
        console.group('🎬 影片元素分析');
        console.log('影片 URL:', src);
        console.log('檔案格式:', ext);
        console.log('');
        
        // 檢查是否有錯誤
        if (videoElement.error) {
            console.error('影片錯誤:', {
                code: videoElement.error.code,
                message: this.getErrorMessage(videoElement.error.code)
            });
        }
        
        // 檢查網路狀態
        console.log('網路狀態:', this.getNetworkStateLabel(videoElement.networkState));
        console.log('就緒狀態:', this.getReadyStateLabel(videoElement.readyState));
        
        // 檢查格式支持
        const support = this.detectSupport();
        const formatKey = this.getFormatKey(ext);
        if (formatKey && support[formatKey]) {
            const formatSupport = support[formatKey];
            console.log('格式支持:', formatSupport.support);
            
            if (formatSupport.support === 'none') {
                console.warn('⚠️ 瀏覽器不支持此格式！');
                const recommended = this.getRecommendedFormats();
                if (recommended.length > 0) {
                    console.log('建議使用:', recommended[0].label);
                }
            } else if (formatSupport.support === 'partial') {
                console.warn('⚠️ 瀏覽器僅部分支持此格式，可能會有播放問題');
            } else {
                console.log('✅ 瀏覽器完全支持此格式');
            }
        }
        
        console.groupEnd();
        
        return {
            src,
            ext,
            error: videoElement.error,
            networkState: videoElement.networkState,
            readyState: videoElement.readyState,
            formatSupport: formatKey ? support[formatKey] : null
        };
    }
    
    /**
     * 根據檔案擴展名獲取格式鍵
     */
    getFormatKey(ext) {
        const mapping = {
            'mp4': 'mp4_h264',
            'webm': 'webm_vp9',
            'mkv': 'mkv_h264',
            'ogg': 'ogg'
        };
        return mapping[ext];
    }
    
    /**
     * 獲取錯誤訊息
     */
    getErrorMessage(code) {
        const messages = {
            1: 'MEDIA_ERR_ABORTED - 播放被用戶中止',
            2: 'MEDIA_ERR_NETWORK - 網路錯誤',
            3: 'MEDIA_ERR_DECODE - 解碼錯誤',
            4: 'MEDIA_ERR_SRC_NOT_SUPPORTED - 格式不支持'
        };
        return messages[code] || '未知錯誤';
    }
    
    /**
     * 獲取網路狀態標籤
     */
    getNetworkStateLabel(state) {
        const labels = {
            0: 'NETWORK_EMPTY - 尚未初始化',
            1: 'NETWORK_IDLE - 已選擇資源但未使用網路',
            2: 'NETWORK_LOADING - 正在下載',
            3: 'NETWORK_NO_SOURCE - 找不到資源'
        };
        return labels[state] || '未知狀態';
    }
    
    /**
     * 獲取就緒狀態標籤
     */
    getReadyStateLabel(state) {
        const labels = {
            0: 'HAVE_NOTHING - 沒有資料',
            1: 'HAVE_METADATA - 元資料已載入',
            2: 'HAVE_CURRENT_DATA - 當前幀可用',
            3: 'HAVE_FUTURE_DATA - 未來幀可用',
            4: 'HAVE_ENOUGH_DATA - 足夠資料可播放'
        };
        return labels[state] || '未知狀態';
    }
}

// 創建全域實例
window.videoFormatDetector = new VideoFormatDetector();

// 在頁面載入時自動執行檢測（僅在開發模式）
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('💡 提示：使用 videoFormatDetector.generateReport() 查看詳細的格式支持報告');
        console.log('💡 提示：使用 videoFormatDetector.analyzeVideoElement(video) 分析影片元素');
    });
}


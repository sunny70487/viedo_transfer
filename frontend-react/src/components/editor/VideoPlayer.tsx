import { useRef, useEffect, forwardRef, useImperativeHandle, useState, useCallback, useMemo } from 'react'
import {
  Play, Pause, Volume2, VolumeX, Maximize, Minimize,
  Subtitles, Gauge, ALargeSmall, ArrowDownUp,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { formatTimestamp } from '@/lib/utils'
import {
  readBilingualPrimaryIsFirstLine,
  writeBilingualPrimaryIsFirstLine,
  splitBilingualDisplay,
} from '@/lib/bilingual-display'
import type { Subtitle } from '@/types/api'

export interface VideoPlayerHandle {
  seek: (time: number) => void
  play: () => void
  pause: () => void
  toggle: () => void
  seekRelative: (delta: number) => void
  getCurrentTime: () => number
  isPlaying: () => boolean
}

interface VideoPlayerProps {
  src?: string
  subtitles?: Subtitle[]
  onTimeUpdate?: (time: number) => void
}

const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2]
const SUBTITLE_SIZE_OPTIONS = [
  { label: '小', value: 14 },
  { label: '中', value: 16 },
  { label: '大', value: 20 },
  { label: '特大', value: 24 },
]

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, subtitles, onTimeUpdate }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)

    const [playing, setPlaying] = useState(false)
    const [muted, setMuted] = useState(false)
    const [currentTime, setCurrentTime] = useState(0)
    const [duration, setDuration] = useState(0)
    const [speed, setSpeed] = useState(1)
    const [ccVisible, setCcVisible] = useState(true)
    const [isFullscreen, setIsFullscreen] = useState(false)
    const [videoError, setVideoError] = useState(false)
    const [speedMenuOpen, setSpeedMenuOpen] = useState(false)
    const [subtitleSize, setSubtitleSize] = useState(16)
    const [subtitleSizeMenuOpen, setSubtitleSizeMenuOpen] = useState(false)
    const [bilingualPrimaryIsFirstLine, setBilingualPrimaryIsFirstLine] = useState(
      readBilingualPrimaryIsFirstLine
    )

    const toggleBilingualPrimaryLine = useCallback(() => {
      setBilingualPrimaryIsFirstLine((prev) => {
        const next = !prev
        writeBilingualPrimaryIsFirstLine(next)
        return next
      })
    }, [])

    useImperativeHandle(ref, () => ({
      seek: (time: number) => {
        if (videoRef.current) videoRef.current.currentTime = time
      },
      play: () => { videoRef.current?.play() },
      pause: () => { videoRef.current?.pause() },
      toggle: () => {
        const v = videoRef.current
        if (v) v.paused ? v.play() : v.pause()
      },
      seekRelative: (delta: number) => {
        const v = videoRef.current
        if (v) v.currentTime = Math.max(0, Math.min(v.duration || 0, v.currentTime + delta))
      },
      getCurrentTime: () => videoRef.current?.currentTime ?? 0,
      isPlaying: () => !videoRef.current?.paused,
    }))

    useEffect(() => {
      setVideoError(false)
    }, [src])

    useEffect(() => {
      const v = videoRef.current
      if (!v) return
      const onTime = () => {
        setCurrentTime(v.currentTime)
        onTimeUpdate?.(v.currentTime)
      }
      const onDur = () => setDuration(v.duration || 0)
      const onPlay = () => setPlaying(true)
      const onPause = () => setPlaying(false)
      const onError = () => setVideoError(true)
      v.addEventListener('timeupdate', onTime)
      v.addEventListener('loadedmetadata', onDur)
      v.addEventListener('play', onPlay)
      v.addEventListener('pause', onPause)
      v.addEventListener('error', onError)
      return () => {
        v.removeEventListener('timeupdate', onTime)
        v.removeEventListener('loadedmetadata', onDur)
        v.removeEventListener('play', onPlay)
        v.removeEventListener('pause', onPause)
        v.removeEventListener('error', onError)
      }
    }, [onTimeUpdate])

    const activeSubtitle = useMemo(() => {
      if (!subtitles?.length || !ccVisible) return null
      for (let i = subtitles.length - 1; i >= 0; i--) {
        if (currentTime >= subtitles[i].start_time && currentTime <= subtitles[i].end_time) {
          return subtitles[i]
        }
      }
      return null
    }, [subtitles, currentTime, ccVisible])

    // Listen for fullscreen changes (user may press Esc)
    useEffect(() => {
      const onFsChange = () => setIsFullscreen(!!document.fullscreenElement)
      document.addEventListener('fullscreenchange', onFsChange)
      return () => document.removeEventListener('fullscreenchange', onFsChange)
    }, [])

    const toggleFullscreen = useCallback(() => {
      const el = containerRef.current
      if (!el) return
      if (document.fullscreenElement) {
        document.exitFullscreen()
      } else {
        el.requestFullscreen()
      }
    }, [])

    const changeSpeed = useCallback((newSpeed: number) => {
      setSpeed(newSpeed)
      setSpeedMenuOpen(false)
      if (videoRef.current) videoRef.current.playbackRate = newSpeed
    }, [])

    if (!src || videoError) {
      return (
        <div className="aspect-video rounded-lg bg-gray-100 dark:bg-gray-800 flex flex-col items-center justify-center gap-2">
          <p className="text-sm text-muted dark:text-muted-dark">
            {videoError ? '此格式無法在瀏覽器中播放，轉錄完成後將自動轉換' : '無可用影片'}
          </p>
        </div>
      )
    }

    const progress = duration > 0 ? (currentTime / duration) * 100 : 0

    return (
      <div className="space-y-2">
        {/* Video container (fullscreen target) */}
        <div
          ref={containerRef}
          className="relative rounded-lg overflow-hidden bg-black group"
        >
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video
            ref={videoRef}
            src={src}
            className="w-full aspect-video"
          />

          {activeSubtitle && (() => {
            const scale = isFullscreen ? 1.5 : 1
            const primarySize = subtitleSize * scale
            const { primary, secondary } = splitBilingualDisplay(
              activeSubtitle.text,
              bilingualPrimaryIsFirstLine
            )
            const isBilingual = secondary != null

            return (
              <div className={`absolute left-4 right-4 flex justify-center pointer-events-none z-10 transition-opacity ${isFullscreen ? 'bottom-16' : 'bottom-3'}`}>
                <span className="inline-block bg-black/75 text-white px-4 py-1.5 rounded-lg max-w-[90%] text-center backdrop-blur-sm shadow-lg">
                  {activeSubtitle.speaker && (
                    <span className="text-sky-400 font-medium mr-1.5" style={{ fontSize: `${primarySize}px` }}>
                      [{activeSubtitle.speaker}]
                    </span>
                  )}
                  {isBilingual ? (
                    <>
                      <span className="block leading-relaxed" style={{ fontSize: `${primarySize}px` }}>
                        {primary}
                      </span>
                      <span className="block leading-relaxed text-white/75" style={{ fontSize: `${primarySize * 0.72}px` }}>
                        {secondary}
                      </span>
                    </>
                  ) : (
                    <span className="leading-relaxed" style={{ fontSize: `${primarySize}px` }}>
                      {activeSubtitle.text}
                    </span>
                  )}
                </span>
              </div>
            )
          })()}

          {/* Fullscreen overlay controls (visible in fullscreen mode) */}
          {isFullscreen && (
            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-4 opacity-0 group-hover:opacity-100 transition-opacity">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  className="text-white hover:text-primary cursor-pointer"
                  onClick={() => {
                    const v = videoRef.current
                    if (v) playing ? v.pause() : v.play()
                  }}
                >
                  {playing ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />}
                </button>
                <div className="flex-1 h-1.5 rounded-full bg-white/30 cursor-pointer overflow-hidden"
                  onClick={(e) => {
                    if (!videoRef.current || !duration) return
                    const rect = e.currentTarget.getBoundingClientRect()
                    videoRef.current.currentTime = ((e.clientX - rect.left) / rect.width) * duration
                  }}
                >
                  <div className="h-full bg-primary rounded-full" style={{ width: `${progress}%` }} />
                </div>
                <span className="text-xs font-mono text-white/80 tabular-nums shrink-0">
                  {formatTimestamp(currentTime)} / {formatTimestamp(duration)}
                </span>

                {/* CC toggle (fullscreen) */}
                <button
                  type="button"
                  className={`cursor-pointer ${ccVisible ? 'text-primary' : 'text-white/60 hover:text-white'}`}
                  onClick={() => setCcVisible(!ccVisible)}
                  title={ccVisible ? '關閉字幕' : '開啟字幕'}
                >
                  <Subtitles className="h-5 w-5" />
                </button>

                <button
                  type="button"
                  className={`cursor-pointer ${bilingualPrimaryIsFirstLine ? 'text-white/60 hover:text-white' : 'text-primary'}`}
                  onClick={toggleBilingualPrimaryLine}
                  title={
                    bilingualPrimaryIsFirstLine
                      ? '雙語：目前為第 1 行主字幕（點擊改為第 2 行）'
                      : '雙語：目前為第 2 行主字幕（點擊改為第 1 行）'
                  }
                >
                  <ArrowDownUp className="h-5 w-5" />
                </button>

                {/* Subtitle size (fullscreen) */}
                <div className="relative">
                  <button
                    type="button"
                    className={`cursor-pointer ${subtitleSize !== 16 ? 'text-primary' : 'text-white/60 hover:text-white'}`}
                    onClick={() => setSubtitleSizeMenuOpen(!subtitleSizeMenuOpen)}
                    title="字幕大小"
                  >
                    <ALargeSmall className="h-5 w-5" />
                  </button>
                  {subtitleSizeMenuOpen && (
                    <>
                      <div className="fixed inset-0 z-40" onClick={() => setSubtitleSizeMenuOpen(false)} />
                      <div className="absolute bottom-full right-0 mb-2 z-50 bg-black/90 backdrop-blur-md border border-white/20 rounded-lg shadow-2xl py-1 min-w-[100px]">
                        {SUBTITLE_SIZE_OPTIONS.map((opt) => (
                          <button
                            key={opt.value}
                            type="button"
                            className={`w-full px-3 py-1.5 text-sm text-left cursor-pointer hover:bg-white/10 transition-colors ${
                              opt.value === subtitleSize ? 'text-primary font-semibold' : 'text-white/80'
                            }`}
                            onClick={() => { setSubtitleSize(opt.value); setSubtitleSizeMenuOpen(false) }}
                          >
                            {opt.label} ({opt.value}px)
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>

                {/* Speed (fullscreen) */}
                <div className="relative">
                  <button
                    type="button"
                    className={`cursor-pointer ${speed !== 1 ? 'text-primary' : 'text-white/60 hover:text-white'}`}
                    onClick={() => setSpeedMenuOpen(!speedMenuOpen)}
                    title="播放速度"
                  >
                    {speed === 1 ? <Gauge className="h-5 w-5" /> : <span className="text-sm font-bold">{speed}x</span>}
                  </button>
                  {speedMenuOpen && (
                    <>
                      <div className="fixed inset-0 z-40" onClick={() => setSpeedMenuOpen(false)} />
                      <div className="absolute bottom-full right-0 mb-2 z-50 bg-black/90 backdrop-blur-md border border-white/20 rounded-lg shadow-2xl py-1 min-w-[80px]">
                        {SPEED_OPTIONS.map((s) => (
                          <button
                            key={s}
                            type="button"
                            className={`w-full px-3 py-1.5 text-sm text-left cursor-pointer hover:bg-white/10 transition-colors ${
                              s === speed ? 'text-primary font-semibold' : 'text-white/80'
                            }`}
                            onClick={() => changeSpeed(s)}
                          >
                            {s}x
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>

                <button
                  type="button"
                  className="text-white hover:text-primary cursor-pointer"
                  onClick={toggleFullscreen}
                >
                  <Minimize className="h-5 w-5" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Control bar (below video, hidden during fullscreen) */}
        {!isFullscreen && (
          <div className="flex items-center gap-1.5">
            {/* Play/Pause */}
            <Button variant="ghost" size="icon" onClick={() => {
              const v = videoRef.current
              if (v) playing ? v.pause() : v.play()
            }}>
              {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </Button>

            {/* Mute */}
            <Button variant="ghost" size="icon" onClick={() => {
              if (videoRef.current) videoRef.current.muted = !muted
              setMuted(!muted)
            }}>
              {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
            </Button>

            {/* Progress bar */}
            <div
              className="flex-1 h-1.5 rounded-full bg-gray-200 dark:bg-gray-700 cursor-pointer overflow-hidden"
              onClick={(e) => {
                if (!videoRef.current || !duration) return
                const rect = e.currentTarget.getBoundingClientRect()
                videoRef.current.currentTime = ((e.clientX - rect.left) / rect.width) * duration
              }}
            >
              <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${progress}%` }} />
            </div>

            {/* Time display */}
            <span className="text-xs font-mono text-muted dark:text-muted-dark tabular-nums shrink-0">
              {formatTimestamp(currentTime)} / {formatTimestamp(duration)}
            </span>

            {/* CC toggle */}
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setCcVisible(!ccVisible)}
              title={ccVisible ? '關閉字幕' : '開啟字幕'}
              className={ccVisible ? 'text-primary' : ''}
            >
              <Subtitles className="h-4 w-4" />
            </Button>

            <Button
              variant="ghost"
              size="icon"
              onClick={toggleBilingualPrimaryLine}
              title={
                bilingualPrimaryIsFirstLine
                  ? '雙語：第 1 行為主字幕（點擊改為第 2 行）'
                  : '雙語：第 2 行為主字幕（點擊改為第 1 行）'
              }
              className={bilingualPrimaryIsFirstLine ? '' : 'text-primary'}
            >
              <ArrowDownUp className="h-4 w-4" />
            </Button>

            {/* Subtitle size selector */}
            <div className="relative">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => { setSubtitleSizeMenuOpen(!subtitleSizeMenuOpen); setSpeedMenuOpen(false) }}
                title="字幕大小"
                className={subtitleSize !== 16 ? 'text-primary' : ''}
              >
                <ALargeSmall className="h-4 w-4" />
              </Button>
              {subtitleSizeMenuOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setSubtitleSizeMenuOpen(false)} />
                  <div className="absolute bottom-full right-0 mb-1 z-50 bg-surface dark:bg-surface-dark border border-border dark:border-border-dark rounded-lg shadow-lg py-1 min-w-[80px]">
                    {SUBTITLE_SIZE_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        className={`w-full px-3 py-1.5 text-sm text-left cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${
                          opt.value === subtitleSize ? 'text-primary font-semibold' : 'text-text dark:text-text-dark'
                        }`}
                        onClick={() => { setSubtitleSize(opt.value); setSubtitleSizeMenuOpen(false) }}
                      >
                        {opt.label} ({opt.value}px)
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Speed selector */}
            <div className="relative">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => { setSpeedMenuOpen(!speedMenuOpen); setSubtitleSizeMenuOpen(false) }}
                title="播放速度"
                className={speed !== 1 ? 'text-primary' : ''}
              >
                {speed === 1 ? (
                  <Gauge className="h-4 w-4" />
                ) : (
                  <span className="text-xs font-bold">{speed}x</span>
                )}
              </Button>
              {speedMenuOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setSpeedMenuOpen(false)} />
                  <div className="absolute bottom-full right-0 mb-1 z-50 bg-surface dark:bg-surface-dark border border-border dark:border-border-dark rounded-lg shadow-lg py-1 min-w-[80px]">
                    {SPEED_OPTIONS.map((s) => (
                      <button
                        key={s}
                        type="button"
                        className={`w-full px-3 py-1.5 text-sm text-left cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${
                          s === speed ? 'text-primary font-semibold' : 'text-text dark:text-text-dark'
                        }`}
                        onClick={() => changeSpeed(s)}
                      >
                        {s}x
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            {/* Fullscreen */}
            <Button variant="ghost" size="icon" onClick={toggleFullscreen} title="全螢幕">
              <Maximize className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    )
  }
)
VideoPlayer.displayName = 'VideoPlayer'

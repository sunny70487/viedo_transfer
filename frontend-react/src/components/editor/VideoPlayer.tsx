import { useRef, useEffect, forwardRef, useImperativeHandle, useState, useCallback } from 'react'
import {
  Play, Pause, Volume2, VolumeX, Maximize, Minimize,
  Subtitles, Gauge,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { formatTimestamp } from '@/lib/utils'
import type { Subtitle } from '@/types/api'

export interface VideoPlayerHandle {
  seek: (time: number) => void
  play: () => void
  getCurrentTime: () => number
}

interface VideoPlayerProps {
  src?: string
  subtitles?: Subtitle[]
  onTimeUpdate?: (time: number) => void
}

const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2]

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, subtitles, onTimeUpdate }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const trackRef = useRef<TextTrack | null>(null)

    const [playing, setPlaying] = useState(false)
    const [muted, setMuted] = useState(false)
    const [currentTime, setCurrentTime] = useState(0)
    const [duration, setDuration] = useState(0)
    const [speed, setSpeed] = useState(1)
    const [ccVisible, setCcVisible] = useState(true)
    const [isFullscreen, setIsFullscreen] = useState(false)
    const [speedMenuOpen, setSpeedMenuOpen] = useState(false)

    useImperativeHandle(ref, () => ({
      seek: (time: number) => {
        if (videoRef.current) videoRef.current.currentTime = time
      },
      play: () => {
        videoRef.current?.play()
      },
      getCurrentTime: () => videoRef.current?.currentTime ?? 0,
    }))

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
      v.addEventListener('timeupdate', onTime)
      v.addEventListener('loadedmetadata', onDur)
      v.addEventListener('play', onPlay)
      v.addEventListener('pause', onPause)
      return () => {
        v.removeEventListener('timeupdate', onTime)
        v.removeEventListener('loadedmetadata', onDur)
        v.removeEventListener('play', onPlay)
        v.removeEventListener('pause', onPause)
      }
    }, [onTimeUpdate])

    // Initialize text track once video element is mounted
    useEffect(() => {
      const v = videoRef.current
      if (!v) return
      const track = v.addTextTrack('subtitles', '字幕', 'zh')
      track.mode = 'showing'
      trackRef.current = track
    }, [src])

    // Rebuild VTTCue entries when subtitles change
    useEffect(() => {
      const track = trackRef.current
      if (!track) return

      while (track.cues && track.cues.length > 0) {
        track.removeCue(track.cues[0])
      }

      if (!subtitles?.length) return

      for (const sub of subtitles) {
        try {
          if (sub.end_time > sub.start_time) {
            const cue = new VTTCue(sub.start_time, sub.end_time, sub.text)
            track.addCue(cue)
          }
        } catch {
          // skip invalid cues
        }
      }
    }, [subtitles])

    // Sync CC visibility with track mode
    useEffect(() => {
      if (trackRef.current) {
        trackRef.current.mode = ccVisible ? 'showing' : 'hidden'
      }
    }, [ccVisible])

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

    if (!src) {
      return (
        <div className="aspect-video rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
          <p className="text-sm text-muted dark:text-muted-dark">無可用影片</p>
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
          <video
            ref={videoRef}
            src={src}
            className="w-full aspect-video"
            crossOrigin="anonymous"
          />

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

            {/* Speed selector */}
            <div className="relative">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSpeedMenuOpen(!speedMenuOpen)}
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

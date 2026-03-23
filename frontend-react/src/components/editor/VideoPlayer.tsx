import { useRef, useEffect, forwardRef, useImperativeHandle, useState } from 'react'
import { Play, Pause, Volume2, VolumeX } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { formatTimestamp } from '@/lib/utils'

export interface VideoPlayerHandle {
  seek: (time: number) => void
  getCurrentTime: () => number
}

interface VideoPlayerProps {
  src?: string
  onTimeUpdate?: (time: number) => void
}

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, onTimeUpdate }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null)
    const [playing, setPlaying] = useState(false)
    const [muted, setMuted] = useState(false)
    const [currentTime, setCurrentTime] = useState(0)
    const [duration, setDuration] = useState(0)

    useImperativeHandle(ref, () => ({
      seek: (time: number) => { if (videoRef.current) videoRef.current.currentTime = time },
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
        <div className="relative rounded-lg overflow-hidden bg-black">
          <video ref={videoRef} src={src} className="w-full aspect-video" />
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={() => {
            const v = videoRef.current
            if (v) playing ? v.pause() : v.play()
          }}>
            {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="icon" onClick={() => { if (videoRef.current) videoRef.current.muted = !muted; setMuted(!muted) }}>
            {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
          </Button>
          <div className="flex-1 h-1.5 rounded-full bg-gray-200 dark:bg-gray-700 cursor-pointer overflow-hidden"
            onClick={(e) => {
              if (!videoRef.current || !duration) return
              const rect = e.currentTarget.getBoundingClientRect()
              videoRef.current.currentTime = ((e.clientX - rect.left) / rect.width) * duration
            }}
          >
            <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${progress}%` }} />
          </div>
          <span className="text-xs font-mono text-muted dark:text-muted-dark tabular-nums shrink-0">
            {formatTimestamp(currentTime)} / {formatTimestamp(duration)}
          </span>
        </div>
      </div>
    )
  }
)
VideoPlayer.displayName = 'VideoPlayer'

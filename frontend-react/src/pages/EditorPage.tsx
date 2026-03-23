import { useEffect, useRef, useCallback, useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { SubtitleToolbar } from '@/components/editor/SubtitleToolbar'
import { SubtitleRow } from '@/components/editor/SubtitleRow'
import { VideoPlayer, type VideoPlayerHandle } from '@/components/editor/VideoPlayer'
import { ExportDialog } from '@/components/editor/ExportDialog'
import { useSubtitles, useSaveSubtitles } from '@/hooks/use-subtitles'
import { useEditorStore } from '@/stores/editor-store'
import { api } from '@/api/client'

export function EditorPage() {
  const { taskId = '' } = useParams()
  const { data, isLoading } = useSubtitles(taskId)
  const saveMutation = useSaveSubtitles(taskId)
  const {
    subtitles, searchTerm,
    setSubtitles, setSelectedIndex, markSaved,
  } = useEditorStore()
  const [exportOpen, setExportOpen] = useState(false)
  const [videoTime, setVideoTime] = useState(0)
  const videoRef = useRef<VideoPlayerHandle>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (data?.subtitles) setSubtitles(data.subtitles)
  }, [data, setSubtitles])

  const filtered = useMemo(() => {
    if (!searchTerm.trim()) return subtitles
    const lower = searchTerm.toLowerCase()
    return subtitles.filter((s) => s.text.toLowerCase().includes(lower))
  }, [subtitles, searchTerm])

  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 72,
    overscan: 10,
  })

  const activeIndex = useMemo(() => {
    for (let i = subtitles.length - 1; i >= 0; i--) {
      if (videoTime >= subtitles[i].start_time && videoTime <= subtitles[i].end_time) return i
    }
    return -1
  }, [subtitles, videoTime])

  const handleSave = useCallback(() => {
    if (!data) return
    saveMutation.mutate(
      { task_id: taskId, subtitles, metadata: data.metadata },
      { onSuccess: () => markSaved() }
    )
  }, [taskId, subtitles, data, saveMutation, markSaved])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); handleSave() }
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') { e.preventDefault(); useEditorStore.getState().undo() }
      if ((e.ctrlKey || e.metaKey) && e.key === 'y') { e.preventDefault(); useEditorStore.getState().redo() }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleSave])

  const videoSrc = data?.metadata?.video_url
    ? (data.metadata.video_url.startsWith('/') ? data.metadata.video_url : api.downloadFile(taskId, 'video'))
    : undefined

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-48" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="aspect-video rounded-lg" />
          <Skeleton className="h-[500px] rounded-lg" />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link to="/">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-5 w-5" /></Button>
        </Link>
        <h1 className="text-xl font-semibold text-text dark:text-text-dark">
          字幕編輯器
        </h1>
        {data?.metadata?.original_file && (
          <span className="text-sm text-muted dark:text-muted-dark truncate">— {data.metadata.original_file}</span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <VideoPlayer ref={videoRef} src={videoSrc} onTimeUpdate={setVideoTime} />
          <Card className="p-4">
            <div className="grid grid-cols-3 gap-4 text-center text-sm">
              <div>
                <p className="text-muted dark:text-muted-dark">字幕數</p>
                <p className="text-lg font-semibold text-text dark:text-text-dark">{subtitles.length}</p>
              </div>
              <div>
                <p className="text-muted dark:text-muted-dark">語言</p>
                <p className="text-lg font-semibold text-text dark:text-text-dark">{data?.metadata?.language || '—'}</p>
              </div>
              <div>
                <p className="text-muted dark:text-muted-dark">模型</p>
                <p className="text-lg font-semibold text-text dark:text-text-dark truncate">{data?.metadata?.model || '—'}</p>
              </div>
            </div>
          </Card>
        </div>

        <Card className="flex flex-col overflow-hidden">
          <SubtitleToolbar onSave={handleSave} onExport={() => setExportOpen(true)} saving={saveMutation.isPending} />
          <div ref={scrollRef} className="flex-1 overflow-auto" style={{ maxHeight: 'calc(100vh - 280px)' }}>
            <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
              {virtualizer.getVirtualItems().map((vItem) => {
                const sub = filtered[vItem.index]
                const realIndex = subtitles.indexOf(sub)
                return (
                  <div
                    key={vItem.key}
                    data-index={vItem.index}
                    ref={virtualizer.measureElement}
                    style={{ position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${vItem.start}px)` }}
                  >
                    <SubtitleRow
                      subtitle={sub}
                      index={realIndex}
                      isActive={realIndex === activeIndex}
                      onSelect={() => setSelectedIndex(realIndex)}
                      onSeek={(t) => videoRef.current?.seek(t)}
                    />
                  </div>
                )
              })}
            </div>
          </div>
        </Card>
      </div>

      <ExportDialog open={exportOpen} onClose={() => setExportOpen(false)} taskId={taskId} />
    </div>
  )
}

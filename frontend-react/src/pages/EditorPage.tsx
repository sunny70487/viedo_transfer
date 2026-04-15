import { useEffect, useRef, useCallback, useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Keyboard, Loader2 } from 'lucide-react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { SubtitleToolbar } from '@/components/editor/SubtitleToolbar'
import { SubtitleRow } from '@/components/editor/SubtitleRow'
import { VideoPlayer, type VideoPlayerHandle } from '@/components/editor/VideoPlayer'
import { ExportDialog } from '@/components/editor/ExportDialog'
import { LlmEnhanceDialog } from '@/components/editor/LlmEnhanceDialog'
import { useSubtitles, useSaveSubtitles } from '@/hooks/use-subtitles'
import { useTask } from '@/hooks/use-task'
import { useEditorStore } from '@/stores/editor-store'
import { api } from '@/api/client'
import type { Subtitle } from '@/types/api'

function ShortcutSection({ title, children }: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <div>
      <p className="text-xs font-semibold text-muted dark:text-muted-dark uppercase tracking-wider mb-1.5">{title}</p>
      <div className="space-y-1">{children}</div>
    </div>
  )
}

function Shortcut({ keys, desc }: Readonly<{ keys: string; desc: string }>) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-text dark:text-text-dark">{desc}</span>
      <kbd className="px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800 border border-border dark:border-border-dark text-xs font-mono text-muted dark:text-muted-dark">{keys}</kbd>
    </div>
  )
}

export function EditorPage() {
  const { taskId = '' } = useParams()
  const { data, isLoading } = useSubtitles(taskId)
  const saveMutation = useSaveSubtitles(taskId)
  const queryClient = useQueryClient()
  const { task: liveTask } = useTask(taskId)
  const {
    subtitles, searchTerm,
    setSubtitles, setSelectedIndex, markSaved, replaceSubtitles,
  } = useEditorStore()
  const [exportOpen, setExportOpen] = useState(false)
  const [enhanceOpen, setEnhanceOpen] = useState(false)
  const [videoTime, setVideoTime] = useState(0)
  const videoRef = useRef<VideoPlayerHandle>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const isStreaming = liveTask !== null && !['completed', 'failed'].includes(liveTask.status ?? '')

  const streamingSubtitles = useMemo<Subtitle[]>(() => {
    if (!isStreaming || !liveTask?.partial_segments) return []
    return liveTask.partial_segments.map((seg, i) => ({
      index: i,
      start_time: seg.start,
      end_time: seg.end,
      text: seg.text,
      speaker: seg.speaker,
    }))
  }, [isStreaming, liveTask?.partial_segments])

  useEffect(() => {
    if (data?.subtitles) setSubtitles(data.subtitles)
  }, [data, setSubtitles])

  // When streaming completes, reload subtitle data
  useEffect(() => {
    if (liveTask?.status === 'completed') {
      queryClient.invalidateQueries({ queryKey: ['subtitles', taskId] })
    }
  }, [liveTask?.status, taskId, queryClient])

  const filtered = useMemo(() => {
    if (isStreaming) return streamingSubtitles
    if (!searchTerm.trim()) return subtitles
    const lower = searchTerm.toLowerCase()
    return subtitles.filter((s) => s.text.toLowerCase().includes(lower))
  }, [subtitles, searchTerm, isStreaming, streamingSubtitles])

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

  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  const prevActiveRef = useRef(-1)
  useEffect(() => {
    if (activeIndex >= 0 && activeIndex !== prevActiveRef.current && !searchTerm.trim()) {
      virtualizer.scrollToIndex(activeIndex, { align: 'center', behavior: 'smooth' })
    }
    prevActiveRef.current = activeIndex
  }, [activeIndex, virtualizer, searchTerm])

  const virtualizerRef = useRef(virtualizer)
  virtualizerRef.current = virtualizer

  const handleSave = useCallback(() => {
    if (!data) return
    saveMutation.mutate(
      { task_id: taskId, subtitles, metadata: data.metadata },
      { onSuccess: () => markSaved() }
    )
  }, [taskId, subtitles, data, saveMutation, markSaved])

  const getActiveIdx = useCallback(() => {
    const time = videoRef.current?.getCurrentTime() ?? 0
    const subs = useEditorStore.getState().subtitles
    for (let i = subs.length - 1; i >= 0; i--) {
      if (time >= subs[i].start_time && time <= subs[i].end_time) return i
    }
    return -1
  }, [])

  const roundTime = (t: number) => Math.round(t * 1000) / 1000

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      const isTextInput = target.tagName === 'TEXTAREA' || target.tagName === 'INPUT' || target.isContentEditable

      if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); handleSave(); return }
      if (isTextInput) return

      const store = useEditorStore.getState()
      const subs = store.subtitles
      const idx = getActiveIdx()

      if (e.ctrlKey || e.metaKey) {
        switch (e.key) {
          case 'z': e.preventDefault(); store.undo(); return
          case 'y': e.preventDefault(); store.redo(); return
          case 'd': e.preventDefault(); if (idx >= 0) store.splitSubtitle(idx, videoRef.current?.getCurrentTime() ?? 0); return
          case 'm': e.preventDefault(); if (idx >= 0) store.mergeWithNext(idx); return
        }
        return
      }

      switch (e.key) {
        case ' ':
          e.preventDefault()
          if (target.tagName === 'BUTTON') target.blur()
          videoRef.current?.toggle()
          break
        case 'ArrowLeft':
          e.preventDefault()
          videoRef.current?.seekRelative(e.shiftKey ? -1 : -5)
          break
        case 'ArrowRight':
          e.preventDefault()
          videoRef.current?.seekRelative(e.shiftKey ? 1 : 5)
          break
        case 'ArrowUp': {
          e.preventDefault()
          const current = store.selectedIndex >= 0 ? store.selectedIndex : idx
          const prev = Math.max(0, current - 1)
          store.setSelectedIndex(prev)
          if (subs[prev]) videoRef.current?.seek(subs[prev].start_time)
          virtualizerRef.current.scrollToIndex(prev, { align: 'center', behavior: 'smooth' })
          break
        }
        case 'ArrowDown': {
          e.preventDefault()
          const current = store.selectedIndex >= 0 ? store.selectedIndex : idx
          const next = Math.min(subs.length - 1, current + 1)
          store.setSelectedIndex(next)
          if (subs[next]) videoRef.current?.seek(subs[next].start_time)
          virtualizerRef.current.scrollToIndex(next, { align: 'center', behavior: 'smooth' })
          break
        }
        case '[':
          e.preventDefault()
          if (idx >= 0) store.updateSubtitle(idx, { start_time: roundTime(Math.max(0, subs[idx].start_time - 0.1)) })
          break
        case ']':
          e.preventDefault()
          if (idx >= 0) store.updateSubtitle(idx, { end_time: roundTime(subs[idx].end_time + 0.1) })
          break
        case '{':
          e.preventDefault()
          if (idx >= 0) store.updateSubtitle(idx, { start_time: roundTime(Math.min(subs[idx].end_time - 0.1, subs[idx].start_time + 0.1)) })
          break
        case '}':
          e.preventDefault()
          if (idx >= 0) store.updateSubtitle(idx, { end_time: roundTime(Math.max(subs[idx].start_time + 0.1, subs[idx].end_time - 0.1)) })
          break
        case '?':
          e.preventDefault()
          setShortcutsOpen(prev => !prev)
          break
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleSave, getActiveIdx])

  const videoSrc = data?.metadata?.video_info?.video_url
    || api.downloadFile(taskId, 'video')

  if (isLoading && !isStreaming) {
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
        {data?.metadata?.video_info?.format && (
          <span className="text-sm text-muted dark:text-muted-dark truncate">— {data.metadata.video_info.format.toUpperCase()}</span>
        )}
        <Button variant="ghost" size="icon" onClick={() => setShortcutsOpen(true)} title="快捷鍵 (?)">
          <Keyboard className="h-4 w-4" />
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          {isStreaming ? (
            <div className="aspect-video rounded-lg bg-bg dark:bg-bg-dark border border-border dark:border-border-dark flex flex-col items-center justify-center gap-3 text-muted dark:text-muted-dark">
              <Loader2 className="h-8 w-8 animate-spin text-primary/60" aria-hidden="true" />
              <p className="text-sm">轉錄完成後影片將顯示於此</p>
              <p className="text-xs">{liveTask?.message || ''}</p>
            </div>
          ) : (
            <VideoPlayer ref={videoRef} src={videoSrc} subtitles={subtitles} onTimeUpdate={setVideoTime} />
          )}
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
                <p className="text-lg font-semibold text-text dark:text-text-dark truncate">{data?.metadata?.model_used || '—'}</p>
              </div>
            </div>
          </Card>
        </div>

        <Card className="flex flex-col overflow-hidden">
          {isStreaming && (
            <div
              className="flex items-center gap-2 px-4 py-2 bg-primary/10 border-b border-primary/20 text-sm text-primary"
              aria-live="polite"
            >
              <Loader2 className="h-4 w-4 animate-spin shrink-0" aria-hidden="true" />
              <span>
                轉錄中… 已完成 {liveTask?.partial_segments?.length ?? 0} 行
                {liveTask?.progress ? `（${Math.round(liveTask.progress)}%）` : ''}
              </span>
            </div>
          )}
          <SubtitleToolbar
            onSave={handleSave}
            onExport={() => setExportOpen(true)}
            onEnhance={() => setEnhanceOpen(true)}
            onImport={replaceSubtitles}
            saving={saveMutation.isPending}
            disabled={isStreaming}
          />
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
                      onSeek={(t) => {
                        videoRef.current?.seek(t)
                        videoRef.current?.play()
                      }}
                      currentTime={videoTime}
                    />
                  </div>
                )
              })}
            </div>
          </div>
        </Card>
      </div>

      <ExportDialog open={exportOpen} onClose={() => setExportOpen(false)} taskId={taskId} />
      <LlmEnhanceDialog
        open={enhanceOpen}
        onClose={() => setEnhanceOpen(false)}
        subtitles={subtitles}
        taskId={taskId}
        onEnhanced={replaceSubtitles}
        onSeekTo={(time) => videoRef.current?.seek(time)}
      />
      {shortcutsOpen && (
        <div
          role="dialog"
          aria-label="快捷鍵說明"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setShortcutsOpen(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShortcutsOpen(false) }}
        >
          <div className="bg-surface dark:bg-surface-dark rounded-xl shadow-2xl border border-border dark:border-border-dark p-6 max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-text dark:text-text-dark mb-4">鍵盤快捷鍵</h2>
            <div className="space-y-3 text-sm">
              <ShortcutSection title="播放控制">
                <Shortcut keys="Space" desc="播放 / 暫停" />
                <Shortcut keys="← / →" desc="後退 / 前進 5 秒" />
                <Shortcut keys="Shift + ← / →" desc="後退 / 前進 1 秒" />
              </ShortcutSection>
              <ShortcutSection title="字幕導航">
                <Shortcut keys="↑ / ↓" desc="上一句 / 下一句字幕" />
              </ShortcutSection>
              <ShortcutSection title="時間微調（當前字幕）">
                <Shortcut keys="[" desc="起始時間 −0.1s" />
                <Shortcut keys="]" desc="結束時間 +0.1s" />
                <Shortcut keys="{" desc="起始時間 +0.1s" />
                <Shortcut keys="}" desc="結束時間 −0.1s" />
              </ShortcutSection>
              <ShortcutSection title="編輯操作">
                <Shortcut keys="Ctrl+D" desc="在當前時間分割字幕" />
                <Shortcut keys="Ctrl+M" desc="合併當前字幕與下一句" />
                <Shortcut keys="Ctrl+Z" desc="復原" />
                <Shortcut keys="Ctrl+Y" desc="重做" />
                <Shortcut keys="Ctrl+S" desc="儲存" />
              </ShortcutSection>
            </div>
            <div className="mt-4 flex justify-end">
              <Button variant="outline" size="sm" onClick={() => setShortcutsOpen(false)}>關閉</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

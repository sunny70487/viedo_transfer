import { useCallback, useEffect, useRef } from 'react'
import type { Task } from '@/types/api'

const ACTIVE_STATUSES = new Set([
  'queued',
  'uploading',
  'downloading',
  'processing',
  'transcribing',
])

const FLASH_TITLE = '(✓) 轉錄完成 - Whisper Transfer'

let notificationPermissionRequested = false

function isActiveStatus(status: string): boolean {
  return ACTIVE_STATUSES.has(status)
}

function requestNotificationOnce(): Promise<boolean> {
  if (typeof Notification === 'undefined') return Promise.resolve(false)
  const perm = Notification.permission
  if (perm === 'granted') return Promise.resolve(true)
  if (perm === 'denied' || notificationPermissionRequested) return Promise.resolve(false)
  notificationPermissionRequested = true
  return Notification.requestPermission().then((p) => p === 'granted')
}

function showNotification(body: string): void {
  void requestNotificationOnce().then((ok) => {
    if (!ok) return
    try {
      new Notification('Whisper Transfer', { body })
    } catch {
      /* ignore */
    }
  })
}

export function useTaskNotifications(tasks?: Record<string, Task>): void {
  const prevStatusesRef = useRef<Record<string, string>>({})
  const titleFlashIdRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const savedTitleRef = useRef('')

  const stopTitleFlash = useCallback(() => {
    if (titleFlashIdRef.current !== null) {
      clearInterval(titleFlashIdRef.current)
      titleFlashIdRef.current = null
    }
    if (savedTitleRef.current) {
      document.title = savedTitleRef.current
      savedTitleRef.current = ''
    }
  }, [])

  const startCompleteTitleFlash = useCallback(() => {
    if (!document.hidden || titleFlashIdRef.current !== null) return
    savedTitleRef.current = document.title
    let showFlash = false
    titleFlashIdRef.current = setInterval(() => {
      showFlash = !showFlash
      document.title = showFlash ? FLASH_TITLE : savedTitleRef.current
    }, 1000)
  }, [])

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'visible') stopTitleFlash()
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      stopTitleFlash()
    }
  }, [stopTitleFlash])

  useEffect(() => {
    if (!tasks) return

    const prev = prevStatusesRef.current
    const next: Record<string, string> = {}

    for (const [, task] of Object.entries(tasks)) {
      const was = prev[task.id]
      const current = task.status

      if (
        was !== undefined &&
        isActiveStatus(was) &&
        (current === 'completed' || current === 'failed')
      ) {
        const name = task.source_name ?? ''
        if (current === 'completed') {
          showNotification(`✓ 轉錄完成\n${name}`)
          if (document.hidden) startCompleteTitleFlash()
        } else {
          showNotification(`✗ 轉錄失敗\n${name}${task.error ?? ''}`)
        }
      }

      next[task.id] = current
    }

    prevStatusesRef.current = next
  }, [tasks, startCompleteTitleFlash])
}

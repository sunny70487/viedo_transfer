import { useState, useEffect, useRef } from 'react'
import type { Task } from '@/types/api'

export function useTask(taskId: string) {
  const [task, setTask] = useState<Task | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!taskId) { setIsLoading(false); return }
    setIsLoading(true)

    function subscribeSSE() {
      esRef.current?.close()
      const es = new EventSource(`/tasks/${taskId}/stream`)
      esRef.current = es
      es.onmessage = (e) => {
        try {
          const data: Task = JSON.parse(e.data)
          setTask(data)
          if (['completed', 'failed'].includes(data.status)) {
            es.close()
          }
        } catch { /* ignore */ }
      }
      es.onerror = () => es.close()
    }

    fetch(`/tasks/${taskId}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data: Task | null) => {
        if (data) setTask(data)
        setIsLoading(false)
        if (data && !['completed', 'failed'].includes(data.status)) {
          subscribeSSE()
        }
      })
      .catch(() => setIsLoading(false))

    return () => {
      esRef.current?.close()
    }
  }, [taskId])

  return { task, isLoading }
}

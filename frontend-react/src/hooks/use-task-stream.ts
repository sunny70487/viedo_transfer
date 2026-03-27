import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Task } from '@/types/api'

/**
 * Subscribe to real-time task updates via Server-Sent Events.
 * Updates the React Query cache directly so every consumer re-renders
 * without additional fetches.
 */
export function useTaskStream(taskId: string, enabled = true) {
  const qc = useQueryClient()
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!taskId || !enabled) return

    const es = new EventSource(`/tasks/${taskId}/stream`)
    esRef.current = es

    es.onmessage = (event) => {
      try {
        const task: Task = JSON.parse(event.data)

        qc.setQueryData(['task', taskId], task)

        qc.setQueryData<Record<string, Task>>(['tasks'], (old) => {
          if (!old) return old
          return { ...old, [taskId]: task }
        })

        if (task.status === 'completed' || task.status === 'failed') {
          es.close()
        }
      } catch {
        // ignore malformed events
      }
    }

    es.addEventListener('deleted', () => {
      es.close()
      qc.invalidateQueries({ queryKey: ['tasks'] })
    })

    es.onerror = () => {
      es.close()
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [taskId, enabled, qc])
}

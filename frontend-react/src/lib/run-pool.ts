export interface TaskPool {
  /** Queue a task; at most `limit` run at once. Settles with the task's result. */
  run<T>(task: () => Promise<T>): Promise<T>
  /** Drop tasks that have not started; their promises reject with an AbortError. */
  clear(): void
  /** Number of tasks running or waiting. */
  readonly size: number
}

interface Waiting {
  start: () => void
  cancel: () => void
}

export function createPool(limit: number): TaskPool {
  let active = 0
  const waiting: Waiting[] = []

  const release = () => {
    active -= 1
    waiting.shift()?.start()
  }

  return {
    run<T>(task: () => Promise<T>): Promise<T> {
      return new Promise<T>((resolve, reject) => {
        const start = () => {
          active += 1
          new Promise<T>((settle) => settle(task())).then(
            (value) => { release(); resolve(value) },
            (error: unknown) => { release(); reject(error) },
          )
        }
        if (active < limit) start()
        else {
          waiting.push({
            start,
            cancel: () => reject(new DOMException('Cancelled before start', 'AbortError')),
          })
        }
      })
    },
    clear() {
      waiting.splice(0).forEach((entry) => entry.cancel())
    },
    get size() {
      return active + waiting.length
    },
  }
}

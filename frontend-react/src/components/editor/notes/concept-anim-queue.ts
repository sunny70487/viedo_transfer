const MAX_CONCURRENT = 2

let active = 0
const waiting: Array<() => void> = []

function release() {
  active -= 1
  const next = waiting.shift()
  if (next) next()
}

export function runInAnimQueue<T>(task: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const start = () => {
      active += 1
      task().then(resolve, reject).finally(release)
    }
    if (active < MAX_CONCURRENT) start()
    else waiting.push(start)
  })
}

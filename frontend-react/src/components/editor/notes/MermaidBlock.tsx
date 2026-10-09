import { useEffect, useState } from 'react'
import { useThemeStore } from '@/stores/theme-store'

let renderSeq = 0

interface MermaidBlockProps {
  code: string
}

type RenderState =
  | { kind: 'pending' }
  | { kind: 'ready'; svg: string }
  | { kind: 'failed' }

export function MermaidBlock({ code }: Readonly<MermaidBlockProps>) {
  const theme = useThemeStore((s) => s.resolved)
  const [state, setState] = useState<RenderState>({ kind: 'pending' })

  useEffect(() => {
    let cancelled = false
    renderSeq += 1
    const id = `mermaid-${renderSeq}`
    import('mermaid')
      .then(async ({ default: mermaid }) => {
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: theme === 'dark' ? 'dark' : 'default',
        })
        const result = await mermaid.render(id, code)
        if (!cancelled) setState({ kind: 'ready', svg: result.svg })
      })
      .catch(() => {
        // mermaid leaves its temporary render node behind on syntax errors
        document.getElementById(id)?.remove()
        document.getElementById(`d${id}`)?.remove()
        if (!cancelled) setState({ kind: 'failed' })
      })
    return () => { cancelled = true }
  }, [code, theme])

  if (state.kind === 'failed') {
    return (
      <div className="my-4">
        <p className="text-xs text-warning mb-1">圖表語法錯誤，顯示原始碼</p>
        <pre className="overflow-auto rounded-lg border border-border dark:border-border-dark bg-bg dark:bg-bg-dark p-3 text-xs font-mono">
          {code}
        </pre>
      </div>
    )
  }

  if (state.kind === 'pending') {
    return <div className="my-4 h-32 rounded-lg bg-gray-100 dark:bg-gray-800 animate-pulse" aria-busy="true" />
  }

  return (
    <div
      className="my-4 flex justify-center overflow-auto rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-3"
      // mermaid output is sanitized by securityLevel: 'strict'
      dangerouslySetInnerHTML={{ __html: state.svg }}
    />
  )
}

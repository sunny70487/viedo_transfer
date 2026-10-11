import { useEffect, useRef } from 'react'
import type { IPureNode } from 'markmap-common'
import type { Markmap } from 'markmap-view'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/stores/theme-store'
import type { MindmapNode } from '@/types/api'

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function toPureNode(node: MindmapNode): IPureNode {
  const label = `${escapeHtml(node.title)} <small style="opacity:.6">${formatTime(node.time)}</small>`
  return {
    content: `<span class="mindmap-seek" data-t="${Number(node.time) || 0}" style="cursor:pointer">${label}</span>`,
    children: node.children.map(toPureNode),
  }
}

interface MindmapViewProps {
  root: MindmapNode
  onSeekTo: (time: number) => void
  className?: string
}

export function MindmapView({ root, onSeekTo, className }: Readonly<MindmapViewProps>) {
  const svgRef = useRef<SVGSVGElement>(null)
  const seekRef = useRef(onSeekTo)
  const dark = useThemeStore((s) => s.resolved === 'dark')

  useEffect(() => { seekRef.current = onSeekTo }, [onSeekTo])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    let cancelled = false
    let mm: Markmap | null = null
    import('markmap-view').then(({ Markmap }) => {
      if (cancelled) return
      svg.innerHTML = ''
      mm = Markmap.create(svg, { initialExpandLevel: 3, duration: 300 }, toPureNode(root))
    })
    return () => {
      cancelled = true
      mm?.destroy()
    }
  }, [root])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const handleClick = (e: MouseEvent) => {
      const target = (e.target as Element | null)?.closest('[data-t]')
      if (!target) return
      const t = Number(target.getAttribute('data-t'))
      if (Number.isFinite(t)) seekRef.current(t)
    }
    svg.addEventListener('click', handleClick)
    return () => svg.removeEventListener('click', handleClick)
  }, [])

  return (
    <div className={cn('rounded-lg border border-border dark:border-border-dark bg-bg dark:bg-bg-dark', className)}>
      <svg
        ref={svgRef}
        className={cn('h-full w-full', dark && 'markmap-dark')}
        style={{ color: dark ? '#F1F5F9' : '#0F172A' }}
      />
    </div>
  )
}

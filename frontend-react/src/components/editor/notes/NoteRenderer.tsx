import { isValidElement, useMemo, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MermaidBlock } from './MermaidBlock'
import { ConceptAnimationCard } from './ConceptAnimationCard'
import { dedupeConceptAnimIds, parseConceptAnimSpec } from './concept-anim-spec'

interface NoteRendererProps {
  markdown: string
  streaming: boolean
  taskId: string
  autoGenerateAnims: boolean
}

function DiagramPlaceholder({ label }: Readonly<{ label: string }>) {
  return (
    <div className="my-4 flex h-24 items-center justify-center rounded-lg border border-dashed border-border dark:border-border-dark text-xs text-muted dark:text-muted-dark">
      {label}
    </div>
  )
}

function readCodeChild(children: ReactNode): { lang: string; text: string } {
  if (!isValidElement<{ className?: string; children?: ReactNode }>(children)) {
    return { lang: '', text: String(children ?? '') }
  }
  const lang = /language-([\w-]+)/.exec(children.props.className ?? '')?.[1] ?? ''
  const text = String(children.props.children ?? '').replace(/\n$/, '')
  return { lang, text }
}

function buildComponents(streaming: boolean, taskId: string, autoGenerateAnims: boolean): Components {
  return {
    h1: ({ children }) => <h1 className="mt-2 mb-4 text-2xl font-bold">{children}</h1>,
    h2: ({ children }) => <h2 className="mt-6 mb-3 text-xl font-semibold border-b border-border dark:border-border-dark pb-1">{children}</h2>,
    h3: ({ children }) => <h3 className="mt-4 mb-2 text-lg font-semibold">{children}</h3>,
    p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
    ul: ({ children }) => <ul className="my-2 ml-5 list-disc space-y-1">{children}</ul>,
    ol: ({ children }) => <ol className="my-2 ml-5 list-decimal space-y-1">{children}</ol>,
    blockquote: ({ children }) => (
      <blockquote className="my-3 border-l-4 border-primary/50 bg-primary/5 px-4 py-2">
        {children}
      </blockquote>
    ),
    a: ({ children, href }) => (
      <a href={href} target="_blank" rel="noreferrer noopener" className="text-primary underline">{children}</a>
    ),
    table: ({ children }) => (
      <div className="my-3 overflow-x-auto">
        <table className="w-full border-collapse text-sm">{children}</table>
      </div>
    ),
    th: ({ children }) => <th className="border border-border dark:border-border-dark bg-bg dark:bg-bg-dark px-2 py-1 text-left font-semibold">{children}</th>,
    td: ({ children }) => <td className="border border-border dark:border-border-dark px-2 py-1 align-top">{children}</td>,
    code: ({ children }) => (
      <code className="rounded bg-gray-100 dark:bg-gray-800 px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
    ),
    pre: ({ children }) => {
      const { lang, text } = readCodeChild(children)
      if (lang === 'mermaid') {
        return streaming ? <DiagramPlaceholder label="圖表產生中…" /> : <MermaidBlock code={text} />
      }
      if (lang === 'concept-anim') {
        if (streaming) return <DiagramPlaceholder label="概念動畫（筆記完成後繪製）" />
        const spec = parseConceptAnimSpec(text)
        if (spec) {
          return <ConceptAnimationCard key={spec.id} taskId={taskId} spec={spec} autoGenerate={autoGenerateAnims} />
        }
      }
      return (
        <pre className="my-3 overflow-auto rounded-lg border border-border dark:border-border-dark bg-bg dark:bg-bg-dark p-3 text-xs leading-relaxed font-mono">
          <code>{text}</code>
        </pre>
      )
    },
  }
}

export function NoteRenderer({ markdown, streaming, taskId, autoGenerateAnims }: Readonly<NoteRendererProps>) {
  const source = useMemo(
    () => (streaming ? markdown : dedupeConceptAnimIds(markdown)),
    [markdown, streaming],
  )
  const components = useMemo(
    () => buildComponents(streaming, taskId, autoGenerateAnims),
    [streaming, taskId, autoGenerateAnims],
  )
  return (
    <article className="text-sm text-text dark:text-text-dark break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {source}
      </ReactMarkdown>
    </article>
  )
}

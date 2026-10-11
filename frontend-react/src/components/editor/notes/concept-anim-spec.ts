import type { ConceptAnimSpec } from '@/types/api'

const ID_RE = /^[a-z0-9-]{1,32}$/
const BLOCK_RE = /```concept-anim[^\S\n]*\n([\s\S]*?)```/g
const MAX_ID_LENGTH = 32

export function parseConceptAnimSpec(text: string): ConceptAnimSpec | null {
  try {
    const data: unknown = JSON.parse(text.trim())
    if (typeof data !== 'object' || data === null) return null
    const { id, title, brief } = data as Record<string, unknown>
    if (typeof id !== 'string' || !ID_RE.test(id)) return null
    if (typeof title !== 'string' || !title.trim()) return null
    if (typeof brief !== 'string' || !brief.trim()) return null
    return { id, title: title.trim(), brief: brief.trim() }
  } catch {
    return null
  }
}

export function dedupeConceptAnimIds(markdown: string): string {
  const seen = new Set<string>()
  return markdown.replace(BLOCK_RE, (block, body: string) => {
    const spec = parseConceptAnimSpec(body)
    if (!spec) return block
    let id = spec.id
    for (let n = 2; seen.has(id); n += 1) {
      const suffix = `-${n}`
      id = `${spec.id.slice(0, MAX_ID_LENGTH - suffix.length)}${suffix}`
    }
    seen.add(id)
    if (id === spec.id) return block
    return '```concept-anim\n' + JSON.stringify({ ...spec, id }) + '\n```'
  })
}

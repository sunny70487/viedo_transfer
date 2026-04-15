import type { Subtitle } from '@/types/api'

function parseTimeToSeconds(timeStr: string): number {
  const parts = timeStr.trim().replace(',', '.').split(':')
  if (parts.length === 3) {
    const [h, m, s] = parts
    return parseInt(h) * 3600 + parseInt(m) * 60 + parseFloat(s)
  }
  if (parts.length === 2) {
    const [m, s] = parts
    return parseInt(m) * 60 + parseFloat(s)
  }
  return parseFloat(timeStr) || 0
}

const TIME_ARROW = /(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})/

function parseSrt(content: string): Subtitle[] {
  const blocks = content.trim().replace(/\r\n/g, '\n').split(/\n\n+/)
  const subs: Subtitle[] = []

  for (const block of blocks) {
    const lines = block.split('\n').filter(l => l.trim())
    if (lines.length < 2) continue

    let timeLineIdx = -1
    for (let i = 0; i < lines.length; i++) {
      if (TIME_ARROW.test(lines[i])) { timeLineIdx = i; break }
    }
    if (timeLineIdx < 0) continue

    const match = lines[timeLineIdx].match(TIME_ARROW)!
    const text = lines.slice(timeLineIdx + 1).join('\n').trim()
    if (!text) continue

    subs.push({
      index: subs.length,
      start_time: parseTimeToSeconds(match[1]),
      end_time: parseTimeToSeconds(match[2]),
      text,
    })
  }
  return subs
}

function parseVtt(content: string): Subtitle[] {
  const lines = content.trim().replace(/\r\n/g, '\n').split('\n')
  const subs: Subtitle[] = []
  let i = 0

  while (i < lines.length && !TIME_ARROW.test(lines[i])) i++

  while (i < lines.length) {
    if (!TIME_ARROW.test(lines[i])) { i++; continue }

    const match = lines[i].match(TIME_ARROW)!
    i++
    const textLines: string[] = []
    while (i < lines.length && lines[i].trim() !== '' && !TIME_ARROW.test(lines[i])) {
      textLines.push(lines[i])
      i++
    }

    const text = textLines.join('\n').trim()
    if (text) {
      subs.push({
        index: subs.length,
        start_time: parseTimeToSeconds(match[1]),
        end_time: parseTimeToSeconds(match[2]),
        text,
      })
    }

    while (i < lines.length && lines[i].trim() === '') i++
  }
  return subs
}

const ASS_TIME = /(\d+):(\d{2}):(\d{2})\.(\d{2})/

function parseAssTime(timeStr: string): number {
  const m = timeStr.match(ASS_TIME)
  if (!m) return 0
  return parseInt(m[1]) * 3600 + parseInt(m[2]) * 60 + parseInt(m[3]) + parseInt(m[4]) / 100
}

function parseAss(content: string): Subtitle[] {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const subs: Subtitle[] = []

  for (const line of lines) {
    if (!line.startsWith('Dialogue:')) continue
    const parts = line.substring(9).split(',')
    if (parts.length < 10) continue

    const startTime = parseAssTime(parts[1].trim())
    const endTime = parseAssTime(parts[2].trim())
    const text = parts.slice(9).join(',')
      .replace(/\{[^}]*\}/g, '')
      .replace(/\\N/gi, '\n')
      .trim()

    if (text) {
      subs.push({ index: subs.length, start_time: startTime, end_time: endTime, text })
    }
  }
  return subs
}

export function parseSubtitleFile(content: string, filename: string): Subtitle[] {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  switch (ext) {
    case 'srt': return parseSrt(content)
    case 'vtt': return parseVtt(content)
    case 'ass':
    case 'ssa': return parseAss(content)
    default: return parseSrt(content)
  }
}

export const IMPORTABLE_EXTENSIONS = '.srt,.vtt,.ass,.ssa'

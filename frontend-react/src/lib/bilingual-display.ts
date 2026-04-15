/** localStorage：雙語字幕是否以「第一行」為主字幕（較大）；false 表示以第二行為主 */
export const BILINGUAL_PRIMARY_FIRST_LINE_KEY = 'editor-bilingual-primary-is-first-line'

export function readBilingualPrimaryIsFirstLine(): boolean {
  try {
    return localStorage.getItem(BILINGUAL_PRIMARY_FIRST_LINE_KEY) !== 'false'
  } catch {
    return true
  }
}

export function writeBilingualPrimaryIsFirstLine(primaryIsFirstLine: boolean): void {
  try {
    localStorage.setItem(
      BILINGUAL_PRIMARY_FIRST_LINE_KEY,
      primaryIsFirstLine ? 'true' : 'false'
    )
  } catch {
    /* ignore quota / private mode */
  }
}

/** 依主字幕列設定拆成主行與副行（副行可含第三行以後，以小字顯示） */
export function splitBilingualDisplay(
  text: string,
  primaryIsFirstLine: boolean
): { primary: string; secondary: string | null } {
  const lines = text.split('\n')
  if (lines.length < 2) {
    return { primary: text, secondary: null }
  }
  if (primaryIsFirstLine) {
    const secondary = lines.slice(1).join('\n')
    return { primary: lines[0], secondary: secondary || null }
  }
  const secondary = [lines[0], ...lines.slice(2)].join('\n')
  return { primary: lines[1], secondary: secondary || null }
}

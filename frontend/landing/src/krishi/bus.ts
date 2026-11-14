/** Open Krishi from anywhere on a farmer's screen — the search button, a quick
 *  action, the sidebar — optionally with a question already asked. Krishi
 *  listens for this; nothing else needs to know where it is mounted. */
export const KRISHI_EVENT = 'ar-krishi'

export function askKrishi(text?: string) {
  window.dispatchEvent(new CustomEvent(KRISHI_EVENT, { detail: { text } }))
}

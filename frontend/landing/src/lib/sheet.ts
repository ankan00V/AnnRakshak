/** Page scroll lock shared by every sheet. Each sheet used to save and restore
 *  body overflow on its own, so two open at once (Krishi under the language
 *  sheet, on a phone) and closed in the other order left the page frozen
 *  until a reload. Counted: locked on the first, released on the last. */
let locks = 0
let before = ''
export function lockScroll(): () => void {
  if (locks++ === 0) {
    before = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  let released = false
  return () => {
    if (released) return
    released = true
    if (--locks === 0) document.body.style.overflow = before
  }
}

/** Escape closes the top sheet only. Each sheet registers while open; the
 *  newest one answers Escape and the ones under it stay put. */
const stack: (() => void)[] = []
let listening = false
export function onEscape(close: () => void): () => void {
  stack.push(close)
  if (!listening) {
    listening = true
    window.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || stack.length === 0) return
      e.preventDefault()
      stack[stack.length - 1]()
    })
  }
  return () => {
    const i = stack.lastIndexOf(close)
    if (i >= 0) stack.splice(i, 1)
  }
}

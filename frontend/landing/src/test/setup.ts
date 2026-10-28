import '@testing-library/jest-dom/vitest'

/** A real Storage, because the test DOM does not supply one.
 *
 *  Vitest 4 hands back a bare `{}` for window.localStorage under both jsdom 29
 *  and happy-dom. Left alone, every assertion about what this browser
 *  remembers would pass without anything being remembered — and the app
 *  wraps each call in try/catch for private mode, so the failure would be
 *  silent. This is the same contract the browser gives. */
class MemoryStorage implements Storage {
  #items = new Map<string, string>()
  get length() { return this.#items.size }
  key(i: number) { return [...this.#items.keys()][i] ?? null }
  getItem(k: string) { return this.#items.get(k) ?? null }
  setItem(k: string, v: string) { this.#items.set(k, String(v)) }
  removeItem(k: string) { this.#items.delete(k) }
  clear() { this.#items.clear() }
}

for (const name of ['localStorage', 'sessionStorage'] as const) {
  const current = globalThis[name] as Storage | undefined
  if (typeof current?.clear !== 'function') {
    const store = new MemoryStorage()
    Object.defineProperty(globalThis, name, { value: store, configurable: true, writable: true })
    if (typeof window !== 'undefined') {
      Object.defineProperty(window, name, { value: store, configurable: true, writable: true })
    }
  }
}

// Each test starts with a browser that remembers nothing.
beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
})

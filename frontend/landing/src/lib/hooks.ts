import { useCallback, useEffect, useRef, useState } from 'react'

// The last answer per request, so going back to a screen or a language shows
// at once while it refreshes. Cleared on sign-in and sign-out.
const CACHE = new Map<string, unknown>()
export const clearCache = () => CACHE.clear()

/** `key` (optional) names the request, e.g. ['home', farmId, lang].join(':'). */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[], key?: string) {
  const [data, setData] = useState<T | null>(() => (key && CACHE.has(key) ? (CACHE.get(key) as T) : null))
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)

  const run = useCallback(() => {
    const id = ++seq.current
    const cached = key !== undefined && CACHE.has(key)
    if (cached) setData(CACHE.get(key!) as T)
    setLoading(!cached)
    setError(null)
    fn()
      .then((d) => {
        if (key !== undefined) CACHE.set(key, d)
        if (id === seq.current) setData(d)
      })
      .catch((e) => id === seq.current && setError(e))
      .finally(() => id === seq.current && setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    run()
  }, [run])

  return { data, error, loading, reload: run, setData }
}

export function usePersistent<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw === null ? initial : (JSON.parse(raw) as T)
    } catch {
      return initial
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* private mode: keep in memory only */
    }
  }, [key, value])
  return [value, setValue] as const
}

/** True while the window is at least `px` wide (Tailwind's lg is 1024). The
 *  farmer app is designed for a phone; wide screens get a layout of their own
 *  only where a screen reads better in two columns, and the phone layout —
 *  order included — is left exactly as it is. */
export function useWide(px = 1024): boolean {
  const query = `(min-width: ${px}px)`
  const [wide, setWide] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const on = () => setWide(m.matches)
    on()
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [query])
  return wide
}

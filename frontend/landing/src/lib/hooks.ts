import { useCallback, useEffect, useRef, useState } from 'react'

// The last answer per request, so going back to a screen or a language shows
// at once while it refreshes. Cleared on sign-in and sign-out.
const CACHE = new Map<string, unknown>()
// When the server gave each of those answers, so a screen that could not reach
// it can say how old what it is showing is.
const WHEN = new Map<string, number>()

/** The requests that are also written to this phone.
 *
 *  The farmer who needs this app most is the one standing where there is no
 *  signal, and the map above dies with the tab: before this, an app opened
 *  offline had the shell, the farmer's session, and nothing to put on the
 *  screen but its own error. These three are what the morning asks for — the
 *  home screen, the field checks and the weather — and each is kept exactly as
 *  the server sent it, so what comes back is what was on screen yesterday and
 *  never a guess assembled from pieces. Nothing else is kept: the answer to a
 *  photograph must be the live one or an honest failure, and no part of the
 *  officer console is read in a field. */
const KEPT = ['home:', 'alerts:', 'weather:']
const STORE = 'ar.last.v1:'
/** Older than this and a saved answer is not worth putting on screen. Last
 *  week's "today's field checks" are not today's, and the honest screen is then
 *  the empty one with a retry on it rather than a page a farmer might act on. */
const KEEP_MS = 3 * 864e5

type Saved<T> = { at: number; data: T }

const kept = (key: string) => KEPT.some((p) => key.startsWith(p))

/** This phone's copy of a request, dropped if it has aged out. */
function load<T>(key: string): Saved<T> | null {
  if (!kept(key)) return null
  try {
    const raw = localStorage.getItem(STORE + key)
    if (raw === null) return null
    const saved = JSON.parse(raw) as Saved<T>
    if (typeof saved?.at !== 'number' || Date.now() - saved.at > KEEP_MS) {
      localStorage.removeItem(STORE + key)
      return null
    }
    return saved
  } catch {
    // Unreadable, or written by a version that shaped it differently: absent.
    return null
  }
}

/** Keep a fresh answer on this phone, and say when it arrived. */
function save(key: string, data: unknown): number {
  const at = Date.now()
  if (!kept(key)) return at
  try {
    localStorage.setItem(STORE + key, JSON.stringify({ at, data }))
  } catch {
    // Private mode, or the quota is full. Showing this answer matters more than
    // keeping it, so a write that fails is not a failure the farmer hears about.
  }
  return at
}

/** The cached answer for a request, pulling this phone's copy into memory the
 *  first time the key is asked for. */
function recall<T>(key: string): { data: T; at: number | null } | null {
  if (CACHE.has(key)) return { data: CACHE.get(key) as T, at: WHEN.get(key) ?? null }
  const saved = load<T>(key)
  if (!saved) return null
  CACHE.set(key, saved.data)
  WHEN.set(key, saved.at)
  return { data: saved.data, at: saved.at }
}

/** Forget every answer, in memory and on this phone. A farmer's home screen is
 *  their own; it must not be waiting here for whoever signs in next. */
export const clearCache = () => {
  CACHE.clear()
  WHEN.clear()
  try {
    const mine: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k?.startsWith(STORE)) mine.push(k)
    }
    // Collected first: removing while walking the list moves the rest along.
    for (const k of mine) localStorage.removeItem(k)
  } catch {
    /* private mode: nothing was ever written */
  }
}

/** `key` (optional) names the request, e.g. ['home', farmId, lang].join(':').
 *  `savedAt` is when the answer now on screen came from the server, which for
 *  a kept request may be a previous day; a screen pairs it with `error` to say
 *  that what it is showing is the last known and not the current. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[], key?: string) {
  const [data, setData] = useState<T | null>(() => (key !== undefined ? recall<T>(key)?.data ?? null : null))
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)
  const shown = useRef(key)

  const run = useCallback(() => {
    const id = ++seq.current
    const cached = key !== undefined ? recall<T>(key) : null
    if (cached) setData(cached.data)
    // A new key (another language, another farm) with nothing cached: drop the
    // old data rather than keep showing it — a slow or failed fetch must never
    // leave the previous language on screen. A reload of the same key keeps it.
    else if (key !== shown.current) setData(null)
    shown.current = key
    setLoading(!cached)
    setError(null)
    fn()
      .then((d) => {
        if (key !== undefined) {
          CACHE.set(key, d)
          WHEN.set(key, save(key, d))
        }
        if (id === seq.current) setData(d)
      })
      .catch((e) => id === seq.current && setError(e))
      .finally(() => id === seq.current && setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    run()
  }, [run])

  return { data, error, loading, savedAt: key !== undefined ? WHEN.get(key) ?? null : null, reload: run, setData }
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

/** True when this device can be carried into the field with its camera pointed
 *  at a plant — a phone or a tablet. A laptop has a camera too, but it faces
 *  the person and the crop is outside, so the live walk is offered there as a
 *  video the farmer already filmed. The primary pointer tells the two apart;
 *  either way both routes stay on the screen, so a wrong guess costs a tap. */
export function useCarryable(): boolean {
  const query = '(pointer: coarse)'
  const [coarse, setCoarse] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const on = () => setCoarse(m.matches)
    on()
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return coarse && typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
}

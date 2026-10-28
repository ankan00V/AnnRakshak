import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError, UNAUTHORIZED } from '../api/client'
import type { Me } from '../api/types'
import { clearCache } from '../lib/hooks'
import { LANG_KEY } from '../lib/i18n'

interface AuthState {
  me: Me | null
  loading: boolean
  /** After a successful login, sign-up or demo sign-in. */
  signIn: (me: Me) => void
  /** After the holder edits their own record, so every screen showing their
   *  name or their districts follows without a reload. */
  update: (me: Me) => void
  logout: () => Promise<void>
  /** True when the holder pressed Log out, as against a session that simply
   *  ran out. The first should land on the front page; the second should go
   *  to the sign-in screen holding the page they were trying to reach. */
  signedOut: boolean
}

const Ctx = createContext<AuthState | null>(null)
const ME_KEY = 'ar.me' // the last known account, so a phone with no signal still opens the app

function remember(me: Me | null) {
  try {
    if (me) localStorage.setItem(ME_KEY, JSON.stringify(me))
    else localStorage.removeItem(ME_KEY)
  } catch {
    /* private mode */
  }
}

function recalled(): Me | null {
  try {
    const raw = localStorage.getItem(ME_KEY)
    return raw ? (JSON.parse(raw) as Me) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [signedOut, setSignedOut] = useState(false)

  useEffect(() => {
    api.me()
      .then((m) => {
        setMe(m)
        remember(m)
      })
      .catch((e: ApiError) => {
        if (e.status === 0) setMe(recalled()) // offline: trust the last session until the server says otherwise
        else remember(null)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const expired = () => {
      setMe(null)
      remember(null)
    }
    window.addEventListener(UNAUTHORIZED, expired)
    return () => window.removeEventListener(UNAUTHORIZED, expired)
  }, [])

  const signIn = useCallback((m: Me) => {
    clearCache()
    remember(m)
    try {
      // The farmer app reads these when it opens: their language, and their field
      // when they have exactly one (several: they pick).
      localStorage.setItem('ar.farm', JSON.stringify(m.farm_ids?.length === 1 ? m.farm_ids[0] : null))
      if (m.role === 'farmer') localStorage.setItem(LANG_KEY, JSON.stringify(m.lang))
    } catch {
      /* private mode */
    }
    setSignedOut(false)
    setMe(m)
  }, [])

  const logout = useCallback(async () => {
    // Forget this browser first, then tell the server. The other way round,
    // the screen keeps the farmer's name, their fields and the account menu
    // until the request comes back — which on a weak signal is long enough to
    // hand the phone over still signed in. Logging out is not a thing to make
    // somebody wait for, and it must not depend on the network answering.
    clearCache()
    remember(null)
    try {
      localStorage.removeItem('ar.farm')
    } catch {
      /* private mode */
    }
    setSignedOut(true)
    setMe(null)
    await api.logout().catch(() => undefined)
  }, [])

  const update = useCallback((m: Me) => {
    setMe(m)
    remember(m)
  }, [])

  return <Ctx.Provider value={{ me, loading, signIn, update, logout, signedOut }}>{children}</Ctx.Provider>
}

export function useAuth() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError, UNAUTHORIZED } from '../api/client'
import type { Me } from '../api/types'
import { clearCache } from '../lib/hooks'

interface AuthState {
  me: Me | null
  loading: boolean
  /** After a successful login, sign-up or demo sign-in. */
  signIn: (me: Me) => void
  logout: () => Promise<void>
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
      if (m.role === 'farmer') localStorage.setItem('ar.lang', JSON.stringify(m.lang))
    } catch {
      /* private mode */
    }
    setMe(m)
  }, [])

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined)
    clearCache()
    remember(null)
    try {
      localStorage.removeItem('ar.farm')
    } catch {
      /* private mode */
    }
    setMe(null)
  }, [])

  return <Ctx.Provider value={{ me, loading, signIn, logout }}>{children}</Ctx.Provider>
}

export function useAuth() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { DiagnoseResult, Lang, LiveEvent } from '../api/types'
import { LANG_KEY, LANGS, loadLocale, makeT, bcp47 } from '../lib/i18n'
import { usePersistent } from '../lib/hooks'

interface FarmerState {
  lang: Lang
  setLang: (l: Lang) => void
  farmId: number | null
  setFarmId: (id: number | null) => void
  result: DiagnoseResult | null
  setResult: (r: DiagnoseResult | null) => void
  t: ReturnType<typeof makeT>
  unread: number
  setUnread: (n: number | ((n: number) => number)) => void
  toast: LiveEvent | null
  setToast: (e: LiveEvent | null) => void
}

const Ctx = createContext<FarmerState | null>(null)

export function FarmerProvider({ children }: { children: ReactNode }) {
  const [saved, setLang] = usePersistent<Lang>(LANG_KEY, 'en')
  // A language saved on this phone may since have been switched off (Odia):
  // fall back rather than leave the app with no language selected.
  const lang: Lang = LANGS.some((l) => l.code === saved) ? saved : 'en'
  const [farmId, setFarmId] = usePersistent<number | null>('ar.farm', null)
  const [result, setResult] = useState<DiagnoseResult | null>(null)
  const [unread, setUnread] = useState(0)
  const [toast, setToast] = useState<LiveEvent | null>(null)
  const [loaded, setLoaded] = useState(0)
  useEffect(() => {
    let on = true
    loadLocale(lang).then((fresh) => on && fresh && setLoaded((n) => n + 1)).catch(() => undefined)
    return () => {
      on = false
    }
  }, [lang])
  // The page says which language it is in, so a screen reader reads Hindi
  // as Hindi rather than spelling it out with English rules, and the browser
  // offers the right keyboard and hyphenation. It said "en" in every language.
  useEffect(() => {
    document.documentElement.lang = bcp47(lang)
    return () => { document.documentElement.lang = 'en' }
  }, [lang])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const t = useMemo(() => makeT(lang), [lang, loaded])
  return (
    <Ctx.Provider value={{ lang, setLang, farmId, setFarmId, result, setResult, t, unread, setUnread, toast, setToast }}>
      {children}
    </Ctx.Provider>
  )
}

export function useFarmer() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useFarmer outside FarmerProvider')
  return ctx
}

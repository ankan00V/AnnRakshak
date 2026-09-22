import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, RotateCcw, Send, Sprout, X } from 'lucide-react'
import { api } from '../api/client'
import type { KrishiAnswer, KrishiChip, Lang } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { useFarmer } from '../farmer/FarmerContext'
import { ListenButton, VoiceButton } from '../ui/kit'

/** Which screen the farmer is on, in the names Krishi's knowledge base uses. */
function screenOf(pathname: string, farmId: number | null): string {
  if (pathname.startsWith('/login')) return 'login'
  if (pathname.startsWith('/signup')) return 'signup'
  const sub = pathname.replace(/^\/app\/?/, '').split('/')[0]
  if (!sub) return farmId == null ? 'onboard' : 'home'
  return sub
}

type Ask = { topic?: string; text?: string } | 'hello'
interface Msg {
  id: number
  from: 'krishi' | 'me'
  text: string
  steps?: string[]
  go?: KrishiAnswer['go']
  lang?: Lang // the language the answer is in (the farmer's own, not always the app's)
  speak?: string // proper-script text for the voice when `text` is romanised
  ask?: Ask // what produced a Krishi message, so it can be asked again in a new language
}

let nextId = 1

/** Krishi, the in-app helper. Answers come from the server's authored help
 *  topics and the farm's own data — never made up.
 *
 *  `anchor` says where the opener sits. In the farmer app it floats in the
 *  bottom-right corner. On sign-up it does not: that screen is a form of
 *  side-by-side choice tiles, and a floating bubble parks itself on top of one
 *  of them (it was covering "Open well"), so the opener goes in the header
 *  where it can never cover an answer the farmer is trying to tap. The panel
 *  it opens is the same either way. */
export default function Krishi({ aboveNav = false, anchor = 'float' }:
  { aboveNav?: boolean; anchor?: 'float' | 'header' }) {
  const { lang, t, farmId } = useFarmer()
  const { me } = useAuth()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const screen = screenOf(pathname, farmId)
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [chips, setChips] = useState<KrishiChip[]>([])
  const [asked, setAsked] = useState<string[]>([]) // topics already answered: not offered again
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const langSeen = useRef(lang)

  const hello = useCallback(async (replace: boolean) => {
    try {
      const h = await api.krishiHello(lang, screen)
      setChips(h.suggestions)
      if (replace) setMsgs([{ id: nextId++, from: 'krishi', text: h.text, ask: 'hello' }])
    } catch {
      if (replace) setMsgs([{ id: nextId++, from: 'krishi', text: t('krishiError') }])
    }
  }, [lang, screen, t])

  // First open: a greeting and this screen's questions. Later screens: fresh questions.
  useEffect(() => {
    if (!open) return
    void hello(msgs.length === 0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, screen])

  // Language changed: the whole conversation again, in the new language.
  useEffect(() => {
    if (langSeen.current === lang) return
    langSeen.current = lang
    if (msgs.length === 0) return
    void (async () => {
      const again = await Promise.all(msgs.map(async (m) => {
        if (m.from !== 'krishi' || !m.ask) return m
        try {
          if (m.ask === 'hello') {
            const h = await api.krishiHello(lang, screen)
            setChips(h.suggestions)
            return { ...m, text: h.text }
          }
          const r = await api.krishiAsk({ ...m.ask, lang, screen, farm_id: farmId })
          return { ...m, text: r.text, steps: r.steps, go: r.go, lang: r.lang, speak: r.speak }
        } catch {
          return m
        }
      }))
      setMsgs(again)
    })()
  }, [lang, msgs, screen, farmId])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [msgs, busy])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const ask = async (q: { topic?: string; text?: string }, shown: string) => {
    if (busy) return
    setMsgs((m) => [...m, { id: nextId++, from: 'me', text: shown }])
    setInput('')
    setBusy(true)
    try {
      const r = await api.krishiAsk({ ...q, lang, screen, farm_id: farmId })
      setMsgs((m) => [...m, { id: nextId++, from: 'krishi', text: r.text, steps: r.steps, go: r.go, lang: r.lang, speak: r.speak, ask: q }])
      setChips(r.suggestions)
      if (r.topic) setAsked((a) => [...a, r.topic!])
    } catch {
      setMsgs((m) => [...m, { id: nextId++, from: 'krishi', text: t('krishiError') }])
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  const submit = () => {
    const q = input.trim()
    if (q) void ask({ text: q }, q)
  }

  if (screen === 'live') return null // the camera call is full screen

  const offset = aboveNav ? 'bottom-[calc(76px+env(safe-area-inset-bottom))] lg:bottom-6 lg:right-6' : 'bottom-5'

  return (
    <>
      {!open && anchor === 'header' && (
        <button
          onClick={() => setOpen(true)}
          aria-label={t('krishiAsk')}
          className="shrink-0 flex items-center gap-1.5 rounded-full bg-cream/15 text-cream ring-1 ring-cream/30 pl-1.5 pr-3 py-1 hover:bg-cream/25 transition"
        >
          <span className="w-7 h-7 rounded-full bg-cream text-leaf-deep flex items-center justify-center">
            <Sprout className="w-4 h-4" />
          </span>
          <span className="text-[13px] font-semibold">{t('krishiName')}</span>
        </button>
      )}

      {!open && anchor === 'float' && (
        <button
          onClick={() => setOpen(true)}
          aria-label={t('krishiAsk')}
          className={`fixed right-4 ${offset} z-40 flex items-center gap-2 rounded-full bg-ochre text-soil-dark pl-1.5 pr-4 py-1.5 shadow-lg shadow-soil-dark/20 ring-2 ring-cream hover:brightness-105 transition animate-fadein`}
        >
          <span className="w-9 h-9 rounded-full bg-leaf-deep text-cream flex items-center justify-center">
            <Sprout className="w-5 h-5" />
          </span>
          <span className="text-left leading-tight">
            <span className="block text-[13px] font-bold">{t('krishiName')}</span>
            <span className="block text-[10px] font-medium opacity-75">{t('krishiAsk')}</span>
          </span>
        </button>
      )}

      {open && (
        <div
          role="dialog"
          aria-label={t('krishiName')}
          className="fixed z-50 inset-x-2 bottom-2 top-16 sm:inset-auto sm:right-4 sm:bottom-4 sm:w-[390px] sm:h-[min(640px,82vh)] flex flex-col rounded-3xl bg-cream text-soil-dark shadow-2xl ring-1 ring-soil-dark/10 overflow-hidden animate-fadein"
        >
          <header className="flex items-center gap-3 bg-leaf-deep text-cream px-4 py-3">
            <span className="w-10 h-10 rounded-full bg-ochre text-soil-dark flex items-center justify-center shrink-0">
              <Sprout className="w-5 h-5" />
            </span>
            <span className="flex-1 min-w-0">
              <span className="block font-semibold leading-tight">{t('krishiName')}</span>
              <span className="block text-[11px] text-cream/70">{t('krishiSub')}</span>
            </span>
            <button onClick={() => { setMsgs([]); setAsked([]); void hello(true) }} aria-label={t('krishiNew')}
              className="w-9 h-9 rounded-full hover:bg-cream/10 flex items-center justify-center">
              <RotateCcw className="w-4 h-4" />
            </button>
            <button onClick={() => setOpen(false)} aria-label={t('krishiClose')}
              className="w-9 h-9 rounded-full hover:bg-cream/10 flex items-center justify-center">
              <X className="w-5 h-5" />
            </button>
          </header>

          <div ref={listRef} className="flex-1 overflow-y-auto px-3 py-4 space-y-3" aria-live="polite">
            {msgs.map((m) => (m.from === 'me' ? (
              <div key={m.id} className="flex justify-end">
                <p className="max-w-[82%] rounded-2xl rounded-br-md bg-leaf-deep text-cream px-3.5 py-2 text-[14px] leading-snug">{m.text}</p>
              </div>
            ) : (
              <div key={m.id} className="flex gap-2 items-start">
                <span className="mt-0.5 w-7 h-7 rounded-full bg-ochre/25 text-leaf-deep flex items-center justify-center shrink-0">
                  <Sprout className="w-4 h-4" />
                </span>
                <div className="max-w-[86%] rounded-2xl rounded-tl-md bg-white border border-soil-dark/10 px-3.5 py-2.5 text-[14px] leading-snug">
                  <p>{m.text}</p>
                  {m.steps && m.steps.length > 0 && (
                    <ol className="mt-2 space-y-1.5">
                      {m.steps.map((s, i) => (
                        <li key={i} className="flex gap-2 text-[13px]">
                          <span className="shrink-0 w-5 h-5 rounded-full bg-leaf/15 text-leaf-deep text-[11px] font-semibold flex items-center justify-center">{i + 1}</span>
                          <span>{s}</span>
                        </li>
                      ))}
                    </ol>
                  )}
                  {((m.go && m.go.length > 0) || me) && (
                    <div className="mt-2.5 flex flex-wrap items-center gap-2">
                      {m.go?.map((g) => (
                        <button key={g.to} onClick={() => { navigate(g.to); if (window.innerWidth < 640) setOpen(false) }}
                          className="inline-flex items-center gap-1 rounded-full bg-leaf-deep text-cream px-3 py-1.5 text-[12px] font-semibold">
                          {g.label}
                          <ArrowRight className="w-3.5 h-3.5" />
                        </button>
                      ))}
                      {me && (
                        <ListenButton text={m.speak ?? [m.text, ...(m.steps ?? [])].join(' ')} lang={m.lang ?? lang}
                          label={t('listen')} stopLabel={t('stop')} compact tone="light" />
                      )}
                    </div>
                  )}
                </div>
              </div>
            )))}
            {busy && (
              <div className="flex gap-2 items-center text-[12px] text-soil-dark/50 pl-9">
                <span className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <span key={i} className="w-1.5 h-1.5 rounded-full bg-leaf-deep/50 animate-bounce" style={{ animationDelay: `${i * 120}ms` }} />
                  ))}
                </span>
                {t('krishiThinking')}
              </div>
            )}
          </div>

          {chips.some((c) => !asked.includes(c.id)) && (
            <div className="px-3 pb-2 flex gap-1.5 overflow-x-auto no-scrollbar">
              {chips.filter((c) => !asked.includes(c.id)).map((c) => (
                <button key={c.id} onClick={() => void ask({ topic: c.id }, c.text)} disabled={busy}
                  className="shrink-0 rounded-full border border-leaf/40 bg-white text-leaf-deep px-3 py-1.5 text-[12px] font-medium hover:bg-leaf/10 disabled:opacity-50">
                  {c.text}
                </button>
              ))}
            </div>
          )}

          <form className="flex items-center gap-2 border-t border-soil-dark/10 bg-white px-3 py-2.5 pb-[max(0.625rem,env(safe-area-inset-bottom))]"
            onSubmit={(e) => { e.preventDefault(); submit() }}>
            {me && (
              <VoiceButton compact lang={lang} label={t('speak')} recordingLabel={t('recording')}
                onText={(txt) => txt && void ask({ text: txt }, txt)} />
            )}
            <input ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} maxLength={300}
              placeholder={t('krishiPlaceholder')} aria-label={t('krishiPlaceholder')} autoFocus
              className="flex-1 min-w-0 min-h-[44px] rounded-xl border border-soil-dark/15 bg-cream/60 px-3 text-[14px] focus:outline-none focus:border-leaf" />
            <button type="submit" disabled={!input.trim() || busy} aria-label={t('krishiSend')}
              className="w-11 h-11 shrink-0 rounded-xl bg-leaf-deep text-cream flex items-center justify-center disabled:opacity-40">
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}
    </>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, Bot, RotateCcw, Send, Sprout, X } from 'lucide-react'
import { api } from '../api/client'
import type { KrishiAnswer, KrishiChip, Lang } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { useFarmer } from '../farmer/FarmerContext'
import { KRISHI_EVENT } from './bus'
import { bcp47 } from '../lib/i18n'
import { ListenButton, VoiceButton } from '../ui/kit'
import { lockScroll, onEscape } from '../lib/sheet'

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

/** A phone: focusing the box there opens the keyboard over half the panel,
 *  hiding the greeting and the answer the farmer is waiting to read. */
const touch = () => typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches

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
  // What to hand focus back to on close. The search box or quick action that
  // opened Krishi from elsewhere; otherwise the opener button, which is
  // unmounted while the panel is up and mounted fresh when it closes.
  const openerRef = useRef<HTMLElement | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
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

  // While the panel is up: Escape closes it; focus moves in (to the box on a
  // computer, to the conversation on a phone so no keyboard pops up); and on
  // a phone, where the panel covers the screen, the page behind stops
  // scrolling. A computer keeps its page scrollable: there the panel is a
  // small window beside it and a "go to" answer navigates with it still open.
  // Closed: focus goes back to whatever opened it.
  const shown = open && screen !== 'live'
  // Modal only where it covers the screen. On a computer the panel is a small
  // window and the page beside it stays usable, so telling a screen reader
  // the page is inert there would be untrue.
  const [phone, setPhone] = useState(() => window.matchMedia?.('(max-width: 639px)').matches ?? false)
  useEffect(() => {
    const mq = window.matchMedia?.('(max-width: 639px)')
    if (!mq) return
    const on = () => setPhone(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  useEffect(() => {
    if (!shown) return
    const unEsc = onEscape(() => setOpen(false))
    ;(touch() ? listRef.current : inputRef.current)?.focus()
    const release = phone ? lockScroll() : () => undefined
    return () => {
      unEsc()
      release()
      const back = openerRef.current?.isConnected ? openerRef.current : buttonRef.current
      openerRef.current = null
      back?.focus()
    }
  }, [shown, phone])

  // The last question and the topic that answered it: sent with the next one,
  // so a follow-up ("no, it's not that") is read in context.
  const last = useRef<{ text: string; topic: string | null } | null>(null)

  /** `typed`: the question came from the text box. Only then does the box get
   *  focus back — after a chip or the voice button it would pop the keyboard
   *  up over the answer that just arrived. */
  const ask = async (q: { topic?: string; text?: string }, shown: string, typed = false) => {
    if (busy) return
    setMsgs((m) => [...m, { id: nextId++, from: 'me', text: shown }])
    setInput('')
    setBusy(true)
    try {
      const r = await api.krishiAsk({ ...q, lang, screen, farm_id: farmId,
        prev_text: last.current?.text ?? null, prev_topic: last.current?.topic ?? null })
      last.current = { text: shown, topic: r.topic }
      setMsgs((m) => [...m, { id: nextId++, from: 'krishi', text: r.text, steps: r.steps, go: r.go, lang: r.lang, speak: r.speak, ask: q }])
      setChips(r.suggestions)
      if (r.topic) setAsked((a) => [...a, r.topic!])
    } catch {
      setMsgs((m) => [...m, { id: nextId++, from: 'krishi', text: t('krishiError') }])
    } finally {
      setBusy(false)
      if (typed) inputRef.current?.focus()
    }
  }

  const submit = () => {
    const q = input.trim()
    if (q) void ask({ text: q }, q, true)
  }

  // Opened from elsewhere on the screen — the search button, a quick action,
  // the sidebar — and asked straight away when a question came with it.
  const askRef = useRef(ask)
  useEffect(() => { askRef.current = ask })
  useEffect(() => {
    const onAsk = (e: Event) => {
      const text = (e as CustomEvent<{ text?: string }>).detail?.text?.trim()
      const from = document.activeElement
      openerRef.current = from instanceof HTMLElement && from !== document.body ? from : null
      setOpen(true)
      if (text) void askRef.current({ text }, text)
    }
    window.addEventListener(KRISHI_EVENT, onAsk)
    return () => window.removeEventListener(KRISHI_EVENT, onAsk)
  }, [])

  if (screen === 'live') return null // the camera call is full screen

  const offset = aboveNav ? 'bottom-[calc(76px+env(safe-area-inset-bottom))] lg:bottom-6 lg:right-6' : 'bottom-5'

  return (
    <>
      {!open && anchor === 'header' && (
        <button
          ref={buttonRef} data-tour="krishi" onClick={() => setOpen(true)}
          aria-label={t('krishiAsk')} aria-haspopup="dialog"
          className="shrink-0 min-h-[44px] flex items-center gap-1.5 rounded-full bg-cream/15 text-cream ring-1 ring-cream/30 pl-1.5 pr-3 py-1 hover:bg-cream/25 transition"
        >
          <span className="w-7 h-7 rounded-full bg-cream text-leaf-deep flex items-center justify-center">
            <Sprout className="w-4 h-4" />
          </span>
          <span className="text-[13px] font-semibold">{t('krishiName')}</span>
        </button>
      )}

      {!open && anchor === 'float' && (
        <button
          ref={buttonRef} data-tour="krishi" onClick={() => setOpen(true)}
          aria-label={t('krishiAsk')} aria-haspopup="dialog"
          className={`fixed right-4 ${offset} z-40 flex items-center gap-2.5 rounded-full bg-[#1d4a2c] text-cream p-1.5 shadow-[0_14px_30px_-12px_rgba(29,74,44,0.7)] ring-2 ring-white/70 hover:brightness-110 transition-[filter]
                      sm:pr-4`}
        >
          <span className="w-11 h-11 rounded-full bg-[#4b8b3b] text-white flex items-center justify-center shrink-0">
            <Bot className="w-6 h-6" aria-hidden />
          </span>
          {/* The name is enough: what it does is in the tour and one tap away. */}
          <span className="hidden sm:block text-[16px] font-semibold">{t('krishiName')}</span>
        </button>
      )}

      {open && (
        <div
          role="dialog" aria-modal={phone || undefined}
          aria-label={t('krishiName')}
          className="fixed z-50 inset-x-2 bottom-[max(0.5rem,env(safe-area-inset-bottom))] top-16 sm:inset-auto sm:right-4 sm:bottom-[max(1rem,env(safe-area-inset-bottom))] sm:w-[390px] sm:h-[min(640px,82vh)] flex flex-col rounded-3xl bg-cream text-soil-dark shadow-2xl ring-1 ring-soil-dark/10 overflow-hidden animate-fadein"
        >
          <header className="flex items-center gap-3 bg-leaf-deep text-cream px-4 py-3">
            <span className="w-10 h-10 rounded-full bg-ochre text-soil-dark flex items-center justify-center shrink-0">
              <Sprout className="w-5 h-5" />
            </span>
            <span className="flex-1 min-w-0">
              <span className="block font-semibold leading-tight">{t('krishiName')}</span>
              <span className="block text-[12px] text-cream/80">{t('krishiSub')}</span>
            </span>
            <button onClick={() => { setMsgs([]); setAsked([]); void hello(true) }} aria-label={t('krishiNew')}
              className="w-11 h-11 rounded-full hover:bg-cream/10 flex items-center justify-center">
              <RotateCcw className="w-5 h-5" />
            </button>
            <button onClick={() => setOpen(false)} aria-label={t('krishiClose')}
              className="-mr-2 w-11 h-11 rounded-full hover:bg-cream/10 flex items-center justify-center">
              <X className="w-5 h-5" />
            </button>
          </header>

          {/* overscroll-contain: reaching the end of the chat must not scroll the
              page behind, or pull it to refresh and wipe the conversation.
              tabIndex: on a phone, opening lands focus here, not in the box. */}
          <div ref={listRef} tabIndex={-1} className="flex-1 overflow-y-auto overscroll-contain px-3 py-4 space-y-3 focus:outline-none" aria-live="polite">
            {msgs.map((m) => (m.from === 'me' ? (
              <div key={m.id} className="flex justify-end">
                <p className="max-w-[82%] rounded-2xl rounded-br-md bg-leaf-deep text-cream px-3.5 py-2 text-[14px] leading-snug">{m.text}</p>
              </div>
            ) : (
              <div key={m.id} className="flex gap-2 items-start">
                <span className="mt-0.5 w-7 h-7 rounded-full bg-ochre/25 text-leaf-deep flex items-center justify-center shrink-0">
                  <Sprout className="w-4 h-4" />
                </span>
                {/* Its own lang: an answer can come back in the farmer's language when the
                    app is in another, and TalkBack must read it in that voice. */}
                <div lang={m.lang ? bcp47(m.lang) : undefined} className="max-w-[86%] rounded-2xl rounded-tl-md bg-white border border-soil-dark/10 px-3.5 py-2.5 text-[14px] leading-snug">
                  <p>{m.text}</p>
                  {m.steps && m.steps.length > 0 && (
                    <ol className="mt-2 space-y-1.5">
                      {m.steps.map((s, i) => (
                        <li key={i} className="flex gap-2 text-[13px]">
                          <span className="shrink-0 w-5 h-5 rounded-full bg-leaf/15 text-leaf-deep text-[12px] font-semibold flex items-center justify-center">{i + 1}</span>
                          <span>{s}</span>
                        </li>
                      ))}
                    </ol>
                  )}
                  {((m.go && m.go.length > 0) || me) && (
                    <div className="mt-2.5 flex flex-wrap items-center gap-2">
                      {m.go?.map((g) => (
                        <button key={g.to} onClick={() => { navigate(g.to); if (window.innerWidth < 640) setOpen(false) }}
                          className="inline-flex min-h-[44px] items-center gap-1.5 rounded-full bg-leaf-deep text-cream px-4 text-[14px] font-semibold">
                          {g.label}
                          <ArrowRight className="w-4 h-4" />
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
              <div className="flex gap-2 items-center text-[13px] text-soil-dark/70 pl-9">
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
            <div className="px-3 pb-2 flex gap-2 overflow-x-auto overscroll-x-contain no-scrollbar">
              {chips.filter((c) => !asked.includes(c.id)).map((c) => (
                <button key={c.id} onClick={() => void ask({ topic: c.id }, c.text)} disabled={busy}
                  className="shrink-0 min-h-[44px] rounded-full border border-leaf/40 bg-white text-leaf-deep px-4 text-[14px] font-medium hover:bg-leaf/10 disabled:opacity-50">
                  {c.text}
                </button>
              ))}
            </div>
          )}

          <form className="flex items-center gap-2 border-t border-soil-dark/10 bg-white px-3 py-2.5"
            onSubmit={(e) => { e.preventDefault(); submit() }}>
            {me && (
              <VoiceButton compact lang={lang} label={t('speak')} recordingLabel={t('recording')}
                onText={(txt) => txt && void ask({ text: txt }, txt)} />
            )}
            <input ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} maxLength={300}
              placeholder={t('krishiPlaceholder')} aria-label={t('krishiPlaceholder')}
              className="flex-1 min-w-0 min-h-[44px] rounded-xl border border-soil-dark/15 bg-cream/60 px-3 text-[16px] focus:outline-none focus:border-leaf" />
            <button type="submit" disabled={!input.trim() || busy} aria-label={t('krishiSend')}
              className="w-11 h-11 shrink-0 rounded-xl bg-leaf-deep text-cream flex items-center justify-center disabled:opacity-40">
              <Send className="w-5 h-5" />
            </button>
          </form>
        </div>
      )}
    </>
  )
}

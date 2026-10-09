import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Loader2, MessageSquare, Send, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { DarpanAnswer } from '../api/types'

type Turn = { asked: string; answer?: DarpanAnswer; error?: string }

/** Darpan — दर्पण, a mirror: the district as it stands, for officers only.
 *
 *  Krishi answers a farmer about their own field and is untouched by this.
 *  Darpan answers an officer about their district, and every line it says is
 *  built from a number the server has just computed, with the link to the
 *  screen those numbers came from. */
export default function Darpan() {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [hello, setHello] = useState<{ greeting: string; suggestions: { label: string; text: string }[] } | null>(null)
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open && !hello) api.darpanHello().then(setHello).catch(() => setHello(null))
  }, [open, hello])

  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns, busy])

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q || busy) return
    setText('')
    setBusy(true)
    setTurns((t) => [...t, { asked: q }])
    try {
      const answer = await api.darpanAsk(q)
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, answer } : turn)))
    } catch (e) {
      const message = (e as Error).message
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: message } : turn)))
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full bg-leaf-deep text-cream shadow-lg shadow-leaf-deep/30 pl-4 pr-5 py-3 text-sm font-medium hover:brightness-110">
        <MessageSquare className="w-4 h-4 text-ochre" />
        Darpan
      </button>
    )
  }

  return (
    <aside className="fixed bottom-0 right-0 z-40 w-full sm:bottom-5 sm:right-5 sm:w-[26rem] max-h-[80vh] flex flex-col rounded-t-3xl sm:rounded-3xl bg-white border border-soil-dark/15 shadow-2xl shadow-soil-dark/20 animate-fadein">
      <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-soil-dark/10 bg-leaf-deep text-cream rounded-t-3xl">
        <span>
          <span className="block text-sm font-semibold">Darpan</span>
          <span className="block text-[11px] text-cream/70">दर्पण · your district, as it stands</span>
        </span>
        <button onClick={() => setOpen(false)} aria-label="Close Darpan" className="text-cream/70 hover:text-cream">
          <X className="w-4 h-4" />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {hello && turns.length === 0 && (
          <>
            <p className="text-sm text-soil-dark/80">{hello.greeting}</p>
            <ul className="space-y-1.5">
              {hello.suggestions.map((s) => (
                <li key={s.text}>
                  <button onClick={() => ask(s.text)}
                    className="w-full text-left rounded-xl border border-soil-dark/15 px-3 py-2 text-sm hover:bg-cream">
                    {s.label}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}

        {turns.map((turn, i) => (
          <div key={i} className="space-y-2">
            <p className="ml-auto w-fit max-w-[85%] rounded-2xl bg-leaf-deep text-cream px-3 py-2 text-sm">
              {turn.asked}
            </p>
            {turn.error && <p className="text-sm text-ember">{turn.error}</p>}
            {turn.answer && (
              <div className="w-fit max-w-[92%] rounded-2xl bg-cream px-3 py-2.5">
                {turn.answer.lines.map((line, j) => (
                  <p key={j} className={`text-sm text-soil-dark/85 ${j ? 'mt-1.5' : ''}`}>{line}</p>
                ))}
                {turn.answer.go.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {turn.answer.go.map((g) => (
                      <Link key={g.to} to={g.to} onClick={() => setOpen(false)}
                        className="inline-flex items-center gap-1 rounded-full bg-white border border-soil-dark/15 px-2.5 py-1 text-xs font-medium hover:border-leaf/50">
                        {g.label} <ArrowRight className="w-3 h-3" />
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {busy && (
          <p className="flex items-center gap-2 text-sm text-soil-dark/60">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> reading the district…
          </p>
        )}
        <div ref={end} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); ask(text) }}
        className="flex items-center gap-2 border-t border-soil-dark/10 p-3">
        <input value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Ask about your district…"
          className="flex-1 min-h-[40px] rounded-full border border-soil-dark/15 bg-cream/50 px-4 text-sm" />
        <button type="submit" disabled={busy || !text.trim()} aria-label="Ask Darpan"
          className="w-10 h-10 shrink-0 rounded-full bg-leaf-deep text-cream flex items-center justify-center disabled:opacity-50">
          <Send className="w-4 h-4" />
        </button>
      </form>
    </aside>
  )
}

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { Check, Undo2, X } from 'lucide-react'

type Toast = { id: number; text: string; undo?: () => Promise<void> | void; tone: 'ok' | 'bad' }

const Ctx = createContext<{
  say: (text: string, undo?: () => Promise<void> | void) => void
  complain: (text: string) => void
}>({ say: () => {}, complain: () => {} })

export const useToast = () => useContext(Ctx)

/** Something happened; say so, and let it be taken back.
 *
 *  An officer moving somebody else's cases or setting one aside should not have
 *  to hunt for grey text to learn whether it worked — and a mis-click on a
 *  queue of forty should cost one press, not an apology. */
export function Toasts({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const next = useRef(1)

  const drop = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), [])

  const push = useCallback((text: string, tone: 'ok' | 'bad', undo?: () => Promise<void> | void) => {
    const id = next.current++
    setToasts((t) => [...t, { id, text, undo, tone }])
    // Long enough to read and to change your mind; short enough not to nag.
    setTimeout(() => drop(id), undo ? 9000 : 5000)
  }, [drop])

  const value = useMemo(() => ({
    say: (text: string, undo?: () => Promise<void> | void) => push(text, 'ok', undo),
    complain: (text: string) => push(text, 'bad'),
  }), [push])

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-50 flex flex-col items-center gap-2 px-4 w-full max-w-md"
        role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id}
            className={`animate-fadein w-full flex items-center gap-3 rounded-2xl px-4 py-3 text-sm shadow-lg ${
              t.tone === 'bad' ? 'bg-ember text-cream shadow-ember/30' : 'bg-soil-dark text-cream shadow-soil-dark/30'}`}>
            {t.tone === 'ok' && <Check className="w-4 h-4 shrink-0 text-ochre" />}
            <span className="flex-1">{t.text}</span>
            {t.undo && (
              <button onClick={async () => { drop(t.id); await t.undo?.() }}
                className="flex items-center gap-1 rounded-full bg-cream/15 px-2.5 py-1 text-xs font-medium hover:bg-cream/25">
                <Undo2 className="w-3 h-3" /> Undo
              </button>
            )}
            <button onClick={() => drop(t.id)} aria-label="Dismiss" className="text-cream/60 hover:text-cream">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}

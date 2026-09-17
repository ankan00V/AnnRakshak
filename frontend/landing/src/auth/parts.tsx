import { useEffect, useRef, useState, type InputHTMLAttributes, type ReactNode } from 'react'
import { Check, Loader2, MailCheck } from 'lucide-react'
import type { OtpSent } from '../api/types'
import { ErrorBox } from '../ui/kit'
import { useFarmer } from '../farmer/FarmerContext'

const input =
  'w-full min-h-[48px] rounded-xl border px-3 bg-white text-[15px] focus:outline-none focus:ring-2 focus:ring-leaf/30'

/** A labelled input. `group` for a set of chips: a <label> would pass a tap
 *  on its title to the first chip inside it. */
export function Field({ label, hint, error, optional, group = false, children }: {
  label: string; hint?: string; error?: string | false; optional?: boolean; group?: boolean; children: ReactNode
}) {
  const { t } = useFarmer()
  const Tag = group ? 'div' : 'label'
  return (
    <Tag className="block" {...(group ? { role: 'group', 'aria-label': label } : {})}>
      <span className="block text-[13px] font-medium text-soil-dark/80 mb-1">
        {label}
        {optional && <span className="font-normal text-soil-dark/45"> · {t('authOptional')}</span>}
      </span>
      {children}
      {error ? (
        <span className="block mt-1 text-[12px] text-ember">{error}</span>
      ) : hint ? (
        <span className="block mt-1 text-[12px] text-soil-dark/50 leading-snug">{hint}</span>
      ) : null}
    </Tag>
  )
}

export function Input({ invalid, className = '', ...rest }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return <input {...rest} className={`${input} ${invalid ? 'border-ember/60' : 'border-soil-dark/20 focus:border-leaf'} ${className}`} />
}

export function Select({ value, onChange, children }: { value: string; onChange: (v: string) => void; children: ReactNode }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className={`${input} border-soil-dark/20 focus:border-leaf`}>
      {children}
    </select>
  )
}

/** Tap-to-choose options: one (`multi` off) or several. */
export function Chips<T extends string>({ options, value, onChange, multi = false, columns }: {
  options: { id: T; label: ReactNode }[]
  value: T[]
  onChange: (v: T[]) => void
  multi?: boolean
  columns?: 2 | 3
}) {
  const toggle = (id: T) => {
    if (!multi) return onChange([id])
    onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])
  }
  return (
    <div className={columns ? `grid gap-2 ${columns === 2 ? 'grid-cols-2' : 'grid-cols-2 sm:grid-cols-3'}` : 'flex flex-wrap gap-2'}>
      {options.map((o) => {
        const on = value.includes(o.id)
        return (
          <button type="button" key={o.id} onClick={() => toggle(o.id)} aria-pressed={on}
            className={`min-h-[42px] rounded-xl border px-3 py-2 text-left text-[13px] font-medium flex items-center gap-2 transition-colors ${
              on ? 'border-leaf-deep bg-leaf/10 text-leaf-deep' : 'border-soil-dark/15 bg-white hover:border-leaf/40'}`}>
            <span className="flex-1 min-w-0">{o.label}</span>
            {on && <Check className="w-4 h-4 shrink-0" />}
          </button>
        )
      })}
    </div>
  )
}

export function Steps({ step, titles }: { step: number; titles: string[] }) {
  const { t } = useFarmer()
  return (
    <div className="mb-5">
      <p className="text-[11px] uppercase tracking-wider text-soil-dark/50 font-semibold">
        {t('authStep').replace('{n}', String(step + 1)).replace('{total}', String(titles.length))}
      </p>
      <h2 className="mt-1 font-instrument-serif text-[28px] leading-tight">{titles[step]}</h2>
      <div className="mt-3 grid gap-1.5" style={{ gridTemplateColumns: `repeat(${titles.length}, 1fr)` }}>
        {titles.map((x, i) => (
          <span key={x + i} className={`h-1.5 rounded-full ${i <= step ? 'bg-leaf-deep' : 'bg-soil-dark/10'}`} />
        ))}
      </div>
    </div>
  )
}

export function Primary({ children, busy, disabled, onClick, type = 'button' }: {
  children: ReactNode; busy?: boolean; disabled?: boolean; onClick?: () => void; type?: 'button' | 'submit'
}) {
  return (
    <button type={type} onClick={onClick} disabled={disabled || busy}
      className="w-full min-h-[52px] rounded-full bg-leaf-deep text-cream text-[15px] font-semibold flex items-center justify-center gap-2 disabled:opacity-50 hover:brightness-110 transition">
      {busy && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  )
}

export function Secondary({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className="min-h-[52px] px-5 rounded-full border border-soil-dark/15 text-[15px] font-medium text-soil-dark/70 hover:bg-white">
      {children}
    </button>
  )
}

/** Six boxes over one real input, so paste, SMS/email autofill and the
 *  numeric keypad all work. */
export function CodeBoxes({ value, onChange, digits = 6, onComplete }: {
  value: string; onChange: (v: string) => void; digits?: number; onComplete?: (v: string) => void
}) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => ref.current?.focus(), [])
  return (
    <div className="relative" onClick={() => ref.current?.focus()}>
      <input ref={ref} value={value} inputMode="numeric" autoComplete="one-time-code" maxLength={digits}
        aria-label="One-time code"
        onChange={(e) => {
          const v = e.target.value.replace(/\D/g, '').slice(0, digits)
          onChange(v)
          if (v.length === digits) onComplete?.(v)
        }}
        className="absolute inset-0 w-full h-full opacity-0 cursor-text" />
      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${digits}, 1fr)` }} aria-hidden>
        {Array.from({ length: digits }, (_, i) => (
          <span key={i}
            className={`h-14 rounded-xl border-2 bg-white flex items-center justify-center text-2xl font-semibold tabular-nums ${
              i === value.length ? 'border-leaf-deep' : value[i] ? 'border-leaf/40' : 'border-soil-dark/15'}`}>
            {value[i] ?? ''}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Send a code, then take it. `request` asks the server to email a code;
 *  `verify` finishes the login or sign-up with it. */
export function CodePanel({ sendLabel, request, verify, submitLabel }: {
  sendLabel: string
  request: () => Promise<OtpSent>
  verify: (challengeId: string, code: string) => Promise<void>
  submitLabel: string
}) {
  const { t } = useFarmer()
  const [sent, setSent] = useState<OtpSent | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [wait, setWait] = useState(0)

  useEffect(() => {
    if (wait <= 0) return
    const id = window.setTimeout(() => setWait((w) => w - 1), 1000)
    return () => window.clearTimeout(id)
  }, [wait])

  const send = async () => {
    setBusy(true)
    setError(null)
    try {
      const s = await request()
      setSent(s)
      setCode('')
      setWait(s.resend_in)
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  const submit = async (c = code) => {
    if (!sent || c.length !== sent.digits) return
    setBusy(true)
    setError(null)
    try {
      await verify(sent.challenge_id, c)
    } catch (e) {
      setError(e as Error)
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  if (!sent) {
    return (
      <div className="space-y-3">
        {error && <ErrorBox error={error} />}
        <Primary busy={busy} onClick={send}>{sendLabel}</Primary>
        <p className="text-[12px] text-soil-dark/50 text-center">{t('authEmailNote')}</p>
      </div>
    )
  }
  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-start rounded-2xl bg-leaf/10 text-leaf-deep p-3">
        <MailCheck className="w-5 h-5 shrink-0 mt-0.5" />
        <div className="text-[13px] leading-snug">
          <p className="font-medium">{t('authCodeSent').replace('{to}', sent.sent_to)}</p>
          <p className="text-leaf-deep/70 mt-0.5">{t('authCodeCheckSpam')}</p>
        </div>
      </div>
      <CodeBoxes value={code} onChange={setCode} digits={sent.digits} onComplete={(c) => void submit(c)} />
      {error && <ErrorBox error={error} />}
      <Primary busy={busy} disabled={code.length !== sent.digits} onClick={() => void submit()}>{submitLabel}</Primary>
      <p className="text-center text-[13px]">
        {wait > 0 ? (
          <span className="text-soil-dark/50">{t('authResendIn').replace('{s}', String(wait))}</span>
        ) : (
          <button type="button" onClick={send} className="text-leaf-deep font-medium underline underline-offset-2">
            {t('authResend')}
          </button>
        )}
      </p>
    </div>
  )
}

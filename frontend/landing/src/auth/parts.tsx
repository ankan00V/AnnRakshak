import { cloneElement, isValidElement, useEffect, useId, useRef, useState, type InputHTMLAttributes, type ReactNode } from 'react'
import { Check, Loader2, MailCheck, MessageSquare } from 'lucide-react'
import type { OtpSent } from '../api/types'
import { ErrorBox, ListenButton } from '../ui/kit'
import { useFarmer } from '../farmer/FarmerContext'
import type { TKey } from '../lib/i18n'
import { wentBySms } from './helpers'
import { usePublishProgress } from './progress'

/** On a phone the page is cream and a white box is the thing you type in. On a
 *  laptop the form sits on a white sheet, so the same white box would vanish
 *  into it — there the boxes take the page's own cream, which is how every
 *  other card in the app holds a field. */
const input =
  'w-full min-h-[48px] rounded-xl border px-3 bg-white lg:bg-cream/50 text-[16px] ' +
  'focus:outline-none focus:ring-2 focus:ring-leaf/30 lg:focus:bg-white'

/** The sheet the form is written on, from `lg` up. */
export function FormCard({ children }: { children: ReactNode }) {
  return (
    <section className="lg:rounded-3xl lg:bg-white lg:border lg:border-soil-dark/10 lg:px-9 lg:py-8
                        lg:shadow-[0_20px_46px_-30px_rgba(43,29,18,0.45)]">
      {children}
    </section>
  )
}

/** The row the form ends on: a rule, then where you can go from here. */
export function Actions({ children }: { children: ReactNode }) {
  return <div className="mt-6 lg:mt-8 lg:pt-6 lg:border-t lg:border-soil-dark/10 flex gap-3">{children}</div>
}

/** What a Field hands the box inside it: its name, its state, its note. */
export type FieldAria = { 'aria-labelledby': string; 'aria-invalid'?: boolean; 'aria-describedby'?: string }

/** A labelled input. `group` for a set of chips: a <label> would pass a tap
 *  on its title to the first chip inside it. A box wrapped in other markup
 *  (the phone number's +91) takes `children` as a function of the aria props. */
export function Field({ label, hint, error, optional, group = false, say, children }: {
  label: string; hint?: string; error?: string | false; optional?: boolean; group?: boolean
  /** An i18n key read aloud by the speaker button beside the label. Typed, so
   *  a key that does not exist is caught here and not as a silent missing clip. */
  say?: TKey
  children: ReactNode | ((aria: FieldAria) => ReactNode)
}) {
  const { t, lang } = useFarmer()
  const Tag = group ? 'div' : 'label'
  const noteId = useId()
  const labelId = useId()
  // The box is named by the label's words alone: a <label> would also lend it
  // the "Listen" button and the error under it. It says it is wrong and points
  // at the sentence saying why, so a screen reader that lands on it hears both
  // (no role=alert: a failed Next would shout every field at once).
  const aria: FieldAria = {
    'aria-labelledby': labelId,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': error || hint ? noteId : undefined,
  }
  const field = typeof children === 'function'
    ? children(aria)
    : !group && isValidElement<Record<string, unknown>>(children)
      && (children.type === Input || children.type === Select || children.type === 'input')
      ? cloneElement(children, aria)
      : children
  return (
    // data-invalid lets a form find the first wrong field and move focus there.
    <Tag className="block" data-invalid={error ? '' : undefined}
      {...(group ? { role: 'group', 'aria-labelledby': labelId, 'aria-describedby': aria['aria-describedby'] } : {})}>
      {/* The speaker button is 36 px tall and a bare label is half that. On a
          phone each field stands alone and it does not matter; in a two-column
          row on a laptop it would leave the boxes beside each other out of
          line, so from `lg` up every label row is the taller of the two. */}
      <span className="flex items-center gap-2 text-[13px] font-medium text-soil-dark/80 mb-1 lg:min-h-[36px]">
        <span id={labelId} className="flex-1">
          {label}
          {optional && <span className="font-normal text-soil-dark/65"> · {t('authOptional')}</span>}
        </span>
        {/* The span swallows the mousedown: this sits inside a <label>, and a
            tap that reaches it would focus the field and raise the keyboard
            over the very help the farmer just asked to hear. */}
        {say && (
          <span onMouseDown={(e) => e.preventDefault()}>
            <ListenButton src={`/help/${lang}/${say}.mp3`} text={t(say)} lang={lang}
              label={t('listen')} stopLabel={t('stop')} compact />
          </span>
        )}
      </span>
      {field}
      {error ? (
        <span id={noteId} className="block mt-1 text-[13px] text-ember">{error}</span>
      ) : hint ? (
        <span id={noteId} className="block mt-1 text-[13px] text-soil-dark/70 leading-snug">{hint}</span>
      ) : null}
    </Tag>
  )
}

export function Input({ invalid, className = '', ...rest }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return <input {...rest} className={`${input} ${invalid ? 'border-ember/60' : 'border-soil-dark/20 focus:border-leaf'} ${className}`} />
}

export function Select({ value, onChange, children, ...aria }: {
  value: string; onChange: (v: string) => void; children: ReactNode
  'aria-invalid'?: boolean; 'aria-describedby'?: string; 'aria-labelledby'?: string
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} {...aria}
      className={`${input} border-soil-dark/20 focus:border-leaf`}>
      {children}
    </select>
  )
}

/** Tap-to-choose options: one (`multi` off) or several. `wide` is how many fit
 *  across once there is a laptop's room — seven irrigation sources stacked two
 *  at a time is a column of chips nobody needs to scroll past. */
export function Chips<T extends string>({ options, value, onChange, multi = false, columns, wide }: {
  options: { id: T; label: ReactNode }[]
  value: T[]
  onChange: (v: T[]) => void
  multi?: boolean
  columns?: 2 | 3
  wide?: 2 | 3 | 4
}) {
  const atLg = wide === 4 ? 'lg:grid-cols-4' : wide === 3 ? 'lg:grid-cols-3' : wide === 2 ? 'lg:grid-cols-2' : ''
  const toggle = (id: T) => {
    if (!multi) return onChange([id])
    onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])
  }
  return (
    <div className={columns
      ? `grid gap-2 ${columns === 2 ? 'grid-cols-2' : 'grid-cols-2 sm:grid-cols-3'} ${atLg}`
      : 'flex flex-wrap gap-2'}>
      {options.map((o) => {
        const on = value.includes(o.id)
        return (
          <button type="button" key={o.id} onClick={() => toggle(o.id)} aria-pressed={on}
            className={`min-h-[44px] lg:min-h-[46px] rounded-xl border px-3 py-2 text-left text-[14px] font-medium flex items-center gap-2 transition-colors active:bg-leaf/5 ${
              on ? 'border-leaf-deep bg-leaf/10 text-leaf-deep'
                : 'border-soil-dark/15 bg-white lg:bg-cream/50 hover:border-leaf/40 lg:hover:bg-cream'}`}>
            <span className="flex-1 min-w-0">{o.label}</span>
            {on && <Check className="w-4 h-4 shrink-0" />}
          </button>
        )
      })}
    </div>
  )
}

/** The step counter on a phone. On a laptop the side panel draws the walk in
 *  full, so only the heading stays here and the bar would say it twice. */
export function Steps({ step, titles }: { step: number; titles: string[] }) {
  const { t } = useFarmer()
  usePublishProgress(step, titles)
  return (
    <div className="mb-5 lg:mb-7 lg:pb-5 lg:border-b lg:border-soil-dark/10">
      <p className="text-[12px] uppercase tracking-wider text-soil-dark/70 font-semibold lg:hidden">
        {t('authStep').replace('{n}', String(step + 1)).replace('{total}', String(titles.length))}
      </p>
      <h2 className="mt-1 lg:mt-0 font-instrument-serif text-[28px] lg:text-[30px] leading-tight">{titles[step]}</h2>
      <div className="mt-3 grid gap-1.5 lg:hidden" style={{ gridTemplateColumns: `repeat(${titles.length}, 1fr)` }}>
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
  // Capped on a laptop: six boxes stretched across the full column read as six
  // letterboxes rather than six digits.
  return (
    <div className="relative lg:max-w-md" onClick={() => ref.current?.focus()}>
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

/** Send a code, then take it. `request` asks the server to send a code — by
 *  SMS to a farmer's mobile number where the server can, else by email — and
 *  `verify` finishes the login or sign-up with it. Once sent, the panel says
 *  where the code really went, because a farmer's SMS that failed falls back
 *  to their email, and "check your messages" would send them to the wrong
 *  place. */
export function CodePanel({ sendLabel, request, verify, submitLabel, blocked, note }: {
  sendLabel: string
  request: () => Promise<OtpSent>
  verify: (challengeId: string, code: string) => Promise<void>
  submitLabel: string
  /** Something on this screen is still outstanding — the officer's undertaking.
   *  Sending a code first would spend the code and then refuse the sign-up. */
  blocked?: boolean
  /** The line under the send button: where the code is going to go. */
  note?: string
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
        {error && <ErrorBox offlineLabel={t('offline')} error={error} />}
        <Primary busy={busy} disabled={blocked} onClick={send}>{sendLabel}</Primary>
        <p className="text-[13px] text-soil-dark/70 text-center">{note ?? t('authEmailNote')}</p>
      </div>
    )
  }
  const sms = wentBySms(sent)
  const Icon = sms ? MessageSquare : MailCheck
  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-start rounded-2xl bg-leaf/10 text-leaf-deep p-3" role="status">
        <Icon className="w-5 h-5 shrink-0 mt-0.5" aria-hidden />
        <div className="text-[13px] leading-snug">
          <p className="font-medium">{t(sms ? 'authCodeSentSms' : 'authCodeSent').replace('{to}', sent.sent_to)}</p>
          <p className="text-leaf-deep/80 mt-0.5">{t(sms ? 'authCodeSmsWait' : 'authCodeCheckSpam')}</p>
        </div>
      </div>
      <CodeBoxes value={code} onChange={setCode} digits={sent.digits} onComplete={(c) => void submit(c)} />
      {error && <ErrorBox offlineLabel={t('offline')} error={error} />}
      <Primary busy={busy} disabled={code.length !== sent.digits} onClick={() => void submit()}>{submitLabel}</Primary>
      <p className="text-center text-[13px]">
        {/* Not a live region: one that changes every second reads the count
            aloud every second. The sr-only one below speaks once, at zero. */}
        {wait > 0 ? (
          <span className="inline-flex min-h-[44px] items-center text-soil-dark/70">{t('authResendIn').replace('{s}', String(wait))}</span>
        ) : (
          // A full thumb's height: a code that never came is the moment this is needed.
          <button type="button" onClick={send} className="inline-flex min-h-[44px] items-center px-2 text-[14px] text-leaf-deep font-medium underline underline-offset-2">
            {t('authResend')}
          </button>
        )}
        <span className="sr-only" aria-live="polite">{wait > 0 ? '' : t('authResend')}</span>
      </p>
    </div>
  )
}


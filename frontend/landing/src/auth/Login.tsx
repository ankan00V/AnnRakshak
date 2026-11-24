import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Sprout, UserCheck } from 'lucide-react'
import { api, ApiError } from '../api/client'
import type { Role } from '../api/types'
import { useFarmer } from '../farmer/FarmerContext'
import { useAsync } from '../lib/hooks'
import { useAuth } from './AuthContext'
import { emailOk, phoneOk, smsCodes } from './helpers'
import { CodePanel, Field, FormCard, Input, Primary } from './parts'
import Turnstile from './Turnstile'

export function RoleSwitch({ role, onChange }: { role: Role; onChange: (r: Role) => void }) {
  const { t } = useFarmer()
  return (
    <div role="tablist" className="grid grid-cols-2 rounded-full bg-[#f6f1e6] p-1">
      {(['farmer', 'expert'] as const).map((r) => {
        const Icon = r === 'farmer' ? Sprout : UserCheck
        return (
          <button key={r} role="tab" aria-selected={role === r} onClick={() => onChange(r)}
            className={`min-h-[44px] rounded-full text-[14px] font-semibold flex items-center justify-center gap-1.5 transition-colors ${
              role === r ? 'bg-[#1d4a2c] text-cream shadow-sm' : 'text-soil-dark/75 hover:text-soil-dark active:bg-soil-dark/5'}`}>
            <Icon className="w-4 h-4" aria-hidden />
            {t(r === 'farmer' ? 'authFarmer' : 'authExpert')}
          </button>
        )
      })}
    </div>
  )
}

export default function Login() {
  const { lang, t } = useFarmer()
  const { signIn } = useAuth()
  const [params, setParams] = useSearchParams()
  const role: Role = params.get('role') === 'expert' ? 'expert' : 'farmer'
  const [identifier, setIdentifier] = useState('')
  const [ready, setReady] = useState(false)
  const [human, setHuman] = useState<string | null>(null)
  const [demoBusy, setDemoBusy] = useState<Role | null>(null)
  const [demoError, setDemoError] = useState<Error | null>(null)
  const options = useAsync(() => api.authOptions(lang), [lang])

  const byEmail = identifier.includes('@')
  const valid = byEmail ? emailOk(identifier) : phoneOk(identifier)
  // Where the code is going, said before it is sent. A farmer's mobile number
  // gets it by SMS when the server can send one; an email address, an officer,
  // and everyone while SMS is off get it by email.
  const smsOn = smsCodes(options.data)
  const note = role === 'farmer' && !byEmail && smsOn ? t('authSmsNote')
    : smsOn ? t('authEmailCodeNote') : undefined
  const setRole = (r: Role) => {
    params.set('role', r)
    setParams(params, { replace: true })
    setReady(false)
  }

  const demo = async (r: Role) => {
    setDemoBusy(r)
    setDemoError(null)
    try {
      signIn(await api.demoLogin(r))
    } catch (e) {
      setDemoError(e as Error)
    } finally {
      setDemoBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <FormCard>
        <RoleSwitch role={role} onChange={setRole} />

        {!ready ? (
          <form className="mt-5 space-y-4" onSubmit={(e) => { e.preventDefault(); if (valid) setReady(true) }}>
            <Field label={t('authIdentifier')}>
              <Input value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username"
                inputMode={/^[\d\s+-]*$/.test(identifier) && identifier ? 'tel' : 'email'}
                placeholder={role === 'expert' ? 'name@kvk.org.in · 98XXXXXXXX' : '98XXXXXXXX'} />
            </Field>
            <Primary type="submit" disabled={!valid}>{t('authNext')}</Primary>
          </form>
        ) : (
          <div className="mt-5 space-y-3">
            <div className="flex items-center justify-between gap-2 rounded-xl bg-[#fbf8f1] border border-soil-dark/10 pl-3 pr-1 py-0.5 text-[15px]">
              <span className="min-w-0 truncate">{identifier}</span>
              {/* A thumb-sized target: a mistyped number is fixed here. */}
              <button type="button" className="inline-flex min-h-[44px] shrink-0 items-center px-3 text-leaf-deep font-medium" onClick={() => setReady(false)}>{t('authChange')}</button>
            </div>
            <Turnstile lang={lang} onToken={setHuman} />
            <CodePanel
              sendLabel={t('authSendCode')}
              request={() => api.requestOtp({ role, purpose: 'login', identifier: identifier.trim(), lang,
                                              turnstile_token: human })}
              verify={async (id, code) => signIn(await api.login(id, code, role, lang))}
              submitLabel={t('authVerify')}
              note={note}
            />
          </div>
        )}

        <p className="mt-6 border-t border-soil-dark/10 pt-5 text-center text-sm text-soil-dark/75">
          {t('authNoAccount')}{' '}
          <Link to={`/signup/${role}`} className="inline-flex min-h-[44px] items-center text-leaf-deep font-semibold underline underline-offset-2">
            {t('authCreateAccount')}
          </Link>
        </p>
      </FormCard>

      {options.data?.demo_login && (
        <div className="rounded-[22px] bg-[#fbf3df] p-4 ring-1 ring-[#e8b450]/40 space-y-3 lg:p-5">
          <p className="text-[13px] font-semibold text-[#8a5a17]">{t('authTryDemo')}</p>
          <div className="grid grid-cols-2 gap-2">
            {(['farmer', 'expert'] as const).map((r) => (
              <button key={r} onClick={() => void demo(r)} disabled={demoBusy !== null}
                className="min-h-[44px] rounded-full bg-white text-[13px] font-semibold text-[#1f3a26] ring-1 ring-[#e8b450]/50 transition hover:bg-[#fff8e8] disabled:opacity-60">
                {demoBusy === r ? '…' : t(r === 'farmer' ? 'authDemoFarmer' : 'authDemoExpert')}
              </button>
            ))}
          </div>
          {demoError && <p role="alert" className="text-[13px] text-ember">{(demoError as ApiError).message}</p>}
        </div>
      )}
    </div>
  )
}

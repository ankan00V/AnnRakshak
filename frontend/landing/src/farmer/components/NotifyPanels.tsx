import { useEffect, useState } from 'react'
import { BellRing, Loader2, Mail, Smartphone } from 'lucide-react'
import { api } from '../../api/client'
import type { Contact, EmailPref } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { disablePush, enablePush, pushState, type PushState } from '../../lib/push'
import { Card, SectionTitle } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'
import { Advisories } from '../screens/Weather'

/** The weather notices issued to this farm, newest first; opening marks them read. */
export function NoticeInbox() {
  const { farmId, lang, t, setUnread } = useFarmer()
  const n = useAsync(() => api.notices(farmId!, lang), [farmId, lang], ['notices', farmId!, lang].join(':'))
  useEffect(() => {
    if (!n.data || n.data.unread === 0) return
    api.markRead(farmId!).then(() => setUnread(0)).catch(() => undefined)
  }, [n.data, farmId, setUnread])
  const items = n.data?.items ?? []
  const active = items.filter((x) => x.active)
  const past = items.filter((x) => !x.active).slice(0, 5)
  return (
    <section className="space-y-2">
      <SectionTitle>{t('noticesTitle')}</SectionTitle>
      {n.loading && !n.data ? null : active.length === 0 ? (
        <Card className="p-4 text-sm text-soil-dark/60">{t('noNotices')}</Card>
      ) : (
        <Advisories items={active} />
      )}
      {past.length > 0 && (
        <ul className="space-y-1">
          {past.map((x) => (
            <li key={x.notice_id} className="flex items-center gap-2 text-xs rounded-xl bg-white/60 border border-soil-dark/10 px-3 py-2 text-soil-dark/60">
              <span className="flex-1 truncate">{x.title}</span>
              <span>{t('expired')}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

const PREFS: EmailPref[] = ['warnings', 'all', 'digest', 'off']

/** Phone notifications (Web Push) and email, per farm. */
export function NotifySettings() {
  const { farmId, lang, t } = useFarmer()
  const [push, setPush] = useState<PushState | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [contact, setContact] = useState<Contact | null>(null)
  const [email, setEmail] = useState('')
  const [pref, setPref] = useState<EmailPref>('warnings')

  useEffect(() => {
    pushState().then(setPush).catch(() => setPush('unsupported'))
    api.contact(farmId!).then((c) => {
      setContact(c)
      setEmail(c.email ?? '')
      setPref(c.email_pref)
    }).catch(() => undefined)
  }, [farmId])

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key)
    setMsg(null)
    try {
      await fn()
    } catch (e) {
      setMsg((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const togglePush = () => run('push', async () => {
    setPush(push === 'on' ? await disablePush() : await enablePush(farmId!))
  })
  const save = () => run('save', async () => {
    const c = await api.saveContact(farmId!, email.trim() || null, pref)
    setContact(c)
    setMsg(t('saved'))
  })
  const sent = (status: string) => setMsg(status === 'sent' ? t('emailSentLive') : t('emailSentOutbox'))

  return (
    <Card className="p-4 space-y-4">
      <div className="flex items-start gap-3">
        <span className="w-10 h-10 rounded-full bg-leaf/10 flex items-center justify-center shrink-0">
          <BellRing className="w-5 h-5 text-leaf-deep" />
        </span>
        <div>
          <h2 className="font-semibold">{t('notifyTitle')}</h2>
          <p className="text-xs text-soil-dark/60">{t('notifySub')}</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Smartphone className="w-4 h-4 text-soil-dark/50 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">{t('phoneAlerts')}</p>
          <p className="text-[11px] text-soil-dark/55">
            {push === 'on' ? t('phoneOn') : push === 'blocked' ? t('phoneBlocked') : push === 'unsupported' ? t('phoneUnsupported') : ''}
          </p>
        </div>
        {push === 'on' || push === 'off' ? (
          <button onClick={togglePush} disabled={busy !== null}
            className={`shrink-0 min-h-[40px] px-4 rounded-full text-xs font-medium ${push === 'on' ? 'bg-white border border-soil-dark/20' : 'bg-leaf-deep text-cream'}`}>
            {busy === 'push' ? <Loader2 className="w-4 h-4 animate-spin" /> : push === 'on' ? t('phoneTurnOff') : t('phoneTurnOn')}
          </button>
        ) : null}
      </div>
      {push === 'on' && (
        <button onClick={() => run('ptest', () => api.pushTest(farmId!, lang))} className="text-xs font-medium text-leaf-deep">
          {busy === 'ptest' ? '…' : t('sendTest')}
        </button>
      )}

      <div className="border-t border-soil-dark/10 pt-3 space-y-2">
        <label className="block text-xs text-soil-dark/60">
          <span className="flex items-center gap-1.5"><Mail className="w-3.5 h-3.5" />{t('emailLabel')}</span>
          <input type="email" inputMode="email" autoComplete="email" value={email} placeholder={t('emailPlaceholder')}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full min-h-[44px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm focus:outline-none focus:border-leaf" />
        </label>
        <div className="grid grid-cols-1 gap-1.5">
          {PREFS.map((p) => (
            <label key={p} className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${pref === p ? 'border-leaf bg-leaf/5' : 'border-soil-dark/10'}`}>
              <input type="radio" name="email-pref" checked={pref === p} onChange={() => setPref(p)} className="accent-leaf-deep" />
              {t(`emailPref_${p}`)}
            </label>
          ))}
        </div>
        <button onClick={save} disabled={busy !== null}
          className="w-full min-h-[44px] rounded-full bg-leaf-deep text-cream text-sm font-medium disabled:opacity-50">
          {busy === 'save' ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : t('saveBtn')}
        </button>
        {contact?.email && (
          <div className="flex gap-2">
            <button onClick={() => run('etest', async () => sent((await api.emailTest(farmId!)).status))} disabled={busy !== null}
              className="flex-1 min-h-[40px] rounded-full border border-soil-dark/20 text-xs font-medium bg-white">
              {busy === 'etest' ? '…' : t('emailTestBtn')}
            </button>
            <button onClick={() => run('esum', async () => sent((await api.emailSummary(farmId!)).status))} disabled={busy !== null}
              className="flex-1 min-h-[40px] rounded-full border border-soil-dark/20 text-xs font-medium bg-white">
              {busy === 'esum' ? '…' : t('emailSummaryBtn')}
            </button>
          </div>
        )}
      </div>
      {msg && <p className="text-xs text-center text-leaf-deep">{msg}</p>}
    </Card>
  )
}

import { useEffect, useState } from 'react'
import { BellRing, CloudSun, Loader2, Mail, Smartphone } from 'lucide-react'
import { api } from '../../api/client'
import type { Contact, EmailPref } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { disablePush, enablePush, pushState, type PushState } from '../../lib/push'
import { useFarmer } from '../FarmerContext'
import { FIELD, LABEL, PANEL, PRIMARY, SECONDARY } from '../tokens'
import { PanelHead } from '../ui'
import DemoNotice, { useReadOnlyFarm } from './DemoNotice'
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
    <section className={`${PANEL} p-5 lg:p-6`}>
      <PanelHead icon={CloudSun} title={t('noticesTitle')} />
      <div className="mt-4">
        {n.loading && !n.data ? null : active.length === 0 ? (
          <p className="rounded-[20px] bg-[#f5f7f1] p-4 text-[15px] text-soil-dark/80">{t('noNotices')}</p>
        ) : (
          <Advisories items={active} />
        )}
      </div>
      {past.length > 0 && (
        <ul className="mt-4 divide-y divide-soil-dark/[0.07]">
          {past.map((x) => (
            <li key={x.notice_id} className="flex items-center gap-3 py-2.5 text-[14px] text-soil-dark/75">
              <span className="min-w-0 flex-1 truncate">{x.title}</span>
              <span className="shrink-0 rounded-full bg-soil-dark/5 px-2.5 py-0.5 text-[12px]">{t('expired')}</span>
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
  // A shared demonstration field is everybody's, so nobody puts their address
  // on its warnings — the next visitor would inherit it, and the mail would
  // be about somebody else's crop.
  const readOnly = useReadOnlyFarm() !== null
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

  if (readOnly) return <DemoNotice />

  return (
    <section className={`${PANEL} space-y-4 p-5`}>
      <PanelHead icon={BellRing} title={t('notifyTitle')} sub={t('notifySub')} />

      <div className="flex items-center gap-3 rounded-[20px] bg-[#f5f7f1] p-3.5">
        <Smartphone className="h-5 w-5 shrink-0 text-leaf-deep" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold">{t('phoneAlerts')}</p>
          <p className="text-[13px] text-soil-dark/75">
            {push === 'on' ? t('phoneOn') : push === 'blocked' ? t('phoneBlocked') : push === 'unsupported' ? t('phoneUnsupported') : ''}
          </p>
        </div>
        {push === 'on' || push === 'off' ? (
          <button onClick={togglePush} disabled={busy !== null}
            className={`min-h-[44px] shrink-0 rounded-full px-4 text-[14px] font-semibold ${push === 'on' ? 'bg-white ring-1 ring-soil-dark/15' : 'bg-[#2f6a39] text-white'}`}>
            {busy === 'push' ? <Loader2 className="h-4 w-4 animate-spin" /> : push === 'on' ? t('phoneTurnOff') : t('phoneTurnOn')}
          </button>
        ) : null}
      </div>
      {push === 'on' && (
        <button onClick={() => run('ptest', () => api.pushTest(farmId!, lang))} className="min-h-[40px] text-[14px] font-medium text-leaf-deep">
          {busy === 'ptest' ? '…' : t('sendTest')}
        </button>
      )}

      <div className="space-y-3">
        <label className={LABEL}>
          <span className="flex items-center gap-1.5"><Mail className="h-4 w-4" aria-hidden />{t('emailLabel')}</span>
          <input type="email" inputMode="email" autoComplete="email" value={email} placeholder={t('emailPlaceholder')}
            onChange={(e) => setEmail(e.target.value)} className={FIELD} />
        </label>
        <div className="grid gap-2">
          {PREFS.map((p) => (
            <label key={p} className={`flex min-h-[48px] cursor-pointer items-center gap-3 rounded-2xl px-4 text-[15px] ring-1 transition-colors ${
              pref === p ? 'bg-[#e3efd9] font-medium text-leaf-deep ring-[#4b8b3b]/40' : 'bg-white ring-soil-dark/10 hover:bg-[#f5f7f1]'}`}>
              <input type="radio" name="email-pref" checked={pref === p} onChange={() => setPref(p)} className="h-4 w-4 accent-[#2f6a39]" />
              {t(`emailPref_${p}`)}
            </label>
          ))}
        </div>
        <button onClick={save} disabled={busy !== null} className={PRIMARY}>
          {busy === 'save' ? <Loader2 className="h-5 w-5 animate-spin" /> : t('saveBtn')}
        </button>
        {contact?.email && (
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => run('etest', async () => sent((await api.emailTest(farmId!)).status))} disabled={busy !== null}
              className={`${SECONDARY} px-3 text-[14px]`}>
              {busy === 'etest' ? '…' : t('emailTestBtn')}
            </button>
            <button onClick={() => run('esum', async () => sent((await api.emailSummary(farmId!)).status))} disabled={busy !== null}
              className={`${SECONDARY} px-3 text-[14px]`}>
              {busy === 'esum' ? '…' : t('emailSummaryBtn')}
            </button>
          </div>
        )}
      </div>
      {msg && <p role="status" className="text-center text-[14px] text-leaf-deep">{msg}</p>}
    </section>
  )
}

import { useState, type ReactNode } from 'react'
import { Check, Loader2, Mail, MapPin, MessageSquareText, Phone, Sprout, Tractor, UserRound } from 'lucide-react'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import FieldManager from '../components/FieldManager'
import { useFarmer } from '../FarmerContext'
import { useAsync } from '../../lib/hooks'
import { bcp47, LANGS } from '../../lib/i18n'
import { ErrorBox } from '../../ui/kit'
import { useProfileSave } from '../../ui/ProfileForm'
import { FIELD, LABEL, PANEL, PRIMARY, SECONDARY } from '../tokens'
import { PanelHead, PhotoCurve } from '../ui'

/** The farmer's own record: what the app knows about them, in one place, and
 *  theirs to correct. Everything here was asked at sign-up and then had
 *  nowhere to be read back — a village spelt wrong stayed wrong.
 *
 *  It opens with who this is rather than with an empty text box, because a
 *  profile that begins at "Full name" is a form, and a farmer who has worked
 *  four fields through a season should see that said back to them before they
 *  are asked to correct a spelling.
 */
export default function Profile() {
  const { t, lang, farmId } = useFarmer()
  const { me } = useAuth()
  const farms = useAsync(() => api.farms(lang), [lang])
  const crops = useAsync(() => api.crops(lang), [lang])
  const { save, busy, done, error } = useProfileSave()
  const p = me?.profile
  // The shell's "Profile" h1 shows only once a field is open.
  const NameHeading = farmId != null ? 'h2' : 'h1'

  const [name, setName] = useState(me?.name ?? '')
  const [village, setVillage] = useState(p?.village ?? '')
  const [taluka, setTaluka] = useState(p?.taluka ?? '')
  const [land, setLand] = useState(p?.total_land_acres != null ? String(p.total_land_acres) : '')

  // Nothing typed yet means nothing to send: the button says so rather than
  // posting a patch identical to what the server already holds.
  const dirty =
    name !== (me?.name ?? '') ||
    village !== (p?.village ?? '') ||
    taluka !== (p?.taluka ?? '') ||
    land !== (p?.total_land_acres != null ? String(p.total_land_acres) : '')

  const list = farms.data ?? []
  const sown = list.filter((f) => f.status !== 'fallow')
  const acres = list.reduce((n, f) => n + (f.area_acres ?? 0), 0)
  const seasons = list.reduce((n, f) => n + (f.seasons ?? 0), 0)

  const place = [p?.village, p?.taluka, p?.district, p?.state].filter(Boolean).join(' · ')
  const language = LANGS.find((l) => l.code === lang)
  const since = me?.created_at
    ? new Date(me.created_at).toLocaleDateString(bcp47(lang), { month: 'long', year: 'numeric' })
    : null

  return (
    <div className="space-y-6">
      <section className={`${PANEL} p-2`}>
        <div className="relative h-[190px] overflow-hidden rounded-[22px] bg-leaf-deep sm:h-[210px]">
          <img src="/photos/sunset.webp" alt="" width={1452} height={570}
            className="absolute inset-0 h-full w-full object-cover object-[center_60%]" />
          <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/65 via-black/25 to-black/5" />
          <div className="relative flex h-full items-end gap-4 p-5 pb-7 text-white lg:p-6 lg:pb-8">
            <Monogram name={me?.name ?? ''} />
            <div className="min-w-0 pb-1">
              {/* One h1 per screen: the shell titles this screen "Profile" once a
                  field is open; before there is one, the name is the title. */}
              <NameHeading className="font-instrument-serif text-[34px] leading-none drop-shadow-sm [overflow-wrap:anywhere] lg:text-[42px]">{me?.name}</NameHeading>
              {place && <p className="mt-2 flex items-center gap-1.5 text-[15px] drop-shadow"><MapPin className="h-4 w-4 shrink-0" aria-hidden />{place}</p>}
            </div>
          </div>
          <PhotoCurve />
        </div>
        <div className="px-3 pb-3 pt-1">
          <div className="flex flex-wrap gap-2">
            <Tag>{t('profileRoleFarmer')}</Tag>
            {language && <Tag>{language.label}</Tag>}
            {me?.is_demo && <Tag>{t('profileDemo')}</Tag>}
            {since && <Tag>{t('profileSince').replace('{on}', since)}</Tag>}
          </div>
          {/* What the account actually amounts to. Read from the fields
              themselves, so it cannot drift from the list further down. */}
          <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label={t('profileStatFields')} value={list.length} loading={farms.loading} />
            <Stat label={t('profileStatGrowing')} value={sown.length} loading={farms.loading} />
            <Stat label={t('profileStatAcres')} value={round(acres)} loading={farms.loading} />
            <Stat label={t('profileStatSeasons')} value={seasons} loading={farms.loading} />
          </dl>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 space-y-6">
          <section className={`${PANEL} space-y-4 p-5 lg:p-6`}>
            <PanelHead icon={UserRound} title={t('profileYou')} />
            <label className={LABEL}>
              {t('authName')}
              <input className={FIELD} value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className={LABEL}>
                {t('authVillage')}
                <input className={FIELD} value={village} placeholder={t('profileNotSet')}
                  onChange={(e) => setVillage(e.target.value)} />
              </label>
              <label className={LABEL}>
                {t('authTaluka')}
                <input className={FIELD} value={taluka} placeholder={t('profileNotSet')}
                  onChange={(e) => setTaluka(e.target.value)} />
              </label>
            </div>
            <label className={LABEL}>
              {t('authTotalLand')}
              <input className={FIELD} type="number" inputMode="decimal" min="0" step="0.1"
                placeholder={t('profileNotSet')} value={land} onChange={(e) => setLand(e.target.value)} />
              <span className="mt-1 block text-[13px] font-normal text-soil-dark/70">{t('profileLandHint')}</span>
            </label>
            {error && <ErrorBox offlineLabel={t('offline')} error={error} />}
            <div className="flex flex-wrap items-center gap-3">
              <button disabled={busy || !dirty} className={`${PRIMARY.replace('w-full', 'w-auto')} px-7`}
                onClick={() => save({
                  name: name.trim(), village: village.trim(), taluka: taluka.trim(),
                  total_land_acres: land === '' ? null : parseFloat(land),
                })}>
                {busy && <Loader2 className="h-5 w-5 animate-spin" />}
                {t('profileSave')}
              </button>
              {done && <span role="status" className="flex items-center gap-1.5 text-[15px] text-leaf-deep"><Check className="h-5 w-5" /> {t('saved')}</span>}
            </div>
          </section>

          <section className={`${PANEL} space-y-4 p-5 lg:p-6`}>
            <PanelHead icon={Tractor} title={t('profileFields')} sub={t('profileFieldsSub')} />
            <FieldManager farms={list} crops={crops.data} onChange={farms.reload} />
          </section>
        </div>

        <aside className="min-w-0 space-y-6">
          <section className={`${PANEL} p-5`}>
            <PanelHead icon={Phone} title={t('profileReach')} />
            <dl className="mt-4 space-y-2">
              <Line icon={Phone} label={t('authMobile')} value={me?.phone} />
              <Line icon={Mail} label={t('authEmail')} value={me?.email} />
              <Line icon={MapPin} label={t('district')}
                value={[p?.district, p?.state].filter(Boolean).join(', ') || null} />
            </dl>
            {!me?.email && !me?.is_demo && <EmailConfirm key={me?.pending_email ?? ''} pending={me?.pending_email ?? null} />}
            <p className="mt-4 text-[13px] leading-relaxed text-soil-dark/70">{t('profileContactNote')}</p>
          </section>

          {/* Shown only where this server can send a text at all: a switch
              that does nothing would be worse than no switch. */}
          {me?.sms_available && me.phone && (
            <section className={`${PANEL} p-5`}>
              <PanelHead icon={MessageSquareText} title={t('smsTitle')} sub={t('smsSub').replace('{phone}', me.phone)} />
              <Choice options={[['warnings', t('smsOn')], ['off', t('smsOff')]]}
                value={me.sms_pref ?? 'warnings'} busy={busy} onPick={(v) => save({ sms_pref: v })} />
            </section>
          )}

          {/* One switch, not one per field. A farmer who says "stop emailing
              me" should have to say it once. */}
          <section className={`${PANEL} p-5`}>
            <PanelHead icon={Mail} title={t('profileEmails')} sub={t('profileEmailsSub')} />
            <Choice options={[['off', t('emailOff')], ['warnings', t('emailWarnings')], ['all', t('emailAll')]]}
              value={me?.email_pref ?? 'warnings'} busy={busy} onPick={(v) => save({ email_pref: v })} />
          </section>
        </aside>
      </div>
    </div>
  )
}

/** An email the farmer gave at an SMS sign-up, or none: proved by a code sent
 *  to it before anything else is ever sent there. */
function EmailConfirm({ pending }: { pending: string | null }) {
  const { t, lang } = useFarmer()
  const { update } = useAuth()
  const [email, setEmail] = useState(pending ?? '')
  const [sent, setSent] = useState<{ id: string; to: string; digits: number } | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const send = async () => {
    setBusy(true)
    setError(null)
    try {
      // The address already waiting is sent as null: the server uses the one it holds.
      const r = await api.addEmail(pending && email.trim() === pending ? null : email.trim(), lang)
      setSent({ id: r.challenge_id, to: r.sent_to, digits: r.digits })
      setCode('')
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }
  const verify = async () => {
    if (!sent) return
    setBusy(true)
    setError(null)
    try {
      update(await api.verifyEmail(sent.id, code.trim(), lang))
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4 space-y-3 rounded-[20px] bg-[#fbf0dc] p-4">
      <p className="text-[16px] font-semibold text-[#7a4f12]">{pending ? t('emailConfirmTitle') : t('emailAddTitle')}</p>
      <p className="text-[14px] text-soil-dark/80">
        {pending ? t('emailConfirmBody').replace('{email}', pending) : t('emailAddBody')}
      </p>
      {!sent ? (
        <>
          <input type="email" inputMode="email" autoComplete="email" value={email} aria-label={t('emailLabel')}
            placeholder={t('emailPlaceholder')} onChange={(e) => setEmail(e.target.value)} className={`${FIELD} mt-0 bg-white`} />
          <button onClick={send} disabled={busy || !email.trim()} className={PRIMARY}>
            {busy && <Loader2 className="h-5 w-5 animate-spin" />}
            {t('emailSendCode')}
          </button>
        </>
      ) : (
        <>
          <p className="text-[14px] text-soil-dark/85">{t('authCodeSent').replace('{to}', sent.to)}</p>
          <input inputMode="numeric" autoComplete="one-time-code" maxLength={sent.digits} value={code}
            aria-label={t('authEnterCode')} placeholder={t('authEnterCode')}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            className={`${FIELD} mt-0 bg-white text-center text-[22px] tracking-[0.4em] tabular-nums`} />
          <button onClick={verify} disabled={busy || code.length < sent.digits} className={PRIMARY}>
            {busy && <Loader2 className="h-5 w-5 animate-spin" />}
            {t('emailConfirmBtn')}
          </button>
          <button onClick={send} disabled={busy} className={`${SECONDARY} w-full`}>{t('authResend')}</button>
        </>
      )}
      {error && <ErrorBox offlineLabel={t('offline')} error={error} />}
    </div>
  )
}

/** Two or three answers to one question, the chosen one filled. */
function Choice<V extends string>({ options, value, busy, onPick }: {
  options: [V, string][]; value: V; busy: boolean; onPick: (v: V) => void
}) {
  return (
    <div className="mt-4 grid gap-2" role="radiogroup">
      {options.map(([v, label]) => {
        const on = v === value
        return (
          <button key={v} role="radio" aria-checked={on} disabled={busy} onClick={() => !on && onPick(v)}
            className={`flex min-h-[52px] items-center gap-3 rounded-2xl px-4 text-left text-[15px] ring-1 transition-colors ${
              on ? 'bg-[#e3efd9] font-semibold text-leaf-deep ring-[#4b8b3b]/40' : 'bg-white ring-soil-dark/10 hover:bg-[#f5f7f1]'}`}>
            <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${on ? 'bg-[#2f6a39] text-white' : 'ring-2 ring-soil-dark/25'}`}>
              {on && <Check className="h-3.5 w-3.5" strokeWidth={3} aria-hidden />}
            </span>
            {label}
          </button>
        )
      })}
    </div>
  )
}

/** Initials, because a farmer who cannot read the name can still recognise the
 *  shape of their own account. */
function Monogram({ name }: { name: string }) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0] ?? '').join('').toUpperCase()
  return (
    <span aria-hidden className="grid h-16 w-16 shrink-0 place-items-center rounded-2xl bg-white text-2xl font-semibold tracking-tight text-[#2f6a39] shadow-lg lg:h-[76px] lg:w-[76px]">
      {initials || <Sprout className="h-7 w-7" />}
    </span>
  )
}

function Tag({ children }: { children: ReactNode }) {
  return <span className="rounded-full bg-[#eef3e6] px-3 py-1 text-[13px] font-medium text-leaf-deep">{children}</span>
}

function Stat({ label, value, loading }: { label: string; value: number; loading: boolean }) {
  return (
    // dt before dd as a description list requires; reversed so the number still sits on top.
    <div className="flex flex-col-reverse rounded-[20px] bg-[#f5f7f1] px-4 py-3">
      <dt className="mt-1.5 text-[13px] text-soil-dark/75">{label}</dt>
      <dd className="text-[26px] font-semibold leading-none tabular-nums">
        {loading ? <span className="inline-block h-6 w-8 animate-pulse rounded bg-soil-dark/10" /> : value}
      </dd>
    </div>
  )
}

function Line({ icon: Icon, label, value }: { icon: typeof Phone; label: string; value?: string | null }) {
  const { t } = useFarmer()
  return (
    <div className="flex items-center gap-3 rounded-[18px] bg-[#f5f7f1] px-3.5 py-2.5">
      <Icon className="h-5 w-5 shrink-0 text-leaf-deep" aria-hidden />
      <div className="min-w-0">
        <dt className="text-[13px] text-soil-dark/70">{label}</dt>
        {/* An address with no spaces in it still has to fit the column. */}
        <dd className="text-[15px] font-medium [overflow-wrap:anywhere]">{value || t('profileNotSet')}</dd>
      </div>
    </div>
  )
}

const round = (n: number) => Math.round(n * 10) / 10

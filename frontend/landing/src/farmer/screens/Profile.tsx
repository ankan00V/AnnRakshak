import { useState } from 'react'
import { Mail, MapPin, Phone, Sprout } from 'lucide-react'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import FieldManager from '../components/FieldManager'
import { useFarmer } from '../FarmerContext'
import { useAsync } from '../../lib/hooks'
import { bcp47, LANGS } from '../../lib/i18n'
import { Card } from '../../ui/kit'
import { Field, ProfileCard, SaveBar, input, useProfileSave } from '../../ui/ProfileForm'
import { EYEBROW, MAIN, SIDE, SPLIT } from '../layout'

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
  const { t, lang } = useFarmer()
  const { me } = useAuth()
  const farms = useAsync(() => api.farms(lang), [lang])
  const crops = useAsync(() => api.crops(lang), [lang])
  const { save, busy, done, error } = useProfileSave()
  const p = me?.profile

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
    <div className="space-y-5">
      <section className="rounded-3xl bg-soil-dark text-cream overflow-hidden">
        <div className="p-5 md:p-7 flex items-start gap-4 md:gap-5">
          <Monogram name={me?.name ?? ''} />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ochre">
              {t('profileTitle')}
            </p>
            <h1 className="mt-1.5 font-instrument-serif text-3xl lg:text-[34px] leading-tight break-words">
              {me?.name}
            </h1>
            {place && <p className="mt-1 text-sm text-cream/65 text-pretty">{place}</p>}
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Tag>{t('profileRoleFarmer')}</Tag>
              {language && <Tag>{language.label}</Tag>}
              {me?.is_demo && <Tag>{t('profileDemo')}</Tag>}
            </div>
          </div>
        </div>

        {/* What the account actually amounts to. Read from the fields
            themselves, so it cannot drift from the list further down. */}
        <dl className="grid grid-cols-2 sm:grid-cols-4 border-t border-cream/10 divide-x divide-cream/10">
          <Stat label={t('profileStatFields')} value={list.length} loading={farms.loading} />
          <Stat label={t('profileStatGrowing')} value={sown.length} loading={farms.loading} />
          <Stat label={t('profileStatAcres')} value={round(acres)} loading={farms.loading} />
          <Stat label={t('profileStatSeasons')} value={seasons} loading={farms.loading} />
        </dl>

        {since && (
          <p className="px-5 md:px-7 py-2.5 border-t border-cream/10 text-[11px] text-cream/45">
            {t('profileSince').replace('{on}', since)}
          </p>
        )}
      </section>

      <div className={`space-y-5 ${SPLIT}`}>
        <div className={`${MAIN} space-y-5`}>
          <ProfileCard title={t('profileYou')} sub={t('profileSub')}>
            <Field label={t('authName')}>
              <input className={input} value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t('authVillage')}>
                <input className={input} value={village} placeholder={t('profileNotSet')}
                  onChange={(e) => setVillage(e.target.value)} />
              </Field>
              <Field label={t('authTaluka')}>
                <input className={input} value={taluka} placeholder={t('profileNotSet')}
                  onChange={(e) => setTaluka(e.target.value)} />
              </Field>
            </div>
            <Field label={t('authTotalLand')} hint={t('profileLandHint')}>
              <input className={input} type="number" inputMode="decimal" min="0" step="0.1"
                placeholder={t('profileNotSet')}
                value={land} onChange={(e) => setLand(e.target.value)} />
            </Field>
            <SaveBar busy={busy} done={done} error={error} label={t('profileSave')} disabled={!dirty}
              onSave={() => save({
                name: name.trim(), village: village.trim(), taluka: taluka.trim(),
                total_land_acres: land === '' ? null : parseFloat(land),
              })} />
          </ProfileCard>

          {/* One switch, not one per field. A farmer who says "stop emailing
              me" should have to say it once. */}
          <ProfileCard title={t('profileEmails')} sub={t('profileEmailsSub')}>
            <div className="grid gap-2 sm:grid-cols-3">
              {(['off', 'warnings', 'all'] as const).map((pref) => {
                const on = (me?.email_pref ?? 'warnings') === pref
                return (
                  <button key={pref} onClick={() => save({ email_pref: pref })}
                    className={`min-h-[46px] rounded-xl border px-3 text-sm font-medium transition-colors ${
                      on ? 'border-leaf-deep bg-leaf/10 text-leaf-deep' : 'border-soil-dark/15 bg-white'}`}>
                    {t(pref === 'off' ? 'emailOff' : pref === 'warnings' ? 'emailWarnings' : 'emailAll')}
                  </button>
                )
              })}
            </div>
          </ProfileCard>

          <ProfileCard title={t('profileFields')} sub={t('profileFieldsSub')}>
            <FieldManager farms={list} crops={crops.data} onChange={farms.reload} />
          </ProfileCard>
        </div>

        <aside className={`${SIDE} space-y-5`}>
          <Card className="p-4 md:p-5">
            <h2 className={EYEBROW}>{t('profileReach')}</h2>
            <dl className="mt-3 space-y-3">
              <Line icon={Phone} label={t('authMobile')} value={me?.phone} />
              <Line icon={Mail} label={t('authEmail')} value={me?.email} />
              <Line icon={MapPin} label={t('district')}
                value={[p?.district, p?.state].filter(Boolean).join(', ') || null} />
            </dl>
            <p className="mt-4 pt-3 border-t border-soil-dark/[0.07] text-[11px] leading-relaxed text-soil-dark/50">
              {t('profileContactNote')}
            </p>
          </Card>

        </aside>
      </div>
    </div>
  )
}

/** Initials, because a farmer who cannot read the name can still recognise the
 *  shape of their own account. */
function Monogram({ name }: { name: string }) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0] ?? '').join('').toUpperCase()
  return (
    <span aria-hidden className="shrink-0 grid place-items-center w-16 h-16 md:w-[72px] md:h-[72px]
                                 rounded-2xl bg-ochre text-soil-dark text-2xl font-semibold tracking-tight">
      {initials || <Sprout className="w-7 h-7" />}
    </span>
  )
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="px-2.5 py-1 rounded-full bg-cream/10 text-[11px] font-medium text-cream/80">{children}</span>
  )
}

function Stat({ label, value, loading }: { label: string; value: number; loading: boolean }) {
  return (
    <div className="px-4 md:px-5 py-3.5">
      <dd className="text-[26px] leading-none font-semibold tabular-nums">
        {loading ? <span className="inline-block w-8 h-6 rounded bg-cream/10 animate-pulse" /> : value}
      </dd>
      <dt className="mt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-cream/50">{label}</dt>
    </div>
  )
}

function Line({ icon: Icon, label, value }: { icon: typeof Phone; label: string; value?: string | null }) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon className="w-4 h-4 mt-0.5 shrink-0 text-soil-dark/35" aria-hidden />
      <div className="min-w-0">
        <dt className="text-[11px] text-soil-dark/50">{label}</dt>
        {/* An address with no spaces in it still has to fit the column. */}
        <dd className="text-sm [overflow-wrap:anywhere]">{value || '—'}</dd>
      </div>
    </div>
  )
}

const round = (n: number) => Math.round(n * 10) / 10

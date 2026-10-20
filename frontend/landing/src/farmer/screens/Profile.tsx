import { useState } from 'react'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import LanguagePicker from '../components/LanguagePicker'
import { useFarmer } from '../FarmerContext'
import { useAsync } from '../../lib/hooks'
import { Card, Pill } from '../../ui/kit'
import { Field, ProfileCard, SaveBar, input, useProfileSave } from '../../ui/ProfileForm'
import { EYEBROW, MAIN, SIDE, SPLIT } from '../layout'

/** The farmer's own record: what the app knows about them, in one place, and
 *  theirs to correct. Everything here was asked at sign-up and then had
 *  nowhere to be read back — a village spelt wrong stayed wrong. */
export default function Profile() {
  const { t, setLang } = useFarmer()
  const { me } = useAuth()
  const farms = useAsync(() => api.farms('en'), [])
  const { save, busy, done, error } = useProfileSave()
  const p = me?.profile

  const [name, setName] = useState(me?.name ?? '')
  const [village, setVillage] = useState(p?.village ?? '')
  const [taluka, setTaluka] = useState(p?.taluka ?? '')
  const [land, setLand] = useState(p?.total_land_acres != null ? String(p.total_land_acres) : '')

  return (
    <div className={`space-y-5 ${SPLIT}`}>
      <div className={`${MAIN} space-y-5`}>
        <div>
          <h1 className="font-instrument-serif text-3xl lg:text-[34px] leading-tight">{t('profileTitle')}</h1>
          <p className="mt-1 text-sm text-soil-dark/60">{t('profileSub')}</p>
        </div>

        <ProfileCard title={t('profileYou')}>
          <Field label={t('authName')}>
            <input className={input} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t('authVillage')}>
              <input className={input} value={village} onChange={(e) => setVillage(e.target.value)} />
            </Field>
            <Field label={t('authTaluka')}>
              <input className={input} value={taluka} onChange={(e) => setTaluka(e.target.value)} />
            </Field>
          </div>
          <Field label={t('authTotalLand')}>
            <input className={input} type="number" inputMode="decimal" min="0" step="0.1"
              value={land} onChange={(e) => setLand(e.target.value)} />
          </Field>
          <SaveBar busy={busy} done={done} error={error} label={t('profileSave')}
            onSave={() => save({
              name: name.trim(), village: village.trim(), taluka: taluka.trim(),
              total_land_acres: land === '' ? null : parseFloat(land),
            })} />
        </ProfileCard>

        <ProfileCard title={t('profileLanguage')} sub={t('profileLanguageSub')}>
          <LanguagePicker variant="grid" wide={false} onPick={(code) => { setLang(code); save({ lang: code }) }} />
        </ProfileCard>
      </div>

      <aside className={`${SIDE} space-y-5`}>
        <Card className="p-4 md:p-5">
          <h2 className={EYEBROW}>{t('profileReach')}</h2>
          <dl className="mt-2 space-y-2 text-sm">
            <div><dt className="text-[11px] text-soil-dark/50">{t('authMobile')}</dt><dd>{me?.phone ?? '—'}</dd></div>
            <div><dt className="text-[11px] text-soil-dark/50">{t('authEmail')}</dt><dd className="break-all">{me?.email ?? '—'}</dd></div>
            <div><dt className="text-[11px] text-soil-dark/50">{t('district')}</dt><dd>{[p?.district, p?.state].filter(Boolean).join(', ') || '—'}</dd></div>
          </dl>
          <p className="mt-3 text-[11px] text-soil-dark/50">{t('profileContactNote')}</p>
        </Card>

        <Card className="p-4 md:p-5">
          <h2 className={EYEBROW}>{t('profileFields')}</h2>
          <ul className="mt-2 space-y-2">
            {(farms.data ?? []).map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="min-w-0 truncate">{f.crop_name} · {f.village || f.district}</span>
                <Pill tone={f.status === 'fallow' ? 'neutral' : 'leaf'}>
                  {f.status === 'fallow' ? t('seasonFallowTag') : `${f.area_acres} ${t('acres')}`}
                </Pill>
              </li>
            ))}
            {farms.data?.length === 0 && <li className="text-sm text-soil-dark/60">—</li>}
          </ul>
        </Card>
      </aside>
    </div>
  )
}

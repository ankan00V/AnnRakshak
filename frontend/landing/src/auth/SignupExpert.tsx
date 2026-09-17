import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { api } from '../api/client'
import type { Lang } from '../api/types'
import { useFarmer } from '../farmer/FarmerContext'
import { LANGS } from '../lib/i18n'
import { useAsync } from '../lib/hooks'
import { Card, ErrorBox, Spinner } from '../ui/kit'
import { useAuth } from './AuthContext'
import { emailOk, phoneOk } from './helpers'
import { Chips, CodePanel, Field, Input, Primary, Secondary, Select, Steps } from './parts'

/** What an expert is asked, and why: it decides which cases reach them and
 *  whether their verdicts can be trusted. Their post and credentials (the
 *  district office verifies them — a verdict reaches farmers and retrains the
 *  model), and their coverage: districts, crops, specialities and the
 *  languages they can answer a farmer in. */
export default function SignupExpert() {
  const { lang, t } = useFarmer()
  const { signIn } = useAuth()
  const options = useAsync(() => api.authOptions(lang), [lang])
  const [step, setStep] = useState(0)
  const [f, setF] = useState({
    name: '', email: '', phone: '',
    designation: 'kvk_scientist', organisation: '', employeeId: '', qualification: 'msc_agri', experience: '',
    state: '', districts: [] as string[], crops: [] as string[], specialities: [] as string[],
    languages: ['mr', 'hi', 'en'] as Lang[],
  })
  const [query, setQuery] = useState('')
  const [touched, setTouched] = useState(false)
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }))

  const bad = {
    name: f.name.trim().length < 2,
    email: !emailOk(f.email),
    phone: !phoneOk(f.phone),
    organisation: f.organisation.trim().length < 2,
    employeeId: f.employeeId.trim().length < 2,
    experience: !(f.experience !== '' && Number(f.experience) >= 0 && Number(f.experience) <= 60),
    districts: f.districts.length === 0,
    crops: f.crops.length === 0,
    specialities: f.specialities.length === 0,
    languages: f.languages.length === 0,
  }
  const stepOk = [
    !bad.name && !bad.email && !bad.phone,
    !bad.organisation && !bad.employeeId && !bad.experience,
    !bad.districts && !bad.crops && !bad.specialities && !bad.languages,
    true,
  ]
  const show = (k: keyof typeof bad) => touched && bad[k]
  const next = () => {
    setTouched(true)
    if (stepOk[step]) {
      setTouched(false)
      setStep((s) => s + 1)
      window.scrollTo(0, 0)
    }
  }

  const places = useAsync(() => api.places(), [], 'places')
  const inState = places.data?.states.find((x) => x.name === f.state)?.districts ?? []
  const districts = useMemo(
    () => inState.map((d) => d.name).filter((d) => d.toLowerCase().includes(query.trim().toLowerCase())),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [query, f.state, places.data],
  )
  const titles = [t('authExpertStep1'), t('authExpertStep2'), t('authExpertStep3'), t('authFarmerStep4')]
  const o = options.data
  const name = (list: { id: string; name: string }[] | undefined, id: string) => list?.find((x) => x.id === id)?.name ?? id

  if (options.error) return <ErrorBox error={options.error} onRetry={options.reload} retryLabel={t('retry')} />
  if (!o) return <Spinner />

  return (
    <div>
      <Steps step={step} titles={titles} />

      {step === 0 && (
        <div className="space-y-4">
          <Field label={t('authName')} error={show('name') && t('authFixField')}>
            <Input value={f.name} onChange={(e) => set('name', e.target.value)} autoComplete="name"
              placeholder="Dr. S. Kale" invalid={show('name')} />
          </Field>
          <Field label={t('authWorkEmail')} hint={t('authWorkEmailHint')} error={show('email') && t('authBadEmail')}>
            <Input value={f.email} onChange={(e) => set('email', e.target.value)} type="email" autoComplete="email"
              placeholder="name@kvk.org.in" invalid={show('email')} />
          </Field>
          <Field label={t('authMobile')} hint={t('authExpertMobileHint')} error={show('phone') && t('authBadPhone')}>
            <div className="flex gap-2">
              <span className="min-h-[48px] px-3 rounded-xl border border-soil-dark/20 bg-cream flex items-center text-[15px] text-soil-dark/60">+91</span>
              <Input value={f.phone} onChange={(e) => set('phone', e.target.value)} type="tel" inputMode="numeric"
                autoComplete="tel-national" maxLength={14} placeholder="98XXXXXXXX" invalid={show('phone')} />
            </div>
          </Field>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <Field group label={t('authDesignation')}>
            <Chips value={[f.designation]} onChange={([v]) => set('designation', v)}
              options={o.designations.map((d) => ({ id: d.id, label: d.name }))} columns={2} />
          </Field>
          <Field label={t('authOrganisation')} hint={t('authOrganisationHint')} error={show('organisation') && t('authFixField')}>
            <Input value={f.organisation} onChange={(e) => set('organisation', e.target.value)} autoComplete="organization"
              invalid={show('organisation')} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t('authEmployeeId')} error={show('employeeId') && t('authFixField')}>
              <Input value={f.employeeId} onChange={(e) => set('employeeId', e.target.value)} invalid={show('employeeId')} />
            </Field>
            <Field label={t('authExperience')} error={show('experience') && t('authFixField')}>
              <Input value={f.experience} onChange={(e) => set('experience', e.target.value)} type="number"
                inputMode="numeric" min="0" max="60" invalid={show('experience')} />
            </Field>
          </div>
          <Field label={t('authQualification')}>
            <Select value={f.qualification} onChange={(v) => set('qualification', v)}>
              {o.qualifications.map((q) => <option key={q.id} value={q.id}>{q.name}</option>)}
            </Select>
          </Field>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-5">
          <Field label={t('authState')}>
            <Select value={f.state} onChange={(v) => set('state', v)}>
              <option value="">{t('authPickState')}</option>
              {(places.data?.states ?? []).map((x) => <option key={x.name}>{x.name}</option>)}
            </Select>
          </Field>
          <Field group label={`${t('authDistricts')} · ${f.districts.length}`} hint={t('authDistrictsHint')}
            error={show('districts') && t('authPickOne')}>
            <div className="flex gap-2 mb-2">
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('authSearch')} />
              <button type="button" onClick={() => set('districts', inState.map((d) => d.name))}
                className="px-3 rounded-xl border border-soil-dark/15 text-[13px] font-medium bg-white">{t('authSelectAll')}</button>
              <button type="button" onClick={() => set('districts', [])}
                className="px-3 rounded-xl border border-soil-dark/15 text-[13px] font-medium bg-white">{t('authClear')}</button>
            </div>
            <div className="max-h-56 overflow-y-auto rounded-xl">
              <Chips multi value={f.districts} onChange={(v) => set('districts', v)}
                options={districts.map((d) => ({ id: d, label: d }))} />
            </div>
          </Field>
          <Field group label={t('authCrops')} error={show('crops') && t('authPickOne')}>
            <Chips multi columns={2} value={f.crops} onChange={(v) => set('crops', v)}
              options={o.crops.map((c) => ({ id: c.id, label: c.name }))} />
          </Field>
          <Field group label={t('authSpecialities')} error={show('specialities') && t('authPickOne')}>
            <Chips multi columns={2} value={f.specialities} onChange={(v) => set('specialities', v)}
              options={o.specialities.map((s) => ({ id: s.id, label: s.name }))} />
          </Field>
          <Field group label={t('authLanguages')} error={show('languages') && t('authPickOne')}>
            <Chips multi value={f.languages} onChange={(v) => set('languages', v)}
              options={LANGS.map((l) => ({ id: l.code, label: l.label }))} />
          </Field>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <Card className="p-4">
            <p className="text-[11px] uppercase tracking-wider text-soil-dark/50 font-semibold mb-2">{t('authReview')}</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
              <dt className="text-soil-dark/55">{t('authName')}</dt><dd className="font-medium">{f.name}</dd>
              <dt className="text-soil-dark/55">{t('authWorkEmail')}</dt><dd className="break-all">{f.email.trim()}</dd>
              <dt className="text-soil-dark/55">{t('authDesignation')}</dt>
              <dd>{name(o.designations, f.designation)} · {f.organisation}</dd>
              <dt className="text-soil-dark/55">{t('authEmployeeId')}</dt>
              <dd>{f.employeeId} · {name(o.qualifications, f.qualification)} · {f.experience} y</dd>
              <dt className="text-soil-dark/55">{t('authDistricts')}</dt>
              <dd>{f.districts.length > 4 ? `${f.districts.slice(0, 4).join(', ')} +${f.districts.length - 4}` : f.districts.join(', ')}</dd>
              <dt className="text-soil-dark/55">{t('authCrops')}</dt>
              <dd>{f.crops.map((c) => name(o.crops, c)).join(', ')}</dd>
              <dt className="text-soil-dark/55">{t('authSpecialities')}</dt>
              <dd>{f.specialities.map((s) => name(o.specialities, s)).join(', ')}</dd>
            </dl>
            <button type="button" onClick={() => setStep(0)} className="mt-3 text-[13px] text-leaf-deep font-medium">
              {t('authChange')}
            </button>
          </Card>
          <div className="flex gap-3 items-start rounded-2xl bg-sky-50 text-sky-900 p-3">
            <ShieldCheck className="w-5 h-5 shrink-0 mt-0.5" />
            <p className="text-[13px] leading-snug">{t('authVerifyNote')}</p>
          </div>
          <CodePanel
            sendLabel={t('authSendCodeTo').replace('{to}', f.email.trim())}
            request={() => api.requestOtp({ role: 'expert', purpose: 'signup', email: f.email.trim(), phone: f.phone, lang })}
            verify={async (challenge_id, code) => signIn(await api.signupExpert({
              challenge_id, code, name: f.name.trim(), phone: f.phone, lang,
              designation: f.designation, organisation: f.organisation.trim(), employee_id: f.employeeId.trim(),
              qualification: f.qualification, experience_years: Number(f.experience),
              districts: f.districts, crops: f.crops, specialities: f.specialities, languages: f.languages,
            }))}
            submitLabel={t('authCreate')}
          />
        </div>
      )}

      <div className="mt-6 flex gap-3">
        {step > 0 && <Secondary onClick={() => setStep((s) => s - 1)}>{t('back')}</Secondary>}
        {step < 3 && <Primary onClick={next}>{t('authNext')}</Primary>}
      </div>

      <p className="mt-8 text-center text-sm text-soil-dark/70">
        {t('authHaveAccount')}{' '}
        <Link to="/login?role=expert" className="text-leaf-deep font-semibold underline underline-offset-2">{t('authLogin')}</Link>
      </p>
    </div>
  )
}

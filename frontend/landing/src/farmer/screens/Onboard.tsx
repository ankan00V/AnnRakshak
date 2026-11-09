import { useState } from 'react'
import { AlertTriangle, ArrowRight, Plus } from 'lucide-react'
import { api, ApiError } from '../../api/client'
import type { CropInfo, Farm } from '../../api/types'
import WherePicker, { type Where } from '../../auth/WherePicker'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox, ListenButton } from '../../ui/kit'
import { FarmPickerSkeleton } from '../components/Skeletons'
import LanguagePicker from '../components/LanguagePicker'
import { useFarmer } from '../FarmerContext'
import { useAuth } from '../../auth/AuthContext'
import { Chips } from '../../auth/parts'
import type { Irrigation } from '../../api/types'
import type { TKey } from '../../lib/i18n'
import { SPLIT } from '../layout'
import { fieldPhoto } from '../fieldPhoto'

/** A field's title with the speaker that reads its help aloud — the same
 *  control the sign-up form uses, so one screen does not teach a farmer a
 *  button the next one contradicts. The span swallows the mousedown because
 *  this sits inside a <label>: a tap reaching it would focus the field and
 *  raise the keyboard over the help just asked for. */
function Ask({ label, say }: { label: string; say: TKey }) {
  const { t, lang } = useFarmer()
  return (
    <span className="flex items-center gap-2">
      <span className="flex-1">{label}</span>
      <span onMouseDown={(e) => e.preventDefault()}>
        <ListenButton src={`/help/${lang}/${say}.mp3`} text={t(say)} lang={lang}
          label={t('listen')} stopLabel={t('stop')} compact />
      </span>
    </span>
  )
}

const RANK: Record<string, number> = { high: 3, medium: 2, low: 1 }

/** What is standing against this field this week. Nothing is drawn when
 *  nothing is building: a row of "all clear" badges teaches the eye to skip
 *  the one place a warning would appear. Solid colours, because on a wide
 *  screen it sits on the photograph and has to read over grass. */
function Standing({ alert, className = '' }: { alert: Farm['alert']; className?: string }) {
  const { t } = useFarmer()
  if (!alert) return null
  const tone = alert.answered ? 'bg-cream text-soil-dark/60 ring-1 ring-soil-dark/10'
    : alert.level === 'high' ? 'bg-ember text-cream'
      : alert.level === 'medium' ? 'bg-ochre text-soil-dark' : 'bg-cream text-leaf-deep ring-1 ring-leaf/20'
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium leading-none shadow-sm ${tone} ${className}`}>
      {!alert.answered && alert.level === 'high' && <AlertTriangle className="w-3 h-3 shrink-0" />}
      {t(`level_${alert.level}` as TKey)} · {alert.name}
    </span>
  )
}

/** A field, shown as the field: its own crop's photograph — or the bare
 *  ground once it is harvested — with the crop and the place over it. On a
 *  phone the photograph is a thumbnail beside the words, so four fields are
 *  still one screen; from lg it is the top of a card. */
function FieldTile({ f, onOpen }: { f: Farm; onOpen: () => void }) {
  const { t } = useFarmer()
  const { me } = useAuth()
  const photo = fieldPhoto(f)
  const urgent = !!f.alert && !f.alert.answered && f.alert.level === 'high'
  const place = f.village || f.district
  // A fallow field has no stage and no age: saying "maturing, 240 days" about
  // bare ground is the bug this replaced.
  const where = f.status === 'fallow'
    ? `${t('seasonRestingShort')} · ${f.area_acres} ${t('acres')}`
    : `${f.stage_name} · ${f.das} ${t('daysOld')} · ${f.area_acres} ${t('acres')}`
  return (
    <button
      onClick={onOpen}
      className={`group w-full h-full min-h-[112px] text-left flex lg:flex-col overflow-hidden rounded-2xl lg:rounded-3xl bg-white
        ring-1 transition-[box-shadow,transform] duration-300 ease-out hover:-translate-y-0.5
        hover:shadow-[0_20px_44px_-26px_rgba(43,29,18,0.55)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-leaf ${
        urgent ? 'ring-ember/45' : 'ring-soil-dark/10'}`}
    >
      <span className="relative shrink-0 w-28 sm:w-36 lg:w-full lg:aspect-[16/9] overflow-hidden bg-leaf/10">
        {photo && (
          <img src={photo.src} alt="" loading="lazy" decoding="async"
            className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-[1.04]" />
        )}
        <span className="absolute inset-0 hidden lg:block bg-gradient-to-t from-soil-dark/75 via-soil-dark/10 to-soil-dark/5" />
        {f.is_demo && (
          <span className="absolute left-2 top-2 lg:left-3 lg:top-3 rounded-full bg-cream/95 px-2 py-0.5 text-[10px] lg:text-[11px] font-medium text-soil-dark shadow-sm">
            {t('demoFarm')}
          </span>
        )}
        <Standing alert={f.alert} className="hidden lg:inline-flex absolute right-3 top-3 max-w-[60%]" />
        <span className="absolute inset-x-0 bottom-0 hidden lg:block p-4 text-cream">
          <span className="block font-instrument-serif text-[30px] leading-none">{f.crop_name}</span>
          <span className="mt-1.5 block text-[13px] text-cream/85">{place}</span>
        </span>
      </span>

      <span className="flex min-w-0 flex-1 flex-col p-3.5 sm:p-4">
        <span className="lg:hidden block text-[15px] font-semibold leading-snug">{f.crop_name}</span>
        <span className="lg:hidden block text-xs text-soil-dark/60">{place}</span>
        <span className="mt-1 lg:mt-0 block text-[13px] leading-snug text-soil-dark/70">
          {where}
          {f.status === 'fallow' && <span className="text-soil-dark/50"> · {t('seasonFallowTag')}</span>}
        </span>
        {/* The farmer's name earns a line only when the list holds more than
            one person's fields; on your own three it is the same word. */}
        {f.farmer_name !== me?.name && (
          <span className="mt-0.5 block truncate text-[12px] text-soil-dark/50">{f.farmer_name}</span>
        )}
        <Standing alert={f.alert} className="lg:hidden mt-2 self-start" />
        <span className="mt-auto hidden lg:flex items-center justify-between pt-4 text-sm font-medium text-leaf-deep">
          {t('openLabel')}
          <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5" />
        </span>
      </span>
    </button>
  )
}

export default function Onboard() {
  const { lang, t, setFarmId, setLang } = useFarmer()
  const { me } = useAuth()
  const farms = useAsync(() => api.farms(lang), [lang], ['farms', lang].join(':'))
  const crops = useAsync(() => api.crops(lang), [lang], ['crops', lang].join(':'))
  const [adding, setAdding] = useState(false)
  const [cropFilter, setCropFilter] = useState<string | null>(null)
  // The question this screen asks is which field we are protecting today, so
  // the field with the worst week answers it first.
  const shown = (farms.data ?? [])
    .filter((f) => !cropFilter || f.crop === cropFilter)
    .slice()
    .sort((a, b) => (RANK[b.alert?.level ?? ''] ?? 0) - (RANK[a.alert?.level ?? ''] ?? 0) || a.id - b.id)
  // A crop nobody here grows is a filter that can only empty the list, and
  // four buttons over three fields is furniture.
  const grown = (crops.data ?? []).filter((c) => (farms.data ?? []).some((f) => f.crop === c.id))
  const filterable = (farms.data?.length ?? 0) > 6 && grown.length > 1

  return (
    /* Explicit cells rather than two stacked columns: on a phone the order on
       screen is the order below — greeting, language, then the fields, exactly
       as it was — while a laptop puts the language in the side rail beside the
       greeting without moving a line of it. */
    <div className={`space-y-5 ${SPLIT}`}>
      <div className="pt-2 lg:col-span-8 lg:col-start-1 lg:row-start-1">
        <h1 className="font-instrument-serif text-[2rem] lg:text-[44px] leading-[1.08] text-balance">{t('welcome')}</h1>
        <p className="mt-2 max-w-xl text-sm text-soil-dark/65 lg:text-[15px] leading-relaxed">
          {me?.is_demo ? t('welcomeSubDemo') : t('welcomeSub')}
        </p>
      </div>

      {/* The language belongs on this screen — it is the first thing a farmer
          may need to change — but not as ten tiles across a laptop, louder
          than the fields they came here to open. */}
      <section className="space-y-2.5 lg:col-span-4 lg:col-start-9 lg:row-start-1 lg:row-span-2">
        <h2 className="text-sm font-semibold text-soil-dark/80">
          {t('chooseLanguage')}
        </h2>
        <div className="lg:rounded-2xl lg:bg-white lg:border lg:border-soil-dark/10 lg:p-3">
          <LanguagePicker variant="grid" wide={false} onPick={setLang} />
        </div>
      </section>

      <div className="space-y-5 lg:col-span-8 lg:col-start-1 lg:row-start-2">
        {farms.loading && !farms.data && <FarmPickerSkeleton />}
        {farms.error && <ErrorBox error={farms.error} onRetry={farms.reload} retryLabel={t('retry')} />}

        {filterable && (
          <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-4 px-4 lg:mx-0 lg:px-0 lg:flex-wrap">
            {[{ id: null as string | null, name: 'All' }, ...grown.map((c) => ({ id: c.id as string | null, name: c.name }))].map((c) => (
              <button key={c.id ?? 'all'} onClick={() => setCropFilter(c.id)}
                className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-medium border ${cropFilter === c.id ? 'bg-leaf-deep text-cream border-leaf-deep' : 'bg-white border-soil-dark/15'}`}>
                {c.name}{c.id ? ` · ${farms.data!.filter((f) => f.crop === c.id).length}` : ''}
              </button>
            ))}
          </div>
        )}

        {farms.data && (
          /* The fields and the way to add one are the same kind of thing — a
             tile you press to get to a field — so on a laptop they belong in
             the same grid. A dashed bar ruled across the whole page under them
             was the widest, loudest thing on a screen whose job is to let you
             pick one of three farms. */
          <ul className="space-y-3 lg:space-y-0 lg:grid lg:grid-cols-2 lg:gap-5 lg:items-stretch">
            {shown.map((f: Farm) => (
              <li key={f.id} className="lg:h-full">
                <FieldTile f={f} onOpen={() => setFarmId(f.id)} />
              </li>
            ))}
            {/* The demo account is shared and its four fields are the demo.
                Offering to add one there promises something it cannot keep:
                whatever a visitor registers stays on the account for the next
                one, and it is not their field anyway. Signing up is where a
                real field goes. */}
            {!adding && !(me?.is_demo && (farms.data?.length ?? 0) > 0) && (
              <li className="lg:h-full">
                <button
                  onClick={() => setAdding(true)}
                  className="w-full h-full min-h-[56px] lg:min-h-[120px] rounded-2xl lg:rounded-3xl border-2 border-dashed border-leaf/40 text-leaf-deep text-sm font-medium flex items-center justify-center gap-2 hover:bg-leaf/5"
                >
                  <Plus className="w-4 h-4" />
                  {(farms.data?.length ?? 0) > 0 ? t('authAddField') : t('registerFarm')}
                </button>
              </li>
            )}
          </ul>
        )}

        {adding && crops.data && <RegisterForm crops={crops.data} onDone={(id) => setFarmId(id)} />}
      </div>
    </div>
  )
}

function RegisterForm({ crops, onDone }: {
  // CropInfo itself, not a hand-copied shape of it: this form asks a different
  // question for a transplanted crop, and it can only know which those are
  // from nursery_days.
  crops: CropInfo[]
  onDone: (id: number) => void
}) {
  const { lang, t } = useFarmer()
  const { me } = useAuth()
  const [name, setName] = useState(me?.name ?? '')
  const [irrigation, setIrrigation] = useState<Irrigation>('rainfed')
  const [crop, setCrop] = useState(crops[0]?.id ?? 'rice')
  const [sowing, setSowing] = useState(() => new Date(Date.now() - 60 * 864e5).toISOString().slice(0, 10))
  const [basis, setBasis] = useState<'' | 'sown' | 'transplanted'>('')
  const [where, setWhere] = useState<Where>({
    state: me?.profile?.state ?? '', district: me?.profile?.district ?? '', village: me?.profile?.village ?? '',
    taluka: me?.profile?.taluka ?? '', lat: null, lon: null, fromGps: false,
  })
  const [area, setArea] = useState('2')
  const [ph, setPh] = useState('')  // Soil Health Card pH, optional
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  /** The refusal, in the farmer's own language.
   *
   *  ErrorBox shows an error's own message, and FastAPI answers a body it
   *  cannot parse with a list of pydantic objects: what reached the farmer was
   *  `[{"type":"missing","loc":["body","lat"]...}]`, in English. The gate on
   *  Save is what keeps that body from being sent at all, so a 422 arriving
   *  here is our mistake and not something a farmer can read or act on — say
   *  the one true thing in their language, and leave the detail in the console
   *  for whoever has to fix it. A sentence the server wrote itself comes back
   *  already in `lang`, and is passed through untouched. */
  const refusal = (e: unknown): Error => {
    if (!(e instanceof ApiError)) return e instanceof Error ? e : new Error(t('notSaved'))
    if (e.status === 0) return new Error(t('offline'))
    if (e.status >= 500 || (e.status === 422 && e.message.trimStart().startsWith('['))) {
      console.error('POST /api/farms refused this field:', e.message)
      return new Error(t('notSaved'))
    }
    return e
  }

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const f = await api.createFarm({
        farmer_name: name.trim(),
        lang,
        crop,
        sowing_date: sowing,
        date_basis: basis || 'sown',
        state: where.state || null,
        district: where.district,
        // The spot, and never a missing one: JSON.stringify leaves an
        // undefined out of the body altogether, and the route has neither a
        // default for lat and lon nor the village lookup sign-up falls back
        // to. `whereBad` below is what guarantees there is a point to send.
        lat: where.lat,
        lon: where.lon,
        area_acres: parseFloat(area),
        irrigation,
        village: where.village || null,
        ...(phOk && ph ? { soil_ph: parseFloat(ph), soil_ph_on: new Date().toISOString().slice(0, 10) } : {}),
      })
      onDone(f.id)
    } catch (e) {
      setError(refusal(e))
    } finally {
      setBusy(false)
    }
  }

  const field = 'w-full min-h-[48px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm focus:outline-none focus:border-leaf'
  const selected = crops.find((c) => c.id === crop)
  const phOk = !ph || (parseFloat(ph) >= 3 && parseFloat(ph) <= 11)
  // Where the field is, which this form left out of its own gate: the three
  // faults WherePicker marks, and the spot the weather, the spray window and
  // the outbreak radius are read at. Sign-up can go without a point — there
  // the server looks the village up — but /api/farms cannot, so a farmer who
  // has not given one is told so here, beside the box that is missing it,
  // instead of being handed the server's complaint about `body.lat`.
  const whereBad = !where.state || !where.district || where.village.trim().length < 2
    || where.lat === null || where.lon === null

  return (
    <Card className="p-4 space-y-3">
      <h2 className="font-medium">{t('registerFarm')}</h2>
      <label className="block text-xs text-soil-dark/60">
        {t('farmerName')}
        <input className={field} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="block text-xs text-soil-dark/60">
          <Ask label={t('crop')} say="helpCrop" />
          <select className={field} value={crop} onChange={(e) => { setCrop(e.target.value); setBasis('') }}>
            {crops.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <label className="block text-xs text-soil-dark/60">
          <Ask label={t('area')} say="helpArea" />
          <input className={field} type="number" inputMode="decimal" min="0.1" step="0.1" value={area}
            onChange={(e) => setArea(e.target.value)} />
        </label>
      </div>
      {selected && !selected.photo_diagnosis && (
        <p className="text-xs rounded-xl bg-sky-50 text-sky-800 p-2.5">{t('photoLater')}</p>
      )}
      {!!selected?.nursery_days && (
        <div className="text-xs text-soil-dark/60">
          <p className="mb-1"><Ask label={t('dateBasisAsk')} say="dateBasisWhy" /></p>
          <Chips columns={2} value={basis ? [basis] : []} onChange={([v]) => setBasis(v)}
            options={[{ id: 'sown' as const, label: t('dateBasisSown') },
                      { id: 'transplanted' as const, label: t('dateBasisTransplanted') }]} />
          <p className="mt-1 text-[11px] text-soil-dark/45">{t('dateBasisWhy')}</p>
        </div>
      )}
      <label className="block text-xs text-soil-dark/60">
        {selected?.nursery_days
          ? (basis === 'transplanted' ? t('transplantDate') : t('sowingDateOnly'))
          : <Ask label={t('sowingDateOnly')} say="helpSowing" />}
        <input className={field} type="date" value={sowing} onChange={(e) => setSowing(e.target.value)} />
      </label>
      {/* The picker is the only place this form asks where the field is. A
          second location button below used to set coordinates it could not
          see, and no state, district or village with them, so the question
          looked answered while the body went up without the names. Sign-up
          reveals these faults on the way to its next step; this form has one
          button and it is disabled while anything is missing, so they have to
          be on screen before the farmer presses anything. */}
      <WherePicker value={where} onChange={setWhere} showErrors needPoint />
      <div className="text-xs text-soil-dark/60">
        <p className="mb-1"><Ask label={t('authIrrigation')} say="helpIrrigation" /></p>
        <Chips columns={2} value={[irrigation]} onChange={([v]) => setIrrigation(v)}
          options={(['rainfed', 'canal', 'borewell', 'open_well', 'farm_pond', 'drip', 'sprinkler'] as const).map((id) => ({ id, label: t(`irr_${id}`) }))} />
      </div>
      <label className="block text-xs text-soil-dark/60">
        <Ask label={t('soilPhCard')} say="helpSoilPh" />
        <input className={field} type="number" inputMode="decimal" min="3" max="11" step="0.1" value={ph}
          placeholder="6.8" onChange={(e) => setPh(e.target.value)} />
        <span className="block mt-1 text-[11px] text-soil-dark/45">{t('soilPhCardHint')}</span>
      </label>
      {error && <ErrorBox error={error} />}
      {whereBad && <p className="text-[12px] text-soil-dark/60 leading-snug">{t('authNeedWhere')}</p>}
      <button
        onClick={submit}
        disabled={busy || !name.trim() || !(parseFloat(area) > 0) || !phOk || whereBad
          || (!!selected?.nursery_days && !basis)}
        className="w-full min-h-[48px] rounded-full bg-leaf-deep text-cream text-sm font-medium disabled:opacity-50"
      >
        {t('save')}
      </button>
    </Card>
  )
}

import { useState } from 'react'
import { AlertTriangle, ChevronRight, LocateFixed, Plus, Sprout } from 'lucide-react'
import { api } from '../../api/client'
import type { CropInfo, Farm } from '../../api/types'
import WherePicker, { type Where } from '../../auth/WherePicker'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox, ListenButton, Pill } from '../../ui/kit'
import { FarmPickerSkeleton } from '../components/Skeletons'
import LanguagePicker from '../components/LanguagePicker'
import { useFarmer } from '../FarmerContext'
import { useAuth } from '../../auth/AuthContext'
import { Chips } from '../../auth/parts'
import type { Irrigation } from '../../api/types'
import type { TKey } from '../../lib/i18n'
import { SPLIT } from '../layout'

const CROP_TINT: Record<string, string> = {
  rice: 'bg-leaf/15 text-leaf-deep',
  maize: 'bg-ochre/20 text-[#8a5a17]',
  cotton: 'bg-sky-100 text-sky-800',
  soybean: 'bg-lime-100 text-lime-800',
}

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
 *  the one place a warning would appear. */
function Standing({ alert }: { alert: Farm['alert'] }) {
  const { t } = useFarmer()
  if (!alert) return null
  const tone = alert.answered ? 'bg-soil-dark/5 text-soil-dark/55'
    : alert.level === 'high' ? 'bg-ember/10 text-ember'
      : alert.level === 'medium' ? 'bg-ochre/15 text-[#8a5a17]' : 'bg-leaf/10 text-leaf-deep'
  return (
    <span className={`mt-1.5 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}>
      {!alert.answered && alert.level === 'high' && <AlertTriangle className="w-3 h-3 shrink-0" />}
      {t(`level_${alert.level}` as TKey)} · {alert.name}
    </span>
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
        <Sprout className="w-8 h-8 text-leaf" />
        <h1 className="mt-2 font-instrument-serif text-3xl lg:text-[40px] leading-tight">{t('welcome')}</h1>
        <p className="mt-1 text-sm text-soil-dark/60 lg:text-[15px]">{t('welcomeSub')}</p>
      </div>

      {/* The language belongs on this screen — it is the first thing a farmer
          may need to change — but not as ten tiles across a laptop, louder
          than the fields they came here to open. */}
      <section className="space-y-2.5 lg:col-span-4 lg:col-start-9 lg:row-start-1 lg:row-span-2">
        <h2 className="text-sm font-semibold lg:text-[11px] lg:uppercase lg:tracking-[0.12em] lg:text-soil-dark/45">
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
          <ul className="space-y-2 lg:space-y-0 lg:grid lg:grid-cols-2 lg:gap-3 lg:items-stretch">
            {shown.map((f: Farm) => (
              <li key={f.id} className="lg:h-full">
                <button
                  onClick={() => setFarmId(f.id)}
                  className={`w-full h-full text-left flex items-start gap-3 rounded-2xl bg-white border p-3 lg:p-4 transition-all hover:shadow-[0_10px_24px_-18px_rgba(43,29,18,0.5)] ${
                    f.alert && !f.alert.answered && f.alert.level === 'high'
                      ? 'border-ember/40 hover:border-ember/70' : 'border-soil-dark/10 hover:border-leaf/50'}`}
                >
                  <span className={`shrink-0 w-11 h-11 lg:w-12 lg:h-12 rounded-xl flex items-center justify-center text-xs font-semibold ${CROP_TINT[f.crop] ?? ''}`}>
                    {f.crop_name.slice(0, 2)}
                  </span>
                  <span className="flex-1 min-w-0">
                    {/* What tells this field apart from the one beside it: the
                        crop and the place. The farmer's own name was the
                        headline on every card, which on your own three fields
                        is the same word three times. It earns the line only
                        when the list holds more than one person's fields. */}
                    <span className="block text-sm lg:text-[15px] font-medium truncate lg:whitespace-normal lg:leading-snug">
                      {f.crop_name} · {f.village || f.district}
                      {f.status === 'fallow' && <span className="font-normal text-soil-dark/45"> · {t('seasonFallowTag')}</span>}
                    </span>
                    <span className="block text-xs text-soil-dark/60 truncate lg:whitespace-normal lg:leading-snug">
                      {/* A fallow field has no stage and no age: saying "maturing,
                          240 days" about bare ground is the bug this replaced. */}
                      {f.status === 'fallow'
                        ? `${t('seasonRestingShort')} · ${f.area_acres} ${t('acres')}`
                        : `${f.stage_name} · ${f.das} ${t('daysOld')} · ${f.area_acres} ${t('acres')}`}
                    </span>
                    {f.farmer_name !== me?.name && (
                      <span className="block text-[11px] text-soil-dark/45 truncate">{f.farmer_name}</span>
                    )}
                    <Standing alert={f.alert} />
                  </span>
                  <span className="flex items-center gap-1.5 shrink-0">
                    {f.is_demo && <Pill>{t('demoFarm')}</Pill>}
                    <ChevronRight className="w-4 h-4 text-soil-dark/40" />
                  </span>
                </button>
              </li>
            ))}
            {!adding && (
              <li className="lg:h-full">
                <button
                  onClick={() => setAdding(true)}
                  className="w-full h-full min-h-[52px] lg:min-h-[84px] rounded-2xl border-2 border-dashed border-leaf/40 text-leaf-deep text-sm font-medium flex items-center justify-center gap-2 hover:bg-leaf/5"
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
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null)
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  const locate = () => {
    if (!navigator.geolocation) return
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setCoords({ lat: p.coords.latitude, lon: p.coords.longitude })
        setLocating(false)
      },
      () => setLocating(false),
      { timeout: 10000 },
    )
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
        lat: where.lat ?? coords?.lat,
        lon: where.lon ?? coords?.lon,
        area_acres: parseFloat(area),
        irrigation,
        village: where.village || null,
        ...(phOk && ph ? { soil_ph: parseFloat(ph), soil_ph_on: new Date().toISOString().slice(0, 10) } : {}),
      })
      onDone(f.id)
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  const field = 'w-full min-h-[48px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm focus:outline-none focus:border-leaf'
  const selected = crops.find((c) => c.id === crop)
  const phOk = !ph || (parseFloat(ph) >= 3 && parseFloat(ph) <= 11)

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
      <WherePicker value={where} onChange={setWhere} />
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
      <button type="button" onClick={locate}
        className="flex items-center gap-2 text-sm text-leaf-deep font-medium min-h-[40px]">
        <LocateFixed className="w-4 h-4" />
        {locating ? t('locating') : coords ? `${t('locationSet')} (${coords.lat.toFixed(3)}, ${coords.lon.toFixed(3)})` : t('useLocation')}
      </button>
      {error && <ErrorBox error={error} />}
      <button
        onClick={submit}
        disabled={busy || !name.trim() || !(parseFloat(area) > 0) || !phOk || (!!selected?.nursery_days && !basis)}
        className="w-full min-h-[48px] rounded-full bg-leaf-deep text-cream text-sm font-medium disabled:opacity-50"
      >
        {t('save')}
      </button>
    </Card>
  )
}

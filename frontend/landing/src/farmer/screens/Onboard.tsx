import { useState } from 'react'
import { ChevronRight, LocateFixed, Plus, Sprout } from 'lucide-react'
import { api } from '../../api/client'
import type { Farm } from '../../api/types'
import WherePicker, { type Where } from '../../auth/WherePicker'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox, Pill, Spinner } from '../../ui/kit'
import LanguagePicker from '../components/LanguagePicker'
import { useFarmer } from '../FarmerContext'
import { useAuth } from '../../auth/AuthContext'
import { Chips } from '../../auth/parts'
import type { Irrigation } from '../../api/types'

const CROP_TINT: Record<string, string> = {
  rice: 'bg-leaf/15 text-leaf-deep',
  maize: 'bg-ochre/20 text-[#8a5a17]',
  cotton: 'bg-sky-100 text-sky-800',
  soybean: 'bg-lime-100 text-lime-800',
}

export default function Onboard() {
  const { lang, t, setFarmId, setLang } = useFarmer()
  const farms = useAsync(() => api.farms(lang), [lang], ['farms', lang].join(':'))
  const crops = useAsync(() => api.crops(lang), [lang], ['crops', lang].join(':'))
  const [adding, setAdding] = useState(false)
  const [cropFilter, setCropFilter] = useState<string | null>(null)
  const shown = (farms.data ?? []).filter((f) => !cropFilter || f.crop === cropFilter)

  return (
    <div className="space-y-5">
      <div className="pt-2">
        <Sprout className="w-8 h-8 text-leaf" />
        <h1 className="mt-2 font-instrument-serif text-3xl leading-tight">{t('welcome')}</h1>
        <p className="mt-1 text-sm text-soil-dark/60">{t('welcomeSub')}</p>
      </div>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">{t('chooseLanguage')}</h2>
        <LanguagePicker variant="grid" onPick={setLang} />
      </section>

      {farms.loading && !farms.data && <Spinner />}
      {farms.error && <ErrorBox error={farms.error} onRetry={farms.reload} retryLabel={t('retry')} />}

      {crops.data && farms.data && (
        <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-4 px-4">
          {[{ id: null as string | null, name: 'All' }, ...crops.data.map((c) => ({ id: c.id as string | null, name: c.name }))].map((c) => (
            <button key={c.id ?? 'all'} onClick={() => setCropFilter(c.id)}
              className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-medium border ${cropFilter === c.id ? 'bg-leaf-deep text-cream border-leaf-deep' : 'bg-white border-soil-dark/15'}`}>
              {c.name}{c.id ? ` · ${farms.data!.filter((f) => f.crop === c.id).length}` : ''}
            </button>
          ))}
        </div>
      )}

      {farms.data && (
        <ul className="space-y-2 lg:space-y-0 lg:grid lg:grid-cols-2 lg:gap-3">
          {shown.map((f: Farm) => (
            <li key={f.id}>
              <button
                onClick={() => setFarmId(f.id)}
                className="w-full text-left flex items-center gap-3 rounded-2xl bg-white border border-soil-dark/10 p-3 hover:border-leaf/50 transition-colors"
              >
                <span className={`shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-xs font-semibold ${CROP_TINT[f.crop] ?? ''}`}>
                  {f.crop_name.slice(0, 2)}
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-medium truncate">{f.farmer_name}</span>
                  <span className="block text-xs text-soil-dark/60 truncate">
                    {f.crop_name} · {f.district} · {f.stage_name} ({f.das} {t('daysOld')})
                  </span>
                </span>
                {f.is_demo && <Pill>{t('demoFarm')}</Pill>}
                <ChevronRight className="w-4 h-4 text-soil-dark/40" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {!adding ? (
        <button
          onClick={() => setAdding(true)}
          className="w-full min-h-[52px] rounded-2xl border-2 border-dashed border-leaf/40 text-leaf-deep text-sm font-medium flex items-center justify-center gap-2 hover:bg-leaf/5"
        >
          <Plus className="w-4 h-4" />
          {(farms.data?.length ?? 0) > 0 ? t('authAddField') : t('registerFarm')}
        </button>
      ) : (
        crops.data && <RegisterForm crops={crops.data} onDone={(id) => setFarmId(id)} />
      )}
    </div>
  )
}

function RegisterForm({ crops, onDone }: {
  crops: { id: string; name: string; photo_diagnosis: boolean }[]
  onDone: (id: number) => void
}) {
  const { lang, t } = useFarmer()
  const { me } = useAuth()
  const [name, setName] = useState(me?.name ?? '')
  const [irrigation, setIrrigation] = useState<Irrigation>('rainfed')
  const [crop, setCrop] = useState(crops[0]?.id ?? 'rice')
  const [sowing, setSowing] = useState(() => new Date(Date.now() - 60 * 864e5).toISOString().slice(0, 10))
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
          {t('crop')}
          <select className={field} value={crop} onChange={(e) => setCrop(e.target.value)}>
            {crops.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <label className="block text-xs text-soil-dark/60">
          {t('area')}
          <input className={field} type="number" inputMode="decimal" min="0.1" step="0.1" value={area}
            onChange={(e) => setArea(e.target.value)} />
        </label>
      </div>
      {selected && !selected.photo_diagnosis && (
        <p className="text-xs rounded-xl bg-sky-50 text-sky-800 p-2.5">{t('photoLater')}</p>
      )}
      <label className="block text-xs text-soil-dark/60">
        {t('sowingDate')}
        <input className={field} type="date" value={sowing} onChange={(e) => setSowing(e.target.value)} />
      </label>
      <WherePicker value={where} onChange={setWhere} />
      <div className="text-xs text-soil-dark/60">
        <p className="mb-1">{t('authIrrigation')}</p>
        <Chips columns={2} value={[irrigation]} onChange={([v]) => setIrrigation(v)}
          options={(['rainfed', 'canal', 'borewell', 'open_well', 'farm_pond', 'drip', 'sprinkler'] as const).map((id) => ({ id, label: t(`irr_${id}`) }))} />
      </div>
      <label className="block text-xs text-soil-dark/60">
        {t('soilPhCard')}
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
        disabled={busy || !name.trim() || !(parseFloat(area) > 0) || !phOk}
        className="w-full min-h-[48px] rounded-full bg-leaf-deep text-cream text-sm font-medium disabled:opacity-50"
      >
        {t('save')}
      </button>
    </Card>
  )
}

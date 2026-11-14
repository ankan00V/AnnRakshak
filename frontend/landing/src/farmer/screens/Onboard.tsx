import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AlertTriangle, ArrowRight, Languages, Plus, Tractor } from 'lucide-react'
import { api, ApiError } from '../../api/client'
import type { CropInfo, Farm } from '../../api/types'
import WherePicker, { type Where } from '../../auth/WherePicker'
import { useAsync } from '../../lib/hooks'
import { ErrorBox, ListenButton } from '../../ui/kit'
import { FarmPickerSkeleton } from '../components/Skeletons'
import LanguagePicker from '../components/LanguagePicker'
import { useFarmer } from '../FarmerContext'
import { useAuth } from '../../auth/AuthContext'
import { Chips } from '../../auth/parts'
import type { Irrigation } from '../../api/types'
import type { TKey } from '../../lib/i18n'
import { FIELD, LABEL, PANEL, PRIMARY } from '../tokens'
import { PanelHead, PhotoCurve, hideBroken } from '../ui'
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
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-medium leading-none shadow-sm ${tone} ${className}`}>
      {!alert.answered && alert.level === 'high' && <AlertTriangle className="h-3.5 w-3.5 shrink-0" />}
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
      className={`group flex h-full min-h-[120px] w-full gap-1 overflow-hidden rounded-[24px] bg-white p-2 text-left
        shadow-[0_10px_30px_-18px_rgba(43,29,18,0.35)] ring-1 transition-[box-shadow,transform] duration-300 ease-out hover:-translate-y-0.5
        hover:shadow-[0_20px_44px_-26px_rgba(43,29,18,0.55)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-leaf lg:flex-col lg:rounded-[28px] ${
        urgent ? 'ring-ember/45' : 'ring-soil-dark/[0.06]'}`}
    >
      <span className="relative w-28 shrink-0 overflow-hidden rounded-[18px] bg-[#e3efd9] sm:w-36 lg:aspect-[16/9] lg:w-full lg:rounded-[22px]">
        {photo && (
          <img onError={hideBroken} src={photo.src} srcSet={photo.srcSet || undefined} alt="" loading="lazy" decoding="async"
            sizes="(min-width: 1024px) 420px, 144px" width={photo.width} height={photo.height}
            className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-[1.04]" />
        )}
        <span className="absolute inset-0 hidden bg-gradient-to-t from-black/65 via-black/10 to-transparent lg:block" />
        {f.is_demo && (
          <span className="absolute left-2 top-2 lg:left-3 lg:top-3 rounded-full bg-white/95 px-2.5 py-0.5 text-[12px] font-medium text-soil-dark shadow-sm">
            {t('demoFarm')}
          </span>
        )}
        <Standing alert={f.alert} className="hidden lg:inline-flex absolute right-3 top-3 max-w-[60%]" />
        <span className="absolute inset-x-0 bottom-0 hidden p-4 text-white lg:block">
          <span className="block font-instrument-serif text-[34px] leading-none drop-shadow-sm">{f.crop_name}</span>
          <span className="mt-1.5 block text-[15px] drop-shadow">{place}</span>
        </span>
      </span>

      <span className="flex min-w-0 flex-1 flex-col p-2.5 sm:p-3 lg:px-3 lg:pb-3 lg:pt-2">
        <span className="block text-[17px] font-semibold leading-snug lg:hidden">{f.crop_name}</span>
        <span className="block text-[14px] text-soil-dark/75 lg:hidden">{place}</span>
        <span className="mt-1 block text-[14px] leading-snug text-soil-dark/80 lg:mt-0">
          {where}
          {f.status === 'fallow' && <span className="text-soil-dark/70"> · {t('seasonFallowTag')}</span>}
        </span>
        {/* The farmer's name earns a line only when the list holds more than
            one person's fields; on your own three it is the same word. */}
        {f.farmer_name !== me?.name && (
          <span className="mt-0.5 block truncate text-[13px] text-soil-dark/70">{f.farmer_name}</span>
        )}
        <Standing alert={f.alert} className="lg:hidden mt-2 self-start" />
        <span className="mt-auto hidden items-center justify-between pt-4 text-[15px] font-semibold text-leaf-deep lg:flex">
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
  const navigate = useNavigate()
  const { pathname } = useLocation()
  // Opened from the sidebar's "My fields" the list is its own page: picking a
  // field takes the farmer to it. Before any field is chosen this is Home.
  const inApp = pathname === '/app/fields'
  const open = (id: number) => {
    setFarmId(id)
    if (pathname !== '/app' && pathname !== '/app/') navigate('/app')
  }
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
    <div className={`grid gap-6 pt-2 ${inApp ? '' : 'lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_380px]'}`}>
      <div className="min-w-0 space-y-6">
        <section className={`${PANEL} p-2`}>
          {/* The height follows the words: at 360 px the welcome runs to three
              lines in English and more in Tamil, and a fixed height cut its
              first line off under the top of the photo. */}
          <div className="relative overflow-hidden rounded-[22px] bg-leaf-deep">
            <img onError={hideBroken} src="/photos/landscape.webp" alt="" width={934} height={442}
              className="absolute inset-0 h-full w-full object-cover object-[center_45%]" />
            <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/65 via-black/25 to-black/5" />
            <div className="relative flex min-h-[200px] flex-col justify-end p-5 pb-8 pt-10 text-white sm:min-h-[230px] lg:p-6 lg:pb-9">
              <h1 className="font-instrument-serif text-[30px] leading-[1.05] drop-shadow-sm text-balance sm:text-[34px] lg:text-[46px]">{t('welcome')}</h1>
              <p className="mt-2 max-w-xl text-[15px] leading-relaxed drop-shadow lg:text-[16px]">
                {me?.is_demo && (farms.data?.length ?? 0) > 0 ? t('welcomeSubDemo') : t('welcomeSub')}
              </p>
            </div>
            <PhotoCurve />
          </div>
        </section>

        {farms.loading && !farms.data && <FarmPickerSkeleton />}
        {farms.error && <ErrorBox offlineLabel={t('offline')} error={farms.error} onRetry={farms.reload} retryLabel={t('retry')} />}

        {filterable && (
          <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 lg:mx-0 lg:flex-wrap lg:px-0">
            {[{ id: null as string | null, name: t('allCrops') }, ...grown.map((c) => ({ id: c.id as string | null, name: c.name }))].map((c) => (
              <button key={c.id ?? 'all'} onClick={() => setCropFilter(c.id)}
                className={`min-h-[40px] shrink-0 rounded-full px-4 text-[14px] font-medium ring-1 ${cropFilter === c.id ? 'bg-[#2f6a39] text-white ring-[#2f6a39]' : 'bg-white ring-soil-dark/15'}`}>
                {c.name}{c.id ? ` · ${farms.data!.filter((f) => f.crop === c.id).length}` : ''}
              </button>
            ))}
          </div>
        )}

        {farms.data && (
          /* The fields and the way to add one are the same kind of thing — a
             tile you press to get to a field — so on a laptop they belong in
             the same grid. */
          <ul className={`space-y-3 lg:grid lg:items-stretch lg:gap-5 lg:space-y-0 ${inApp ? 'lg:grid-cols-3' : 'lg:grid-cols-2'}`}>
            {shown.map((f: Farm) => (
              <li key={f.id} className="lg:h-full">
                <FieldTile f={f} onOpen={() => open(f.id)} />
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
                  className="flex h-full min-h-[64px] w-full items-center justify-center gap-2 rounded-[24px] border-2 border-dashed border-[#4b8b3b]/40 bg-white/60 text-[16px] font-semibold text-leaf-deep hover:bg-[#eef3e6] lg:min-h-[140px] lg:rounded-[28px]"
                >
                  <Plus className="h-5 w-5" />
                  {(farms.data?.length ?? 0) > 0 ? t('authAddField') : t('registerFarm')}
                </button>
              </li>
            )}
          </ul>
        )}

        {adding && crops.data && <RegisterForm crops={crops.data} onDone={open} />}
      </div>

      {/* Before a field is chosen the language belongs on this screen — it is
          the first thing a farmer may need to change. Opened from "My fields"
          inside the app, the language menu is already in the top bar. */}
      {!inApp && <aside className="min-w-0">
        <section className={`${PANEL} p-5 lg:sticky lg:top-6`}>
          <PanelHead icon={Languages} title={t('chooseLanguage')} />
          <div className="mt-4">
            <LanguagePicker variant="grid" wide={false} onPick={setLang} />
          </div>
        </section>
      </aside>}
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
    <section className={`${PANEL} space-y-4 p-5 lg:p-6`}>
      <PanelHead icon={Tractor} title={t('registerFarm')} />
      <label className={LABEL}>
        {t('farmerName')}
        <input className={FIELD} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {/* One above the other on a narrow phone: side by side at 360 px the
          crop box cut "Rice (paddy)" to "Rice (padd". */}
      <div className="grid gap-3 min-[400px]:grid-cols-2">
        <label className={LABEL}>
          <Ask label={t('crop')} say="helpCrop" />
          <select className={FIELD} value={crop} onChange={(e) => { setCrop(e.target.value); setBasis('') }}>
            {crops.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <label className={LABEL}>
          <Ask label={t('area')} say="helpArea" />
          <input className={FIELD} type="number" inputMode="decimal" min="0.1" step="0.1" value={area}
            onChange={(e) => setArea(e.target.value)} />
        </label>
      </div>
      {selected && !selected.photo_diagnosis && (
        <p className="rounded-[18px] bg-sky-50 p-3.5 text-[14px] text-sky-950/85">{t('photoLater')}</p>
      )}
      {!!selected?.nursery_days && (
        <div className={LABEL}>
          <p className="mb-1.5"><Ask label={t('dateBasisAsk')} say="dateBasisWhy" /></p>
          <Chips columns={2} value={basis ? [basis] : []} onChange={([v]) => setBasis(v)}
            options={[{ id: 'sown' as const, label: t('dateBasisSown') },
                      { id: 'transplanted' as const, label: t('dateBasisTransplanted') }]} />
          <p className="mt-1.5 text-[13px] font-normal text-soil-dark/70">{t('dateBasisWhy')}</p>
        </div>
      )}
      <label className={LABEL}>
        {selected?.nursery_days
          ? (basis === 'transplanted' ? t('transplantDate') : t('sowingDateOnly'))
          : <Ask label={t('sowingDateOnly')} say="helpSowing" />}
        <input className={FIELD} type="date" value={sowing} onChange={(e) => setSowing(e.target.value)} />
      </label>
      {/* The picker is the only place this form asks where the field is. A
          second location button below used to set coordinates it could not
          see, and no state, district or village with them, so the question
          looked answered while the body went up without the names. Sign-up
          reveals these faults on the way to its next step; this form has one
          button and it is disabled while anything is missing, so they have to
          be on screen before the farmer presses anything. */}
      <WherePicker value={where} onChange={setWhere} showErrors needPoint />
      <div className={LABEL}>
        <p className="mb-1.5"><Ask label={t('authIrrigation')} say="helpIrrigation" /></p>
        <Chips columns={2} value={[irrigation]} onChange={([v]) => setIrrigation(v)}
          options={(['rainfed', 'canal', 'borewell', 'open_well', 'farm_pond', 'drip', 'sprinkler'] as const).map((id) => ({ id, label: t(`irr_${id}`) }))} />
      </div>
      <label className={LABEL}>
        <Ask label={t('soilPhCard')} say="helpSoilPh" />
        <input className={FIELD} type="number" inputMode="decimal" min="3" max="11" step="0.1" value={ph}
          placeholder="6.8" onChange={(e) => setPh(e.target.value)} />
        <span className="mt-1 block text-[13px] font-normal text-soil-dark/70">{t('soilPhCardHint')}</span>
      </label>
      {error && <ErrorBox offlineLabel={t('offline')} error={error} />}
      {whereBad && <p className="text-[14px] leading-snug text-soil-dark/75">{t('authNeedWhere')}</p>}
      <button
        onClick={submit}
        disabled={busy || !name.trim() || !(parseFloat(area) > 0) || !phOk || whereBad
          || (!!selected?.nursery_days && !basis)}
        className={PRIMARY}
      >
        {t('save')}
      </button>
    </section>
  )
}

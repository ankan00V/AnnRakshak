import { useState } from 'react'
import {
  AlertTriangle, ArrowRight, BookOpen, Bug, CalendarCheck, CalendarDays, Camera, Check, ChevronDown, ChevronRight,
  Clock, CloudRain, Droplet, Droplets, FlaskConical, Leaf, Loader2, MapPin, ShieldCheck, Sparkles, Video, Wheat, Wind,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import ReportSheet from '../components/ReportSheet'
import type { AlertView, CropInfo, Farm, Lang, ProblemView, WeatherView } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { bcp47 } from '../../lib/i18n'
import { useReadOnlyFarm } from '../components/DemoNotice'
import SeasonSwitch from '../components/SeasonSwitch'
import { fieldPhoto } from '../fieldPhoto'
import { Card, ErrorBox } from '../../ui/kit'
import { HomeSkeleton } from '../components/Skeletons'
import LastKnown from '../components/LastKnown'
import LocationAsk from '../components/LocationAsk'
import ProblemRow from '../components/ProblemRow'
import { askKrishi } from '../../krishi/bus'
import { PestPhoto, PhotoCurve, SkyIcon } from '../ui'
import { PANEL, RISK, wmoKey } from '../tokens'
import { TourButton } from '../tour/Tour'
import { useFarmer } from '../FarmerContext'

export default function Home() {
  const { farmId, lang, t } = useFarmer()
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  const crops = useAsync(() => api.crops(lang), [lang], ['crops', lang].join(':'))
  // The same request, and the same cache entry, as the weather screen's.
  const weather = useAsync(() => api.weather(farmId!, lang), [farmId, lang], ['weather', farmId!, lang].join(':'))

  if (home.loading && !home.data) return <HomeSkeleton />
  // Only with nothing at all to show does the error become the screen. Where
  // this phone kept the last home payload the farmer gets their own field back
  // and the error is one line above it, which in a place with no signal is
  // worth more to them than a page that is empty but correct.
  if (home.error && !home.data) return <ErrorBox error={home.error} onRetry={home.reload} retryLabel={t('retry')} />
  const d = home.data!
  const w = weather.data
  const lastKnown = home.error ? <LastKnown at={home.savedAt} onRetry={home.reload} /> : null
  const crop = crops.data?.find((c) => c.id === d.farm.crop)
  const openAlerts = d.alerts.filter((a) => a.outcome === null || a.outcome === 'snoozed')
  const waiting = d.problems.filter((p) => p.case?.status === 'open').length
  const due = d.followups_due

  // The field's own lifecycle: close the season when the crop comes off, and
  // start the next one here rather than registering the plot again.
  const season = (
    <SeasonSwitch farm={d.farm} crops={crops.data ?? null} onChange={() => home.reload()} />
  )
  const location = <LocationAsk farm={d.farm} onUpdated={(farm) => home.setData({ ...d, farm })} />

  // A harvested field gets its own screen rather than the working one with
  // the contents removed. The crop is off: there is nothing to do today, and
  // a screen that still looks like a working one invites the farmer to look
  // for something that is not there. One statement, one way forward.
  if (d.farm.status === 'fallow') {
    return (
      <div className="max-w-2xl mx-auto space-y-5">
        {lastKnown}
        <Card className="overflow-hidden p-0 bg-soil-dark text-cream border-0">
          {/* A cut paddy field, straw still lying in windrows. The state this
              screen is describing, for a farmer who reads little — the picture
              says "harvested" before the sentence does. Illustration, not a
              photograph of this particular plot. */}
          <div className="relative h-[140px] md:h-[170px]">
            <img src={fieldPhoto(d.farm)?.src ?? ''} alt="" width={1280} height={430} loading="lazy"
              className="w-full h-full object-cover" />
            <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-soil-dark via-soil-dark/45 to-soil-dark/10" />
          </div>
          <div className="relative -mt-8 p-5 md:p-7">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-ochre/20 px-2.5 py-1 text-[11px] font-semibold text-ochre">
              <Wheat className="w-3.5 h-3.5" /> {t('seasonRestingShort')}
            </span>
            <h1 className="mt-3 font-instrument-serif text-3xl leading-tight">{t('harvestedTitle')}</h1>
            <p className="mt-2 text-sm font-light leading-relaxed text-cream/75 text-pretty">
              {t('harvestedBody').replace('{on}', d.farm.harvested_on ?? '')}
            </p>
          </div>
        </Card>
        {season}
        <Link to="/app/history" className="block text-center text-sm font-medium text-leaf-deep">
          {t('harvestedHistory')} →
        </Link>
      </div>
    )
  }

  const stageName = crop?.stages.find((s) => s.key === d.farm.stage)?.name ?? d.farm.stage_name
  const attention = waiting > 0 || openAlerts.some((a) => a.level === 'high')
  const recent = d.problems.filter((p) => p.gate_outcome !== 'retake')

  return (
    <div className="space-y-6">
      {lastKnown}
      {location}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-6 min-w-0">
          <FieldCard farm={d.farm} stages={crop?.stages ?? []} attention={attention} />
          {due.length > 0 && (
            <section className="space-y-3">
              {due.slice(0, 2).map((f) => (
                <FollowUp key={f.id} id={f.id} name={f.name} dueOn={f.due_on} onDone={home.reload} />
              ))}
            </section>
          )}
          <QuickActions />
          <div className="lg:hidden"><WeatherPanel v={w} loading={weather.loading && !w} /></div>
          <FieldChecks alerts={openAlerts} stage={stageName} />
          {d.model.is_stub && (
            <p className="flex items-center gap-1.5 text-xs text-soil-dark/70">
              <Sparkles className="w-3.5 h-3.5" aria-hidden /> {t('demoModel')}
            </p>
          )}
        </div>
        <aside className="space-y-6 min-w-0">
          <div className="hidden lg:block"><WeatherPanel v={w} loading={weather.loading && !w} /></div>
          <SeasonCard farm={d.farm} />
          <RecentProblems problems={recent} />
          {season}
          <div className="lg:hidden"><TourButton variant="row" /></div>
        </aside>
      </div>
    </div>
  )
}

/** The field: its photograph, its name and age, how it is doing, and where it
 *  is in its season. */
function FieldCard({ farm, stages, attention }: { farm: Farm; stages: CropInfo['stages']; attention: boolean }) {
  const { t } = useFarmer()
  const navigate = useNavigate()
  const photo = fieldPhoto(farm)
  const track = stages.slice(0, -1)   // the last stage is the harvest itself
  const at = track.findIndex((s) => s.key === farm.stage)
  const now = at === -1 ? (farm.das > (track.at(-1)?.das[1] ?? 0) ? track.length : -1) : at
  return (
    <section data-tour="farm" className={`${PANEL} p-2`}>
      <div className="relative h-[230px] overflow-hidden rounded-[22px] bg-leaf-deep lg:h-[250px]">
        {photo && <img src={photo.src} alt="" width={1444} height={570} className="absolute inset-0 h-full w-full object-cover object-[center_70%]" />}
        <div aria-hidden className="absolute inset-0 bg-gradient-to-r from-black/55 via-black/25 to-transparent" />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/45 via-transparent to-black/20" />
        <div className="relative flex h-full flex-col justify-between p-5 text-white lg:p-6">
          <div className="flex items-start justify-between gap-3">
            {/* The place is also where a farmer with two fields changes field. */}
            <button onClick={() => navigate('/app/fields')} aria-label={t('switchFarm')}
              className="flex min-w-0 items-center gap-1.5 whitespace-nowrap text-[14px] font-medium drop-shadow sm:text-[15px]">
              <MapPin className="h-4 w-4" aria-hidden />
              {farm.village || farm.district} • {farm.area_acres} {t('acres')}
              <ChevronDown className="h-4 w-4 opacity-80" aria-hidden />
            </button>
            <span className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1 text-[13px] font-semibold shadow-sm sm:px-3.5 sm:py-1.5 sm:text-[14px] ${
              attention ? 'bg-white text-[#8a5a17]' : 'bg-white text-leaf-deep'}`}>
              {attention ? <AlertTriangle className="h-4 w-4 text-ochre" aria-hidden /> : <Leaf className="h-4 w-4 text-[#4b8b3b]" aria-hidden />}
              {attention ? t('statusAttention') : t('statusHealthy')}
            </span>
          </div>
          <div className="pb-3">
            <h2 className="font-instrument-serif text-[42px] leading-none drop-shadow-sm lg:text-[52px]">{farm.crop_name}</h2>
            <p className="mt-2 text-[17px] drop-shadow"><span className="text-[26px] font-semibold tabular-nums">{farm.das}</span> {t('daysOld')}</p>
          </div>
        </div>
        <PhotoCurve />
      </div>
      {track.length > 0 && (
        <div className="px-3 pb-4 pt-2 sm:px-6">
          <ol className="relative flex items-start justify-between">
            <span aria-hidden className="absolute left-[10%] right-[10%] top-[13px] h-[3px] rounded-full bg-soil-dark/10" />
            <span aria-hidden className="absolute left-[10%] top-[13px] h-[3px] rounded-full bg-[#4b8b3b]"
              style={{ width: `${Math.max(0, Math.min(1, now / Math.max(1, track.length - 1))) * 80}%` }} />
            {track.map((s, i) => {
              const done = i < now
              const here = i === now
              return (
                <li key={s.key} className="relative flex w-1/5 flex-col items-center text-center" aria-current={here ? 'step' : undefined}>
                  <span className={`flex h-7 w-7 items-center justify-center rounded-full ${
                    done ? 'bg-[#4b8b3b] text-white' : here ? 'bg-white ring-4 ring-ochre' : 'bg-white ring-2 ring-soil-dark/15'}`}>
                    {done && <Check className="h-4 w-4" strokeWidth={3} aria-hidden />}
                    {!done && !here && <span className="h-2.5 w-2.5 rounded-full bg-soil-dark/20" />}
                  </span>
                  <span className={`mt-2 text-[12px] leading-tight sm:text-[14px] ${
                    here ? 'rounded-full bg-[#e3efd9] px-2.5 py-1 font-semibold text-leaf-deep' : 'text-soil-dark/80'}`}>
                    {s.name}
                  </span>
                </li>
              )
            })}
          </ol>
        </div>
      )}
    </section>
  )
}

/** The four things a farmer comes to the app to do. */
function QuickActions() {
  const { t } = useFarmer()
  // White cards that sit off the cream page, each led by its own colour so
  // the four read apart at a glance; scanning, the main job, is the solid one.
  const tile = 'group relative flex min-h-[136px] flex-col justify-between gap-4 rounded-[22px] p-4 transition-[transform,box-shadow] duration-200 ease-out hover:-translate-y-0.5 lg:p-5'
  const card = `${tile} bg-white text-soil-dark shadow-[0_10px_24px_-16px_rgba(43,29,18,0.45)] ring-1 ring-soil-dark/[0.07] hover:shadow-[0_16px_30px_-16px_rgba(43,29,18,0.5)]`
  const badge = 'flex h-12 w-12 items-center justify-center rounded-2xl'
  const go = (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-soil-dark/[0.05] text-soil-dark/60 transition-colors group-hover:bg-[#2f6a39] group-hover:text-white" aria-hidden>
      <ChevronRight className="h-5 w-5" />
    </span>
  )
  const label = 'text-[16px] font-semibold leading-snug lg:text-[17px]'
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 className="text-[22px] font-semibold tracking-tight text-soil-dark">{t('qaTitle')}</h2>
        <p className="text-[15px] text-soil-dark/75">{t('qaSub')}</p>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <Link to="/app/scan" data-tour="scan"
          className={`${tile} bg-gradient-to-br from-[#3a7d45] to-[#24552d] text-white shadow-[0_14px_28px_-14px_rgba(29,74,44,0.85)] hover:shadow-[0_18px_32px_-14px_rgba(29,74,44,0.9)]`}>
          <span className="flex items-start justify-between">
            <span className={`${badge} bg-white/15`}><Camera className="h-7 w-7" strokeWidth={1.9} aria-hidden /></span>
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15" aria-hidden><ChevronRight className="h-5 w-5" /></span>
          </span>
          <span className={label}>{t('qaScan')}</span>
        </Link>
        <Link to="/app/live" data-tour="live" className={card}>
          <span className="flex items-start justify-between">
            <span className={`${badge} bg-[#fde5df] text-[#b5381c]`}><Video className="h-7 w-7" strokeWidth={1.9} aria-hidden /></span>
            <span className="inline-flex items-center gap-1 rounded-full bg-[#c2401f] px-2 py-0.5 text-[11px] font-bold tracking-wide text-white">
              <span className="h-1.5 w-1.5 rounded-full bg-white motion-safe:animate-pulse" aria-hidden />LIVE
            </span>
          </span>
          <span className={label}>{t('qaLive')}</span>
        </Link>
        <Link to="/app/spray" className={card}>
          <span className="flex items-start justify-between">
            <span className={`${badge} bg-[#fbe9c4] text-[#9a6210]`}><FlaskConical className="h-7 w-7" strokeWidth={1.9} aria-hidden /></span>
            {go}
          </span>
          <span className={label}>{t('qaSpray')}</span>
        </Link>
        <button onClick={() => askKrishi()} className={`${card} text-left`}>
          <span className="flex items-start justify-between">
            <span className={`${badge} bg-[#dcebf7] text-[#1f5f8f]`}><BookOpen className="h-7 w-7" strokeWidth={1.9} aria-hidden /></span>
            {go}
          </span>
          <span className={label}>{t('qaAdvice')}</span>
        </button>
      </div>
    </section>
  )
}

/** What to go and look at in the field today, with a picture of what it is. */
function FieldChecks({ alerts, stage }: { alerts: AlertView[]; stage: string }) {
  const { t } = useFarmer()
  return (
    <section data-tour="checks" className={`${PANEL} p-5 lg:p-6`}>
      <div className="flex items-start gap-3">
        <span className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#e3efd9] text-[#2f6a39] sm:flex">
          <CalendarCheck className="h-6 w-6" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[20px] font-semibold tracking-tight sm:text-[22px]">{t('todayChecks')}</h2>
          <p className="text-[14px] text-soil-dark/75 sm:text-[15px]">{t('checksSub').replace('{stage}', stage)}</p>
        </div>
        {alerts.length > 0 && (
          <Link to="/app/alerts" className="shrink-0 flex items-center gap-1 whitespace-nowrap text-[15px] font-medium text-leaf-deep hover:underline">
            {t('seeAll')} <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        )}
      </div>
      {alerts.length === 0 ? (
        <p className="mt-4 flex items-center gap-3 rounded-2xl bg-[#f1f6ec] p-4 text-[15px] text-soil-dark/85">
          <ShieldCheck className="h-6 w-6 shrink-0 text-[#4b8b3b]" aria-hidden /> {t('noChecks')}
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {alerts.slice(0, 3).map((a) => {
            const r = RISK[a.level]
            return (
              <li key={a.id}>
                <Link to="/app/alerts" className={`flex items-center gap-3 rounded-[20px] p-2.5 ring-1 ring-soil-dark/[0.05] transition-colors hover:brightness-[0.98] sm:gap-4 sm:p-3 ${r.row}`}>
                  <PestPhoto target={a.target} />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <Bug className="hidden h-5 w-5 text-ember sm:block" aria-hidden />
                      <span className="text-[16px] font-semibold sm:text-[17px]">{a.name}</span>
                      <span className={`rounded-full px-2.5 py-0.5 text-[13px] font-medium ${r.pill}`}>{t(r.key)}</span>
                    </span>
                    <span className="mt-1 block text-[14px] leading-snug text-soil-dark/85 line-clamp-2 sm:text-[15px]">{a.tasks[0] ?? a.reason}</span>
                  </span>
                  <span className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/80 text-soil-dark/70 sm:flex" aria-hidden>
                    <ChevronRight className="h-5 w-5" />
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

const dayLabel = (iso: string, lang: Lang) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(bcp47(lang), { day: 'numeric', month: 'short' })

/** The weather at the field: now, the one thing it means, and the days ahead. */
function WeatherPanel({ v, loading }: { v: WeatherView | null | undefined; loading: boolean }) {
  const { t, lang } = useFarmer()
  if (!v) return loading ? <div className={`${PANEL} h-[360px] motion-safe:animate-pulse`} /> : null
  const c = v.current
  const urgent = v.advisories.find((a) => a.rule !== 'spray_window' && a.severity !== 'info')
  // Dry days ahead, counted from tomorrow, for the line under the warning.
  let dry = 0
  for (const day of v.daily.slice(1)) {
    if ((day.rain ?? 0) >= 1 || (day.prob ?? 0) >= 50) break
    dry++
  }
  const sub = urgent && (urgent.category === 'irrigation' || urgent.category === 'heat') && dry >= 2
    ? t('noRainDays').replace('{n}', String(dry))
    : urgent?.text.split(/(?<=[.।])\s/)[0]
  const stat = (Icon: typeof Droplets, value: string, label: string) => (
    <div className="flex flex-col items-center gap-0.5 px-2.5 text-center sm:px-3">
      <Icon className="h-5 w-5 text-sky-700" aria-hidden />
      <span className="whitespace-nowrap text-[16px] font-semibold tabular-nums">{value}</span>
      <span className="text-[13px] text-soil-dark/75">{label}</span>
    </div>
  )
  return (
    <section data-tour="weather" className={`${PANEL} p-5`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
        <div className="flex items-center gap-3">
          <SkyIcon code={c.code} night={c.is_day === 0} className="h-14 w-14" />
          <div>
            <p className="text-[40px] font-semibold leading-none tabular-nums">{c.temp != null ? Math.round(c.temp) : '–'}<span className="align-top text-[22px]">°C</span></p>
            <p className="mt-1 text-[15px] text-soil-dark/85">{t(wmoKey(c.code))}</p>
          </div>
        </div>
        <div className="grid grid-cols-3 divide-x divide-soil-dark/10 rounded-2xl bg-[#f5f7f1] py-2 sm:flex sm:bg-transparent sm:py-0">
          {stat(Droplets, `${c.rh ?? '–'}%`, t('humidity'))}
          {stat(CloudRain, `${c.prob_3h ?? '–'}%`, t('wRain'))}
          {stat(Wind, `${c.wind ?? '–'} km/h`, t('wWind'))}
        </div>
      </div>
      {urgent && (
        <Link to="/app/weather" className="mt-4 flex items-center gap-3 rounded-2xl bg-[#fbf0dc] p-3.5 transition-colors hover:bg-[#f8e8cc]">
          <Droplet className="h-7 w-7 shrink-0 text-ochre" fill="currentColor" aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="block text-[16px] font-semibold text-[#8a5a17]">{urgent.title}</span>
            {sub && <span className="block text-[14px] text-soil-dark/80 line-clamp-1">{sub}</span>}
          </span>
          <ChevronRight className="h-5 w-5 shrink-0 text-soil-dark/60" aria-hidden />
        </Link>
      )}
      <div className="mt-5 flex items-center justify-between">
        <h3 className="text-[17px] font-semibold">{t('w5Day')}</h3>
        <Link to="/app/weather" className="flex items-center gap-1 text-[15px] font-medium text-leaf-deep hover:underline">
          {t('viewFull')} <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
      <div className="mt-3 grid grid-cols-5 gap-2">
        {v.daily.slice(0, 5).map((day) => (
          <div key={day.on} className="flex flex-col items-center gap-1.5 rounded-2xl bg-[#f5f7f1] py-3">
            <span className="text-[12px] text-soil-dark/75">{dayLabel(day.on, lang)}</span>
            <SkyIcon code={day.code} night={false} className="h-7 w-7" />
            <span className="text-[16px] font-semibold tabular-nums">{day.tmax != null ? Math.round(day.tmax) : '–'}°</span>
            <span className="text-[13px] text-soil-dark/70 tabular-nums">{day.tmin != null ? Math.round(day.tmin) : '–'}°</span>
          </div>
        ))}
      </div>
    </section>
  )
}

/** How far through its season the crop is, and when it will be ready —
 *  from this field's own temperatures where the app has them. */
function SeasonCard({ farm }: { farm: Farm }) {
  const { t, lang } = useFarmer()
  const eh = farm.expected_harvest
  if (!eh) return null
  const on = new Date(eh.on + 'T00:00:00')
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Math.round((on.getTime() - today.getTime()) / 86400000)
  // How sure the prediction is decides how wide the window is said to be.
  const spread = eh.confidence === 'high' ? 2 : eh.confidence === 'medium' ? 4 : 7
  const a = Math.max(0, days - spread)
  const b = days + spread
  const pct = Math.round(Math.min(1, farm.das / Math.max(1, farm.das + Math.max(0, days))) * 100)
  const from = new Date(on.getTime() - spread * 86400000)
  const to = new Date(on.getTime() + spread * 86400000)
  const fmt = (dt: Date, withMonth: boolean) =>
    dt.toLocaleDateString(bcp47(lang), withMonth ? { day: 'numeric', month: 'short' } : { day: 'numeric' })
  const window = from.getMonth() === to.getMonth() ? `${fmt(from, false)} – ${fmt(to, true)}` : `${fmt(from, true)} – ${fmt(to, true)}`
  return (
    <section className={`${PANEL} p-5`}>
      <div className="flex items-start gap-3">
        <Wheat className="h-8 w-8 shrink-0 text-ochre" aria-hidden />
        <div>
          <h2 className="text-[20px] font-semibold tracking-tight">{t('seasonTitle')}</h2>
          <p className="text-[15px] text-soil-dark/80">
            {days <= 0 ? t('harvestDue') : t('harvestAway').replace('{a}', String(a)).replace('{b}', String(b))}
          </p>
        </div>
      </div>
      <div className="mt-4 rounded-2xl bg-[#f5f7f1] p-4">
        <div className="h-3 rounded-full bg-soil-dark/10">
          <div className="h-3 rounded-full bg-gradient-to-r from-[#4b8b3b] to-[#78b04a]" style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-2 text-right text-[13px] text-soil-dark/75">{t('pctComplete').replace('{p}', String(pct))}</p>
        <p className="mt-3 flex items-center gap-2 text-[15px]">
          <CalendarDays className="h-5 w-5 text-leaf-deep" aria-hidden />
          <span className="text-soil-dark/80">{t('expectedHarvest')}:</span>
          <span className="font-semibold tabular-nums">{window}</span>
        </p>
      </div>
    </section>
  )
}

function RecentProblems({ problems }: { problems: ProblemView[] }) {
  const { t } = useFarmer()
  return (
    <section className={`${PANEL} p-5`}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex min-w-0 items-center gap-2 text-[18px] font-semibold tracking-tight sm:text-[20px]">
          <Clock className="h-6 w-6 shrink-0 text-leaf-deep" aria-hidden /> {t('recentProblems')}
        </h2>
        {problems.length > 0 && (
          <Link to="/app/history" className="flex shrink-0 items-center gap-1 whitespace-nowrap text-[15px] font-medium text-leaf-deep hover:underline">
            {t('seeAll')} <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        )}
      </div>
      {problems.length === 0 ? (
        <p className="mt-3 text-[15px] text-soil-dark/75">{t('noProblems')}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {problems.slice(0, 2).map((p) => <li key={p.id}><ProblemRow p={p} /></li>)}
        </ul>
      )}
    </section>
  )
}

function FollowUp({ id, name, dueOn, onDone, row = false }: {
  id: number; name: string | null; dueOn: string; onDone: () => void; row?: boolean
}) {
  const { t, lang } = useFarmer()
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  // Answering on a shared demo field edits what the next visitor walks into,
  // so the server refuses it; the buttons would only be able to fail.
  const readOnly = useReadOnlyFarm() !== null
  // "It got worse" goes to a district officer, so it asks for a photo and the
  // farmer's own words first rather than sending an empty case.
  const [reporting, setReporting] = useState(false)
  const send = async (r: 'improved' | 'no_change' | 'got_worse',
                      evidence?: { photo: Blob | null; note: string }) => {
    setBusy(r)
    try {
      const out = await api.followup(id, r, lang, evidence)
      setReporting(false)
      if (out.message) {
        setMsg(out.message)
        setTimeout(onDone, 2500)
      } else onDone()
    } catch {
      // "It got worse" carries a photo and the farmer's own words to a district
      // officer. Losing it without a word is the worst of the three to lose.
      // The slot it lands in is already ember, and onDone is NOT called: the
      // card stays, with the buttons live.
      setMsg(t('notSaved'))
    } finally {
      setBusy(null)
    }
  }
  const choose = (r: 'improved' | 'no_change' | 'got_worse') =>
    r === 'got_worse' ? setReporting(true) : void send(r)
  const choices = ([['improved', t('improved'), 'bg-leaf text-cream'], ['no_change', t('noChange'), 'bg-white border border-soil-dark/20'], ['got_worse', t('gotWorse'), 'bg-ember text-cream']] as const)
  // Two treatments of the same disease give two cards with the same name on
  // them. Without the date a farmer cannot tell which one they are answering.
  const when = new Date(dueOn + 'T00:00:00').toLocaleDateString(bcp47(lang), { day: 'numeric', month: 'short' })
  if (row) {
    return (
      <div className="flex items-center gap-6 px-5 py-4">
        <p className="flex-1 min-w-0 font-semibold truncate">
          {name ?? t('followupDue')}
          <span className="ml-2 font-normal text-soil-dark/55">{when}</span>
        </p>
        {msg ? (
          <p className="text-sm text-ember">{msg}</p>
        ) : readOnly ? (
          <p className="text-xs text-soil-dark/50 shrink-0">{t('demoReadOnlyShort')}</p>
        ) : (
          <div className="grid grid-cols-3 gap-2 w-[22rem] shrink-0">
            {choices.map(([r, label, cls]) => (
              <button key={r} onClick={() => choose(r)} disabled={busy !== null} className={`min-h-[40px] rounded-xl text-sm font-medium ${cls}`}>
                {busy === r ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : label}
              </button>
            ))}
          </div>
        )}
        {reporting && (
          <div className="basis-full">
            <ReportSheet busy={busy !== null} onCancel={() => setReporting(false)}
              onSend={(ev) => void send('got_worse', ev)} />
          </div>
        )}
      </div>
    )
  }
  return (
    <Card className="p-4 border-ochre/40 bg-ochre/5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-semibold">{t('followupDue')}</p>
        <p className="text-xs text-soil-dark/55 shrink-0">{when}</p>
      </div>
      {name && <p className="text-xs text-soil-dark/60 mt-0.5">{name}</p>}
      {msg ? (
        <p className="mt-2 text-sm text-ember">{msg}</p>
      ) : readOnly ? (
        <p className="mt-2 text-xs text-soil-dark/50">{t('demoReadOnlyShort')}</p>
      ) : (
        <div className="mt-3 grid grid-cols-3 gap-2">
          {choices.map(([r, label, cls]) => (
            <button key={r} onClick={() => choose(r)} disabled={busy !== null} className={`min-h-[44px] rounded-xl text-sm font-medium ${cls}`}>
              {busy === r ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : label}
            </button>
          ))}
        </div>
      )}
      {reporting && !msg && (
        <ReportSheet busy={busy !== null} onCancel={() => setReporting(false)}
          onSend={(ev) => void send('got_worse', ev)} />
      )}
    </Card>
  )
}

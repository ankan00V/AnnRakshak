import {
  Check, ChevronDown, CloudFog, CloudRain, CloudSun, Droplets, ListChecks, MapPin,
  Satellite, ShieldCheck, Snowflake, SprayCan, Sprout, Sun, Sunrise, Sunset, Wind, Zap,
} from 'lucide-react'
import { api } from '../../api/client'
import type { Lang, WeatherAdvisory, WeatherDay, WeatherHour, WeatherView } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { ErrorBox, ListenButton } from '../../ui/kit'
import { WeatherSkeleton } from '../components/Skeletons'
import LastKnown from '../components/LastKnown'
import { bcp47 } from '../../lib/i18n'
import { useFarmer } from '../FarmerContext'
import { PanelHead, PestPhoto, PhotoCurve, SkyIcon } from '../ui'
import { PANEL, RISK, wmoKey } from '../tokens'
import SprayTimes from '../components/SprayTimes'

type T = ReturnType<typeof useFarmer>['t']

/** How loud an advisory is: a warning, a piece of advice, or a note. */
const SEV = {
  warning: { box: 'bg-[#fdf0ed]', icon: 'bg-[#f9dcd5] text-[#9a2f17]', title: 'text-[#9a2f17]' },
  advice: { box: 'bg-[#fbf0dc]', icon: 'bg-[#f6e2bb] text-[#8a5a17]', title: 'text-[#7a4f12]' },
  info: { box: 'bg-[#f1f6ec]', icon: 'bg-[#dcebd0] text-[#2f5a24]', title: 'text-[#2f5a24]' },
} as const
const CAT_ICON = {
  safety: Zap, rain: CloudRain, wind: Wind, cold: Snowflake, heat: Sun, spray: SprayCan, disease: Sprout,
  irrigation: Droplets, fog: CloudFog,
} as const

function compass(deg: number | null, t: T): string {
  if (deg == null) return ''
  return t('compass').split('|')[Math.round(deg / 45) % 8]
}

/** "Today", "Tomorrow", then "Sat 15", in the farmer's language. */
function dayLabel(on: string, lang: Lang): string {
  const d = new Date(on + 'T00:00:00')
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const diff = Math.round((d.getTime() - today.getTime()) / 864e5)
  if (diff === 0 || diff === 1) {
    const s = new Intl.RelativeTimeFormat(bcp47(lang), { numeric: 'auto' }).format(diff, 'day')
    return s.charAt(0).toUpperCase() + s.slice(1)
  }
  return d.toLocaleDateString(bcp47(lang), { weekday: 'short', day: 'numeric' })
}

const hhmm = (iso: string) => iso.slice(11, 16)
const deg = (v: number | null) => (v != null ? `${Math.round(v)}°` : '–')

export default function Weather() {
  const { farmId, lang, t } = useFarmer()
  const w = useAsync(() => api.weather(farmId!, lang), [farmId, lang], ['weather', farmId!, lang].join(':'))
  if (w.loading && !w.data) return <WeatherSkeleton />
  // A forecast kept on this phone still tells a farmer what the week looked
  // like when it was fetched, and `fetched_at` dates it. The error takes the
  // screen only when there is nothing kept.
  if (w.error && !w.data) return <ErrorBox error={w.error} onRetry={w.reload} retryLabel={t('retry')} />
  const v = w.data!
  const advice = v.advisories.filter((a) => a.rule !== 'spray_window')

  return (
    <div className="space-y-6">
      {v.stale && <p className="rounded-2xl bg-[#fbf0dc] p-3.5 text-[14px] text-[#7a4f12]">{t('staleData')}</p>}
      {/* `stale` is the server saying its own copy is old; this is the phone
          saying it never reached the server at all. */}
      {w.error && <LastKnown at={w.savedAt} onRetry={w.reload} />}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 space-y-6">
          <NowPanel v={v} />
          <ToDoPanel v={v} items={advice} />
          <div className="lg:hidden"><SprayTimes v={v} /></div>
          <HoursPanel hours={v.hourly.slice(0, 24)} />
          <DaysPanel days={v.daily} />
        </div>
        <aside className="min-w-0 space-y-6">
          <div className="hidden lg:block"><SprayTimes v={v} /></div>
          <WaterPanel v={v} />
          <SatellitePanel />
        </aside>
      </div>
    </div>
  )
}

/** The sky over the field right now, over a photograph of open country. */
function NowPanel({ v }: { v: WeatherView }) {
  const { t, lang } = useFarmer()
  const c = v.current
  const today = v.daily[0]
  const night = c.is_day === 0
  const speech = v.advisories.filter((a) => a.rule !== 'spray_window').slice(0, 3)
    .map((a) => `${a.title}. ${a.text}`).join(' ')
  const stat = (Icon: typeof Droplets, value: string, label: string) => (
    <div className="flex flex-col items-center gap-0.5 px-2 py-1 text-center">
      <Icon className="h-5 w-5 text-sky-700" aria-hidden />
      <span className="whitespace-nowrap text-[17px] font-semibold tabular-nums">{value}</span>
      <span className="text-[13px] leading-tight text-soil-dark/75">{label}</span>
    </div>
  )
  return (
    <section className={`${PANEL} p-2`}>
      <div className="relative h-[250px] overflow-hidden rounded-[22px] bg-leaf-deep lg:h-[270px]">
        <img src={night ? '/photos/sunset.webp' : '/photos/landscape.webp'} alt="" width={934} height={442}
          className="absolute inset-0 h-full w-full object-cover object-[center_40%]" />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-r from-black/55 via-black/25 to-transparent" />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-black/25" />
        <div className="relative flex h-full flex-col justify-between p-5 text-white lg:p-6">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 drop-shadow">
              <p className="flex min-w-0 items-center gap-1.5 text-[15px] font-semibold">
                <MapPin className="h-4 w-4 shrink-0" aria-hidden />
                <span className="truncate">{v.location.district}</span>
              </p>
              <p className="mt-0.5 pl-[22px] text-[13px] opacity-90">{t('updatedAt').replace('{t}', hhmm(v.fetched_at))}</p>
            </div>
            {speech && <ListenButton text={speech} lang={lang} label={t('listen')} stopLabel={t('stop')} tone="light" />}
          </div>
          <div className="flex items-end justify-between gap-4 pb-3">
            <div className="flex items-end gap-3">
              <p className="text-[64px] font-semibold leading-[0.85] tabular-nums drop-shadow-sm lg:text-[76px]">
                {c.temp != null ? Math.round(c.temp) : '–'}<span className="align-top text-[28px]">°C</span>
              </p>
              <div className="pb-1">
                <p className="font-instrument-serif text-[28px] leading-none drop-shadow-sm lg:text-[32px]">{t(wmoKey(c.code))}</p>
                {c.feels != null && <p className="mt-1 text-[15px] drop-shadow">{t('feelsLike').replace('{v}', String(Math.round(c.feels)))}</p>}
              </div>
            </div>
            {today && (
              <div className="hidden text-right text-[14px] leading-relaxed drop-shadow sm:block">
                <p>{t('wxDayNight').replace('{hi}', deg(today.tmax)).replace('{lo}', deg(today.tmin))}</p>
                {today.sunrise && today.sunset && (
                  <p className="flex items-center justify-end gap-3">
                    <span className="flex items-center gap-1"><Sunrise className="h-4 w-4" aria-hidden />{hhmm(today.sunrise)}</span>
                    <span className="flex items-center gap-1"><Sunset className="h-4 w-4" aria-hidden />{hhmm(today.sunset)}</span>
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
        <PhotoCurve />
      </div>
      <div className="grid grid-cols-2 gap-y-2 divide-soil-dark/10 px-2 pb-3 pt-1 sm:grid-cols-4 sm:divide-x">
        {stat(Droplets, `${c.rh ?? '–'}%`, t('humidity'))}
        {stat(CloudRain, `${c.prob_3h ?? '–'}%`, t('wxRainNext'))}
        {stat(Wind, `${c.wind ?? '–'} km/h`, [t('wWind'), compass(c.wdir, t)].filter(Boolean).join(' · '))}
        {stat(CloudSun, `${today?.rain ?? 0} mm`, t('wxRainToday'))}
      </div>
    </section>
  )
}

/** One piece of weather advice: what is happening, and what to do about it.
 *  Also the notices list's card, so a notice looks the same wherever it is. */
function AdviceCard({ a, compact = false }: { a: WeatherAdvisory; compact?: boolean }) {
  const { t } = useFarmer()
  const s = SEV[a.severity]
  const Icon = CAT_ICON[a.category] ?? CloudSun
  return (
    <article className={`rounded-[20px] p-4 ${s.box}`}>
      <div className="flex items-center gap-3">
        <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${s.icon}`}>
          <Icon className="h-6 w-6" aria-hidden />
        </span>
        <h3 className={`min-w-0 flex-1 text-[17px] font-semibold leading-snug ${s.title}`}>{a.title}</h3>
      </div>
      {/* Full width on a phone, where the icon's column would squeeze it. */}
      <p className="mt-2 text-[15px] leading-snug text-soil-dark/85 text-pretty sm:mt-0 sm:pl-14">{a.text}</p>
      {!compact && a.do.length > 0 && (
        <ul className="mt-3 space-y-2 sm:pl-14">
          {a.do.map((d) => (
            <li key={d} className="flex items-start gap-2.5 text-[15px] leading-snug">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-[#4b8b3b]">
                <Check className="h-3.5 w-3.5" strokeWidth={3} aria-hidden />
              </span>
              {d}
            </li>
          ))}
        </ul>
      )}
      {/* Where the advice comes from matters to an officer checking it, not to
          a farmer acting on it: there when asked for, out of the way when not. */}
      {!compact && a.source && (
        <details className="group mt-3 sm:pl-14">
          <summary className="flex cursor-pointer list-none items-center gap-1 text-[13px] font-medium text-soil-dark/70 [&::-webkit-details-marker]:hidden">
            {t('wxWhy')} <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden />
          </summary>
          <p className="mt-1.5 text-[13px] leading-snug text-soil-dark/70">{a.source}</p>
        </details>
      )}
    </article>
  )
}

export function Advisories({ items, compact = false }: { items: WeatherAdvisory[]; compact?: boolean }) {
  const { t } = useFarmer()
  if (items.length === 0) {
    return (
      <p className="flex items-center gap-3 rounded-[20px] bg-[#f1f6ec] p-4 text-[15px] text-soil-dark/85">
        <ShieldCheck className="h-6 w-6 shrink-0 text-[#4b8b3b]" aria-hidden /> {t('allClear')}
      </p>
    )
  }
  return <div className="space-y-3">{items.map((a) => <AdviceCard key={a.id} a={a} compact={compact} />)}</div>
}

/** What the week's weather means for this crop, and the pests it favours. */
function ToDoPanel({ v, items }: { v: WeatherView; items: WeatherAdvisory[] }) {
  const { t, lang } = useFarmer()
  return (
    <section className={`${PANEL} p-5 lg:p-6`}>
      <PanelHead icon={ListChecks} title={t('weatherToDo')} sub={t('wxToDoSub').replace('{crop}', v.crop.name)} />
      <div className="mt-4"><Advisories items={items} /></div>
      {v.watch_for.length > 0 && (
        <div className="mt-6">
          <h3 className="text-[17px] font-semibold">{t('watchFor').replace('{crop}', v.crop.name)}</h3>
          <ul className="mt-3 grid gap-3 sm:grid-cols-2">
            {v.watch_for.map((r) => {
              const k = RISK[r.level]
              return (
                <li key={r.target} className={`flex items-center gap-3 rounded-[20px] p-2.5 ring-1 ring-soil-dark/[0.05] ${k.row}`}>
                  <PestPhoto target={r.target} className="h-14 w-14" />
                  <span className="min-w-0">
                    <span className="block text-[16px] font-semibold leading-snug">{r.name}</span>
                    <span className={`mt-1 inline-block rounded-full px-2.5 py-0.5 text-[13px] font-medium ${k.pill}`}>{t(k.key)}</span>
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
      {v.seasonal.length > 0 && (
        <div className="mt-6 rounded-[20px] bg-[#f5f7f1] p-4">
          <p className="text-[15px] text-soil-dark/85">
            {t('kccSeasonal').replace('{month}', new Date().toLocaleDateString(bcp47(lang), { month: 'long' })).replace('{district}', v.location.district)}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {v.seasonal.map((s) => (
              <span key={s.group} className="rounded-full bg-white px-3 py-1 text-[14px] ring-1 ring-soil-dark/10">{s.name}</span>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

/** The next day in three-hour steps: what a farmer plans a day of work by. */
function HoursPanel({ hours }: { hours: WeatherHour[] }) {
  const { t } = useFarmer()
  const steps = hours.filter((_, i) => i % 3 === 0).slice(0, 8)
  if (steps.length < 2) return null
  return (
    <section className={`${PANEL} p-5 lg:p-6`}>
      <h2 className="text-[20px] font-semibold tracking-tight sm:text-[22px]">{t('next24h')}</h2>
      <ol className="no-scrollbar -mx-1 mt-4 flex gap-2 overflow-x-auto px-1 pb-1 sm:grid sm:grid-cols-8 sm:overflow-visible">
        {steps.map((h, i) => (
          <li key={h.t} className={`flex w-[72px] shrink-0 flex-col items-center gap-1.5 rounded-2xl py-3 sm:w-auto ${
            i === 0 ? 'bg-[#e3efd9]' : 'bg-[#f5f7f1]'}`}>
            <span className={`text-[13px] tabular-nums ${i === 0 ? 'font-semibold text-leaf-deep' : 'text-soil-dark/75'}`}>
              {i === 0 ? t('wxNow') : hhmm(h.t)}
            </span>
            <SkyIcon code={h.code} night={h.is_day === 0} className="h-7 w-7" />
            <span className="text-[17px] font-semibold tabular-nums">{deg(h.temp)}</span>
            <span className={`flex items-center gap-0.5 text-[12px] tabular-nums ${(h.prob ?? 0) >= 20 ? 'text-sky-700' : 'text-soil-dark/45'}`}>
              <Droplets className="h-3 w-3" aria-hidden />{h.prob ?? 0}%
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}

/** The week: each day's sky, its warmest and coolest, and whether it rains. */
function DaysPanel({ days }: { days: WeatherDay[] }) {
  const { t, lang } = useFarmer()
  if (days.length === 0) return null
  const lo = Math.min(...days.map((d) => d.tmin ?? 99)), hi = Math.max(...days.map((d) => d.tmax ?? -99))
  return (
    <section className={`${PANEL} p-5 lg:p-6`}>
      <h2 className="text-[20px] font-semibold tracking-tight sm:text-[22px]">{t('next7')}</h2>
      <ul className="mt-3 divide-y divide-soil-dark/[0.07]">
        {days.map((d) => {
          const left = (((d.tmin ?? lo) - lo) / (hi - lo || 1)) * 100
          const width = (((d.tmax ?? hi) - (d.tmin ?? lo)) / (hi - lo || 1)) * 100
          const wet = (d.rain ?? 0) >= 1 || (d.prob ?? 0) >= 30
          return (
            <li key={d.on} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 py-3 sm:grid-cols-[150px_minmax(0,1fr)_200px]">
              <div className="flex min-w-0 items-center gap-3">
                <SkyIcon code={d.code} night={false} className="h-8 w-8 shrink-0" />
                <span className="min-w-0">
                  <span className="block text-[16px] font-semibold">{dayLabel(d.on, lang)}</span>
                  <span className="block truncate text-[13px] text-soil-dark/70">{t(wmoKey(d.code))}</span>
                </span>
              </div>
              <p className={`text-right text-[14px] sm:order-last ${wet ? 'font-medium text-sky-700' : 'text-soil-dark/70'}`}>
                {wet
                  ? <span className="inline-flex items-center gap-1"><Droplets className="h-4 w-4" aria-hidden />{d.prob ?? 0}% · {d.rain ?? 0} mm</span>
                  : t('wxNoRain')}
              </p>
              <div className="col-span-2 flex items-center gap-2 text-[14px] tabular-nums sm:col-span-1">
                <span className="w-9 text-right text-soil-dark/70">{deg(d.tmin)}</span>
                <span className="relative h-2 flex-1 rounded-full bg-soil-dark/[0.08]">
                  <span className="absolute inset-y-0 rounded-full bg-gradient-to-r from-sky-400 to-ochre"
                    style={{ left: `${left}%`, width: `${Math.max(width, 4)}%` }} />
                </span>
                <span className="w-9 font-semibold">{deg(d.tmax)}</span>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/** Does the crop need water: what it drank this week against what rain gave. */
function WaterPanel({ v }: { v: WeatherView }) {
  const { t } = useFarmer()
  const w = v.water
  const ph = v.soil?.ph
  const sat = v.sat_rain
  if (!w.available && !ph && !sat) return null
  const used = w.etc_week ?? 0
  const rain = w.eff_rain_week ?? 0
  const top = Math.max(used, rain, 1)
  const bar = (label: string, mm: number, cls: string) => (
    <div>
      <div className="flex items-baseline justify-between text-[14px]">
        <span className="text-soil-dark/80">{label}</span>
        <span className="font-semibold tabular-nums">{Math.round(mm)} mm</span>
      </div>
      <div className="mt-1.5 h-3 rounded-full bg-soil-dark/[0.08]">
        <div className={`h-3 rounded-full ${cls}`} style={{ width: `${Math.max(mm > 0 ? 4 : 0, (mm / top) * 100)}%` }} />
      </div>
    </div>
  )
  const need = w.verdict === 'irrigate'
  return (
    <section className={`${PANEL} p-2`}>
      <div className="relative h-[110px] overflow-hidden rounded-[22px] bg-leaf-deep">
        <img src="/photos/field-canal.webp" alt="" width={622} height={468} loading="lazy"
          className="absolute inset-0 h-full w-full object-cover object-[center_65%]" />
        <PhotoCurve />
      </div>
      <div className="px-3 pb-3 pt-1">
        <PanelHead icon={Droplets} title={t('wxWaterTitle')} />
        {w.available && (
          <>
            {w.verdict && (
              <p className={`mt-4 rounded-[20px] p-3.5 text-[16px] font-semibold ${need ? 'bg-[#fbf0dc] text-[#7a4f12]' : 'bg-[#f1f6ec] text-[#2f5a24]'}`}>
                {t(`wv_${w.verdict}`)}
              </p>
            )}
            <div className="mt-4 space-y-3">
              {bar(t('weekUsed'), used, 'bg-ochre')}
              {bar(t('weekRain'), rain, 'bg-sky-500')}
            </div>
            {!!w.deficit && (
              <p className="mt-3 text-[15px]">
                {t('shortfall')}: <b className="tabular-nums">{Math.round(w.deficit)} mm</b>
              </p>
            )}
          </>
        )}
        {sat && (
          <p className="mt-4 flex items-center justify-between gap-3 rounded-[20px] bg-sky-50 p-3.5">
            <span className="flex items-center gap-2 text-[14px] text-sky-950/80">
              <Satellite className="h-4 w-4 shrink-0" aria-hidden />{t('satRainTitle')}
            </span>
            <span className="shrink-0 text-[17px] font-semibold tabular-nums text-sky-900">{sat.mm} mm</span>
          </p>
        )}
        {ph && (
          <div className="mt-4 flex items-baseline justify-between gap-3 rounded-[20px] bg-[#f5f7f1] p-3.5">
            <span>
              <span className="block text-[14px] text-soil-dark/75">{t('soilPh')}</span>
              <span className="text-[17px] font-semibold tabular-nums">{ph.value}</span>{' '}
              <span className="text-[15px] text-soil-dark/80">{ph.band}</span>
            </span>
            <span className="text-right text-[13px] leading-tight text-soil-dark/65">{t(`ph_${ph.how}`)}</span>
          </div>
        )}
        <p className="mt-3 text-[12px] text-soil-dark/60">{t('modelledNote')}</p>
      </div>
    </section>
  )
}

const GREEN = {
  sparse: 'bg-[#f6e6c4] text-[#7a4f12]', low: 'bg-[#eef3d6] text-[#55631a]',
  moderate: 'bg-[#dcebd0] text-[#2f5a24]', dense: 'bg-[#4b8b3b] text-white',
} as const

/** How green the field looked from the satellite, and whether that is falling. */
function SatellitePanel() {
  const { farmId, lang, t } = useFarmer()
  const s = useAsync(() => api.satellite(farmId!), [farmId], ['satellite', farmId!].join(':'))
  const d = s.data?.available && s.data.latest ? s.data : null
  if (!d) return null
  const date = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString(bcp47(lang), { day: 'numeric', month: 'short' })
  const series = d?.series ?? []
  const W = 300, H = 48
  const xs = (i: number) => (series.length > 1 ? (i / (series.length - 1)) * (W - 8) + 4 : W / 2)
  const ys = (n: number) => H - 4 - n * (H - 8)
  return (
    <section className={`${PANEL} p-5`}>
      <PanelHead icon={Satellite} title={t('satTitle')} />
      {d.latest && (
        <div className="mt-4 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[15px] text-soil-dark/80">{t('wxGreenness')}</span>
            {d.band && <span className={`rounded-full px-3 py-1 text-[14px] font-semibold ${GREEN[d.band]}`}>{t(`ndvi_${d.band}`)}</span>}
          </div>
          {series.length > 1 && (
            <svg viewBox={`0 0 ${W} ${H}`} className="h-12 w-full" aria-hidden>
              <path d={series.map((p, i) => `${i ? 'L' : 'M'}${xs(i)},${ys(p.mean)}`).join(' ')} fill="none" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" className="stroke-[#4b8b3b]" />
              {series.map((p, i) => <circle key={p.on} cx={xs(i)} cy={ys(p.mean)} r={3} className="fill-[#2f6a39]" />)}
            </svg>
          )}
          <p className="text-[14px] text-soil-dark/75">{t('satLastClear').replace('{date}', date(d.latest.on))}</p>
          {d.drop && <p className="rounded-[20px] bg-[#fdf0ed] p-3.5 text-[15px] font-medium text-[#9a2f17]">{t('satDrop')}</p>}
          {(d.age_days ?? 0) > 20 && <p className="rounded-[20px] bg-sky-50 p-3.5 text-[14px] text-sky-950/80">{t('satCloudy')}</p>}
        </div>
      )}
    </section>
  )
}

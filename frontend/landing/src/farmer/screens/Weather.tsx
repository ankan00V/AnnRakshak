import {
  ArrowDown, ArrowUp, CloudFog, Satellite, CloudRain, CloudSun, Droplets, Eye, Gauge, Minus, Navigation, Snowflake, SprayCan,
  Sprout, Sun, Thermometer, Wind, Zap,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import type { Lang, WeatherAdvisory, WeatherDay, WeatherHour, WeatherView } from '../../api/types'
import { useAsync, useWide } from '../../lib/hooks'
import { Card, ErrorBox, ListenButton, Pill, SectionTitle, Spinner } from '../../ui/kit'
import { bcp47 } from '../../lib/i18n'
import { useFarmer } from '../FarmerContext'
import { MAIN, SIDE, SPLIT } from '../layout'

type T = ReturnType<typeof useFarmer>['t']

export const SEV_STYLE = {
  warning: 'border-ember/40 bg-ember/5',
  advice: 'border-ochre/40 bg-ochre/5',
  info: 'border-leaf/30 bg-leaf/5',
} as const
const SEV_TEXT = { warning: 'text-ember', advice: 'text-[#8a5a17]', info: 'text-leaf-deep' } as const
const CAT_ICON = {
  safety: Zap, rain: CloudRain, wind: Wind, cold: Snowflake, heat: Sun, spray: SprayCan, disease: Sprout,
  irrigation: Droplets, fog: CloudFog,
} as const
const SPRAY_COLOR = { good: 'bg-leaf', caution: 'bg-ochre', avoid: 'bg-ember/80' } as const
const UV_COLOR = {
  low: 'bg-leaf/15 text-leaf-deep', moderate: 'bg-lime-100 text-lime-800', high: 'bg-ochre/20 text-[#8a5a17]',
  very_high: 'bg-ember/15 text-ember', extreme: 'bg-purple-100 text-purple-800',
} as const

export function wmoKey(code: number | null): string {
  if (code == null) return 'wmo_partly'
  if (code === 0) return 'wmo_clear'
  if (code <= 2) return 'wmo_partly'
  if (code === 3) return 'wmo_overcast'
  if (code === 45 || code === 48) return 'wmo_fog'
  if (code >= 51 && code <= 57) return 'wmo_drizzle'
  if (code >= 61 && code <= 67) return 'wmo_rain'
  if (code >= 71 && code <= 77) return 'wmo_snow'
  if (code >= 80 && code <= 86) return 'wmo_showers'
  if (code >= 95) return 'wmo_thunder'
  return 'wmo_partly'
}

function compass(deg: number | null, t: T): string {
  if (deg == null) return ''
  return t('compass').split('|')[Math.round(deg / 45) % 8]
}

const locale = (lang: Lang) => bcp47(lang)

function dayLabel(on: string, lang: Lang): string {
  const d = new Date(on + 'T00:00:00')
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const diff = Math.round((d.getTime() - today.getTime()) / 864e5)
  if (diff === 0 || diff === 1) {
    const s = new Intl.RelativeTimeFormat(locale(lang), { numeric: 'auto' }).format(diff, 'day')
    return s.charAt(0).toUpperCase() + s.slice(1)
  }
  return d.toLocaleDateString(locale(lang), { weekday: 'short', day: 'numeric' })
}

const hhmm = (iso: string) => iso.slice(11, 16)

export default function Weather() {
  const { farmId, lang, t } = useFarmer()  // lang also feeds dates and the KCC month name
  const w = useAsync(() => api.weather(farmId!, lang), [farmId, lang], ['weather', farmId!, lang].join(':'))
  const wide = useWide()
  if (w.loading && !w.data) return <Spinner label={t('loading')} />
  if (w.error) return <ErrorBox error={w.error} onRetry={w.reload} retryLabel={t('retry')} />
  const v = w.data!
  const speech = v.advisories.filter((a) => a.rule !== 'spray_window').slice(0, 3).map((a) => `${a.title}. ${a.text}`).join(' ')

  const header = (
    <>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="font-instrument-serif text-3xl leading-tight">{t('weatherTitle')}</h1>
            <p className="text-xs text-soil-dark/50 mt-0.5">
              {v.location.district} · {v.crop.name} · {v.crop.stage_name} · {t('updatedAt').replace('{t}', hhmm(v.fetched_at))}
            </p>
          </div>
          {speech && <ListenButton text={speech} lang={lang} label={t('listen')} stopLabel={t('stop')} compact />}
        </div>
        {v.stale && <p className="text-xs rounded-xl bg-ochre/10 text-[#8a5a17] p-2.5">{t('staleData')}</p>}
    </>
  )
  const todo = (
        <section className="space-y-2">
          <SectionTitle>{t('weatherToDo')}</SectionTitle>
          <Advisories items={v.advisories.filter((a) => a.rule !== 'spray_window')} />
          {v.watch_for.length > 0 && (
            <div className="rounded-2xl bg-white border border-soil-dark/10 p-3">
              <p className="text-xs text-soil-dark/60">{t('watchFor').replace('{crop}', v.crop.name)}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {v.watch_for.map((r) => (
                  <Pill key={r.target} tone={r.level === 'high' ? 'ember' : r.level === 'medium' ? 'ochre' : 'neutral'}>
                    {r.name} · {t(`level_${r.level}`)}
                  </Pill>
                ))}
              </div>
            </div>
          )}
          {v.seasonal.length > 0 && (
            <div className="rounded-2xl bg-sky-50 border border-sky-100 p-3">
              <p className="text-xs text-sky-900">
                {t('kccSeasonal').replace('{month}', new Date().toLocaleDateString(bcp47(lang), { month: 'long' })).replace('{district}', v.location.district)}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {v.seasonal.map((s) => (
                  <span key={s.group} className="rounded-full bg-white border border-sky-200 px-2.5 py-1 text-[11px] text-sky-900">
                    {s.name}{s.district_calls_this_month > 0 && <span className="text-sky-700/70"> · {s.district_calls_this_month}</span>}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
  )
  const sources = (
        <p className="text-[11px] text-soil-dark/45 leading-relaxed">
          {t('sources')}: {v.source.forecast}; {t('rainNow')}: {v.source.current}; ET₀: {v.source.et0}
          {v.source.soil ? `; ${v.source.soil}` : ''}.
        </p>
  )

  // Desktop: conditions and the forecast on the left; what to do, the spraying
  // window and the satellite view beside them (the shared 8 | 4 grid).
  if (wide) {
    return (
      <div className="space-y-6">
        {header}
        <div className={SPLIT}>
          <div className={`${MAIN} space-y-6`}>
            <NowCard v={v} />
            <HourlyChart hours={v.hourly.slice(0, 24)} />
            <DailyList days={v.daily} />
            <SoilWater v={v} />
          </div>
          <aside className={`${SIDE} space-y-6`}>
            {todo}
            <SprayCard v={v} />
            <SatelliteCard />
          </aside>
        </div>
        {sources}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {header}

      <NowCard v={v} />

      {todo}

      <SprayCard v={v} />
      <HourlyChart hours={v.hourly.slice(0, 24)} />
      <DailyList days={v.daily} />
      <SoilWater v={v} />
      <SatelliteCard />

      {sources}
    </div>
  )
}

function NowCard({ v }: { v: WeatherView }) {
  const { t } = useFarmer()
  const c = v.current
  const trend = c.pressure_trend_24h
  const TrendIcon = trend == null || Math.abs(trend) < 1 ? Minus : trend > 0 ? ArrowUp : ArrowDown
  const trendKey = trend == null || Math.abs(trend) < 1 ? 'pressure_steady' : trend > 0 ? 'pressure_up' : 'pressure_down'
  const tiles: [typeof Droplets, string, string, string?][] = [
    [Droplets, t('humidity'), `${c.rh ?? '–'}%`],
    [CloudRain, t('rainChance'), `${c.prob_3h ?? '–'}%`, t('next3h')],
    [CloudRain, t('rainNow'), `${c.precip ?? 0} mm`],
    [Wind, t('windLabel'), `${c.wind ?? '–'} km/h`, compass(c.wdir, t)],
    [Wind, t('gustsLabel'), `${c.gust ?? '–'} km/h`],
    [Sun, t('uvLabel'), `${c.uv ?? '–'}`, c.uv_band ? t(`uv_${c.uv_band}`) : undefined],
    [CloudSun, t('cloudLabel'), `${c.cloud ?? '–'}%`],
    [Eye, t('visibilityLabel'), c.vis != null ? `${(c.vis / 1000).toFixed(c.vis < 10000 ? 1 : 0)} km` : '–'],
    [Gauge, t('pressureLabel'), `${c.pressure ?? '–'} hPa`, t(trendKey)],
  ]
  return (
    <section className="rounded-3xl bg-gradient-to-br from-leaf-deep to-soil-dark text-cream p-5 shadow-lg shadow-leaf-deep/20">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-6xl font-semibold leading-none tracking-tight">{c.temp != null ? Math.round(c.temp) : '–'}°</p>
          <p className="mt-2 text-sm text-cream/80">{t(wmoKey(c.code))} · {t('feelsLike').replace('{v}', String(c.feels != null ? Math.round(c.feels) : '–'))}</p>
          <p className="text-[11px] text-cream/55 mt-0.5 flex items-center gap-1">
            <Thermometer className="w-3 h-3" /> {t('dewLabel')} {c.dew ?? '–'}°
            {c.station ? ` · ${c.station}` : ''}
          </p>
        </div>
        {c.wdir != null && (
          <div className="text-center">
            <Navigation className="w-8 h-8 text-ochre mx-auto" style={{ transform: `rotate(${(c.wdir + 180) % 360}deg)` }} />
            <p className="text-[11px] text-cream/70 mt-1">{compass(c.wdir, t)} · {c.wind} km/h</p>
          </div>
        )}
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2">
        {tiles.map(([Icon, label, value, sub], i) => (
          <div key={i} className="rounded-2xl bg-cream/10 px-2.5 py-2">
            <p className="flex items-center gap-1 text-[10px] text-cream/60"><Icon className="w-3 h-3" />{label}</p>
            <p className="text-sm font-semibold mt-0.5">{value}</p>
            {sub && (
              <p className={`text-[10px] mt-0.5 ${label === t('uvLabel') && c.uv_band ? `inline-block rounded px-1 ${UV_COLOR[c.uv_band]}` : 'text-cream/60'}`}>
                {label === t('pressureLabel') && <TrendIcon className="inline w-3 h-3 -mt-0.5 mr-0.5" />}{sub}
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}

export function Advisories({ items, compact = false }: { items: WeatherAdvisory[]; compact?: boolean }) {
  const { t } = useFarmer()
  if (items.length === 0) {
    return <Card className="p-4 text-sm text-leaf-deep">✓ {t('allClear')}</Card>
  }
  return (
    <div className="space-y-2">
      {items.map((a) => {
        const Icon = CAT_ICON[a.category] ?? CloudSun
        return (
          <article key={a.id} className={`rounded-2xl border p-3.5 ${SEV_STYLE[a.severity]}`}>
            <p className={`flex items-start gap-2 font-semibold text-[15px] leading-snug ${SEV_TEXT[a.severity]}`}>
              <Icon className="w-5 h-5 shrink-0 mt-0.5" /> {a.title}
            </p>
            <p className="mt-1.5 text-sm leading-snug text-soil-dark/80">{a.text}</p>
            {!compact && (
              <>
                <ul className="mt-2 space-y-1">
                  {a.do.map((d) => <li key={d} className="text-sm leading-snug">• {d}</li>)}
                </ul>
                <p className="mt-2 text-[10.5px] text-soil-dark/45">{a.source}</p>
              </>
            )}
          </article>
        )
      })}
    </div>
  )
}

function SprayCard({ v }: { v: WeatherView }) {
  const { t, lang } = useFarmer()
  const hours = v.hourly.slice(0, 24)
  const now = v.spray.now
  const best = v.spray.windows[0]
  return (
    <section>
      <SectionTitle sub={t('sprayLegend')}>
        <span className="flex items-center gap-2"><SprayCan className="w-5 h-5 text-leaf" />{t('sprayWindowTitle')}</span>
      </SectionTitle>
      <Card className="p-4">
        {now && (
          <p className={`text-sm font-semibold ${now.status === 'good' ? 'text-leaf-deep' : now.status === 'caution' ? 'text-[#8a5a17]' : 'text-ember'}`}>
            {t(`spray_${now.status}`)}
            {v.spray.reasons_text && <span className="block text-xs font-normal text-soil-dark/60 mt-0.5">{v.spray.reasons_text}</span>}
          </p>
        )}
        <div className="mt-3 flex gap-[3px]" aria-hidden>
          {hours.map((h) => (
            <span key={h.t} className={`flex-1 h-7 rounded-[4px] ${SPRAY_COLOR[h.spray]} ${h.is_day ? '' : 'opacity-40'}`} title={`${hhmm(h.t)} ${h.spray}`} />
          ))}
        </div>
        <div className="mt-1 flex justify-between text-[10px] text-soil-dark/45">
          {hours.filter((_, i) => i % 6 === 0).map((h) => <span key={h.t}>{hhmm(h.t)}</span>)}
        </div>
        <p className="mt-3 text-sm">
          {best
            ? t('sprayBest').replace('{when}', `${dayLabel(best.start.slice(0, 10), lang)} ${hhmm(best.start)}–${hhmm(best.end)}`)
            : t('sprayNoneShort')}
        </p>
        <Link to="/app/spray" className="mt-2 inline-block text-xs font-medium text-leaf-deep">{t('spray')} →</Link>
      </Card>
    </section>
  )
}

function HourlyChart({ hours }: { hours: WeatherHour[] }) {
  const { t } = useFarmer()
  // A wider drawing on desktop keeps labels at their phone size instead of
  // scaling the whole chart up with the column.
  const wide = useWide()
  if (hours.length < 2) return null
  const W = wide ? 640 : 336, H = wide ? 150 : 120, top = 16, bottom = 22
  const temps = hours.map((h) => h.temp ?? 0)
  const lo = Math.min(...temps) - 1, hi = Math.max(...temps) + 1
  const x = (i: number) => (i / (hours.length - 1)) * (W - 16) + 8
  const y = (v: number) => top + (1 - (v - lo) / (hi - lo || 1)) * (H - top - bottom - 20)
  const line = temps.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return (
    <section>
      <SectionTitle>{t('next24h')}</SectionTitle>
      <Card className="p-3 overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label={t('next24h')}>
          {hours.map((h, i) => {
            const p = h.prob ?? 0
            const bh = (p / 100) * 34
            return <rect key={h.t} x={x(i) - 5} y={H - bottom - bh} width={10} height={bh} rx={2} className="fill-sky-300/70" />
          })}
          <path d={line} fill="none" strokeWidth={2.2} className="stroke-ochre" />
          {hours.map((h, i) => i % 4 === 0 && (
            <g key={h.t}>
              <text x={x(i)} y={y(temps[i]) - 6} textAnchor="middle" className="fill-soil-dark text-[9px] font-semibold">{Math.round(temps[i])}°</text>
              <text x={x(i)} y={H - 6} textAnchor="middle" className="fill-soil-dark/50 text-[9px]">{hhmm(h.t)}</text>
            </g>
          ))}
        </svg>
        <p className="text-[10px] text-soil-dark/50 flex gap-3">
          <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-ochre inline-block" />{t('temp')}</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 bg-sky-300 inline-block rounded-sm" />{t('rainChance')}</span>
        </p>
      </Card>
    </section>
  )
}

function DailyList({ days }: { days: WeatherDay[] }) {
  const { t, lang } = useFarmer()
  const lo = Math.min(...days.map((d) => d.tmin ?? 99)), hi = Math.max(...days.map((d) => d.tmax ?? -99))
  return (
    <section>
      <SectionTitle>{t('next7')}</SectionTitle>
      <Card className="divide-y divide-soil-dark/5">
        {days.map((d) => {
          const left = (((d.tmin ?? lo) - lo) / (hi - lo || 1)) * 100
          const width = (((d.tmax ?? hi) - (d.tmin ?? lo)) / (hi - lo || 1)) * 100
          return (
            <div key={d.on} className="px-3 py-2.5 grid grid-cols-[64px_1fr_auto] items-center gap-3">
              <div>
                <p className="text-sm font-medium">{dayLabel(d.on, lang)}</p>
                <p className="text-[10px] text-soil-dark/50">{t(wmoKey(d.code))}</p>
              </div>
              <div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="w-7 text-right text-soil-dark/60">{d.tmin != null ? Math.round(d.tmin) : '–'}°</span>
                  <span className="relative flex-1 h-1.5 rounded-full bg-soil-dark/10">
                    <span className="absolute inset-y-0 rounded-full bg-gradient-to-r from-sky-400 to-ochre" style={{ left: `${left}%`, width: `${Math.max(width, 4)}%` }} />
                  </span>
                  <span className="w-7 font-semibold">{d.tmax != null ? Math.round(d.tmax) : '–'}°</span>
                </div>
                <p className="mt-1 text-[10.5px] text-soil-dark/55">
                  <Wind className="inline w-3 h-3 -mt-0.5" /> {d.wind_max ?? '–'}–{d.gust_max ?? '–'} km/h · UV {d.uv_max ?? '–'}
                  {d.et0 != null && <> · ET₀ {d.et0}</>}
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-sky-700">{d.rain ?? 0} mm</p>
                <p className="text-[10px] text-soil-dark/50">{d.prob ?? 0}%</p>
              </div>
            </div>
          )
        })}
      </Card>
    </section>
  )
}

function SoilWater({ v }: { v: WeatherView }) {
  const { t } = useFarmer()
  const w = v.water
  const s = v.soil
  if (!s && !w.available) return null
  return (
    <section>
      <SectionTitle sub={t('modelledNote')}>{t('soilWater')}</SectionTitle>
      <Card className="p-4 space-y-4">
        {s?.ph && (
          <div className="flex items-baseline gap-3 border-b border-soil-dark/10 pb-3">
            <div>
              <p className="text-xs text-soil-dark/60">{t('soilPh')}</p>
              <p className="text-lg font-semibold">
                {s.ph.value} <span className="text-sm font-normal text-soil-dark/70">{s.ph.band}</span>
              </p>
            </div>
            {/* Where the number came from decides how much a farmer should lean
                on it: their own sensor, the card they were given, or a map. */}
            <p className="ml-auto text-right text-[11px] leading-tight text-soil-dark/50">
              {t(`ph_${s.ph.how}`)}<br />{s.ph.source}
            </p>
          </div>
        )}
        {s && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-soil-dark/60">{t('soilTemp')}</p>
              <p className="text-lg font-semibold">{s.temp_surface ?? '–'}°C</p>
              <p className="text-[11px] text-soil-dark/50">{t('surface')} · 6 cm {s.temp_6cm ?? '–'}°C</p>
            </div>
            <div>
              <p className="text-xs text-soil-dark/60">{t('soilMoisture')}</p>
              <div className="mt-1 space-y-1">
                {s.moisture.map((m) => (
                  <div key={m.depth} className="flex items-center gap-2 text-[11px]">
                    <span className="w-12 text-soil-dark/55">{m.depth}</span>
                    <span className="relative flex-1 h-1.5 rounded-full bg-soil-dark/10">
                      <span className="absolute inset-y-0 left-0 rounded-full bg-sky-500" style={{ width: `${Math.min(100, (m.pct ?? 0) * 2)}%` }} />
                    </span>
                    <span className="w-8 text-right font-medium">{m.pct ?? '–'}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        {w.available && (
          <div className="border-t border-soil-dark/10 pt-3">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <p><span className="block text-xs text-soil-dark/60">{t('et0Today')}</span><b>{w.et0_today ?? '–'} mm</b></p>
              <p><span className="block text-xs text-soil-dark/60">{t('cropUseToday')}</span><b>{w.etc_today ?? '–'} mm</b> <span className="text-[10px] text-soil-dark/45">Kc {w.kc}</span></p>
              <p><span className="block text-xs text-soil-dark/60">{t('weekUsed')}</span><b>{w.etc_week} mm</b></p>
              <p><span className="block text-xs text-soil-dark/60">{t('weekRain')}</span><b>{w.eff_rain_week} mm</b></p>
            </div>
            <p className={`mt-3 text-sm font-semibold ${w.verdict === 'irrigate' ? 'text-ember' : 'text-leaf-deep'}`}>
              <Droplets className="inline w-4 h-4 -mt-0.5 mr-1" />
              {t(`wv_${w.verdict}`)}
              {!!w.deficit && <span className="font-normal text-soil-dark/60"> · {t('shortfall')} {w.deficit} mm</span>}
            </p>
          </div>
        )}
      </Card>
    </section>
  )
}

/** Compact card for Home: now, the top advice, and the way in. */
export function WeatherNowCard() {
  const { farmId, lang, t } = useFarmer()
  const w = useAsync(() => api.weather(farmId!, lang), [farmId, lang], ['weather', farmId!, lang].join(':'))
  const v = w.data
  if (!v) return null
  const c = v.current
  const top = v.advisories.find((a) => a.rule !== 'spray_window')
  return (
    <Link to="/app/weather" className="block rounded-3xl bg-white border border-soil-dark/10 p-4 active:scale-[0.99] transition-transform lg:h-full lg:p-6 lg:flex lg:flex-col lg:hover:border-leaf/40">
      <div className="flex items-center gap-4">
        <div className="shrink-0 w-16 text-center lg:w-20">
          <p className="text-3xl font-semibold leading-none lg:text-5xl">{c.temp != null ? Math.round(c.temp) : '–'}°</p>
          <p className="text-[10px] text-soil-dark/55 mt-1 lg:text-xs">{t(wmoKey(c.code))}</p>
        </div>
        <div className="flex-1 grid grid-cols-3 gap-2 text-center">
          <p className="text-[10px] text-soil-dark/55"><Droplets className="w-3.5 h-3.5 mx-auto text-sky-600" />{c.rh}%</p>
          <p className="text-[10px] text-soil-dark/55"><CloudRain className="w-3.5 h-3.5 mx-auto text-sky-600" />{c.prob_3h ?? '–'}%</p>
          <p className="text-[10px] text-soil-dark/55"><Wind className="w-3.5 h-3.5 mx-auto text-sky-600" />{c.wind} km/h</p>
        </div>
      </div>
      {top && (
        <p className={`mt-3 rounded-xl border px-3 py-2 text-[13px] font-medium leading-snug ${SEV_STYLE[top.severity]} ${SEV_TEXT[top.severity]}`}>
          {top.title}
        </p>
      )}
      <p className="mt-2 text-xs font-medium text-leaf-deep lg:mt-auto lg:pt-3 lg:text-sm">{t('fullWeather')} →</p>
    </Link>
  )
}

const NDVI_COLOR = { sparse: 'bg-ochre/20 text-[#8a5a17]', low: 'bg-lime-100 text-lime-800', moderate: 'bg-leaf/15 text-leaf-deep', dense: 'bg-leaf text-cream' } as const

/** Greenness from clear Sentinel-2 / Landsat 8 images, and satellite soil data. */
function SatelliteCard() {
  const { farmId, lang, t } = useFarmer()
  const s = useAsync(() => api.satellite(farmId!), [farmId], ['satellite', farmId!].join(':'))
  const d = s.data
  if (!d || !d.available || !d.latest) return null
  const date = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString(bcp47(lang), { day: 'numeric', month: 'short' })
  const series = d.series ?? []
  const W = 300, H = 44
  const xs = (i: number) => (series.length > 1 ? (i / (series.length - 1)) * (W - 8) + 4 : W / 2)
  const ys = (v: number) => H - 4 - v * (H - 8)
  return (
    <section>
      <SectionTitle sub={d.source}>
        <span className="flex items-center gap-2"><Satellite className="w-5 h-5 text-leaf" />{t('satTitle')}</span>
      </SectionTitle>
      <Card className="p-4 space-y-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-xs text-soil-dark/60">{t('satNdvi')}</p>
            <p className="text-3xl font-semibold leading-none mt-1">{d.latest.mean.toFixed(2)}</p>
          </div>
          {d.band && <span className={`rounded-full px-3 py-1 text-xs font-semibold ${NDVI_COLOR[d.band]}`}>{t(`ndvi_${d.band}`)}</span>}
        </div>
        {series.length > 1 && (
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-11" aria-hidden>
            <path d={series.map((p, i) => `${i ? 'L' : 'M'}${xs(i)},${ys(p.mean)}`).join(' ')} fill="none" strokeWidth={2} className="stroke-leaf" />
            {series.map((p, i) => <circle key={p.on} cx={xs(i)} cy={ys(p.mean)} r={2.5} className="fill-leaf-deep" />)}
          </svg>
        )}
        <p className="text-xs text-soil-dark/60">{t('satLastClear').replace('{date}', date(d.latest.on)).replace('{source}', d.latest.source)}</p>
        {d.previous && d.change != null && (
          <p className={`text-sm font-medium ${d.drop ? 'text-ember' : 'text-soil-dark/70'}`}>
            {t('satChange').replace('{date}', date(d.previous.on)).replace('{v}', `${d.change > 0 ? '+' : ''}${d.change.toFixed(2)}`)}
            {d.drop && <span className="block">{t('satDrop')}</span>}
          </p>
        )}
        {(d.age_days ?? 0) > 20 && <p className="text-xs rounded-xl bg-sky-50 text-sky-900 p-2.5">{t('satCloudy')}</p>}
        {d.soil && (
          <div className="grid grid-cols-2 gap-3 border-t border-soil-dark/10 pt-3 text-sm">
            <p><span className="block text-xs text-soil-dark/60">{t('satSoil')}</span><b>{d.soil.moisture_pct}%</b></p>
            <p><span className="block text-xs text-soil-dark/60">{t('satSoilTemp')}</span><b>{d.soil.t10_c}°C</b></p>
          </div>
        )}
      </Card>
    </section>
  )
}

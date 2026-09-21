import { CloudRain, Droplets } from 'lucide-react'
import type { Home } from '../../api/types'
import { Pill } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'
import { bcp47 } from '../../lib/i18n'

export default function WeatherStrip({ weather, rain }: { weather: Home['weather']; rain: Home['rain_context'] }) {
  const { t, lang } = useFarmer()
  const days = weather.days.slice(-10)
  const src = weather.source
  const dep = rain?.departure_pct

  return (
    <section className="rounded-2xl bg-white border border-soil-dark/10 p-4 lg:p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold flex items-center gap-1.5">
          <CloudRain className="w-4 h-4 text-leaf" />
          {t('weather')}
        </h2>
        <Pill tone={src === 'live' ? 'leaf' : src === 'unavailable' ? 'ember' : 'neutral'}>{t(`weatherSrc_${src}`)}</Pill>
      </div>

      {days.length > 0 && (
        <div className="mt-3 flex gap-1 overflow-x-auto no-scrollbar -mx-1 px-1 lg:grid lg:grid-cols-5 lg:gap-1.5 lg:overflow-visible">
          {days.map((d) => {
            const date = new Date(d.on + 'T00:00:00')
            const humid = (d.rh_max ?? 0) >= 90
            return (
              <div
                key={d.on}
                className={`shrink-0 w-[52px] rounded-xl px-1 py-2 text-center lg:w-auto ${
                  d.forecast ? 'bg-sky-50 border border-dashed border-sky-200' : 'bg-cream/70'
                }`}
              >
                <p className="text-[10px] text-soil-dark/50">
                  {date.toLocaleDateString(bcp47(lang), { day: 'numeric', month: 'short' })}
                </p>
                <p className="text-xs font-semibold mt-0.5">{d.t_max != null ? Math.round(d.t_max) : '–'}°</p>
                <p className="text-[10px] text-soil-dark/50">{d.t_min != null ? Math.round(d.t_min) : '–'}°</p>
                <p className={`mt-1 text-[10px] font-medium flex items-center justify-center gap-0.5 ${humid ? 'text-ember' : 'text-soil-dark/60'}`}>
                  <Droplets className="w-2.5 h-2.5" />
                  {d.rh_max != null ? Math.round(d.rh_max) : '–'}
                </p>
                <p className="text-[10px] text-sky-700">{d.rain_mm ? `${d.rain_mm.toFixed(0)}mm` : '·'}</p>
              </div>
            )
          })}
        </div>
      )}

      {rain?.text && (
        <div className="mt-3 flex items-center gap-3 rounded-xl bg-cream/70 p-3">
          <span
            className={`shrink-0 min-w-[56px] text-center rounded-lg py-1.5 text-sm font-semibold ${
              dep == null ? '' : dep > 25 ? 'bg-sky-100 text-sky-800' : dep < -25 ? 'bg-ochre/20 text-[#8a5a17]' : 'bg-leaf/15 text-leaf-deep'
            }`}
          >
            {dep != null ? `${dep > 0 ? '+' : ''}${dep}%` : '–'}
          </span>
          <p className="text-[12px] leading-snug text-soil-dark/70">
            <span className="block font-medium text-soil-dark text-xs">{t('rainVsNormal')}</span>
            {rain.text}
          </p>
        </div>
      )}
    </section>
  )
}

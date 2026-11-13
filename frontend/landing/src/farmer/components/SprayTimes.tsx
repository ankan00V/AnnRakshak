import { FlaskConical, SprayCan } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Lang, WeatherView } from '../../api/types'
import { bcp47 } from '../../lib/i18n'
import { useFarmer } from '../FarmerContext'
import { PANEL } from '../tokens'
import { PanelHead } from '../ui'

const SPRAY = {
  good: { bar: 'bg-[#4b8b3b]', box: 'bg-[#f1f6ec] text-[#2f5a24]', dot: 'bg-[#4b8b3b]', key: 'wxGood' },
  caution: { bar: 'bg-ochre', box: 'bg-[#fbf0dc] text-[#7a4f12]', dot: 'bg-ochre', key: 'wxCareful' },
  avoid: { bar: 'bg-ember/80', box: 'bg-[#fdf0ed] text-[#9a2f17]', dot: 'bg-ember/80', key: 'wxAvoid' },
} as const

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

/** Whether to spray now, the next day of hours in colour, and the good times. */
export default function SprayTimes({ v, toCheck = true }: { v: WeatherView; toCheck?: boolean }) {
  const { t, lang } = useFarmer()
  const hours = (v.hourly ?? []).slice(0, 24)   // a cached copy from before hours were sent has none
  const now = v.spray.now
  const windows = v.spray.windows.slice(0, 3)
  return (
    <section className={`${PANEL} p-5`}>
      <PanelHead icon={SprayCan} title={t('wxSprayTitle')} />
      {now && (
        <div className={`mt-4 rounded-[20px] p-3.5 ${SPRAY[now.status].box}`}>
          <p className="flex items-center gap-2 text-[17px] font-semibold">
            <span className={`h-3 w-3 shrink-0 rounded-full ${SPRAY[now.status].dot}`} aria-hidden />
            {t(`spray_${now.status}`)}
          </p>
          {v.spray.reasons_text && <p className="mt-1 text-[14px] text-soil-dark/80">{v.spray.reasons_text}</p>}
        </div>
      )}
      {hours.length > 0 && (
        <div className="mt-4">
          <div className="flex gap-[3px]" aria-hidden>
            {hours.map((h) => (
              <span key={h.t} className={`h-8 flex-1 rounded-[5px] ${SPRAY[h.spray].bar} ${h.is_day ? '' : 'opacity-45'}`} />
            ))}
          </div>
          <div className="mt-1.5 flex justify-between text-[12px] text-soil-dark/70 tabular-nums">
            {hours.filter((_, i) => i % 6 === 0).map((h, i) => <span key={h.t}>{i === 0 ? t('wxNow') : hhmm(h.t)}</span>)}
          </div>
          <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-soil-dark/75">
            {(['good', 'caution', 'avoid'] as const).map((k) => (
              <span key={k} className="flex items-center gap-1.5">
                <span className={`h-2.5 w-2.5 rounded-full ${SPRAY[k].dot}`} aria-hidden />{t(SPRAY[k].key)}
              </span>
            ))}
          </p>
        </div>
      )}
      <h3 className="mt-5 text-[16px] font-semibold">{t('wxBestTimes')}</h3>
      {windows.length === 0 ? (
        <p className="mt-2 text-[15px] text-soil-dark/80">{t('sprayNoneShort')}</p>
      ) : (
        <ul className="mt-2 divide-y divide-soil-dark/[0.07]">
          {windows.map((x) => (
            <li key={x.start} className="flex items-center justify-between gap-3 py-2.5 text-[15px]">
              <span className="font-medium">{dayLabel(x.start.slice(0, 10), lang)}</span>
              <span className="tabular-nums">{hhmm(x.start)} – {hhmm(x.end)}</span>
            </li>
          ))}
        </ul>
      )}
      {toCheck && <Link to="/app/spray" className="mt-4 flex min-h-[48px] items-center justify-center gap-2 rounded-full bg-[#eef3e6] text-[15px] font-semibold text-leaf-deep ring-1 ring-[#4b8b3b]/15 transition-colors hover:bg-[#e6eedb]">
        <FlaskConical className="h-5 w-5" aria-hidden /> {t('qaSpray')}
      </Link>}
    </section>
  )
}

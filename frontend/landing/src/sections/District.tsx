import Reveal from '../ui/Reveal'
import { useFarmer } from '../farmer/FarmerContext'

/** The district office's view of the same ground: plots running to a
 *  village, and over them the officer's map, drawn only from cases an expert
 *  has confirmed. */

function DistrictMap() {
  const { t } = useFarmer()
  // Three confirmed cases and their 5 km rings. Every field inside a ring was
  // told to inspect (fourteen, as the legend says); the grey ones outside
  // every ring were not, which is the point of drawing them.
  const cases = [{ cx: 62, cy: 60, r: 30 }, { cx: 166, cy: 94, r: 28 }, { cx: 104, cy: 128, r: 21 }]
  const told = [
    [44, 48], [78, 44], [70, 80], [50, 70], [84, 62],
    [150, 82], [184, 86], [170, 114], [152, 106], [186, 104],
    [92, 120], [118, 124], [100, 142], [114, 140],
  ]
  const others = [[210, 28], [20, 130], [222, 148], [132, 26], [30, 18], [214, 62]]
  return (
    <div className="rounded-[18px] bg-white p-4 text-soil-dark shadow-[0_24px_50px_-24px_rgba(0,0,0,0.5)] ring-1 ring-black/5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[14px] font-semibold leading-snug">{t('landMapTitle')}</p>
        <p className="text-[11px] text-soil-dark/60">{t('landMapRings')}</p>
      </div>
      <svg viewBox="0 0 244 160" className="mt-3 h-auto w-full rounded-xl" role="img"
        aria-label={t('landMapLabel')}>
        <rect width="244" height="160" fill="#eef0ea" />
        <path d="M0 53h244M0 106h244M80 0v160M170 0v160" stroke="#d3d8cb" strokeWidth="1" fill="none" />
        {cases.map(({ cx, cy, r }) => (
          <circle key={`r${cx}`} cx={cx} cy={cy} r={r} fill="#b0472a" fillOpacity="0.08" stroke="#b0472a" strokeOpacity="0.5" strokeDasharray="3 3" />
        ))}
        {others.map(([x, y]) => <circle key={`o${x}-${y}`} cx={x} cy={y} r="3.5" fill="#b9bfb0" />)}
        {told.map(([x, y]) => <circle key={`t${x}-${y}`} cx={x} cy={y} r="3.5" fill="#c8862d" />)}
        {cases.map(({ cx, cy }) => <circle key={`c${cx}`} cx={cx} cy={cy} r="5" fill="#b0472a" />)}
      </svg>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-soil-dark/70">
        <li className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-ember" />{t('landMapConfirmed').replace('{n}', '3')}</li>
        <li className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-ochre" />{t('landMapTold').replace('{n}', '14')}</li>
        <li className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-[#b9bfb0]" />{t('landMapLeft')}</li>
      </ul>
    </div>
  )
}

export default function District() {
  const { t } = useFarmer()
  return (
    <section id="district" className="w-full bg-[#f6f1e6] text-[#1f3a26]">
      <div className="mx-auto grid max-w-[1720px] gap-10 px-6 pb-16 pt-4 md:px-12 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:items-center lg:gap-[4vw] lg:px-[7vw] lg:pb-[clamp(56px,5vw,96px)] lg:pt-0">
        <Reveal>
          <figure className="relative">
            <img src="/footage/village-fields.webp" alt={t('landDistrictAlt')} loading="lazy" decoding="async"
              className="aspect-[16/9] w-full rounded-[24px] object-cover object-[center_60%]" />
            <div className="relative -mt-20 mx-4 sm:mx-auto sm:max-w-[360px] lg:absolute lg:bottom-[7%] lg:right-[5%] lg:m-0 lg:w-[44%] lg:max-w-none">
              <DistrictMap />
            </div>
          </figure>
        </Reveal>
        <Reveal delay={80}>
          <p className="text-[14px] font-semibold text-[#9a6210] lg:text-[clamp(12px,0.9vw,16px)]">{t('landDistrictKicker')}</p>
          <h2 className="mt-3 font-display text-[34px] leading-[1.08] tracking-[-0.01em] text-balance lg:mt-[0.9vw] lg:text-[clamp(28px,2.35vw,46px)]">
            {t('landDistrictTitle')}
          </h2>
          <p className="mt-4 text-[15px] leading-relaxed text-[#3d4a40] text-pretty lg:mt-[1.1vw] lg:text-[clamp(13px,0.98vw,17px)]">
            {t('landDistrictSub')}
          </p>
          <p className="mt-5 border-t border-black/10 pt-3 text-[13px] text-[#55615a] lg:mt-[1.3vw] lg:text-[clamp(12px,0.85vw,15px)]">
            {t('landDistrictNote')}
          </p>
        </Reveal>
      </div>
    </section>
  )
}

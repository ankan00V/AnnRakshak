import { CheckCircle2, ClipboardCheck, Satellite, Volume2 } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import Reveal from '../ui/Reveal'
import FootageBackdrop from '../ui/FootageBackdrop'

/** The app, shown working on the ground it is about.
 *
 *  Every piece of footage on this page is here for one reason: it is the
 *  moment in a season when the screen laid over it is what a farmer or an
 *  officer actually sees. The ground is real and so is the screen — nothing
 *  is drawn over a field that the app does not do at that point.
 *
 *    sowing     last season's stubble worked into strips, seed on the trolley
 *               → the field card on day 1, when the count starts
 *    tillering  standing paddy
 *               → the leaf-blast alert, in Marathi, as Bhandara gets it
 *    harvest    a combine in the paddy, the farmer in the cut rows
 *               → the harvest date, from degree-days and the satellite
 *    after      the straw baled off the cleared field
 *               → the season closed and kept, ready to sow again
 *    district   plots running to a village
 *               → the officer's map of the same ground
 *
 *  Day 41 is tillering in the rice calendar (days 26–55), which is the stage
 *  in the photograph. Day 126 is the harvest the phenology model predicted
 *  for a real rice field sown on 13 July, from that field's own weather.
 */

const SCRIM = <div className="absolute inset-0 bg-gradient-to-t from-soil-dark/45 via-transparent to-transparent" />

function Still({ src, alt, focus = 'object-center' }: { src: string; alt: string; focus?: string }) {
  return (
    <div className="absolute inset-0">
      <img src={src} alt={alt} loading="lazy" decoding="async" className={`w-full h-full object-cover ${focus}`} />
      {SCRIM}
    </div>
  )
}

/** A screen from the app, at the size it would be read. */
function Screen({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-2xl bg-white p-4 sm:p-5 text-soil-dark shadow-2xl shadow-black/40 ring-1 ring-black/5">
      {children}
    </div>
  )
}

const STAGES = ['Nursery', 'Tillering', 'Panicle', 'Flowering', 'Grain fill']

function FieldScreen() {
  return (
    <Screen>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] text-soil-dark/60">Bhandara · 2.5 acre</p>
          <p className="mt-1 font-instrument-serif text-[1.75rem] leading-none">Rice (paddy)</p>
        </div>
        <div className="text-right">
          <p className="font-instrument-serif text-[2.25rem] leading-none text-leaf-deep">1</p>
          <p className="text-[10px] text-soil-dark/60">day</p>
        </div>
      </div>
      <div className="mt-4 flex gap-1" aria-hidden>
        {STAGES.map((s, i) => (
          <span key={s} className="h-1.5 flex-1 rounded-full bg-soil-dark/10 overflow-hidden">
            {i === 0 && <span className="block h-full w-[6%] bg-ochre" />}
          </span>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] text-soil-dark/50">
        {STAGES.map((s, i) => (
          <span key={s} className={i === 0 ? 'font-semibold text-soil-dark' : ''}>{s}</span>
        ))}
      </div>
      <p className="mt-3 border-t border-soil-dark/10 pt-3 text-[11px] text-soil-dark/65">
        Sown 13 Jul · harvest expected around 16 Nov
      </p>
    </Screen>
  )
}

function AlertScreen() {
  return (
    <Screen>
      <div className="flex items-center justify-between gap-3">
        <span className="rounded-full bg-ember/10 px-2.5 py-1 text-[11px] font-medium text-ember">जास्त धोका</span>
        <Volume2 className="w-4 h-4 text-leaf-deep" aria-label="Read aloud" />
      </div>
      <p lang="mr" className="mt-3 text-[15px] font-semibold leading-snug">शेत तपासणी: करपा (ब्लास्ट)</p>
      <p lang="mr" className="mt-1.5 text-[12px] font-light leading-relaxed text-soil-dark/75">
        सलग 5 दिवस आर्द्रता 90% पेक्षा जास्त व सरासरी तापमान 22–28°C. हे हवामान करपा रोगासाठी अनुकूल आहे.
      </p>
      <p className="mt-3 flex items-center gap-1.5 border-t border-soil-dark/10 pt-3 text-[11px] font-semibold text-leaf-deep">
        <ClipboardCheck className="w-3.5 h-3.5" aria-hidden />
        <span lang="mr">आज हे तपासा</span>
      </p>
      <p lang="mr" className="mt-1.5 flex gap-2 text-[12px] font-light leading-relaxed text-soil-dark/80">
        <CheckCircle2 className="w-3.5 h-3.5 text-leaf shrink-0 mt-0.5" aria-hidden />
        तिरक्या रेषेत चाला व 10 रोपांच्या वरच्या पानांवर डोळ्यासारखे राखाडी ठिपके पाहा.
      </p>
    </Screen>
  )
}

function HarvestScreen() {
  return (
    <Screen>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-soil-dark/60">Expected harvest</p>
        <span className="inline-flex items-center gap-1 rounded-full bg-leaf/10 px-2 py-0.5 text-[10px] font-medium text-leaf-deep">
          <Satellite className="w-3 h-3" aria-hidden /> Seen from orbit
        </span>
      </div>
      <p className="mt-1 font-instrument-serif text-[2.25rem] leading-none">16 Nov</p>
      <div className="mt-4 h-1.5 rounded-full bg-soil-dark/10 overflow-hidden" aria-hidden>
        <span className="block h-full w-[99%] rounded-full bg-ochre" />
      </div>
      <p className="mt-1.5 flex justify-between text-[10px] tabular-nums text-soil-dark/60">
        <span>2,180 degree-days banked</span><span>of 2,200</span>
      </p>
      <p className="mt-3 border-t border-soil-dark/10 pt-3 text-[11px] leading-relaxed text-soil-dark/70">
        The canopy has started to turn. The date now rests on what the satellite saw, not on the estimate.
      </p>
    </Screen>
  )
}

function ClosedScreen() {
  return (
    <Screen>
      <p className="font-semibold leading-snug">This field is harvested</p>
      <p className="mt-1 text-[11px] text-soil-dark/60">Season 1 · 13 Jul – 16 Nov · 126 days</p>
      <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
        {[['3', 'alerts'], ['1', 'case confirmed'], ['2', 'sprays logged']].map(([n, l]) => (
          <div key={l} className="rounded-xl bg-cream px-1 py-2">
            <dt className="sr-only">{l}</dt>
            <dd className="font-instrument-serif text-xl leading-none">{n}</dd>
            <dd className="mt-1 text-[10px] leading-tight text-soil-dark/60">{l}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 grid grid-cols-2 gap-2 text-[12px] font-medium">
        <span className="rounded-full bg-leaf-deep py-2 text-center text-cream">Sow again</span>
        <span className="rounded-full border border-soil-dark/20 py-2 text-center">Turn off</span>
      </div>
    </Screen>
  )
}

function DistrictScreen() {
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
    <Screen>
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-semibold leading-snug">Bhandara · this week</p>
        <p className="text-[11px] text-soil-dark/60">5 km rings</p>
      </div>
      <svg viewBox="0 0 244 160" className="mt-3 w-full h-auto rounded-xl" role="img"
        aria-label="District map: three expert-confirmed cases with 5 km rings; the fourteen fields inside them told to inspect, the fields outside left alone">
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
        <li className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-ember" />3 confirmed</li>
        <li className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-ochre" />14 told to inspect</li>
        <li className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#b9bfb0]" />left alone</li>
      </ul>
    </Screen>
  )
}

type Scene = {
  when: string
  title: string
  body: string
  how: string
  media: ReactNode
  screen: ReactNode
}

const SCENES: Scene[] = [
  {
    when: 'Day 1 · sowing',
    title: 'The day it goes in, the count starts.',
    body: 'A farmer registers the field once: the crop, the sowing date, where it is. From then on the app keeps that plot’s own calendar — its crop stage, the heat it has banked, and the weather over it, not the district’s average.',
    how: 'Weather is fetched for the field’s own coordinates, every day of the season.',
    media: <FootageBackdrop src="/footage/new-season.mp4" poster="/footage/new-season-poster.webp" objectClass="object-[62%_55%]" scrim={SCRIM} />,
    screen: <FieldScreen />,
  },
  {
    when: 'Day 41 · tillering',
    title: 'Told where to look, before anything shows.',
    body: 'Five humid nights at the temperature leaf blast likes. Before a single spot appears, this farmer gets one thing to check today — in Marathi, read aloud — and the alert stays open until they say what they found.',
    how: 'ICAR-IIRR’s leaf-blast conditions, matched against this field’s last five days.',
    media: <Still src="/field/rice.webp" alt="Standing paddy at tillering" />,
    screen: <AlertScreen />,
  },
  {
    when: 'Day 126 · harvest',
    title: 'A harvest date worked out, not guessed.',
    body: 'Degree-days counted from this field’s daily temperatures since sowing. When the satellite sees the canopy turn, what it saw wins over the estimate — and the farmer knows when to book the harvester.',
    how: 'Rice: 2,200 degree-days above 10°C, capped at 35°C. Sentinel-2 and Landsat 8 NDVI.',
    media: <FootageBackdrop src="/footage/field.mp4" poster="/footage/field-poster.webp" objectClass="object-[52%_50%]" scrim={SCRIM} />,
    screen: <HarvestScreen />,
  },
  {
    when: 'After the harvest',
    title: 'The season closes, and is kept.',
    body: 'Alerts stop the day the crop comes off. Every alert, photo and treatment from the season stays on the farmer’s record, and sowing again starts a fresh count from day 1.',
    how: 'Nothing is sent about a field that is no longer standing.',
    media: <FootageBackdrop src="/footage/baling.mp4" poster="/footage/baling-poster.webp" objectClass="object-[45%_60%]" scrim={SCRIM} />,
    screen: <ClosedScreen />,
  },
  {
    when: 'All season · the district office',
    title: 'Every field, as the officer sees it.',
    body: 'A case an expert confirms sends an inspection task to every registered field within 5 km, the same evening. The officer’s map is built from those confirmed cases — not from rumours, and not from the model’s word.',
    how: 'Only expert-confirmed cases draw a ring.',
    media: <Still src="/footage/village-fields.webp" alt="Plots running in rows to a village" focus="object-[center_55%]" />,
    screen: <DistrictScreen />,
  },
]

export default function InTheField() {
  const rail = useRef<HTMLDivElement>(null)
  const [at, setAt] = useState(0)

  // The scene whose left edge is nearest the rail's: snapping puts one there.
  const onRail = () => {
    const el = rail.current
    if (!el) return
    const kids = Array.from(el.children) as HTMLElement[]
    const left = el.getBoundingClientRect().left
    let best = 0
    kids.forEach((k, i) => {
      if (Math.abs(k.getBoundingClientRect().left - left) < Math.abs(kids[best].getBoundingClientRect().left - left)) best = i
    })
    setAt(best)
  }
  const go = (i: number) => {
    const el = rail.current
    const kid = el?.children[i] as HTMLElement | undefined
    if (!el || !kid) return
    const pad = parseFloat(getComputedStyle(el).paddingLeft)
    el.scrollTo({ left: el.scrollLeft + kid.getBoundingClientRect().left - el.getBoundingClientRect().left - pad, behavior: 'smooth' })
  }

  return (
    <section id="in-the-field" className="w-full bg-soil-dark text-cream">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-14 sm:py-20 md:py-28">
        <Reveal className="max-w-3xl">
          <h2 className="font-instrument-serif text-[2rem] sm:text-5xl md:text-[3.5rem] leading-[1.05] text-balance">
            On the ground, all season.
          </h2>
          <p className="mt-4 max-w-2xl text-sm md:text-base font-light leading-relaxed text-cream/75 text-pretty">
            Real fields, filmed by the team. Over each one, the screen a farmer or an officer sees
            at that moment of the season.
          </p>
        </Reveal>

        {/* Below lg the scenes are a row you swipe through, one season stage
            per screen with the next one showing at the edge: five stacked
            scenes were five screens of scrolling on a phone. From lg up they
            stack as alternating rows, and the screen hangs off the corner of
            each frame nearest its words. */}
        <div
          ref={rail}
          onScroll={onRail}
          className="mt-10 sm:mt-14 lg:mt-24 -mx-6 md:-mx-12 px-6 md:px-12 scroll-px-6 md:scroll-px-12
                     flex gap-4 sm:gap-6 overflow-x-auto snap-x snap-mandatory overscroll-x-contain
                     [scrollbar-width:none] [&::-webkit-scrollbar]:hidden
                     lg:mx-0 lg:px-0 lg:block lg:overflow-visible lg:space-y-32"
        >
          {SCENES.map((s, i) => {
            const flip = i % 2 === 1
            return (
              <Reveal key={s.when} className="snap-start shrink-0 w-[86%] sm:w-[62%] md:w-[52%] lg:w-auto">
              <article aria-label={`${s.when}: ${s.title}`}
                className="lg:grid lg:items-center lg:grid-cols-12 lg:gap-x-16">
                <figure className={`relative lg:col-span-7 ${flip ? 'lg:order-2' : ''}`}>
                  <div className="relative aspect-[4/3] lg:aspect-[16/10] overflow-hidden rounded-[1.25rem] lg:rounded-[1.75rem] bg-soil">
                    {s.media}
                  </div>
                  <div className={`relative -mt-14 mx-3 sm:mx-5
                    lg:absolute lg:m-0 lg:w-[320px] lg:-bottom-8 ${flip ? 'lg:-left-10' : 'lg:-right-10'}`}>
                    {s.screen}
                  </div>
                </figure>

                <div className={`mt-6 lg:mt-0 lg:col-span-5 ${flip ? 'lg:order-1' : ''}`}>
                  <p className="text-sm font-medium text-ochre">{s.when}</p>
                  <h3 className="mt-2 font-instrument-serif text-[1.75rem] sm:text-4xl lg:text-[2.5rem] leading-[1.08] text-balance">
                    {s.title}
                  </h3>
                  <p className="mt-3 lg:mt-4 max-w-[46ch] text-[15px] font-light leading-relaxed text-cream/80 text-pretty">
                    {s.body}
                  </p>
                  <p className="mt-4 lg:mt-5 max-w-[46ch] border-t border-cream/10 pt-3 lg:pt-4 text-xs leading-relaxed text-cream/60">
                    {s.how}
                  </p>
                </div>
              </article>
              </Reveal>
            )
          })}
        </div>

        {/* Where you are in the season, and a way to jump. Swipe-only rows
            hide what is past the edge; this says there are five and which
            one is open. */}
        <div className="mt-7 flex items-center justify-between gap-4 lg:hidden">
          <p className="text-xs tabular-nums text-cream/60" aria-live="polite">
            {at + 1} of {SCENES.length}
          </p>
          <div className="flex items-center gap-1">
            {SCENES.map((s, i) => (
              <button key={s.when} type="button" onClick={() => go(i)}
                aria-label={`Show ${s.when}`} aria-current={i === at}
                className="grid h-8 w-8 place-items-center">
                <span className={`block h-1.5 rounded-full transition-all duration-300 ${
                  i === at ? 'w-5 bg-ochre' : 'w-1.5 bg-cream/30'}`} />
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

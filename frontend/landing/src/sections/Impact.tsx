import { CheckCircle2, ClipboardCheck, Volume2 } from 'lucide-react'
import Reveal from '../ui/Reveal'

const FARMER_POINTS = [
  'Where to look, before the symptoms spread — from this field’s own weather and crop stage.',
  'Fewer wasted sprays: the wrong class, the wrong crop and weed killers are all stopped.',
  'An honest “I am not sure”, and a real expert, instead of a confident wrong answer.',
]

const OFFICIAL_POINTS = [
  'Hotspots built from expert-confirmed cases, not rumours, with a 5 km spread radius.',
  'A queue that measures field accuracy instead of taking the model’s word for it.',
  'A weekly risk outlook by pest and district — and which ICAR bio-inputs to stock now.',
]

function Points({ points, dot }: { points: string[]; dot: string }) {
  return (
    <ul className="mt-7 space-y-4">
      {points.map((p) => (
        <li key={p} className="flex gap-3.5 text-sm md:text-[15px] font-light leading-relaxed text-cream/80 text-pretty">
          <span aria-hidden className={`mt-[9px] w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} />
          {p}
        </li>
      ))}
    </ul>
  )
}

/** The alert as it reaches a Bhandara farmer: her language, her weather, two things to check. */
function AlertVignette() {
  return (
    <div className="mt-9 rounded-[1.75rem] bg-cream/[0.06] ring-1 ring-cream/10 p-3">
      <div className="rounded-3xl bg-cream p-5 text-soil-dark shadow-xl shadow-black/20">
        <div className="flex items-center justify-between gap-3">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-ember/10 px-2.5 py-1 text-[11px] font-medium text-ember">
            जास्त धोका
          </span>
          <Volume2 className="w-4 h-4 text-leaf-deep" aria-hidden />
        </div>
        <p lang="mr" className="mt-3 text-base font-medium leading-snug">शेत तपासणी: करपा (ब्लास्ट)</p>
        <p lang="mr" className="mt-2 text-[13px] font-light leading-relaxed text-soil-dark/75">
          22/09 ते 26/09 सलग 5 दिवस आर्द्रता 90% पेक्षा जास्त व सरासरी तापमान 22–28°C राहिले. हे हवामान
          करपा रोगासाठी अनुकूल आहे.
        </p>
        <div className="mt-4 border-t border-soil-dark/10 pt-3">
          <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-leaf-deep">
            <ClipboardCheck className="w-3.5 h-3.5" aria-hidden />
            आज हे तपासा
          </p>
          <ul lang="mr" className="mt-2.5 space-y-2 text-[13px] font-light leading-relaxed text-soil-dark/80">
            <li className="flex gap-2">
              <CheckCircle2 className="w-4 h-4 text-leaf shrink-0 mt-0.5" aria-hidden />
              आज तिरक्या रेषेत चाला व 10 रोपांच्या वरच्या पानांवर डोळ्यासारखे राखाडी ठिपके पाहा.
            </li>
            <li className="flex gap-2">
              <CheckCircle2 className="w-4 h-4 text-leaf shrink-0 mt-0.5" aria-hidden />
              5 रोपांवर लोंबीखालची गाठ तपासा — गाठ काळी असल्यास लगेच तज्ज्ञांना दाखवा.
            </li>
          </ul>
        </div>
      </div>
      <p className="px-2 pt-3 pb-1 text-[11px] text-cream/70">
        A real alert: the rule is ICAR-IIRR’s, the weather is this farm’s, and it stays open until
        she records what she found.
      </p>
    </div>
  )
}

/** Confirmed cases, the farms inside their spread radius, and where scouts go next. */
function HotspotVignette() {
  const cases = [
    { cx: 58, cy: 62, r: 26 },
    { cx: 150, cy: 104, r: 22 },
    { cx: 104, cy: 158, r: 18 },
  ]
  const awaiting = [{ cx: 196, cy: 54 }, { cx: 76, cy: 124 }, { cx: 168, cy: 160 }]
  const advised = [{ cx: 128, cy: 40 }, { cx: 36, cy: 104 }, { cx: 208, cy: 128 }, { cx: 148, cy: 188 }]

  return (
    <div className="mt-9 rounded-[1.75rem] bg-cream/[0.06] ring-1 ring-cream/10 p-3">
      <div className="rounded-3xl bg-[#eef0ea] p-4">
        <svg viewBox="0 0 244 210" className="w-full h-auto" role="img"
          aria-label="District map: three expert-confirmed cases with 5 km spread rings, farms awaiting an expert, and AI-advised cases">
          <rect width="244" height="210" rx="12" fill="#e7eae1" />
          {/* field boundaries, kept faint */}
          <g stroke="#c9d0c0" strokeWidth="1" fill="none">
            <path d="M0 70h244M0 140h244M80 0v210M170 0v210" />
          </g>
          {cases.map(({ cx, cy, r }) => (
            <g key={`${cx}-${cy}`}>
              <circle cx={cx} cy={cy} r={r} fill="#b0472a" fillOpacity="0.1" stroke="#b0472a"
                strokeOpacity="0.45" strokeDasharray="3 3" />
              <circle cx={cx} cy={cy} r="5" fill="#b0472a" />
            </g>
          ))}
          {awaiting.map(({ cx, cy }) => <circle key={`a${cx}`} cx={cx} cy={cy} r="4.5" fill="#2f6fa8" />)}
          {advised.map(({ cx, cy }) => <circle key={`d${cx}`} cx={cx} cy={cy} r="4.5" fill="#c8862d" />)}
        </svg>
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[11px] text-soil-dark/70">
          <li className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-ember" />Expert-confirmed</li>
          <li className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#2f6fa8]" />Awaiting expert</li>
          <li className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-ochre" />AI-advised</li>
        </ul>
      </div>
      <p className="px-2 pt-3 pb-1 text-[11px] text-cream/70">
        A confirmed case sends an inspection task to every farm inside its ring — the same evening.
      </p>
    </div>
  )
}

export default function Impact() {
  return (
    <section id="impact" className="w-full bg-soil-dark text-cream">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-20 md:py-28">
        <div className="grid gap-14 md:gap-12 lg:grid-cols-2 lg:gap-16">
          <Reveal>
            <div className="lg:pr-6">
              <h2 className="font-instrument-serif text-[2rem] sm:text-4xl md:text-5xl">For farmers</h2>
              <p className="mt-3 text-sm font-light leading-relaxed text-cream/75 text-pretty">
                One screen, in her language, that says what to do today.
              </p>
              <Points points={FARMER_POINTS} dot="bg-ochre" />
              <AlertVignette />
            </div>
          </Reveal>

          <Reveal delay={120}>
            <div id="for-officials" className="scroll-mt-24 lg:border-l lg:border-cream/10 lg:pl-16">
              <h2 className="font-instrument-serif text-[2rem] sm:text-4xl md:text-5xl">For officials</h2>
              <p className="mt-3 text-sm font-light leading-relaxed text-cream/75 text-pretty">
                The district, as it actually stands this week.
              </p>
              <Points points={OFFICIAL_POINTS} dot="bg-cream/60" />
              <HotspotVignette />
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

import { BellRing, Camera, HelpCircle, Sprout, UserCheck } from 'lucide-react'
import Reveal from '../ui/Reveal'

/** Five steps, each one line a farmer can read at a glance. The order is the
 *  point, so these are the one numbered sequence on the page. */
const STEPS = [
  { icon: BellRing, label: 'Get a warning', line: 'It tells you what to check, before the damage shows.' },
  { icon: Camera, label: 'Take a photo', line: 'It names the disease or pest on the leaf.' },
  { icon: HelpCircle, label: 'Not sure?', line: 'It asks you one question, or sends it to an expert.' },
  { icon: Sprout, label: 'Treat it', line: 'The safest fix first, with the right dose for your field.' },
  { icon: UserCheck, label: 'Check back', line: 'Four days later it asks if the crop is better.' },
]

/** What happened to 126 held-out ICAR photos the model had never seen. */
const GATE = [
  { pct: 89.7, label: 'Got an answer', tone: 'bg-ochre' },
  { pct: 0.8, label: 'Asked a question', tone: 'bg-cream/70' },
  { pct: 9.5, label: 'Sent to an expert', tone: 'bg-cream/30' },
]

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="w-full bg-leaf-deep text-cream">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-14 sm:py-20 md:py-24">
        <Reveal className="max-w-3xl">
          <h2 className="font-instrument-serif text-[2rem] sm:text-5xl md:text-[3.5rem] leading-[1.05] text-balance">
            From a warning to a crop that’s better.
          </h2>
        </Reveal>

        <ol className="mt-10 sm:mt-14 grid gap-6 md:grid-cols-5 md:gap-6">
          {STEPS.map(({ icon: Icon, label, line }, i) => (
            <Reveal key={label} delay={i * 70}>
              <li className="relative flex items-start gap-4 md:block">
                {i < STEPS.length - 1 && (
                  <span aria-hidden className="hidden md:block absolute top-6 left-14 right-[-1.5rem] h-px bg-cream/15" />
                )}
                <span className="relative flex items-center justify-center w-12 h-12 shrink-0 rounded-full bg-cream/[0.08] ring-1 ring-cream/15">
                  <Icon className="w-5 h-5 text-ochre" aria-hidden />
                  <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-ochre text-[11px] font-semibold text-soil-dark">
                    {i + 1}
                  </span>
                </span>
                <div className="md:mt-5">
                  <h3 className="text-base md:text-lg font-medium leading-snug">{label}</h3>
                  <p className="mt-1 text-sm font-light leading-relaxed text-cream/75 text-pretty">{line}</p>
                </div>
              </li>
            </Reveal>
          ))}
        </ol>

        {/* The honesty of it, in a farmer's words: what happened to photos the
            model had never seen. The thresholds behind it belong in the docs. */}
        <Reveal className="mt-12 sm:mt-16 md:mt-20">
          <div className="grid gap-6 border-t border-cream/15 pt-8 md:grid-cols-12 md:gap-10">
            <h3 className="md:col-span-5 font-instrument-serif text-[1.75rem] sm:text-4xl leading-[1.08] text-balance">
              When it isn’t sure, it says so.
            </h3>
            <div className="md:col-span-7">
              <p className="text-[15px] font-light leading-relaxed text-cream/80 text-pretty">
                Tested on 126 crop photos it had never seen: 9 in 10 got an answer, and 98 in 100 of
                those answers were right. The rest got one question, or went to a real expert —
                never a guess.
              </p>
              <div className="mt-5 flex h-2.5 w-full overflow-hidden rounded-full bg-cream/10" role="img"
                aria-label="Of 126 photos: 89.7% got an answer, 0.8% were asked a question, 9.5% were sent to an expert">
                {GATE.map(({ pct, label, tone }) => (
                  <span key={label} className={`${tone} h-full`} style={{ width: `${pct}%` }} />
                ))}
              </div>
              <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-cream/70">
                {GATE.map(({ pct, label, tone }) => (
                  <li key={label} className="flex items-center gap-1.5">
                    <span aria-hidden className={`h-2 w-2 rounded-full ${tone}`} />
                    {label} · {pct}%
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

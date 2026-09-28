import { BellRing, Camera, HelpCircle, Sprout, UserCheck } from 'lucide-react'
import Reveal from '../ui/Reveal'

const STEPS = [
  { icon: BellRing, label: 'Alert', line: 'Weather, crop stage, traps and confirmed nearby cases say where to look — before damage shows.' },
  { icon: Camera, label: 'Photo', line: 'The model names the disease or pest, and shows the part of the leaf it read.' },
  { icon: HelpCircle, label: 'Ask or escalate', line: 'Torn between two? One field question. Still unsure? A KVK expert, never a guess.' },
  { icon: Sprout, label: 'Act', line: 'Safest step first, a dose worked out for your plot, and a spray check before you buy.' },
  { icon: UserCheck, label: 'Follow up', line: 'A day-4 check-in. A confirmed case warns the neighbours and is recorded against the model.' },
]

/** What the gate did on the 126 held-out ICAR photos it has never seen. */
const GATE = [
  { pct: 89.7, label: 'Advised', note: '98.2% of those were right', tone: 'bg-ochre' },
  { pct: 0.8, label: 'Asked one question', note: 'the answer settled it every time', tone: 'bg-cream/70' },
  { pct: 9.5, label: 'Sent to an expert', note: 'the farmer waits for a person', tone: 'bg-cream/25' },
]

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="w-full bg-leaf-deep text-cream">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-20 md:py-28">
        <Reveal className="max-w-3xl">
          <h2 className="font-instrument-serif text-[2rem] sm:text-5xl md:text-[3.5rem] leading-[1.05] text-balance">
            From an early warning to a treatment someone checked.
          </h2>
        </Reveal>

        {/* The rail: a numbered sequence, because the order is the point. */}
        <ol className="mt-14 md:mt-20 grid gap-8 md:grid-cols-5 md:gap-5">
          {STEPS.map(({ icon: Icon, label, line }, i) => (
            <Reveal key={label} delay={i * 80}>
              <li className="relative flex md:flex-col items-start gap-5 md:gap-0 h-full">
                {i < STEPS.length - 1 && (
                  <span aria-hidden className="hidden md:block absolute top-6 left-[calc(50%+2rem)] right-[-1.25rem] h-px bg-gradient-to-r from-cream/30 to-cream/5" />
                )}
                <span className="relative z-10 flex items-center justify-center w-12 h-12 rounded-2xl bg-cream/[0.08] ring-1 ring-cream/15 shrink-0 md:mx-auto">
                  <Icon className="w-5 h-5 text-ochre" />
                </span>
                <div className="md:mt-6 md:text-center">
                  <span className="text-[11px] font-semibold tabular-nums text-ochre/80">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <h3 className="mt-0.5 text-lg font-medium leading-snug">{label}</h3>
                  <p className="mt-2 text-sm font-light leading-relaxed text-cream/75 text-pretty">{line}</p>
                </div>
              </li>
            </Reveal>
          ))}
        </ol>

        {/* The centrepiece: what the confidence gate actually did. */}
        <Reveal className="mt-16 md:mt-24">
          <div className="rounded-3xl bg-cream/[0.06] ring-1 ring-cream/10 p-6 md:p-10">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h3 className="font-instrument-serif text-2xl md:text-3xl">
                  Step 3 is the one nobody else ships.
                </h3>
                <p className="mt-2 max-w-xl text-sm font-light leading-relaxed text-cream/75 text-pretty">
                  Every photo passes a confidence gate before a farmer is told anything. Below
                  0.70 it asks or escalates; below 0.40 it never speaks at all.
                </p>
              </div>
              <p className="text-xs text-cream/70 md:text-right">
                126 held-out ICAR photos,<br className="hidden md:block" /> never seen in training
              </p>
            </div>

            <div className="mt-8 flex h-3 w-full overflow-hidden rounded-full bg-cream/10" role="img"
              aria-label="Of 126 held-out photos: advised 89.7%, asked one question 0.8%, sent to an expert 9.5%">
              {GATE.map(({ pct, label, tone }) => (
                <span key={label} className={`${tone} h-full`} style={{ width: `${pct}%` }} />
              ))}
            </div>

            <dl className="mt-6 grid gap-5 sm:grid-cols-3">
              {GATE.map(({ pct, label, note, tone }) => (
                <div key={label}>
                  <dt className="flex items-center gap-2 text-sm font-medium">
                    <span aria-hidden className={`w-2.5 h-2.5 rounded-full ${tone}`} />
                    {label}
                  </dt>
                  <dd className="mt-1 pl-[18px]">
                    <span className="font-instrument-serif text-3xl tabular-nums">{pct}%</span>
                    <span className="block text-xs text-cream/70">{note}</span>
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

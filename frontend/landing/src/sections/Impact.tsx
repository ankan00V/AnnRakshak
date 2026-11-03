import { Check } from 'lucide-react'
import type { ReactNode } from 'react'
import Reveal from '../ui/Reveal'
import PhoneShot from '../ui/PhoneShot'

/** Who it is for, one panel each: a line, the thing they actually see, and
 *  three short promises. The farmer's picture is the real answer screen in
 *  Marathi, with its listen button; the officer's is the case as it reaches
 *  the expert queue, with everything needed to confirm it. */

const FARMER_POINTS = [
  'What to check today, for this field.',
  'A wrong spray stopped before it is bought.',
  'A real expert when the app is not sure.',
]

const OFFICIAL_POINTS = [
  'Hotspots from confirmed cases only.',
  'Field accuracy measured, not assumed.',
  'A weekly outlook, and what to stock.',
]

function CaseCard() {
  return (
    <div className="rounded-[1.6rem] bg-white p-4 sm:p-5 text-soil-dark shadow-2xl shadow-black/30">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-soil-dark/60">Bhandara · rice · day 84</p>
        <span className="rounded-full bg-ochre/15 px-2.5 py-0.5 text-[11px] font-medium text-soil">Waiting for you</span>
      </div>
      <div className="mt-3 flex gap-3">
        <img src="/shots/gradcam-blast.webp" alt="The farmer's photo, with where the model looked"
          loading="lazy" className="h-20 w-20 shrink-0 rounded-xl object-cover" />
        <div className="min-w-0 flex-1 space-y-2">
          {[['Neck blast', 71], ['False smut', 22]].map(([name, pct]) => (
            <div key={name}>
              <p className="flex justify-between text-[12px]"><span className="font-medium">{name}</span><span className="tabular-nums text-soil-dark/60">{pct}%</span></p>
              <div className="mt-1 h-1.5 rounded-full bg-soil-dark/10"><div className="h-full rounded-full bg-ochre" style={{ width: `${pct}%` }} /></div>
            </div>
          ))}
        </div>
      </div>
      <p className="mt-3 rounded-xl bg-cream px-3 py-2 text-[12px] leading-relaxed text-soil-dark/80">
        Farmer’s answer: the node under the panicle has turned black.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] font-medium">
        <span className="rounded-full bg-leaf-deep py-2 text-center text-cream">Confirm</span>
        <span className="rounded-full border border-soil-dark/20 py-2 text-center">Correct it</span>
      </div>
    </div>
  )
}

function Panel({ id, title, line, show, points }: {
  id?: string; title: string; line: string; show: ReactNode; points: string[]
}) {
  return (
    <div id={id} className="scroll-mt-24 h-full rounded-[2rem] bg-cream/[0.05] ring-1 ring-cream/10 p-6 sm:p-8 md:p-10 flex flex-col">
      <h2 className="font-instrument-serif text-[2rem] sm:text-4xl md:text-5xl leading-none">{title}</h2>
      <p className="mt-3 text-[15px] font-light leading-relaxed text-cream/75 text-pretty">{line}</p>
      <div className="mt-7 flex-1 flex items-center">
        <div className="mx-auto w-full max-w-[340px]">{show}</div>
      </div>
      <ul className="mt-8 space-y-2.5">
        {points.map((p) => (
          <li key={p} className="flex items-start gap-2.5 text-sm text-cream/85">
            <Check className="w-4 h-4 mt-0.5 shrink-0 text-ochre" aria-hidden />
            {p}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Impact() {
  return (
    <section id="impact" className="w-full bg-soil-dark text-cream">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-14 sm:py-20 md:py-24">
        <div className="grid gap-5 lg:grid-cols-2 lg:gap-6">
          <Reveal className="h-full">
            <Panel
              title="For farmers"
              line="One screen, in their own language, read aloud — saying what to do today."
              show={
                <PhoneShot src="/demo/result-mr.webp"
                  alt="The answer in Marathi: the disease name, how sure it is, and what not to do, with a listen button"
                  crop={{ aspect: 'aspect-[4/3]', position: 'object-[50%_29%]' }} />
              }
              points={FARMER_POINTS}
            />
          </Reveal>
          <Reveal delay={100} className="h-full">
            <Panel
              id="for-officials"
              title="For officials"
              line="Every case arrives with what an expert needs to confirm it in minutes."
              show={<CaseCard />}
              points={OFFICIAL_POINTS}
            />
          </Reveal>
        </div>
      </div>
    </section>
  )
}

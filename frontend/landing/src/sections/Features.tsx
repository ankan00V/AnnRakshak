import { ArrowRight, Ban } from 'lucide-react'
import type { ReactNode } from 'react'
import Reveal from '../ui/Reveal'

/** Three things a farmer would notice, each said in one line and shown in a
 *  small picture of what it looks like. Languages, crops and the expert
 *  behind every answer are in the closing strip, so they are not repeated. */

const HEAT = [
  { src: '/shots/gradcam-blast.webp', alt: 'Heat map on a rice panicle, hot on the blackened neck — neck blast' },
  { src: '/shots/gradcam-turcicum.webp', alt: 'Heat map along the long lesion on a maize leaf — turcicum leaf blight' },
  { src: '/shots/gradcam-brown.webp', alt: 'Heat map tight on two dark spots on a rice leaf — brown spot' },
]

function Looked() {
  return (
    <div className="grid grid-cols-3 gap-2">
      {HEAT.map(({ src, alt }) => (
        <img key={src} src={src} alt={alt} loading="lazy" width={440} height={440}
          className="w-full aspect-square rounded-xl object-cover" />
      ))}
    </div>
  )
}

function Ladder() {
  const rungs = ['Field care', 'Natural', 'Chemical, last']
  return (
    <ol className="flex flex-wrap items-center gap-1.5 text-[12px] sm:text-[13px]">
      {rungs.map((r, i) => (
        <li key={r} className="flex items-center gap-1.5">
          <span className={`rounded-full px-2.5 sm:px-3 py-1.5 whitespace-nowrap ${
            i === 2 ? 'border border-soil-dark/20 text-soil-dark/70' : 'bg-leaf-deep text-cream'}`}>{r}</span>
          {i < rungs.length - 1 && <ArrowRight className="w-3.5 h-3.5 text-soil-dark/40" aria-hidden />}
        </li>
      ))}
    </ol>
  )
}

function Refused() {
  return (
    <div className="rounded-xl border border-ember/25 bg-ember/[0.06] p-3.5">
      <p className="flex items-center gap-2 text-sm font-medium text-ember">
        <Ban className="w-4 h-4 shrink-0" aria-hidden /> Glyphosate 41% SL — do not spray
      </p>
      <p className="mt-1 text-xs leading-relaxed text-soil-dark/70">
        A weed killer, against a leaf disease. It will burn the crop.
      </p>
    </div>
  )
}

const THINGS: { title: string; line: string; show: ReactNode }[] = [
  {
    title: 'It shows where it looked',
    line: 'Every answer marks the part of the leaf it read, so you — and the expert — can check it.',
    show: <Looked />,
  },
  {
    title: 'The safest fix comes first',
    line: 'What to do in the field, then natural control. Chemicals only when nothing else will do.',
    show: <Ladder />,
  },
  {
    title: 'It stops the wrong spray',
    line: 'Check a bottle before you buy. If it is wrong for your crop or your problem, it says so.',
    show: <Refused />,
  },
]

export default function Features() {
  return (
    <section id="features" className="w-full bg-cream text-soil-dark">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-14 sm:py-20 md:py-24">
        <Reveal className="max-w-3xl">
          <h2 className="font-instrument-serif text-[2rem] sm:text-5xl md:text-[3.5rem] leading-[1.05] text-balance">
            Careful with your crop, and your money.
          </h2>
        </Reveal>

        <div className="mt-10 sm:mt-14 grid gap-10 md:grid-cols-3 md:gap-10">
          {THINGS.map(({ title, line, show }, i) => (
            <Reveal key={title} delay={i * 80}>
              <div className="border-t border-soil-dark/15 pt-6">
                {/* One height for the three pictures, so the titles under them
                    line up across the row. */}
                <div className="md:h-28 md:flex md:flex-col md:justify-center">{show}</div>
                <h3 className="mt-5 text-lg font-medium leading-snug">{title}</h3>
                <p className="mt-1.5 text-sm font-light leading-relaxed text-soil-dark/75 text-pretty">{line}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

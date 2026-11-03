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

export default function Impact() {
  return (
    <section id="impact" className="w-full bg-soil-dark text-cream">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-12 sm:py-16 md:py-28">
        <div className="grid gap-10 sm:gap-12 md:gap-12 lg:grid-cols-2 lg:gap-16">
          <Reveal>
            <div className="lg:pr-6">
              <h2 className="font-instrument-serif text-[2rem] sm:text-4xl md:text-5xl">For farmers</h2>
              <p className="mt-3 text-sm font-light leading-relaxed text-cream/75 text-pretty">
                One screen, in her language, that says what to do today.
              </p>
              <Points points={FARMER_POINTS} dot="bg-ochre" />
            </div>
          </Reveal>

          <Reveal delay={120}>
            <div id="for-officials" className="scroll-mt-24 lg:border-l lg:border-cream/10 lg:pl-16">
              <h2 className="font-instrument-serif text-[2rem] sm:text-4xl md:text-5xl">For officials</h2>
              <p className="mt-3 text-sm font-light leading-relaxed text-cream/75 text-pretty">
                The district, as it actually stands this week.
              </p>
              <Points points={OFFICIAL_POINTS} dot="bg-cream/60" />
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

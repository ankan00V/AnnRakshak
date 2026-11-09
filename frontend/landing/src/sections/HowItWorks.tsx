import Reveal from '../ui/Reveal'
import PhoneShot from '../ui/PhoneShot'

/** How it works, shown with the app itself: three real screens, in order.
 *  These are the one numbered sequence on the page, because the order is
 *  what a farmer does. What used to be a separate Features section — where
 *  the model looked, the safest fix first, what not to do — is visible on
 *  these screens, so it is shown here instead of described somewhere else. */
const STEPS = [
  {
    src: '/demo/scan-en.webp',
    alt: 'The scan screen: photograph a sick plant, with a frame to fill and a live field check option',
    title: 'Take a photo',
    line: 'Point the camera at the sick leaf, in daylight. No typing, no forms.',
  },
  {
    src: '/demo/result-en-0.webp',
    alt: 'The answer: a rice panicle with the Grad-CAM heat map over it, named False smut, 98% sure',
    title: 'See what it is',
    line: 'It names the disease, marks where it looked, and says how sure it is.',
  },
  {
    src: '/demo/result-en-1.webp',
    alt: 'The treatment: what not to do, with a listen button, then the safest field practice first',
    title: 'Treat it safely',
    line: 'What not to do, then the safest step first. Chemicals only if it keeps spreading.',
  },
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
            From a photo to a safe treatment.
          </h2>
        </Reveal>

        {/* Three screens. On a phone they are a row you swipe, so three tall
            screenshots do not stack into three screens of scrolling. */}
        <ol
          id="features"
          className="scroll-mt-24 mt-10 sm:mt-14 -mx-6 px-6 md:mx-0 md:px-0 scroll-px-6 md:scroll-px-0
                     flex gap-5 overflow-x-auto snap-x snap-mandatory overscroll-x-contain
                     [scrollbar-width:none] [&::-webkit-scrollbar]:hidden
                     md:grid md:grid-cols-3 md:gap-10 lg:gap-14 md:overflow-visible"
        >
          {STEPS.map(({ src, alt, title, line }, i) => (
            <li key={title} className="snap-start shrink-0 w-[68%] sm:w-[44%] md:w-auto">
              <Reveal delay={i * 90}>
                <PhoneShot src={src} alt={alt} className="mx-auto max-w-[280px]" />
                <div className="mx-auto mt-6 max-w-[280px]">
                  <p className="flex items-baseline gap-2.5">
                    <span className="font-instrument-serif text-2xl leading-none text-ochre">{i + 1}</span>
                    <span className="text-lg font-medium leading-snug">{title}</span>
                  </p>
                  <p className="mt-1.5 text-sm font-light leading-relaxed text-cream/75 text-pretty">{line}</p>
                </div>
              </Reveal>
            </li>
          ))}
        </ol>

        {/* The honesty of it, in a farmer's words. */}
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

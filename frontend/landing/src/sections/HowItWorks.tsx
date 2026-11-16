import { ArrowRight } from 'lucide-react'
import Reveal from '../ui/Reveal'

/** How it works, shown with the app itself: three real screens, in order —
 *  each captured at iPhone size from the running app and set in a phone
 *  (scripts/hero-phone). These are the one numbered sequence on the page,
 *  because the order is what a farmer does. */
const STEPS = [
  {
    src: '/photos/phone-scan.webp',
    alt: 'The scan screen: a camera frame to fill with the sick leaf, with buttons to open the camera or choose from the gallery',
    title: 'Take a photo',
    line: 'Point the camera at the sick leaf, in daylight. No typing, no forms.',
  },
  {
    src: '/photos/phone-result.webp',
    alt: 'The answer: a rice panicle with where the AI looked, named False smut, 97% sure',
    title: 'See what it is',
    line: 'It names the disease, marks where it looked, and says how sure it is.',
  },
  {
    src: '/photos/phone-treat.webp',
    alt: 'The treatment: what not to do, with a listen button, then the safest field practice first and the chemical only on request',
    title: 'Treat it safely',
    line: 'What not to do, then the safest step first. Chemicals only if it keeps spreading.',
  },
]

/** A leaf, drawn: the panel's corners. */
function Leaf({ className = '' }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 90 110" className={className}>
      <defs>
        <linearGradient id="hiw-leaf" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#2f6f2a" /><stop offset="0.55" stopColor="#5fa53b" /><stop offset="1" stopColor="#9ad063" />
        </linearGradient>
      </defs>
      <path d="M4 104 C 0 60, 30 16, 88 3 C 86 52, 56 94, 4 104 Z" fill="url(#hiw-leaf)" />
      <path d="M6 101 C 30 72, 56 40, 86 6" stroke="#2a5f27" strokeOpacity="0.55" strokeWidth="1.6" fill="none" />
    </svg>
  )
}

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="w-full bg-[#f6f1e6] px-3 md:px-6 lg:px-[2.6vw]">
      <div className="relative mx-auto max-w-[1840px] overflow-hidden rounded-[28px] bg-[#1d4a2c] text-cream lg:rounded-[36px]">
        <div aria-hidden className="absolute inset-0 bg-[radial-gradient(60%_80%_at_20%_0%,rgba(143,207,107,0.14),transparent_60%),radial-gradient(50%_70%_at_100%_100%,rgba(0,0,0,0.25),transparent_70%)]" />
        <Leaf className="absolute -left-4 -top-6 hidden w-[5.5vw] max-w-[100px] -scale-y-100 opacity-90 lg:block" />
        <Leaf className="absolute -bottom-6 -right-3 hidden w-[6vw] max-w-[110px] -scale-x-100 opacity-90 lg:block" />

        <div className="relative px-5 py-12 md:px-10 lg:px-[4.4vw] lg:py-[clamp(40px,3.6vw,72px)]">
          <Reveal>
            <h2 className="font-display text-[32px] leading-[1.08] tracking-[-0.01em] text-balance lg:text-[clamp(28px,2.35vw,46px)]">
              From a photo to a safe treatment.
            </h2>
          </Reveal>

          {/* Each screen large enough to read, with its step under it. On a
              phone the three are a row you swipe, so three tall screens do
              not stack into three screens of scrolling. */}
          <ol id="features"
            className="-mx-5 mt-8 flex scroll-mt-24 snap-x snap-mandatory gap-6 overflow-x-auto px-5 [scrollbar-width:none] md:mx-0 md:grid md:grid-cols-3 md:gap-6 md:overflow-visible md:px-0 lg:mt-[2.8vw] lg:gap-[3.4vw] [&::-webkit-scrollbar]:hidden">
            {STEPS.map(({ src, alt, title, line }, i) => (
              <li key={title} className="relative w-[72%] shrink-0 snap-start sm:w-[46%] md:w-auto">
                <Reveal delay={i * 90} className="flex flex-col items-center text-center">
                  <img src={src} alt={alt} width={620} height={1266} loading="lazy" decoding="async"
                    className="w-full max-w-[260px] drop-shadow-[0_28px_36px_rgba(0,0,0,0.45)] md:max-w-[240px] lg:w-[clamp(220px,19vw,340px)] lg:max-w-none" />
                  <span className="mt-6 flex h-9 w-9 items-center justify-center rounded-full border border-[#e8b450]/70 font-display text-[18px] text-[#f0c060] lg:mt-[1.8vw] lg:h-[clamp(30px,2.2vw,40px)] lg:w-[clamp(30px,2.2vw,40px)] lg:text-[clamp(15px,1.15vw,20px)]">{i + 1}</span>
                  <p className="mt-3 text-[19px] font-semibold leading-snug lg:mt-[0.8vw] lg:text-[clamp(17px,1.3vw,23px)]">{title}</p>
                  <p className="mx-auto mt-1.5 max-w-[30ch] text-[14px] leading-relaxed text-cream/75 text-pretty lg:text-[clamp(13px,0.95vw,17px)]">{line}</p>
                </Reveal>
                {i < STEPS.length - 1 && (
                  <ArrowRight aria-hidden className="absolute -right-[2.4vw] top-[34%] hidden h-6 w-6 -translate-y-1/2 translate-x-1/2 text-cream/55 md:block" />
                )}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  )
}

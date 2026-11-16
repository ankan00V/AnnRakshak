import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Play, X } from 'lucide-react'
import Navbar from './Navbar'
import { BellSolid, LeafSolid, SprayBottleSolid, SunSolid } from './ui/SolidIcons'

/** The first screen: who it is for, what it does, and the app doing it.
 *
 *  A farmer in his field with his phone, and beside him the screen he would
 *  be looking at — the real Scan screen, captured from the app. The claim keeps
 *  the left. The page then turns to
 *  cream on a field-edge curve, and the four everyday jobs sit on a strip
 *  across that seam.
 */
export default function Hero() {
  const [video, setVideo] = useState(false)
  return (
    <>
      <section className="relative w-full overflow-hidden bg-[#10301b]">
        {/* The farmer in his field. On wide screens the photograph fills the
            page from a fifth of the way in, which stands him between the words
            and the phone, and starts a little below the top so his head stays
            clear of the menu; it fades into deep green under the words and
            under the menu. On a phone it fills the frame behind the words,
            darkened so they read. */}
        <div aria-hidden className="absolute inset-0">
          <img src="/photos/hero-farmer.webp" alt=""
            srcSet="/photos/hero-farmer-900.webp 900w, /photos/hero-farmer.webp 1774w"
            sizes="(min-width: 1024px) 82vw, 100vw" width={1774} height={887} fetchPriority="high"
            className="absolute inset-y-0 right-0 h-full w-full object-cover object-[58%_25%]
                       lg:top-[4.2vw] lg:h-[calc(100%-4.2vw)] lg:w-[81.5%] lg:object-[0%_10%]
                       lg:[mask-image:linear-gradient(to_right,transparent,black_22%),linear-gradient(to_bottom,transparent,black_9%)]
                       lg:[mask-composite:intersect] lg:[-webkit-mask-composite:source-in]" />
          <div className="absolute inset-0 bg-[#10301b]/70 lg:bg-transparent lg:bg-gradient-to-r lg:from-[#10301b] lg:from-[14%] lg:via-[#163d24]/55 lg:via-[34%] lg:to-transparent lg:to-[48%]" />
          <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-black/40 to-transparent" />
        </div>

        <div className="relative z-20">
          <Navbar />
          {/* Sizes follow the width on wide screens, so the hero keeps the same
              proportions on a laptop and on a large monitor. */}
          <div className="mx-auto max-w-[1720px] px-6 pb-32 pt-6 md:px-12 lg:px-[7vw] lg:pb-[clamp(130px,11vw,210px)] lg:pt-[clamp(32px,3.2vw,64px)]">
            <div className="mx-auto max-w-2xl text-center lg:mx-0 lg:w-[46%] lg:max-w-none lg:text-left">
              <h1 className="font-display text-[40px] leading-[1.04] tracking-[-0.01em] text-white drop-shadow-[0_2px_18px_rgba(0,0,0,0.25)] sm:text-[54px] lg:text-[clamp(44px,4.15vw,80px)]">
                Crop and Pest <br className="hidden sm:block" />
                Detection for Every{' '}
                <span className="relative inline-block pr-1 italic text-[#f0c060]">
                  Farmer
                  {/* A brush stroke: heavy under the word, thinning out to the right. */}
                  <svg aria-hidden viewBox="0 0 400 34" className="absolute -bottom-[0.3em] left-[2%] w-[105%] lg:w-[150%]" fill="#e8b450">
                    <path d="M4 27 C 50 20, 120 15, 200 14 C 280 13, 350 9, 398 2 C 352 13, 284 19, 204 20.5 C 130 22, 60 25.5, 4 27 Z" />
                  </svg>
                </span>
              </h1>
              <p className="mx-auto mt-9 max-w-xl text-[17px] leading-relaxed text-white/90 lg:mx-0 lg:mt-[clamp(26px,2.2vw,40px)] lg:max-w-[33vw] lg:text-[clamp(15px,1.12vw,20px)] lg:leading-[1.6]">
                We help farmers catch crop disease and pest damage early and protect every harvest before it&apos;s too late.
              </p>
              <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row lg:mt-[clamp(22px,1.9vw,36px)] lg:justify-start lg:gap-[1.2vw]">
                <Link to="/app"
                  className="group inline-flex min-h-[52px] items-center gap-2 rounded-full bg-[#f6e3b4] px-8 text-[17px] font-semibold text-[#173a22] shadow-[0_14px_30px_-14px_rgba(0,0,0,0.6)] transition hover:bg-[#f9ebc8]
                             lg:min-h-[clamp(46px,3.35vw,60px)] lg:px-[clamp(22px,2vw,36px)] lg:text-[clamp(15px,1.05vw,18px)]">
                  See It Detect <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-0.5" aria-hidden />
                </Link>
                <button onClick={() => setVideo(true)}
                  className="inline-flex min-h-[52px] items-center gap-3 rounded-full border border-white/70 bg-black/10 px-7 text-[17px] font-semibold text-white backdrop-blur-[2px] transition hover:bg-white/10
                             lg:min-h-[clamp(46px,3.35vw,60px)] lg:px-[clamp(18px,1.6vw,30px)] lg:text-[clamp(15px,1.05vw,18px)]">
                  <span className="flex h-8 w-8 items-center justify-center rounded-full border border-white/80"><Play className="h-4 w-4 fill-white" aria-hidden /></span>
                  Watch Demo
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* The real Scan screen, on a real phone: the app captured at iPhone
            size and set into a photographed handset (scripts/hero-phone).
            It stands inside the right margin and takes its size from the
            hero: from just under the menu down onto the field's edge. */}
        <div className="absolute bottom-[clamp(6px,0.8vw,16px)] right-[7vw] top-[clamp(76px,6.4vw,120px)] z-20 hidden lg:block 2xl:right-[max(7vw,calc((100vw-1720px)/2+7vw))]">
          <svg aria-hidden viewBox="0 0 60 50" className="absolute -right-[16%] top-[3%] w-[16%] text-white/90" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round">
            <path d="M30 4 C 26 16, 20 26, 10 36" /><path d="M54 22 C 44 28, 34 32, 22 40" />
          </svg>
          <img src="/photos/hero-phone.webp" width={911} height={1513}
            alt="The AnnRakshak Scan screen on a phone: photograph a sick plant, open the camera"
            className="block h-full w-auto max-w-none rotate-[4deg] drop-shadow-[0_30px_40px_rgba(0,0,0,0.35)]" />
        </div>

        {/* A leaf at the field's edge, in the left margin. */}
        <svg aria-hidden viewBox="0 0 90 110" className="absolute bottom-[clamp(40px,4.2vw,80px)] left-[-1vw] z-10 hidden w-[5vw] max-w-[90px] xl:block">
          <defs>
            <linearGradient id="hero-leaf" x1="0" y1="1" x2="1" y2="0">
              <stop offset="0" stopColor="#2f6f2a" /><stop offset="0.55" stopColor="#5fa53b" /><stop offset="1" stopColor="#9ad063" />
            </linearGradient>
          </defs>
          <path d="M4 104 C 0 60, 30 16, 88 3 C 86 52, 56 94, 4 104 Z" fill="url(#hero-leaf)" />
          <path d="M6 101 C 30 72, 56 40, 86 6" stroke="#2a5f27" strokeOpacity="0.55" strokeWidth="1.6" fill="none" />
        </svg>

        {/* The field's edge: the page turns to cream on a curve, with a band
            of young green along it. */}
        <svg aria-hidden viewBox="0 0 1440 140" preserveAspectRatio="none" className="absolute bottom-[-1px] left-0 z-10 h-[80px] w-full lg:h-[clamp(70px,6.5vw,120px)]">
          <path d="M0 34 C 320 62, 720 116, 1020 104 S 1350 52, 1440 0 L 1440 140 L 0 140 Z" fill="#a9c98a" fillOpacity="0.45" />
          <path d="M0 44 C 320 74, 720 128, 1020 116 S 1350 68, 1440 22 L 1440 140 L 0 140 Z" fill="#f6f1e6" />
        </svg>
      </section>

      <FeatureStrip />
      {video && <DemoVideo onClose={() => setVideo(false)} />}
    </>
  )
}

/** The four everyday jobs, on the seam between the field and the page. */
function FeatureStrip() {
  const items = [
    [LeafSolid, 'Scan Crops', 'Detect diseases instantly', 'bg-[#e4eedb]'],
    [SprayBottleSolid, 'Spray Check', 'Ensure safe usage', 'bg-[#e4eedb]'],
    [SunSolid, 'Check Weather', 'Plan better, grow smarter', ''],
    [BellSolid, 'Get Alerts', 'Stay informed', 'bg-[#e4eedb]'],
  ] as const
  return (
    <div className="relative z-20 -mt-6 bg-[#f6f1e6] px-4 md:px-12 lg:-mt-[2px] lg:px-[7vw] lg:pt-[0.6vw]">
      <div className="relative mx-auto max-w-[1720px]">
      <ul className="grid grid-cols-2 gap-y-6 rounded-[28px] bg-[#fdfbf6] px-4 py-6 shadow-[0_24px_60px_-30px_rgba(43,29,18,0.45)] ring-1 ring-black/[0.06] md:px-8 lg:grid-cols-4 lg:px-[2.4vw] lg:py-[clamp(16px,1.35vw,26px)]">
        {items.map(([Icon, title, sub, tone], i) => (
          <li key={title} className={`flex flex-col items-center gap-3 px-1 text-center sm:flex-row sm:gap-4 sm:px-2 sm:text-left lg:gap-[1.3vw] lg:px-[2vw] ${i ? 'lg:border-l lg:border-black/[0.08]' : ''}`}>
            <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full sm:h-14 sm:w-14 lg:h-[clamp(48px,4.1vw,74px)] lg:w-[clamp(48px,4.1vw,74px)] ${tone}`}>
              <Icon className={tone ? 'h-[55%] w-[55%]' : 'h-[85%] w-[85%]'} />
            </span>
            <span className="min-w-0">
              <span className="block text-[17px] font-semibold text-[#1f3a26] md:text-[19px] lg:text-[clamp(15px,1.17vw,21px)]">{title}</span>
              <span className="mt-0.5 block text-[13px] leading-snug text-[#4d5a4f] sm:text-[14px] md:text-[15px] lg:text-[clamp(12px,0.9vw,16px)] xl:whitespace-nowrap">{sub}</span>
            </span>
          </li>
        ))}
      </ul>
      </div>
    </div>
  )
}

/** The launch film, played over the page. */

function DemoVideo({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    ref.current?.focus()
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    const before = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', esc)
    return () => { window.removeEventListener('keydown', esc); document.body.style.overflow = before }
  }, [onClose])
  return (
    <div role="dialog" aria-modal="true" aria-label="AnnRakshak demo video" onClick={onClose}
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/85 p-4 animate-fadein">
      <button ref={ref} onClick={onClose} aria-label="Close video"
        className="absolute right-4 top-4 flex h-12 w-12 items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25">
        <X className="h-6 w-6" />
      </button>
      <video src="/brand/annrakshak-complete-final-2.mp4" controls autoPlay playsInline preload="metadata"
        onClick={(e) => e.stopPropagation()}
        className="aspect-video w-full max-w-6xl rounded-2xl bg-black shadow-2xl" />
    </div>
  )
}

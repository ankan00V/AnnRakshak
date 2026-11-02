import { Link } from 'react-router-dom'
import { ArrowRight, Play } from 'lucide-react'
import Navbar from './Navbar'
import { smoothScrollTo } from './smoothScroll'
import ScanDemo from './stageshow/ScanDemo'

/** The first screen: what the app claims, and the app doing it.
 *
 *  This used to be an eleven-megabyte video of a field, hot-linked from
 *  somebody else's CDN, with the headline laid over it. Three things were
 *  wrong with that. It told a third party the IP of every visitor before the
 *  page had painted. It cost a farmer on a village connection eleven megabytes
 *  to look at stock footage. And it showed a field, which is the one thing the
 *  visitor already knows about — not the product, which is the thing they came
 *  to judge.
 *
 *  So the claim keeps the left and the product takes the right: a phone,
 *  cropped at the foot, running the real flow in Marathi. Below `lg` the
 *  demo follows the copy rather than being squeezed beside it.
 */
export default function Hero() {
  return (
    <section className="w-full min-h-screen overflow-hidden relative bg-leaf-deep">
      {/* The ground the hero sits on: the brand's green, with light coming
          from where the demo is, so the eye starts at the phone. */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(90% 70% at 78% 28%, rgba(200,134,45,0.20), transparent 62%),' +
            'radial-gradient(80% 90% at 12% 85%, rgba(61,107,74,0.45), transparent 70%)',
        }}
      />

      <div className="relative z-10 flex flex-col min-h-screen">
        <Navbar />

        <div className="flex-1 w-full max-w-7xl mx-auto px-6 lg:px-10 pb-10
                        grid lg:grid-cols-[1fr_minmax(0,430px)] lg:items-center gap-8 lg:gap-10">
          <div className="pt-6 lg:pt-0 text-center lg:text-left">
            <h1 className="font-instrument-serif text-white text-4xl sm:text-5xl md:text-6xl lg:text-6xl xl:text-7xl
                           leading-[1.04] max-w-2xl mx-auto lg:mx-0">
              CROP <span className="italic font-instrument-serif">and</span> PEST
              <br />
              DETECTION <span className="italic font-instrument-serif">for</span> EVERY
              <br />
              FARMER
            </h1>
            <p className="mt-5 md:mt-6 text-white/70 text-base md:text-lg font-light
                          max-w-lg mx-auto lg:mx-0 leading-relaxed">
              We help farmers catch crop disease and pest damage early and protect
              every harvest before it&apos;s too late.
            </p>
            <div className="mt-7 md:mt-8 flex flex-col sm:flex-row items-center lg:items-start
                            justify-center lg:justify-start gap-4">
              <Link
                to="/app"
                className="group bg-white text-black rounded-full px-7 py-3 text-sm font-medium"
              >
                <span className="inline-flex items-center gap-2">
                  See It Detect
                  <ArrowRight className="w-4 h-4 transition-transform duration-200 group-hover:translate-x-0.5" />
                </span>
              </Link>
              <button
                onClick={() => smoothScrollTo('how-it-works')}
                className="bg-transparent border border-white/40 text-white rounded-full px-7 py-3
                           text-sm font-light hover:bg-white/10 hover:border-white/60
                           transition-colors duration-200"
              >
                <span className="inline-flex items-center gap-2">
                  <Play className="w-4 h-4" />
                  Watch Demo
                </span>
              </button>
            </div>
          </div>

          {/* The phone is the figure: it leads, and it stands whole, because
              the thing being judged is what the screen is doing. */}
          <div className="relative lg:justify-self-end w-full flex justify-center
                          pointer-events-none select-none">
            <ScanDemo />
          </div>
        </div>
      </div>
    </section>
  )
}

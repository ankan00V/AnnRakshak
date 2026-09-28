import { Ban, Bug, Map, UserCheck } from 'lucide-react'
import Reveal from '../ui/Reveal'

const GRADCAM = [
  { src: '/shots/gradcam-blast.webp', alt: 'Heat map over a rice panicle, concentrated on the blackened neck node — rice neck blast', caption: 'rice neck blast' },
  { src: '/shots/gradcam-turcicum.webp', alt: 'Heat map over a maize leaf, following the long cigar-shaped lesion — turcicum leaf blight', caption: 'turcicum leaf blight' },
  { src: '/shots/gradcam-brown.webp', alt: 'Heat map tight around two dark spots on a rice leaf — brown spot', caption: 'rice brown spot' },
]

/** Cultural first, chemical last — the order the knowledge base refuses to load without. */
const LADDER = [
  { step: 'Field practice', line: 'Remove and burn infected debris. Drain the standing water.' },
  { step: 'Natural control', line: 'Trichoderma, Bt, a pheromone trap — ICAR-released, named with its institute.' },
  { step: 'Chemical', line: 'Last. Dosed for your plot, with the label rule quoted and an officer to confirm it.' },
]

const LANGUAGES = ['मराठी', 'हिन्दी', 'English', 'বাংলা', 'ગુજરાતી', 'ಕನ್ನಡ', 'മലയാളം', 'ਪੰਜਾਬੀ', 'தமிழ்', 'తెలుగు', 'ଓଡ଼ିଆ']

const ALSO = [
  { icon: Bug, title: 'Traps and field sensors', line: 'Pheromone-trap counts read against ICAR-CICR action levels. A farm’s own sensor overrides the district forecast.' },
  { icon: UserCheck, title: 'Expert validation in three minutes', line: 'A case arrives pre-packed: photos, ranked hypotheses, the farmer’s answer, trap counts, recent alerts.' },
  { icon: Map, title: 'Surveillance for officials', line: 'Hotspots, weekly risk outlook, field accuracy, IMD rainfall against normal, the state pesticide baseline.' },
]

function Tile({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-3xl border border-soil-dark/10 bg-white/80 p-6 md:p-8 ${className}`}>
      {children}
    </div>
  )
}

export default function Features() {
  return (
    <section id="features" className="w-full bg-cream text-soil-dark">
      <div className="max-w-6xl mx-auto px-6 md:px-12 py-20 md:py-28">
        <Reveal className="max-w-3xl">
          <h2 className="font-instrument-serif text-[2rem] sm:text-5xl md:text-[3.5rem] leading-[1.05] text-balance">
            Built for how farmers actually work — and honest when it isn’t sure.
          </h2>
        </Reveal>

        <div className="mt-12 md:mt-16 grid gap-5 lg:grid-cols-6">
          {/* Explainability, shown rather than claimed. */}
          <Reveal className="lg:col-span-4 h-full">
            <Tile className="h-full">
              <h3 className="font-instrument-serif text-2xl md:text-3xl">Where the model looked</h3>
              <p className="mt-2 max-w-xl text-sm font-light leading-relaxed text-soil-dark/70 text-pretty">
                Every diagnosis carries its own Grad-CAM. If the heat sits on the soil instead of
                the lesion, the farmer and the KVK expert can both see it and say so.
              </p>
              <div className="mt-6 grid grid-cols-3 gap-3">
                {GRADCAM.map(({ src, alt, caption }) => (
                  <figure key={src}>
                    <img src={src} alt={alt} loading="lazy" width={440} height={440}
                      className="w-full aspect-square object-cover rounded-2xl bg-soil-dark/5" />
                    <figcaption className="mt-2 text-[11px] text-soil-dark/70">{caption}</figcaption>
                  </figure>
                ))}
              </div>
            </Tile>
          </Reveal>

          {/* The ladder, as rungs. */}
          <Reveal className="lg:col-span-2 h-full" delay={80}>
            <Tile className="h-full">
              <Ban className="w-5 h-5 text-ember" />
              <h3 className="mt-4 text-lg font-medium">Chemical last, veto first</h3>
              <ol className="mt-5 space-y-4">
                {LADDER.map(({ step, line }, i) => (
                  <li key={step} className="relative pl-7">
                    <span aria-hidden className="absolute left-0 top-1 text-[11px] font-semibold tabular-nums text-ochre">
                      {i + 1}
                    </span>
                    {i < LADDER.length - 1 && (
                      <span aria-hidden className="absolute left-[5px] top-6 bottom-[-14px] w-px bg-soil-dark/15" />
                    )}
                    <p className="text-sm font-medium">{step}</p>
                    <p className="mt-1 text-xs font-light leading-relaxed text-soil-dark/75">{line}</p>
                  </li>
                ))}
              </ol>
            </Tile>
          </Reveal>

          {/* The spray check, as the farmer sees it. */}
          <Reveal className="lg:col-span-3 h-full" delay={40}>
            <Tile className="h-full">
              <h3 className="text-lg font-medium">It can refuse a bottle. It can never bless one.</h3>
              <div className="mt-5 space-y-3">
                <div className="rounded-2xl border border-ember/25 bg-ember/[0.06] p-4">
                  <p className="text-sm font-medium text-ember">Glyphosate 41% SL — do not spray</p>
                  <p className="mt-1 text-xs font-light leading-relaxed text-soil-dark/70">
                    A weed killer, against a leaf disease. It will not touch the fungus and it will
                    burn the crop.
                  </p>
                </div>
                <p className="text-xs font-light leading-relaxed text-soil-dark/75">
                  The check has no vocabulary for “safe”. It vetoes the wrong class, the wrong crop
                  and anything off-label; the printed label still decides the dose.
                </p>
              </div>
            </Tile>
          </Reveal>

          {/* Languages, in their own scripts. */}
          <Reveal className="lg:col-span-3 h-full" delay={120}>
            <Tile className="h-full flex flex-col">
              <h3 className="text-lg font-medium">Eleven languages, read out loud</h3>
              <p className="mt-2 text-sm font-light leading-relaxed text-soil-dark/70 text-pretty">
                Every advisory, alert and question in the farmer’s own language — spoken through
                Bhashini, so a farmer who does not read still gets the whole answer.
              </p>
              <ul className="mt-auto pt-6 flex flex-wrap gap-2">
                {LANGUAGES.map((l) => (
                  <li key={l} className="rounded-full bg-leaf-deep/[0.07] px-3 py-1.5 text-sm text-leaf-deep">
                    {l}
                  </li>
                ))}
              </ul>
            </Tile>
          </Reveal>
        </div>

        {/* The rest, as a ruled list rather than three more cards. */}
        <div className="mt-12 md:mt-16 border-t border-soil-dark/15">
          {ALSO.map(({ icon: Icon, title, line }, i) => (
            <Reveal key={title} delay={i * 70}>
              <div className="grid gap-2 md:grid-cols-12 md:gap-8 items-start border-b border-soil-dark/15 py-6">
                <h3 className="md:col-span-5 flex items-center gap-3 text-base font-medium">
                  <Icon className="w-4 h-4 text-leaf shrink-0" />
                  {title}
                </h3>
                <p className="md:col-span-7 text-sm font-light leading-relaxed text-soil-dark/70 text-pretty">
                  {line}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

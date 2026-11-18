import { ArrowRight, ScanSearch, ShieldCheck, UserRoundCheck } from 'lucide-react'
import { useFarmer } from '../farmer/FarmerContext'
import { LeafSolid } from '../ui/SolidIcons'
import { smoothScrollTo } from '../smoothScroll'

/** What a farmer gets, in three pictures, and what it adds up to. */
const CARDS = [
  { img: '/photos/card-leaf.webp', icon: ScanSearch, label: 'landCardIdentify', pos: 'object-[40%_center]' },
  { img: '/photos/card-expert.webp', icon: UserRoundCheck, label: 'landCardExpert', pos: 'object-[46%_center]' },
  { img: '/photos/card-farmer-app.webp', icon: ShieldCheck, label: 'landCardProtect', pos: 'object-[70%_center]' },
] as const

export default function HelpsYou() {
  const { t } = useFarmer()
  return (
    <section id="helps" className="w-full bg-[#f6f1e6] text-[#1f3a26]">
      <div className="mx-auto grid max-w-[1720px] gap-8 px-6 py-16 md:px-12 lg:grid-cols-[minmax(0,1.85fr)_minmax(0,1fr)] lg:items-center xl:grid-cols-[minmax(0,1.05fr)_minmax(0,1.85fr)_minmax(0,1fr)] lg:gap-[2.6vw] lg:px-[7vw] lg:py-[clamp(48px,4vw,80px)]">
        <div className="flex flex-col justify-center lg:col-span-2 xl:col-span-1">
          <span className="inline-flex w-fit items-center gap-2 whitespace-nowrap rounded-full bg-[#e6f0dc] px-4 py-1.5 text-[15px] font-medium text-[#2f6a39] lg:text-[clamp(13px,0.92vw,16px)]">
            <LeafSolid className="h-[18px] w-[18px]" /> {t('landSmart')}
          </span>
          <h2 className="mt-5 font-display text-[38px] leading-[1.06] tracking-[-0.01em] lg:mt-[1.2vw] lg:text-[clamp(32px,2.75vw,52px)]">{t('landHelpsTitle')}</h2>
          <p className="mt-5 text-[17px] leading-relaxed text-[#3d4a40] lg:mt-[1.3vw] lg:text-[clamp(14px,1.02vw,18px)]">
            {t('landHelpsSub')}
          </p>
          <button onClick={() => smoothScrollTo('how-it-works')}
            className="group mt-7 inline-flex min-h-[52px] w-fit items-center gap-2 rounded-full bg-[#1d4a2c] px-7 text-[16px] font-semibold text-white transition hover:bg-[#245a35] lg:mt-[1.8vw] lg:min-h-[clamp(44px,3vw,54px)] lg:px-[1.7vw] lg:text-[clamp(14px,0.98vw,17px)]">
            {t('landExplore')} <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-0.5" aria-hidden />
          </button>
        </div>

        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:gap-[1.2vw]">
          {CARDS.map(({ img, icon: Icon, label, pos }) => (
            <li key={label} className="group relative min-h-[230px] overflow-hidden rounded-[24px] border-[5px] border-white shadow-[0_20px_44px_-26px_rgba(43,29,18,0.6)] sm:min-h-[300px] lg:aspect-[7/8] lg:min-h-0">
              <img src={img} alt="" loading="lazy" decoding="async"
                className={`absolute inset-0 h-full w-full object-cover ${pos} transition-transform duration-700 group-hover:scale-[1.04]`} />
              <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/15 to-transparent" />
              <div className="absolute inset-x-0 bottom-0 p-5 lg:p-[1.2vw]">
                <span className="flex h-11 w-11 items-center justify-center rounded-full border-2 border-white/90 text-white lg:h-[clamp(32px,2.3vw,42px)] lg:w-[clamp(32px,2.3vw,42px)]">
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <p className="mt-3 text-[19px] font-semibold leading-tight text-white lg:mt-[0.7vw] lg:text-[clamp(14px,1vw,18px)]">{t(label)}</p>
              </div>
            </li>
          ))}
        </ul>

        <div className="relative flex min-h-[280px] flex-col overflow-hidden rounded-[24px] bg-[#1d4a2c] p-7 text-white shadow-[0_20px_44px_-26px_rgba(43,29,18,0.6)] lg:aspect-[11/8] lg:min-h-0 lg:p-[1.7vw]">
          <img src="/photos/impact-tree.webp" alt="" loading="lazy" decoding="async"
            className="absolute inset-x-0 bottom-0 h-[66%] w-full object-cover object-[100%_60%] opacity-90 [mask-image:linear-gradient(to_bottom,transparent,black_45%)]" />
          <div className="relative">
            <p className="flex items-center gap-3 text-[20px] font-semibold lg:text-[clamp(16px,1.15vw,21px)]"><LeafSolid className="h-8 w-8" from="#a6dc6e" to="#5fa53b" /> {t('landImpact')}</p>
            <p className="mt-3 text-[17px] leading-snug text-white/90 lg:mt-[0.8vw] lg:text-[clamp(13px,1vw,18px)]">{t('landImpactLine')}</p>
          </div>
          <p className="relative mt-auto pt-10 font-display text-[38px] leading-[1.08] drop-shadow-[0_2px_12px_rgba(0,0,0,0.45)] lg:pt-[1.5vw] lg:text-[clamp(26px,2.1vw,40px)]">
            {t('landGreener')}
            <span className="relative block">
              {t('landIndia')}
              <svg aria-hidden viewBox="0 0 200 18" className="absolute -bottom-2 left-0 w-[4.3em]" fill="none">
                <path d="M3 12 C 50 4, 120 3, 197 8" stroke="#e8bf6a" strokeWidth="3.5" strokeLinecap="round" />
              </svg>
            </span>
          </p>
        </div>
      </div>
    </section>
  )
}

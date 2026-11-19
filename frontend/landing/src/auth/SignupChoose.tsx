import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useFarmer } from '../farmer/FarmerContext'

/** The fork: which of the two apps is yours, each with a picture of who it
 *  is for. The question itself is on the photograph above or beside it. */
export default function SignupChoose() {
  const { t } = useFarmer()
  const cards = [
    { to: '/signup/farmer', img: '/photos/card-farmer-app.webp', pos: 'object-[70%_35%]', title: t('authFarmerCard'), sub: t('authFarmerCardSub') },
    { to: '/signup/expert', img: '/photos/card-expert.webp', pos: 'object-[45%_30%]', title: t('authExpertCard'), sub: t('authExpertCardSub') },
  ]
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        {cards.map(({ to, img, pos, title, sub }) => (
          <Link key={to} to={to}
            className="group flex flex-col overflow-hidden rounded-[24px] bg-white ring-1 ring-black/[0.06] shadow-[0_18px_40px_-28px_rgba(43,29,18,0.55)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_48px_-28px_rgba(43,29,18,0.6)]">
            <span className="relative block aspect-[16/10] overflow-hidden">
              <img src={img} alt="" decoding="async" className={`h-full w-full object-cover ${pos} transition-transform duration-700 group-hover:scale-[1.04]`} />
            </span>
            <span className="flex flex-1 flex-col p-5">
              <span className="font-display text-[24px] leading-tight text-[#1f3a26]">{title}</span>
              <span className="mt-1.5 text-[14px] leading-relaxed text-soil-dark/75">{sub}</span>
              <span className="mt-4 inline-flex items-center gap-1.5 text-[14px] font-semibold text-[#1d4a2c]">
                {t('authNext')} <ArrowRight aria-hidden className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </span>
            </span>
          </Link>
        ))}
      </div>
      <p className="text-center text-sm text-soil-dark/75">
        {t('authHaveAccount')}{' '}
        <Link to="/login" className="inline-flex min-h-[44px] items-center text-leaf-deep font-semibold underline underline-offset-2">{t('authLogin')}</Link>
      </p>
    </div>
  )
}

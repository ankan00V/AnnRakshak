import { Link } from 'react-router-dom'
import { ChevronRight, Sprout, UserCheck } from 'lucide-react'
import { useFarmer } from '../farmer/FarmerContext'

export default function SignupChoose() {
  const { t } = useFarmer()
  const cards = [
    { to: '/signup/farmer', icon: Sprout, title: t('authFarmerCard'), sub: t('authFarmerCardSub'), tone: 'bg-leaf/15 text-leaf-deep' },
    { to: '/signup/expert', icon: UserCheck, title: t('authExpertCard'), sub: t('authExpertCardSub'), tone: 'bg-ochre/20 text-[#8a5a17]' },
  ]
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-instrument-serif text-[34px] leading-tight">{t('authWhoAreYou')}</h1>
        <p className="mt-1 text-sm text-soil-dark/60">{t('authWhoSub')}</p>
      </div>
      <div className="space-y-3">
        {cards.map(({ to, icon: Icon, title, sub, tone }) => (
          <Link key={to} to={to}
            className="flex items-center gap-4 rounded-2xl bg-white border border-soil-dark/10 p-4 hover:border-leaf/50 transition-colors">
            <span className={`shrink-0 w-14 h-14 rounded-2xl flex items-center justify-center ${tone}`}>
              <Icon className="w-7 h-7" />
            </span>
            <span className="flex-1 min-w-0">
              <span className="block text-[17px] font-semibold">{title}</span>
              <span className="block mt-0.5 text-[13px] text-soil-dark/60 leading-snug">{sub}</span>
            </span>
            <ChevronRight className="w-5 h-5 text-soil-dark/40 shrink-0" />
          </Link>
        ))}
      </div>
      <p className="text-center text-sm text-soil-dark/70">
        {t('authHaveAccount')}{' '}
        <Link to="/login" className="text-leaf-deep font-semibold underline underline-offset-2">{t('authLogin')}</Link>
      </p>
    </div>
  )
}

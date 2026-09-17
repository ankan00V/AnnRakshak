import { Globe, Mail } from 'lucide-react'
import { Link } from 'react-router-dom'
import BrandMark from '../ui/BrandMark'
import { useAuth } from '../auth/AuthContext'
import { homeOf } from '../auth/helpers'
import { useFarmer } from '../farmer/FarmerContext'

export default function FinalCta() {
  const { me, logout } = useAuth()
  const { t } = useFarmer()
  return (
    <section id="cta" className="w-full bg-leaf-deep text-cream">
      <div className="max-w-4xl mx-auto px-6 md:px-12 pt-16 md:pt-24 pb-10 text-center">
        <h2 className="font-instrument-serif text-3xl sm:text-4xl md:text-5xl leading-tight">
          {t('landReady')}
        </h2>
        {me ? (
          <>
            <div className="mt-8 flex justify-center">
              <Link
                to={homeOf(me.role)}
                className="w-full sm:w-auto bg-ochre text-soil-dark rounded-full px-8 py-4 text-sm font-medium hover:brightness-105 transition"
              >
                {t('landContinue').replace('{name}', me.name)}
              </Link>
            </div>
            <p className="mt-5 text-sm text-cream/70">
              {t('landNotYou')}{' '}
              <button onClick={() => { void logout() }} className="text-cream font-medium underline underline-offset-4">
                {t('landSwitchUser')}
              </button>
            </p>
          </>
        ) : (
          <>
            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link
                to="/signup/farmer"
                className="w-full sm:w-auto bg-ochre text-soil-dark rounded-full px-8 py-4 text-sm font-medium hover:brightness-105 transition"
              >
                {t('landFarmer')}
              </Link>
              <Link
                to="/signup/expert"
                className="w-full sm:w-auto border border-cream/60 text-cream rounded-full px-8 py-4 text-sm font-medium hover:bg-cream/10 transition-colors"
              >
                {t('landExpert')}
              </Link>
            </div>
            <p className="mt-5 text-sm text-cream/70">
              {t('authHaveAccount')}{' '}
              <Link to="/login" className="text-cream font-medium underline underline-offset-4">{t('authLogin')}</Link>
            </p>
          </>
        )}

        <footer id="contact" className="mt-16 md:mt-24 border-t border-cream/10 pt-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <span className="flex items-center gap-2 font-semibold tracking-tight"><BrandMark size={28} />AnnRakshak</span>
            <p className="text-xs font-light text-cream/60 order-last sm:order-none">
              Smart India Hackathon 2026 · PS 26131 · Govt. of Maharashtra
            </p>
            <div className="flex items-center gap-4">
              <a
                href="mailto:team@annrakshak.in"
                aria-label="Email the team"
                className="text-cream/60 hover:text-cream transition-colors"
              >
                <Mail className="w-4 h-4" />
              </a>
              <a
                href="https://github.com/annrakshak"
                aria-label="Project repository"
                className="text-cream/60 hover:text-cream transition-colors"
              >
                <Globe className="w-4 h-4" />
              </a>
            </div>
          </div>
        </footer>
      </div>
    </section>
  )
}

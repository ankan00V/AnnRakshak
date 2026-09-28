import { Globe, Mail } from 'lucide-react'
import { Link } from 'react-router-dom'
import BrandMark from '../ui/BrandMark'
import Reveal from '../ui/Reveal'
import { useAuth } from '../auth/AuthContext'
import { homeOf } from '../auth/helpers'
import { useFarmer } from '../farmer/FarmerContext'

/** What the advice actually rests on. Government sources, named. */
const SOURCES = [
  { name: 'ICAR', line: 'Rice and maize disease images; 24 released bio-inputs with the institute to call' },
  { name: 'IMD', line: 'Subdivision rainfall normals, 1901–2017, for all four Maharashtra subdivisions' },
  { name: 'MoSPI', line: 'State pesticide consumption — the 8,719 t baseline this has to move' },
  { name: 'Sentinel-2 · Landsat 8', line: 'Per-field NDVI, cloud-filtered, watched for a fall in vigour' },
]

export default function FinalCta() {
  const { me, logout } = useAuth()
  const { t } = useFarmer()
  return (
    <section id="cta" className="w-full bg-leaf-deep text-cream">
      <div className="max-w-6xl mx-auto px-6 md:px-12 pt-20 md:pt-28">
        <Reveal>
          <div className="grid gap-y-7 gap-x-8 sm:grid-cols-2 lg:grid-cols-4 border-y border-cream/15 py-8">
            {SOURCES.map(({ name, line }) => (
              <div key={name}>
                <p className="text-sm font-medium text-ochre">{name}</p>
                <p className="mt-1.5 text-xs font-light leading-relaxed text-cream/75 text-pretty">{line}</p>
              </div>
            ))}
          </div>
        </Reveal>
      </div>

      <div className="max-w-4xl mx-auto px-6 md:px-12 pt-16 md:pt-20 pb-10 text-center">
        <h2 className="font-instrument-serif text-[2rem] sm:text-4xl md:text-5xl leading-[1.05] text-balance">
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
            <p className="text-xs font-light text-cream/75 order-last sm:order-none">
              Smart India Hackathon 2026 · PS 26131 · Govt. of Maharashtra
            </p>
            <div className="flex items-center gap-4">
              <a
                href="mailto:team@annrakshak.in"
                aria-label="Email the team"
                className="text-cream/75 hover:text-cream transition-colors"
              >
                <Mail className="w-4 h-4" />
              </a>
              <a
                href="https://github.com/annrakshak"
                aria-label="Project repository"
                className="text-cream/75 hover:text-cream transition-colors"
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

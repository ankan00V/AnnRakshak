import { Globe, Mail } from 'lucide-react'
import { Link } from 'react-router-dom'
import BrandMark from '../ui/BrandMark'
import Reveal from '../ui/Reveal'
import FootageBackdrop from '../ui/FootageBackdrop'
import { useAuth } from '../auth/AuthContext'
import { homeOf } from '../auth/helpers'
import { useFarmer } from '../farmer/FarmerContext'
import { LANGS } from '../lib/i18n'
import { PHOTO_CREDITS } from '../lib/photoCredits'

const LANGUAGES = LANGS.filter((l) => l.ready).length

/** Who we are, in four lines a farmer or an officer would care about. The
 *  datasets behind the advice are in the docs; this strip is about the app. */
const ABOUT = [
  { name: 'Anna + rakshak', line: 'landAboutName' },
  { name: 'landAboutCrops', line: 'landAboutCropsLine' },
  { name: 'landAboutLangs', line: 'landAboutLangsLine' },
  { name: 'landAboutPerson', line: 'landAboutPersonLine' },
]

export default function FinalCta() {
  const { me, logout } = useAuth()
  const { t } = useFarmer()
  return (
    <section id="cta" className="relative w-full overflow-hidden bg-[#0e2a17] text-cream">
      {/* The closing block asks whether you are ready to protect your
          harvest; behind it, a harvest, filmed by the team: the combine at the
          top, the words on the paddy below it, and the page ends on deep green
          under the four facts and the footer. */}
      {/* The clip is cut from the 1080p original to the combine and the paddy
          (the village behind them is left out), slowed to 60% with the
          in-between frames interpolated, so the three-second shot plays as a
          calm five. It plays as a band: the
          combine along the top, the words on the paddy beneath it. The band's
          shape follows the width, so the combine stays clear of the words at
          every size. */}
      <div className="absolute inset-x-0 top-0 h-[128vw] sm:h-[72vw] lg:h-[46vw]">
        <FootageBackdrop src="/footage/harvest.mp4" poster="/footage/harvest-poster.webp"
          objectClass="object-[50%_30%]"
          scrim={<>
            <div className="absolute inset-0 bg-gradient-to-b from-[#0e2a17]/5 via-[#0e2a17]/25 via-[50%] to-[#0e2a17] to-[96%]" />
            <div className="absolute inset-0 bg-[radial-gradient(40%_22%_at_50%_64%,rgba(10,30,16,0.5),transparent_75%)]" />
          </>} />
        {/* Covers the band's last pixel row, which would otherwise show as a
            thin line where the video meets the green. */}
        <div aria-hidden className="absolute inset-x-0 -bottom-1 h-8 bg-[#0e2a17]" />
      </div>

      <div className="relative mx-auto max-w-[1720px] px-6 md:px-12 lg:px-[7vw]">
        <div className="mx-auto max-w-3xl pt-[80vw] text-center sm:pt-[44vw] lg:pt-[24vw]">
          <h2 className="font-display text-[34px] leading-[1.06] tracking-[-0.01em] text-balance drop-shadow-[0_2px_18px_rgba(0,0,0,0.35)] lg:text-[clamp(30px,2.8vw,54px)]">
            {t('landReady')}
          </h2>
          {me ? (
            <>
              <div className="mt-8 flex justify-center lg:mt-[2vw]">
                <Link to={homeOf(me.role)}
                  className="inline-flex min-h-[52px] w-full items-center justify-center rounded-full bg-[#f0b84a] px-8 text-[15px] font-semibold text-[#1f2a14] shadow-[0_14px_30px_-14px_rgba(0,0,0,0.6)] transition hover:bg-[#f4c565] sm:w-auto">
                  {t('landContinue').replace('{name}', me.name)}
                </Link>
              </div>
              <p className="mt-5 text-sm text-cream/80">
                {t('landNotYou')}{' '}
                <button onClick={() => { void logout() }} className="font-medium text-cream underline underline-offset-4">
                  {t('landSwitchUser')}
                </button>
              </p>
            </>
          ) : (
            <>
              <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row lg:mt-[2vw] lg:gap-[1vw]">
                <Link to="/signup/farmer"
                  className="inline-flex min-h-[52px] w-full items-center justify-center rounded-full bg-[#f0b84a] px-8 text-[15px] font-semibold text-[#1f2a14] shadow-[0_14px_30px_-14px_rgba(0,0,0,0.6)] transition hover:bg-[#f4c565] sm:w-auto">
                  {t('landFarmer')}
                </Link>
                <Link to="/signup/expert"
                  className="inline-flex min-h-[52px] w-full items-center justify-center rounded-full border border-cream/70 bg-black/15 px-8 text-[15px] font-semibold text-cream backdrop-blur-[2px] transition hover:bg-white/10 sm:w-auto">
                  {t('landExpert')}
                </Link>
              </div>
              <p className="mt-5 text-sm text-cream/85">
                {t('authHaveAccount')}{' '}
                <Link to="/login" className="font-medium text-cream underline underline-offset-4">{t('authLogin')}</Link>
              </p>
            </>
          )}
        </div>

        <Reveal>
          <div className="mt-14 grid gap-x-8 gap-y-6 border-t border-cream/15 pt-8 sm:grid-cols-2 lg:mt-[clamp(56px,5vw,96px)] lg:grid-cols-4 lg:gap-0">
            {ABOUT.map(({ name, line }, i) => (
              <div key={name} className={`lg:px-[1.6vw] ${i ? 'lg:border-l lg:border-cream/15' : 'lg:pl-0'}`}>
                <p className="text-[15px] font-semibold text-[#f0c060]">{name.startsWith('land') ? t(name).replace('{n}', String(LANGUAGES)) : name}</p>
                <p className="mt-1.5 text-[13px] leading-relaxed text-cream/75 text-pretty">{t(line)}</p>
              </div>
            ))}
          </div>
        </Reveal>

        <footer id="contact" className="mt-10 flex flex-col items-center justify-between gap-4 border-t border-cream/10 py-7 sm:flex-row">
          <span className="flex items-center gap-2.5 font-semibold tracking-tight">
            <span className="rounded-full bg-white p-[2px]"><BrandMark size={28} /></span>AnnRakshak
          </span>
          <div className="flex items-center gap-2">
            <a href="mailto:team@annrakshak.in" aria-label={t('landEmailTeam')}
              className="grid h-11 w-11 place-items-center rounded-full text-cream/75 transition-colors hover:bg-white/10 hover:text-cream">
              <Mail className="h-[18px] w-[18px]" />
            </a>
            <a href="https://github.com/annrakshak" aria-label={t('landRepo')}
              className="grid h-11 w-11 place-items-center rounded-full text-cream/75 transition-colors hover:bg-white/10 hover:text-cream">
              <Globe className="h-[18px] w-[18px]" />
            </a>
          </div>
        </footer>
        {/* CC BY 4.0 asks for credit wherever its photographs are shown; the
            field checks show one per problem (kb/reference_photos.json). */}
        <p className="pb-6 text-center text-[12px] leading-relaxed text-cream/55 text-pretty">
          {t('landPhotoCredits')}:{' '}
          {PHOTO_CREDITS.map((c, i) => (
            <span key={c.url}>
              {i > 0 && ' · '}
              <a href={c.url} target="_blank" rel="noreferrer" className="underline decoration-cream/30 underline-offset-2 hover:text-cream">{c.name}</a>
              {' '}({c.licence})
            </span>
          ))}
        </p>
      </div>
    </section>
  )
}

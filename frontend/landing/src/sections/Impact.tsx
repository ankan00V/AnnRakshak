import { CheckCircle2 } from 'lucide-react'
import { useFarmer } from '../farmer/FarmerContext'
import type { ReactNode } from 'react'
import Reveal from '../ui/Reveal'

/** Who it is for, one card each: the thing they actually see, a line, and
 *  three short promises. The farmer's picture is the real answer screen in
 *  Marathi; the officer's is the case as it reaches the expert queue, with
 *  everything needed to confirm it. */

const FARMER_POINTS = [
  'landFarmerP1',
  'landFarmerP2',
  'landFarmerP3',
]

const OFFICIAL_POINTS = [
  'landOfficialP1',
  'landOfficialP2',
  'landOfficialP3',
]

function CaseCard() {
  const { t } = useFarmer()
  return (
    <div className="rounded-[18px] bg-white p-3.5 text-soil-dark shadow-[0_18px_36px_-22px_rgba(43,29,18,0.5)] ring-1 ring-black/[0.06]">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-soil-dark/60">{t('landCaseMeta')}</p>
        <span className="rounded-full bg-ochre/15 px-2.5 py-0.5 text-[10px] font-medium text-soil">{t('landCaseWaiting')}</span>
      </div>
      <div className="mt-3 flex gap-3">
        <img src="/shots/gradcam-blast.webp" alt={t('landCaseAlt')}
          loading="lazy" className="h-16 w-16 shrink-0 rounded-xl object-cover" />
        <div className="min-w-0 flex-1 space-y-2">
          {[[t('landNeckBlast'), 71], [t('landFalseSmut'), 22]].map(([name, pct]) => (
            <div key={name}>
              <p className="flex justify-between text-[11px]"><span className="font-medium">{name}</span><span className="tabular-nums text-soil-dark/60">{pct}%</span></p>
              <div className="mt-1 h-1.5 rounded-full bg-soil-dark/10"><div className="h-full rounded-full bg-ochre" style={{ width: `${pct}%` }} /></div>
            </div>
          ))}
        </div>
      </div>
      <p className="mt-3 rounded-xl bg-cream px-3 py-2 text-[11px] leading-relaxed text-soil-dark/80">
        {t('landCaseAnswer')}
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] font-medium">
        <span className="rounded-full bg-leaf-deep py-1.5 text-center text-cream">{t('landCaseConfirm')}</span>
        <span className="rounded-full border border-soil-dark/20 py-1.5 text-center">{t('landCaseCorrect')}</span>
      </div>
    </div>
  )
}

function Card({ id, title, line, show, points }: {
  id?: string; title: string; line: string; show: ReactNode; points: string[]
}) {
  const { t } = useFarmer()
  return (
    <div id={id} className="scroll-mt-24 grid h-full items-center gap-6 overflow-hidden rounded-[26px] bg-gradient-to-br from-[#eef2e3] to-[#f8f6ee] p-6 ring-1 ring-[#1d4a2c]/[0.07] sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1fr)] lg:gap-[2vw] lg:p-[2vw]">
      <div>{show}</div>
      <div>
        <h2 className="font-display text-[30px] leading-none tracking-[-0.01em] lg:text-[clamp(24px,2vw,38px)]">{title}</h2>
        <p className="mt-3 text-[15px] leading-relaxed text-[#3d4a40] text-pretty lg:mt-[0.9vw] lg:text-[clamp(13px,0.95vw,17px)]">{line}</p>
        <ul className="mt-5 space-y-2.5 lg:mt-[1.3vw]">
          {points.map((p) => (
            <li key={p} className="flex items-start gap-2.5 text-[14px] text-[#2c3a30] lg:text-[clamp(13px,0.9vw,16px)]">
              <CheckCircle2 className="mt-0.5 h-[18px] w-[18px] shrink-0 fill-[#4f8a37] text-white" aria-hidden />
              {t(p)}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default function Impact() {
  const { t } = useFarmer()
  return (
    <section id="impact" className="w-full bg-[#f6f1e6] text-[#1f3a26]">
      <div className="mx-auto grid max-w-[1720px] gap-5 px-6 py-14 md:px-12 lg:grid-cols-2 lg:gap-[1.6vw] lg:px-[7vw] lg:py-[clamp(48px,4vw,80px)]">
        <Reveal className="h-full">
          <Card
            title={t('landForFarmers')}
            line={t('landForFarmersLine')}
            show={
              // The Marathi answer, cropped to the name and how sure it is.
              <div className="relative mx-auto aspect-[5/4] max-w-[320px] overflow-hidden [mask-image:linear-gradient(to_bottom,black_80%,transparent)]">
                <img src="/photos/phone-result-mr.webp" width={620} height={1266} loading="lazy" decoding="async"
                  alt={t('landFarmerAlt')}
                  className="absolute left-0 top-[-104%] w-full drop-shadow-[0_18px_24px_rgba(0,0,0,0.25)]" />
              </div>
            }
            points={FARMER_POINTS}
          />
        </Reveal>
        <Reveal delay={100} className="h-full">
          <Card
            id="for-officials"
            title={t('landForOfficials')}
            line={t('landForOfficialsLine')}
            show={<div className="mx-auto max-w-[320px]"><CaseCard /></div>}
            points={OFFICIAL_POINTS}
          />
        </Reveal>
      </div>
    </section>
  )
}

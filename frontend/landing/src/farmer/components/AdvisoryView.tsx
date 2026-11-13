import { useState } from 'react'
import { Ban, BadgeCheck, BookOpen, ChevronDown, FlaskConical, Leaf, ListChecks, Phone, PhoneCall, ShieldAlert, Sprout } from 'lucide-react'
import type { Advisory, IcarTech, LadderRung } from '../../api/types'
import { ListenButton, Pill } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'
import { PANEL } from '../tokens'
import { PanelHead } from '../ui'

const TIER = {
  cultural: { icon: Sprout, tone: 'bg-[#e3efd9] text-[#2f6a39]', key: 'cultural' },
  biological: { icon: Leaf, tone: 'bg-[#eef3d6] text-[#55631a]', key: 'biological' },
  chemical: { icon: FlaskConical, tone: 'bg-[#f9dcd5] text-[#9a2f17]', key: 'chemical' },
}

/** The advisory in the order the product promises: what NOT to do first and
 *  loudest, then the ladder cultural → biological → chemical, with the
 *  chemical rung collapsed until the farmer asks for it. */
export default function AdvisoryView({ advisory }: { advisory: Advisory }) {
  const { t, lang } = useFarmer()
  const [showChem, setShowChem] = useState(false)
  const nonChem = advisory.ladder.filter((r) => r.tier !== 'chemical')
  const chem = advisory.ladder.filter((r) => r.tier === 'chemical')

  const speech = [
    advisory.name + '.',
    t('whatToAvoid') + ': ' + advisory.what_to_avoid.join(' '),
    t('whatToDo') + ': ' + nonChem.map((r) => r.action).join(' '),
    advisory.what_to_check,
  ].join(' ')

  return (
    <div className="space-y-4">
      <section className="rounded-[28px] bg-[#fdf0ed] p-5 ring-1 ring-[#9a2f17]/10 lg:p-6">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#f9dcd5] text-[#9a2f17]">
            <Ban className="h-6 w-6" aria-hidden />
          </span>
          <h2 className="min-w-0 flex-1 text-[20px] font-semibold tracking-tight text-[#9a2f17] sm:text-[22px]">{t('whatToAvoid')}</h2>
          <ListenButton text={speech} lang={lang} label={t('listen')} stopLabel={t('stop')} />
        </div>
        <ul className="mt-4 space-y-2.5">
          {advisory.what_to_avoid.map((a, i) => (
            <li key={i} className="flex gap-2.5 text-[15px] font-medium leading-snug text-soil-dark">
              <span aria-hidden className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-[12px] font-bold text-[#9a2f17]">✕</span>
              {a}
            </li>
          ))}
        </ul>
      </section>

      <section className={`${PANEL} p-5 lg:p-6`}>
        <PanelHead icon={ListChecks} title={t('whatToDo')} sub={advisory.what_to_check} />
        <ol className="mt-5 space-y-4">
          {nonChem.map((r, i) => (
            <Rung key={i} rung={r} n={i + 1} />
          ))}
        </ol>

        {chem.length > 0 && (
          <div className="mt-5 rounded-[20px] bg-[#f5f7f1] p-4">
            <p className="text-[14px] text-soil-dark/80">{t('chemicalLast')}</p>
            <button
              onClick={() => setShowChem((s) => !s)}
              aria-expanded={showChem}
              className="mt-3 flex min-h-[48px] w-full items-center justify-center gap-2 rounded-full bg-white text-[15px] font-semibold text-[#9a2f17] ring-1 ring-[#9a2f17]/20"
            >
              <FlaskConical className="w-4 h-4" />
              {showChem ? t('hideChemical') : t('showChemical')}
              <ChevronDown className={`w-4 h-4 transition-transform ${showChem ? 'rotate-180' : ''}`} />
            </button>
            {showChem && (
              <ol className="mt-3 space-y-3 animate-fadein">
                {chem.map((r, i) => (
                  <Rung key={i} rung={r} n={nonChem.length + i + 1} />
                ))}
              </ol>
            )}
          </div>
        )}
      </section>

      {advisory.icar_options?.length > 0 && (
        <section className={`${PANEL} p-5 lg:p-6`}>
          <PanelHead icon={BadgeCheck} title={t('icarTitle')} sub={t('icarSub')} />
          <ul className="mt-4 space-y-3">
            {advisory.icar_options.map((o) => <IcarOption key={o.id} o={o} />)}
          </ul>
        </section>
      )}

      <section className="rounded-[28px] bg-[#1d4a2c] p-5 text-white lg:p-6">
        <div className="flex items-start gap-3">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-white/15">
            <PhoneCall className="h-6 w-6" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[17px] font-semibold">{t('expertTrigger')}</p>
            <p className="mt-1 text-[15px] leading-snug text-white/85">{advisory.expert_trigger}</p>
          </div>
        </div>
        <a href="tel:18001801551"
          className="mt-4 flex min-h-[48px] w-full items-center justify-center gap-2 rounded-full bg-white px-5 text-center text-[15px] font-semibold text-[#1d4a2c] sm:ml-[60px] sm:w-auto sm:inline-flex">
          <Phone className="h-4 w-4" aria-hidden /> {t('callKcc')}
        </a>
      </section>

      <details className="group rounded-[20px] bg-white/70 p-4 text-[13px] ring-1 ring-soil-dark/[0.06]">
        <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-soil-dark/75 [&::-webkit-details-marker]:hidden">
          <BookOpen className="h-4 w-4" aria-hidden />
          {t('sources')} ({advisory.citations.length})
          <ChevronDown className="ml-auto h-4 w-4 transition-transform group-open:rotate-180" aria-hidden />
        </summary>
        <ul className="mt-3 space-y-2">
          {advisory.citations.map((c, i) => (
            <li key={i} className="text-soil-dark/70">
              <span className="font-medium text-soil-dark">{c.title}</span> — {c.publisher}
              {c.url && (
                <a href={c.url} target="_blank" rel="noreferrer" className="ml-1 text-leaf-deep underline">
                  {c.url.replace(/^https?:\/\//, '')}
                </a>
              )}
            </li>
          ))}
        </ul>
      </details>
    </div>
  )
}

function Rung({ rung, n }: { rung: LadderRung; n: number }) {
  const { t } = useFarmer()
  const tier = TIER[rung.tier]
  const Icon = tier.icon
  return (
    <li className="flex gap-3">
      <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${tier.tone}`}>
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-soil-dark/70">
          {n}. {t(tier.key)}
        </p>
        {rung.tier !== 'chemical' ? (
          <p className="mt-0.5 text-[15px] leading-snug">{rung.action}</p>
        ) : (
          <div className="mt-0.5 space-y-1">
            <p className="text-[14px] font-semibold">{rung.product}</p>
            {rung.dose && <p className="text-[13px]">{rung.dose}</p>}
            {rung.for_field && (
              <p className="text-[13px] rounded-lg bg-cream px-2 py-1.5">
                <span className="font-medium">{t('doseForField')}: </span>
                {rung.for_field.replace(/^[^:]+:\s*/, '')}
              </p>
            )}
            {rung.timing && <p className="text-xs text-soil-dark/60">{rung.timing}</p>}
            <p className="text-xs flex items-start gap-1.5 text-soil-dark/70">
              <ShieldAlert className="w-3.5 h-3.5 text-ochre shrink-0 mt-px" />
              {rung.label_rule}
            </p>
            {!rung.verified && <Pill tone="ochre">{t('dosePending')}</Pill>}
          </div>
        )}
      </div>
    </li>
  )
}

const ICAR_TYPE_KEY = {
  biocontrol: 'icar_biocontrol',
  variety: 'icar_variety',
  practice: 'icar_practice',
  app: 'icar_app',
  monitoring: 'icar_monitoring',
  reference: 'icar_monitoring',
} as const

function IcarOption({ o }: { o: IcarTech }) {
  const { t } = useFarmer()
  return (
    <li className="rounded-[20px] bg-[#f5f7f1] p-4">
      <Pill tone="leaf" className="!text-[10px]">{t(ICAR_TYPE_KEY[o.type])}</Pill>
      <p className="mt-2 text-[15px] leading-snug">{o.summary}</p>
      {o.link_reason && (
        <p className="mt-1 text-xs text-soil-dark/70"><span className="font-medium">{t('icarWhy')}: </span>{o.link_reason}</p>
      )}
      {o.claim && (
        <p className="mt-1 text-xs text-leaf-deep"><span className="font-medium">{t('icarResult')}: </span>{o.claim}</p>
      )}
      {o.supply && (
        <p className="mt-1 text-xs text-soil-dark/70"><span className="font-medium">{t('icarSupply')}: </span>{o.supply}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-soil-dark/60">
        <span>{o.institute.name}, {o.institute.city}</span>
        {o.institute.phone && (
          <a href={`tel:${o.institute.phone.replace(/[^0-9+]/g, '')}`} className="inline-flex items-center gap-1 text-leaf-deep font-medium">
            <Phone className="w-3 h-3" /> {t('icarCall')} {o.institute.phone}
          </a>
        )}
        {o.lead_time_days && <Pill tone="ochre" className="!text-[10px]">{t('icarLead').replace('{n}', String(o.lead_time_days))}</Pill>}
      </div>
    </li>
  )
}

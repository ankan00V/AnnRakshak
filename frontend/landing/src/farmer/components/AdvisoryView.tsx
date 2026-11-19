import { useState } from 'react'
import { Ban, BadgeCheck, BookOpen, ChevronDown, CookingPot, FlaskConical, Leaf, ListChecks, Phone, PhoneCall, ShieldAlert, Sprout } from 'lucide-react'
import type { Advisory, HomemadeOption, IcarTech, LadderRung, OrganicOption } from '../../api/types'
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
 *  loudest, then everything organic — field steps, natural control, registered
 *  organic products and neem made at home — and the chemical last, collapsed
 *  until the farmer asks, or a plain statement that none is registered. */
export default function AdvisoryView({ advisory }: { advisory: Advisory }) {
  const { t, lang } = useFarmer()
  const [showChem, setShowChem] = useState(false)
  const nonChem = advisory.ladder.filter((r) => r.tier !== 'chemical')
  const chem = advisory.ladder.filter((r) => r.tier === 'chemical')
  // A deficiency or a disorder is not a pest: its steps stand alone, with no
  // organic-or-chemical framing that would suggest a pesticide could help.
  const pestOrDisease = !advisory.kind || ['pest', 'disease', 'virus'].includes(advisory.kind)

  const speech = [
    advisory.name + '.',
    t('whatToAvoid') + ': ' + advisory.what_to_avoid.join(' '),
    t('whatToDo') + ': ' + nonChem.map((r) => r.action).join(' '),
    ...(advisory.organic?.length
      ? [t('organicTitle') + ': ' + advisory.organic.map((o) => `${o.product}. ${o.dose}`).join(' ')]
      : []),
    ...(advisory.homemade?.length
      ? [t('homemadeTitle') + ': ' + advisory.homemade.map((h) => `${h.name}. ${h.dose} ${h.timing}`).join(' ')]
      : []),
    ...(advisory.chemical_none ? [advisory.chemical_none] : []),
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
        {pestOrDisease ? (
          <Organic rungs={nonChem} options={advisory.organic ?? []} homemade={advisory.homemade ?? []} />
        ) : (
          <ol className="mt-5 space-y-4">
            {nonChem.map((r, i) => (
              <Rung key={i} rung={r} n={i + 1} />
            ))}
          </ol>
        )}

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
        {chem.length === 0 && advisory.chemical_none && (
          <div className="mt-5 flex items-start gap-3 rounded-[20px] bg-[#f5f7f1] p-4">
            <FlaskConical className="mt-0.5 h-5 w-5 shrink-0 text-[#9a2f17]" aria-hidden />
            <div>
              <p className="text-[14px] font-semibold text-[#9a2f17]">{t('chemicalNoneTitle')}</p>
              <p className="mt-0.5 text-[14px] leading-snug text-soil-dark/85">{advisory.chemical_none}</p>
            </div>
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
                <a href={c.url} target="_blank" rel="noreferrer" className="ml-1 text-leaf-deep underline [overflow-wrap:anywhere]">
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
          <>
            <p className="mt-0.5 text-[15px] leading-snug">{rung.action}</p>
            {rung.source && <p className="mt-1 text-[12px] text-soil-dark/60">{t('homemadeSource')}: {rung.source}</p>}
          </>
        ) : (
          <div className="mt-0.5 space-y-1">
            <p className="text-[14px] font-semibold">{rung.product}</p>
            {rung.use === 'seed' && <Pill tone="neutral" className="!text-[12px]">{t('useSeed')}</Pill>}
            {rung.dose && <p className="text-[13px]">{rung.dose}</p>}
            {rung.for_field && (
              <p className="text-[13px] rounded-lg bg-cream px-2 py-1.5">
                <span className="font-medium">{t('doseForField')}: </span>
                {rung.for_field.replace(/^[^:]+:\s*/, '')}
              </p>
            )}
            {rung.timing && <p className="text-[13px] text-soil-dark/75">{rung.timing}</p>}
            {rung.waiting && <p className="text-[13px] font-medium text-soil-dark/85">{rung.waiting}</p>}
            <p className="text-[13px] flex items-start gap-1.5 text-soil-dark/75">
              <ShieldAlert className="w-3.5 h-3.5 text-ochre shrink-0 mt-0.5" aria-hidden />
              {rung.label_rule}
            </p>
            {!rung.verified && <Pill tone="ochre">{t('dosePending')}</Pill>}
          </div>
        )}
      </div>
    </li>
  )
}

const USE_KEY = { spray: 'useSpray', seed: 'useSeed', root_dip: 'useRootDip' } as const

/** The organic products India registers for this problem, between the field
 *  steps and the chemical — or a plain statement that there are none. */
function Organic({ rungs, options, homemade }: { rungs: LadderRung[]; options: OrganicOption[]; homemade: HomemadeOption[] }) {
  const { t } = useFarmer()
  const living = options.some((o) => o.kind === 'bio-agent')
  return (
    <div className="mt-5 rounded-[22px] bg-[#f3f6e4] p-4 ring-1 ring-[#55631a]/10 lg:p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#e2eac0] text-[#55631a]">
          <Leaf className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-[17px] font-semibold tracking-tight text-[#3d4812]">{t('organicTitle')}</h3>
          <p className="text-[14px] leading-snug text-soil-dark/75">{t('organicStart')}</p>
        </div>
      </div>
      <ol className="mt-4 space-y-4 rounded-[18px] bg-white p-4 ring-1 ring-soil-dark/[0.05]">
        {rungs.map((r, i) => (
          <Rung key={i} rung={r} n={i + 1} />
        ))}
      </ol>
      <h4 className="mt-5 text-[15px] font-semibold text-[#3d4812]">{t('organicProducts')}</h4>
      {options.length > 0 ? (
        <>
          <p className="text-[13px] leading-snug text-soil-dark/75">{t('organicSub')}</p>
          <ul className="mt-3 space-y-3">
            {options.map((o, i) => (
              <li key={i} className="rounded-[18px] bg-white p-4 ring-1 ring-soil-dark/[0.05]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Pill tone="leaf" className="!text-[12px]">{t(USE_KEY[o.use])}</Pill>
                  <Pill tone="neutral" className="!text-[12px]">{t(o.kind === 'botanical' ? 'organicBotanical' : 'organicBio')}</Pill>
                </div>
                <p className="mt-2 text-[15px] font-semibold leading-snug">{o.product}</p>
                <p className="mt-1 text-[14px] leading-snug">{o.dose}</p>
                {o.for_field && (
                  <p className="mt-1.5 rounded-lg bg-cream px-2 py-1.5 text-[13px]">
                    <span className="font-medium">{t('doseForField')}: </span>
                    {o.for_field.replace(/^[^:]+:\s*/, '')}
                  </p>
                )}
                {o.timing && <p className="mt-1.5 text-[13px] text-soil-dark/75">{o.timing}</p>}
                {o.waiting && <p className="mt-1 text-[13px] font-medium text-soil-dark/85">{o.waiting}</p>}
                <p className="mt-2 flex items-center gap-1.5 text-[12px] text-[#55631a]">
                  <BadgeCheck className="h-3.5 w-3.5 shrink-0" aria-hidden /> {t('organicRegistered')}
                </p>
              </li>
            ))}
          </ul>
          {living && <p className="mt-3 text-[13px] leading-snug text-soil-dark/70">{t('organicCare')}</p>}
        </>
      ) : (
        <p className="mt-1 text-[13px] leading-snug text-soil-dark/75">{t('organicNoProduct')}</p>
      )}
      {homemade.length > 0 && <Homemade items={homemade} />}
    </div>
  )
}

/** Neem preparations the farmer makes at home. Not registered products, so
 *  no label and no waiting period: the strength, when to spray, how to make
 *  it, and the government source that recommends it for this problem. */
function Homemade({ items }: { items: HomemadeOption[] }) {
  const { t } = useFarmer()
  return (
    <div className="mt-5 border-t border-[#55631a]/15 pt-4">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#e2eac0] text-[#55631a]">
          <CookingPot className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h4 className="text-[16px] font-semibold tracking-tight text-[#3d4812]">{t('homemadeTitle')}</h4>
          <p className="text-[13px] leading-snug text-soil-dark/75">{t('homemadeSub')}</p>
        </div>
      </div>
      <ul className="mt-3 space-y-3">
        {items.map((h, i) => (
          <li key={i} className="rounded-[18px] bg-white p-4 ring-1 ring-soil-dark/[0.05]">
            <p className="text-[15px] font-semibold leading-snug">{h.name}</p>
            <p className="mt-1 text-[14px] leading-snug">{h.dose}</p>
            <p className="mt-1.5 text-[13px] text-soil-dark/75">{h.timing}</p>
            <details className="group mt-2.5 rounded-xl bg-[#f6f8ef] px-3 py-2">
              <summary className="flex min-h-[36px] cursor-pointer list-none items-center justify-between text-[14px] font-medium text-[#3d4812]">
                {t('homemadeRecipe')}
                <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden />
              </summary>
              <ol className="mt-1 list-decimal space-y-1 pb-1 pl-5 text-[13px] leading-snug">
                {h.recipe.map((step, j) => <li key={j}>{step}</li>)}
              </ol>
            </details>
            <p className="mt-2 text-[12px] text-soil-dark/65">{t('homemadeSource')}: {h.source}</p>
          </li>
        ))}
      </ul>
    </div>
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
      <Pill tone="leaf" className="!text-[12px]">{t(ICAR_TYPE_KEY[o.type])}</Pill>
      <p className="mt-2 text-[15px] leading-snug">{o.summary}</p>
      {o.link_reason && (
        <p className="mt-1 text-[13px] text-soil-dark/75"><span className="font-medium">{t('icarWhy')}: </span>{o.link_reason}</p>
      )}
      {o.claim && (
        <p className="mt-1 text-[13px] text-leaf-deep"><span className="font-medium">{t('icarResult')}: </span>{o.claim}</p>
      )}
      {o.supply && (
        <p className="mt-1 text-[13px] text-soil-dark/75"><span className="font-medium">{t('icarSupply')}: </span>{o.supply}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-[13px] text-soil-dark/75">
        <span>{o.institute.name}, {o.institute.city}</span>
        {/* A pill a thumb can hit: calling the institute is how a farmer gets the input. */}
        {o.institute.phone && (
          <a href={`tel:${o.institute.phone.replace(/[^0-9+]/g, '')}`}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-full bg-white px-3 text-[14px] font-medium text-leaf-deep ring-1 ring-[#4b8b3b]/20 active:brightness-95">
            <Phone className="w-4 h-4" aria-hidden /> {t('icarCall')} <span className="tabular-nums">{o.institute.phone}</span>
          </a>
        )}
        {o.lead_time_days && <Pill tone="ochre" className="!text-[12px]">{t('icarLead').replace('{n}', String(o.lead_time_days))}</Pill>}
      </div>
    </li>
  )
}

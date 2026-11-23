import { useEffect, useRef, useState } from 'react'
import { Ban, BadgeCheck, BookOpen, ChevronDown, CookingPot, FlaskConical, Leaf, ListChecks, Phone, PhoneCall, ShieldAlert, Sprout, Trees } from 'lucide-react'
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
 *  loudest, then everything organic, and the chemical last, collapsed until the
 *  farmer asks, or a plain statement that none is registered.
 *
 *  The organic part is four groups, each headed by who stands behind it:
 *    1. field steps (an ICAR or university step carries a small mark),
 *    2. products registered by CIB&RC for this crop and problem,
 *    3. preparations made at home that ICAR, a university or government IPM
 *       guidance recommends,
 *    4. preparations from the ICAR natural farming protocol, which are not
 *       registered pesticides and have no tested dose — said in the heading. */
export default function AdvisoryView({ advisory }: { advisory: Advisory }) {
  const { t, lang } = useFarmer()
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
    ...byBacking(advisory.homemade ?? []).flatMap(([key, items]) =>
      items.length ? [t(key) + ': ' + items.map((h) => `${h.name}. ${h.dose} ${h.timing}`).join(' ')] : []),
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
          <Choice advisory={advisory} nonChem={nonChem} chem={chem} />
        ) : (
          <ol className="mt-5 space-y-4">
            {nonChem.map((r, i) => (
              <Rung key={i} rung={r} n={i + 1} />
            ))}
          </ol>
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

/** Home preparations in two groups, recommended first: [heading key, items]. */
function byBacking(items: HomemadeOption[]): ['levelRecommended' | 'levelNatural', HomemadeOption[]][] {
  return [
    ['levelRecommended', items.filter((h) => h.backing !== 'natural_farming')],
    ['levelNatural', items.filter((h) => h.backing === 'natural_farming')],
  ]
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
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] font-semibold text-soil-dark/70">
          <span>{n}. {t(tier.key)}</span>
          {rung.backing === 'recommended' && (
            <span className="inline-flex items-center gap-1 rounded-full bg-[#e3efd9] px-2 py-0.5 text-[11px] font-semibold text-[#2f6a39]">
              <BadgeCheck className="h-3 w-3" aria-hidden /> {t('chipRecommended')}
            </span>
          )}
        </p>
        {rung.tier !== 'chemical' ? (
          <>
            <p className="mt-0.5 text-[15px] leading-snug">{rung.action}</p>
            {rung.source && <p className="mt-1 text-[12px] text-soil-dark/60">{t('homemadeSource')}: {rung.source}</p>}
          </>
        ) : (
          <>
            <p className="mt-0.5 text-[14px] font-semibold">{rung.product}</p>
            <ChemDetails rung={rung} />
          </>
        )}
      </div>
    </li>
  )
}

/** A chemical product: dose, the farmer's field, when, waiting period, and
 *  the rule that the printed label decides. */
function ChemDetails({ rung }: { rung: LadderRung }) {
  const { t } = useFarmer()
  return (
    <div className="mt-0.5 space-y-1.5">
      {rung.use === 'seed' && <Pill tone="neutral" className="!text-[12px]">{t('useSeed')}</Pill>}
      {rung.dose && <p className="text-[14px]">{rung.dose}</p>}
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
  )
}

const USE_KEY = { spray: 'useSpray', seed: 'useSeed', root_dip: 'useRootDip', dispenser: 'useDispenser' } as const
const KIND_KEY = { 'bio-agent': 'organicBio', botanical: 'organicBotanical', pheromone: 'organicPheromone' } as const

/** Organic and chemical, side by side.
 *
 *  Where the panel is narrow (a phone, or the side column of the history
 *  screen) the two are cards next to each other at the top, and one is open
 *  below at a time: organic first, so the chemical is something the farmer
 *  chooses to look at. Where the panel itself is wide enough for two columns
 *  (WIDE), both show at once. It is the panel's width that decides, not the
 *  screen's: the same advice sits in a narrow column on a laptop. Inside,
 *  every group and every product is a dropdown, so the screen opens on a short
 *  list of headings rather than one long trail. */
function Choice({ advisory, nonChem, chem }: { advisory: Advisory; nonChem: LadderRung[]; chem: LadderRung[] }) {
  const { t } = useFarmer()
  const [side, setSide] = useState<'organic' | 'chemical'>('organic')
  const box = useRef<HTMLDivElement>(null)
  const [wide, setWide] = useState(false)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWide(e.contentRect.width >= WIDE))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const options = advisory.organic ?? []
  const [recommended, natural] = byBacking(advisory.homemade ?? []).map(([, items]) => items)
  const organicCount = nonChem.length + options.length + recommended.length + natural.length
  const count = (n: number) => (n === 1 ? t('optCountOne') : t('optCount').replace('{n}', String(n)))
  const tabs = [
    { id: 'organic' as const, icon: Leaf, label: t('optOrganic'), sub: count(organicCount),
      tone: 'bg-[#f3f6e4] text-[#3d4812] ring-[#55631a]/40' },
    { id: 'chemical' as const, icon: FlaskConical, label: t('optChemical'),
      sub: chem.length ? count(chem.length) : t('optNoneRegistered'),
      tone: 'bg-[#fbeeea] text-[#9a2f17] ring-[#9a2f17]/40' },
  ]
  return (
    <div ref={box} className="mt-5">
      {!wide && <div role="tablist" className="grid grid-cols-2 gap-2">
        {tabs.map(({ id, icon: Icon, label, sub, tone }) => (
          <button key={id} role="tab" aria-selected={side === id} onClick={() => setSide(id)}
            className={`flex min-h-[60px] items-center gap-2.5 rounded-2xl px-3 text-left transition ${
              side === id ? `${tone} ring-2` : 'bg-white text-soil-dark/70 ring-1 ring-soil-dark/10'}`}>
            <Icon className="h-5 w-5 shrink-0" aria-hidden />
            <span className="min-w-0">
              <span className="block text-[15px] font-semibold leading-tight">{label}</span>
              <span className="block text-[12px] opacity-80">{sub}</span>
            </span>
          </button>
        ))}
      </div>}

      <div className={`grid gap-4 ${wide ? 'grid-cols-2 items-start' : 'mt-3'}`}>
        <div className={wide || side === 'organic' ? '' : 'hidden'}>
          <Column wide={wide} icon={Leaf} title={t('optOrganic')} sub={t('organicStart')} tone="bg-[#f3f6e4] ring-[#55631a]/10" iconTone="bg-[#e2eac0] text-[#55631a]">
            <Dropdown icon={Sprout} title={t('organicSteps')} count={nonChem.length} defaultOpen>
              <p className="mb-3 text-[13px] text-soil-dark/75">{t('organicStepsSub')}</p>
              <ol className="space-y-4">
                {nonChem.map((r, i) => <Rung key={i} rung={r} n={i + 1} />)}
              </ol>
            </Dropdown>
            <Dropdown icon={BadgeCheck} title={t('organicProducts')} count={options.length}>
              <p className="text-[13px] leading-snug text-soil-dark/75">{options.length ? t('organicSub') : t('organicNoProduct')}</p>
              {options.length > 0 && <OrganicProducts options={options} />}
            </Dropdown>
            {recommended.length > 0 && (
              <Dropdown icon={CookingPot} title={t('levelRecommended')} count={recommended.length}>
                <p className="mb-3 text-[13px] leading-snug text-soil-dark/75">{t('homemadeSub')}</p>
                <HomemadeList items={recommended} />
              </Dropdown>
            )}
            {natural.length > 0 && (
              <Dropdown icon={Trees} title={t('levelNatural')} count={natural.length}>
                <p className="mb-3 rounded-xl bg-[#fdf6e3] p-3 text-[13px] leading-snug text-soil-dark/85">{t('levelNaturalSub')}</p>
                <HomemadeList items={natural} />
              </Dropdown>
            )}
          </Column>
        </div>

        <div className={wide || side === 'chemical' ? '' : 'hidden'}>
          <Column wide={wide} icon={FlaskConical} title={t('optChemical')} sub={chem.length ? t('chemicalAfterOrganic') : ''} tone="bg-[#fbf3f0] ring-[#9a2f17]/10" iconTone="bg-[#f9dcd5] text-[#9a2f17]">
            {chem.length > 0 ? (
              chem.map((r, i) => (
                <Dropdown key={i} icon={FlaskConical} title={r.product ?? ''} tone="text-[#9a2f17]"
                  note={r.use === 'seed' ? t('useSeed') : undefined}>
                  <ChemDetails rung={r} />
                </Dropdown>
              ))
            ) : advisory.chemical_none ? (
              <div className="rounded-[18px] bg-white p-4 ring-1 ring-soil-dark/[0.05]">
                <p className="text-[14px] font-semibold text-[#9a2f17]">{t('chemicalNoneTitle')}</p>
                <p className="mt-1 text-[14px] leading-snug text-soil-dark/85">{advisory.chemical_none}</p>
              </div>
            ) : null}
          </Column>
        </div>
      </div>
    </div>
  )
}

/** The panel width, in px, from which organic and chemical sit in two columns. */
const WIDE = 640

/** One side of the choice: its heading, then its dropdowns. */
function Column({ icon: Icon, title, sub, tone, iconTone, wide, children }: {
  icon: typeof Leaf; title: string; sub: string; tone: string; iconTone: string; wide: boolean; children: React.ReactNode
}) {
  return (
    <section className={`rounded-[22px] p-3 ring-1 sm:p-4 ${tone}`}>
      {/* With tabs, the tab already names the side; the line under it is what is left. */}
      <div className="flex items-start gap-3 px-1 pb-3">
        {wide && (
          <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${iconTone}`}>
            <Icon className="h-5 w-5" aria-hidden />
          </span>
        )}
        <div className="min-w-0 flex-1">
          {wide && <h3 className="text-[17px] font-semibold tracking-tight">{title}</h3>}
          {sub && <p className="text-[13px] leading-snug text-soil-dark/75">{sub}</p>}
        </div>
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  )
}

/** A heading that opens to show what is under it: a group of options, or one
 *  chemical product. The count says how much is inside before it is opened. */
function Dropdown({ icon: Icon, title, count, note, tone = 'text-[#3d4812]', defaultOpen = false, children }: {
  icon: typeof Leaf; title: string; count?: number; note?: string; tone?: string; defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="overflow-hidden rounded-[18px] bg-white ring-1 ring-soil-dark/[0.06]">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex min-h-[56px] w-full items-center gap-3 px-3.5 py-2.5 text-left sm:px-4">
        <Icon className={`h-5 w-5 shrink-0 ${tone}`} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className={`block text-[15px] font-semibold leading-snug ${tone}`}>{title}</span>
          {note && <span className="block text-[12px] text-soil-dark/65">{note}</span>}
        </span>
        {count !== undefined && (
          <span className="shrink-0 rounded-full bg-soil-dark/[0.06] px-2 py-0.5 text-[12px] font-semibold tabular-nums text-soil-dark/70">{count}</span>
        )}
        <ChevronDown className={`h-5 w-5 shrink-0 text-soil-dark/50 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>
      {open && <div className="border-t border-soil-dark/[0.06] px-3.5 pb-4 pt-3 animate-fadein sm:px-4">{children}</div>}
    </div>
  )
}

/** The registered organic products: dose, the farmer's field, when, and the
 *  registration it rests on. */
function OrganicProducts({ options }: { options: OrganicOption[] }) {
  const { t } = useFarmer()
  const living = options.some((o) => o.kind === 'bio-agent')
  return (
    <>
      <ul className="mt-3 space-y-3">
        {options.map((o, i) => (
          <li key={i} className="rounded-[16px] bg-[#f8faf3] p-3.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <Pill tone="leaf" className="!text-[12px]">{t(USE_KEY[o.use])}</Pill>
              <Pill tone="neutral" className="!text-[12px]">{t(KIND_KEY[o.kind] ?? 'organicBio')}</Pill>
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
  )
}

/** Preparations made at home: not registered products, so no label and no
 *  waiting period — the strength, when to spray, how to make it, and the
 *  source it comes from. */
function HomemadeList({ items }: { items: HomemadeOption[] }) {
  const { t } = useFarmer()
  return (
    <ul className="space-y-3">
      {items.map((h, i) => (
        <li key={i} className="rounded-[16px] bg-[#f8faf3] p-3.5">
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

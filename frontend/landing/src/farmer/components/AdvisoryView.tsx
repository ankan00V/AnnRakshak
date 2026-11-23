import { Ban, BadgeCheck, BookOpen, ChevronDown, CookingPot, FlaskConical, GraduationCap, Info, Leaf, ListChecks, Microscope, Phone, PhoneCall, Radio, ShieldAlert, Sprout } from 'lucide-react'
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
          <Ladder advisory={advisory} nonChem={nonChem} chem={chem} />
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

/** What to do, as the treatment ladder an extension worker would draw.
 *
 *  Three steps on one rail, in the order they are tried: field work (free,
 *  first), organic sprays and inputs, and the chemical, last. Nothing sits
 *  behind a tab. Every option is one row of the same shape — what it is, the
 *  one fact that matters, the dose — so an organic product and a chemical can
 *  be compared by eye. A small badge says who stands behind each one. Only the
 *  long recipes fold away. */
function Ladder({ advisory, nonChem, chem }: { advisory: Advisory; nonChem: LadderRung[]; chem: LadderRung[] }) {
  const { t } = useFarmer()
  const options = advisory.organic ?? []
  const [recommended, natural] = byBacking(advisory.homemade ?? []).map(([, items]) => items)
  const organicRows = options.length + recommended.length + natural.length
  const living = options.some((o) => o.kind === 'bio-agent')
  return (
    <ol className="mt-6">
      <Stage n={1} tone="green" title={t('stepStart')} sub={t('stepStartSub')}>
        {nonChem.map((r, i) => <StepRow key={i} rung={r} />)}
      </Stage>

      <Stage n={2} tone="olive" title={t('stepOrganic')} sub={t('stepOrganicSub')}
        foot={<>
          {organicRows === 0 && <p className="text-[14px] leading-snug text-soil-dark/80">{t('organicNoProduct')}</p>}
          {living && <Note icon={Info}>{t('organicCare')}</Note>}
          {natural.length > 0 && <Note icon={Info} warm>{t('natNote')}</Note>}
        </>}>
        {options.map((o, i) => <ProductRow key={`o${i}`} o={o} />)}
        {recommended.map((h, i) => <HomeRow key={`h${i}`} h={h} />)}
        {natural.map((h, i) => <HomeRow key={`n${i}`} h={h} />)}
      </Stage>

      <Stage n={3} tone="rust" title={t('stepChemical')} sub={chem.length ? t('stepChemicalSub') : ''} last
        foot={chem.length > 0
          ? <Note icon={ShieldAlert}>{chem[0].label_rule}</Note>
          : advisory.chemical_none
            ? <p className="text-[14px] leading-snug text-soil-dark/85"><span className="font-semibold text-[#9a2f17]">{t('chemicalNoneTitle')}. </span>{advisory.chemical_none}</p>
            : null}>
        {chem.map((r, i) => <ChemRow key={i} rung={r} />)}
      </Stage>
    </ol>
  )
}

const STAGE_TONE = {
  green: { dot: 'bg-[#2f6a39] text-white', soft: 'bg-[#e3efd9] text-[#2f6a39]', head: 'text-[#1f3d2b]' },
  olive: { dot: 'bg-[#55631a] text-white', soft: 'bg-[#eef3d6] text-[#55631a]', head: 'text-[#3d4812]' },
  rust: { dot: 'bg-[#9a2f17] text-white', soft: 'bg-[#f9dcd5] text-[#9a2f17]', head: 'text-[#7a2512]' },
} as const

/** One step of the ladder: a numbered marker on the rail, its heading, its rows. */
function Stage({ n, tone, title, sub, last = false, foot, children }: {
  n: number; tone: keyof typeof STAGE_TONE; title: string; sub: string; last?: boolean
  foot?: React.ReactNode; children: React.ReactNode
}) {
  const c = STAGE_TONE[tone]
  const rows = Array.isArray(children) ? children.flat().filter(Boolean) : children ? [children] : []
  return (
    <li className="relative grid grid-cols-[36px_minmax(0,1fr)] gap-x-3 pb-7 last:pb-0 sm:grid-cols-[44px_minmax(0,1fr)] sm:gap-x-4">
      {!last && <span aria-hidden className="absolute bottom-0 left-[17px] top-10 w-0.5 rounded bg-soil-dark/10 sm:left-[21px] sm:top-12" />}
      <span className={`flex h-9 w-9 items-center justify-center rounded-full text-[15px] font-bold tabular-nums sm:h-11 sm:w-11 sm:text-[17px] ${c.dot}`}>{n}</span>
      <div className="min-w-0 pt-1 sm:pt-2">
        <h3 className={`text-[18px] font-semibold leading-tight tracking-tight sm:text-[19px] ${c.head}`}>{title}</h3>
        {sub && <p className="mt-0.5 text-[14px] text-soil-dark/70">{sub}</p>}
        {rows.length > 0 && (
          <ul className="mt-3 divide-y divide-soil-dark/[0.07] overflow-hidden rounded-[18px] bg-white ring-1 ring-soil-dark/[0.07]">
            {rows}
          </ul>
        )}
        {foot && <div className="mt-2.5 space-y-2">{foot}</div>}
      </div>
    </li>
  )
}

function Note({ icon: Icon, warm = false, children }: { icon: typeof Leaf; warm?: boolean; children: React.ReactNode }) {
  return (
    <p className={`flex items-start gap-2 text-[13px] leading-snug ${warm ? 'rounded-xl bg-[#fdf6e3] p-2.5 text-[#6b4a12]' : 'text-soil-dark/70'}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> <span>{children}</span>
    </p>
  )
}

/** Who stands behind an option, in a few words: CIB&RC, ICAR or a university, or natural farming. */
function Backing({ kind, source }: { kind: 'registered' | 'recommended' | 'natural'; source?: string }) {
  const { t } = useFarmer()
  const look = {
    registered: { icon: BadgeCheck, cls: 'bg-[#e3efd9] text-[#2f6a39]', label: t('badgeRegistered') },
    recommended: { icon: GraduationCap, cls: 'bg-[#e7eefb] text-[#284f8f]', label: shortSource(source) ?? t('chipRecommended') },
    natural: { icon: Sprout, cls: 'bg-[#fbf0d8] text-[#7a5410]', label: t('badgeNatural') },
  }[kind]
  const Icon = look.icon
  return (
    <span title={source} className={`inline-flex max-w-full items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${look.cls}`}>
      <Icon className="h-3 w-3 shrink-0" aria-hidden /> <span className="truncate">{look.label}</span>
    </span>
  )
}

/** "PAU Ludhiana, Package of Practices…" -> "PAU Ludhiana": the institution, not the title. */
function shortSource(source?: string): string | null {
  if (!source) return null
  const head = source.split(/[,;(]/)[0].trim()
  return head.length <= 28 ? head : null
}

/** A sentence's first clause as the line to read, the rest quieter. */
function lead(text?: string): [string, string] {
  const s = (text ?? '').trim()
  // A full stop, semicolon or colon first; failing that, a comma far enough in
  // to leave a real phrase in front of it.
  const m = s.match(/^(.{12,110}?[;:।.])\s+(.+)$/s) ?? s.match(/^(.{20,80}?,)\s+(.+)$/s)
  return m ? [m[1].replace(/[;:,]$/, ''), m[2]] : [s, '']
}

/** The shared row: icon, what it is, the one fact, the dose on the right. */
function Row({ icon: Icon, iconCls, title, fact, rest, dose, badge, extra }: {
  icon: typeof Leaf; iconCls: string; title: string; fact?: string; rest?: string; dose?: string
  badge?: React.ReactNode; extra?: React.ReactNode
}) {
  const short = dose && dose.length <= 30
  return (
    <li className="flex gap-3 px-3.5 py-3.5 sm:px-4">
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${iconCls}`}>
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-semibold leading-snug text-soil-dark [overflow-wrap:anywhere]">{title}</p>
        {short && (
          <span className="mt-1.5 inline-flex rounded-lg bg-cream px-2.5 py-1 text-[14px] font-semibold tabular-nums text-soil-dark ring-1 ring-soil-dark/[0.06]">{dose}</span>
        )}
        {dose && !short && <p className="mt-1 text-[14px] font-medium leading-snug text-soil-dark/90">{dose}</p>}
        {fact && <p className="mt-1 text-[14px] leading-snug text-soil-dark/85">{fact}</p>}
        {rest && <p className="mt-0.5 text-[13px] leading-snug text-soil-dark/60">{rest}</p>}
        {badge && <div className="mt-2">{badge}</div>}
        {extra}
      </div>
    </li>
  )
}

function StepRow({ rung }: { rung: LadderRung }) {
  const { t } = useFarmer()
  const tier = TIER[rung.tier]
  const [head, rest] = lead(rung.action)
  return (
    <Row icon={tier.icon} iconCls={tier.tone} title={head} rest={rest}
      badge={rung.backing === 'recommended' ? <Backing kind="recommended" source={rung.source} /> : <span className="text-[12px] text-soil-dark/55">{t(tier.key)}</span>} />
  )
}

function ProductRow({ o }: { o: OrganicOption }) {
  const { t } = useFarmer()
  const Icon = o.kind === 'botanical' ? Leaf : o.kind === 'pheromone' ? Radio : Microscope
  return (
    <Row icon={Icon} iconCls="bg-[#eef3d6] text-[#55631a]" title={o.product} dose={o.dose}
      badge={<span className="flex flex-wrap gap-1"><Backing kind="registered" /><span className="rounded-full bg-soil-dark/[0.05] px-2 py-0.5 text-[11px] font-semibold text-soil-dark/70">{t(USE_KEY[o.use])}</span></span>}
      fact={o.for_field?.replace(/^[^:]+:\s*/, '')}
      rest={[o.timing, o.waiting].filter(Boolean).join(' ')} />
  )
}

function HomeRow({ h }: { h: HomemadeOption }) {
  const { t } = useFarmer()
  const natural = h.backing === 'natural_farming'
  return (
    <Row icon={natural ? Sprout : CookingPot} iconCls={natural ? 'bg-[#fbf0d8] text-[#7a5410]' : 'bg-[#e7eefb] text-[#284f8f]'}
      title={h.name} dose={h.dose}
      badge={<Backing kind={natural ? 'natural' : 'recommended'} source={h.source} />}
      rest={h.timing}
      extra={
        <details className="group mt-2">
          <summary className="inline-flex min-h-[36px] cursor-pointer list-none items-center gap-1 rounded-full bg-[#f6f8ef] px-3 text-[13px] font-semibold text-[#3d4812] [&::-webkit-details-marker]:hidden">
            {t('homemadeRecipe')}
            <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden />
          </summary>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-[13px] leading-snug text-soil-dark/85">
            {h.recipe.map((step, j) => <li key={j}>{step}</li>)}
          </ol>
        </details>
      } />
  )
}

function ChemRow({ rung }: { rung: LadderRung }) {
  const { t } = useFarmer()
  return (
    <Row icon={FlaskConical} iconCls="bg-[#f9dcd5] text-[#9a2f17]" title={rung.product ?? ''} dose={rung.dose}
      badge={<span className="flex flex-wrap gap-1">
        <Backing kind="registered" />
        {rung.use === 'seed' && <span className="rounded-full bg-soil-dark/[0.05] px-2 py-0.5 text-[11px] font-semibold text-soil-dark/70">{t('useSeed')}</span>}
        {!rung.verified && <span className="rounded-full bg-[#fbf0d8] px-2 py-0.5 text-[11px] font-semibold text-[#7a5410]">{t('dosePending')}</span>}
      </span>}
      fact={rung.for_field?.replace(/^[^:]+:\s*/, '')}
      rest={[rung.waiting, rung.timing].filter(Boolean).join(' ')} />
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

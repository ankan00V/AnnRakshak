import { useState } from 'react'
import { HelpCircle } from 'lucide-react'
import { api } from '../../api/client'
import type { GapRow } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox, Pill } from '../../ui/kit'
import {
  AccuracyPanel, CardHead, GatePanel, KccPanel, labelName, ModelPanel, PageHead, Panel, PanelBone,
  PesticidePanel, shortDate,
} from '../panels'

/** How the system is doing, and — the part that decides what gets built next —
 *  what officers keep seeing that the model has no name for.
 *
 *  Read top to bottom it answers three questions in order: how good is the
 *  model on photographs it has never seen; what happened to the photographs
 *  farmers actually sent; and where it is weak in the field, which is where the
 *  next training round goes. The two outside measures — what farmers ring the
 *  call centre about, and how much the state sprays — close the page, because
 *  they are the check on whether any of it is working. */
export default function ModelGaps() {
  const summary = useAsync(() => api.summary(), [], 'summary')
  const model = useAsync(() => api.modelCard(), [])
  const gaps = useAsync(() => api.gaps(), [])
  const kcc = useAsync(() => api.kcc(), [])
  const spray = useAsync(() => api.pesticideBaseline(), [])

  return (
    <>
      <PageHead title="Model & gaps"
        purpose="What the model gets right, what it could not name, and where it still needs photographs." />

      <div className="grid gap-5 lg:grid-cols-12 lg:items-stretch">
        <div className="lg:col-span-7"><Panel q={model} rows={7}>{(m) => <ModelPanel m={m} />}</Panel></div>
        <div className="lg:col-span-5"><Panel q={summary} rows={7}>{(s) => <GatePanel s={s} />}</Panel></div>
      </div>

      <div className="grid gap-5 lg:grid-cols-12 lg:items-start">
        <div className="lg:col-span-7"><Panel q={summary} rows={8}>{(s) => <AccuracyPanel s={s} />}</Panel></div>
        <div className="lg:col-span-5">
          <Card className="p-4 md:p-5">
            <CardHead icon={HelpCircle} tone="text-ochre" title="What it could not name"
              sub="Cases an officer closed as “something else”, in their own words. A problem that keeps turning up here is the next class worth training — and the reason the app never guessed at it."
              aside={gaps.data && gaps.data.length > 0 ? <Pill tone="ochre" className="shrink-0">{gaps.data.length}</Pill> : undefined} />
            {gaps.error && !gaps.data ? <div className="mt-4"><ErrorBox error={gaps.error} onRetry={gaps.reload} /></div>
              : !gaps.data ? <div className="mt-4"><PanelBone rows={4} /></div>
              : gaps.data.length === 0 ? (
                <p className="mt-4 text-sm text-soil-dark/60">
                  Nothing yet. Every case so far fitted a problem the knowledge base knows.
                </p>
              ) : <Gaps rows={gaps.data} />}
          </Card>
        </div>
      </div>

      {(kcc.data?.available || spray.data?.available) && (
        <>
          <h2 className="pt-2 text-[11px] font-semibold uppercase tracking-wide text-soil-dark/50">
            Outside measures — is any of it working?
          </h2>
          <div className="grid gap-5 lg:grid-cols-2 lg:items-stretch">
            {kcc.data?.available && <KccPanel k={kcc.data} />}
            {spray.data?.available && <PesticidePanel p={spray.data} />}
          </div>
        </>
      )}
    </>
  )
}

/** Newest first, five at a time. The officer's own words are the content, so
 *  they are set at reading size, and what the model guessed is underneath
 *  them rather than competing with them in a pill. */
function Gaps({ rows }: { rows: GapRow[] }) {
  const [all, setAll] = useState(false)
  const shown = all ? rows : rows.slice(0, 5)
  return (
    <>
      <ul className="mt-3 divide-y divide-soil-dark/[0.07]">
        {shown.map((g) => (
          <li key={g.id} className="py-3 flex gap-3">
            <span className="w-11 shrink-0 pt-0.5 text-[11px] tabular-nums text-soil-dark/50">{shortDate(g.on)}</span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-sm font-medium">{g.district}</span>
                <span className="text-[11px] capitalize text-soil-dark/50">{g.crop}</span>
                {g.referred_to_lab && <Pill tone="sky" className="!py-0.5">sent to a lab</Pill>}
              </div>
              {g.note && <p className="mt-1 text-sm leading-snug text-soil-dark/80 text-pretty">“{g.note}”</p>}
              <p className="mt-1 text-[11px] text-soil-dark/50">
                {g.model_label && <>Model said <span className="text-soil-dark/70">{labelName(g.model_label)}</span> · </>}
                {g.expert}
              </p>
            </div>
          </li>
        ))}
      </ul>
      {rows.length > 5 && (
        <button type="button" onClick={() => setAll((v) => !v)}
          className="mt-2 text-xs font-medium text-leaf-deep hover:underline underline-offset-2">
          {all ? 'Show fewer' : `Show all ${rows.length}`}
        </button>
      )}
    </>
  )
}

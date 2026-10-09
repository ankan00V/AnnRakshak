import { FlaskConical } from 'lucide-react'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { Card, Pill } from '../../ui/kit'
import { AccuracyPanel, GatePanel, ModelPanel, PanelBone } from '../panels'

/** How the system is doing, and — the part that decides what gets built next —
 *  what officers keep seeing that the model has no name for. */
export default function ModelGaps() {
  const summary = useAsync(() => api.summary(), [])
  const model = useAsync(() => api.modelCard(), [])
  const gaps = useAsync(() => api.gaps(), [])

  return (
    <>
      <div className="grid gap-5 lg:grid-cols-2">
        {summary.data ? <GatePanel s={summary.data} /> : !summary.error && <PanelBone rows={4} />}
        {model.data ? <ModelPanel m={model.data} /> : <PanelBone rows={6} />}
      </div>

      <Card className="p-4 md:p-5">
        <h2 className="font-semibold flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-ochre" /> Problems the model cannot name
        </h2>
        <p className="text-xs text-soil-dark/60 mt-0.5">
          Cases an officer closed as “something else”, in their words. A problem that keeps appearing
          here is the next class worth training — and the reason the app never guessed at it.
        </p>
        {!gaps.data ? <div className="mt-4"><PanelBone rows={4} /></div>
          : gaps.data.length === 0 ? (
            <p className="mt-4 text-sm text-soil-dark/70">
              Nothing yet. Every case so far fitted a problem the knowledge base knows.
            </p>
          ) : (
            <ul className="mt-4 divide-y divide-soil-dark/10">
              {gaps.data.map((g) => (
                <li key={g.id} className="py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{g.district} · {g.crop}</span>
                    {g.model_label && <Pill tone="neutral">model said {g.model_label.replace(/_/g, ' ')}</Pill>}
                    {g.referred_to_lab && <Pill tone="sky">sent to a lab</Pill>}
                    <span className="ml-auto text-[11px] text-soil-dark/50">{g.on} · {g.expert}</span>
                  </div>
                  {g.note && <p className="mt-1 text-sm text-soil-dark/80">{g.note}</p>}
                </li>
              ))}
            </ul>
          )}
      </Card>

      {summary.data && <AccuracyPanel s={summary.data} />}
    </>
  )
}

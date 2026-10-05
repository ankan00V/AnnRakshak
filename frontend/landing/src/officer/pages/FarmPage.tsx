import { useState } from 'react'
import { ArrowLeft, MapPin, Phone, Sprout } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox, Pill } from '../../ui/kit'
import { useToast } from '../../ui/Toast'
import { PanelBone, pct } from '../panels'

const LEVEL: Record<string, 'ember' | 'ochre' | 'neutral'> = { high: 'ember', medium: 'ochre', low: 'neutral' }

/** Most farmers ring the office rather than open the app. The answer belongs on
 *  the alert either way, which is also the only way the follow-up numbers stop
 *  reading zero. */
function RecordIt({ alertId, onDone }: { alertId: number; onDone: () => void }) {
  const [busy, setBusy] = useState(false)
  const { say, complain } = useToast()
  const record = async (outcome: 'found' | 'nothing_found') => {
    setBusy(true)
    try {
      await api.recordInspection(alertId, outcome)
      say(outcome === 'found' ? 'Recorded: they found it.' : 'Recorded: nothing found.')
      onDone()
    } catch (e) {
      complain((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <span className="flex items-center gap-1">
      <button onClick={() => record('found')} disabled={busy}
        className="rounded-full border border-ember/40 text-ember px-2 py-0.5 text-[11px] font-medium hover:bg-ember/5 disabled:opacity-50">
        found it
      </button>
      <button onClick={() => record('nothing_found')} disabled={busy}
        className="rounded-full border border-soil-dark/20 px-2 py-0.5 text-[11px] hover:bg-soil-dark/5 disabled:opacity-50">
        nothing
      </button>
    </span>
  )
}

/** One farm, everything the office knows about it — what an officer wants in
 *  front of them before they ring the farmer or send somebody out. */
export default function FarmPage() {
  const { id } = useParams()
  const d = useAsync(() => api.farmDossier(Number(id)), [id])

  if (d.error) return <Card className="p-4"><ErrorBox error={d.error} onRetry={d.reload} /></Card>
  if (!d.data) return <PanelBone rows={8} />
  const { farm } = d.data

  return (
    <>
      <Link to="/officer/queue" className="inline-flex items-center gap-1 text-sm text-soil-dark/60 hover:text-soil-dark">
        <ArrowLeft className="w-4 h-4" /> Queue
      </Link>

      <Card className="p-4 md:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-instrument-serif text-3xl leading-tight">{farm.farmer_name}</h1>
            <p className="text-sm text-soil-dark/70 flex items-center gap-1.5 mt-1">
              <MapPin className="w-3.5 h-3.5" />
              {[farm.village, farm.district].filter(Boolean).join(' · ')}
            </p>
            <p className="text-sm text-soil-dark/70 flex items-center gap-1.5 mt-1">
              <Sprout className="w-3.5 h-3.5" />
              {farm.crop_name}{farm.variety ? ` (${farm.variety})` : ''} · {farm.stage_name} · {farm.das} days · {farm.area_acres} acres
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {d.data.open_problems > 0 && <Pill tone="ember">{d.data.open_problems} open</Pill>}
            {d.data.inspection_rate != null && (
              <Pill tone="neutral">{pct(d.data.inspection_rate)} of alerts inspected</Pill>
            )}
            {d.data.found_rate != null && (
              <Pill tone="ochre">{pct(d.data.found_rate)} of those found something</Pill>
            )}
            <a href="tel:1800-180-1551" className="inline-flex items-center gap-1.5 rounded-full border border-soil-dark/20 px-3 py-1.5 text-xs font-medium">
              <Phone className="w-3.5 h-3.5" /> Kisan Call Centre
            </a>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-soil-dark/60">Alerts sent to this farm</h2>
          {d.data.alerts.length === 0 ? (
            <p className="mt-3 text-sm text-soil-dark/70">No alert has been raised for this field.</p>
          ) : (
            <ul className="mt-3 divide-y divide-soil-dark/10">
              {d.data.alerts.map((a) => (
                <li key={a.id} className="py-2.5 flex items-center justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block text-sm font-medium truncate">{a.name}</span>
                    <span className="block text-[11px] text-soil-dark/60">{a.issued_on} · {a.trigger}</span>
                  </span>
                  <span className="flex items-center gap-1.5 shrink-0">
                    <Pill tone={LEVEL[a.level] ?? 'neutral'}>{a.level}</Pill>
                    {a.outcome
                      ? <Pill tone={a.outcome === 'found' ? 'ember' : 'leaf'}>
                          {a.outcome === 'found' ? 'found it' : a.outcome === 'nothing_found' ? 'nothing found' : a.outcome}
                        </Pill>
                      : <RecordIt alertId={a.id} onDone={d.reload} />}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-soil-dark/60">Cases and verdicts</h2>
          {d.data.cases.length === 0 && d.data.confirmations.length === 0 ? (
            <p className="mt-3 text-sm text-soil-dark/70">Nothing has been escalated from this field.</p>
          ) : (
            <>
              <ul className="mt-3 space-y-1.5">
                {d.data.cases.map((c) => (
                  <li key={c.id}>
                    <Link to={`/officer/queue?q=${encodeURIComponent(farm.farmer_name)}`}
                      className="flex items-center justify-between gap-3 rounded-xl px-2 py-1.5 hover:bg-cream">
                      <span className="text-sm">Case #{c.id} <span className="text-soil-dark/60">· {c.reason.replace(/_/g, ' ').toLowerCase()}</span></span>
                      <Pill tone={c.status === 'open' ? 'ochre' : 'leaf'}>{c.status}</Pill>
                    </Link>
                  </li>
                ))}
              </ul>
              {d.data.confirmations.length > 0 && (
                <ul className="mt-3 border-t border-soil-dark/10 pt-3 space-y-2">
                  {d.data.confirmations.map((c, i) => (
                    <li key={i} className="text-sm">
                      <span className="font-medium">{c.final_label.replace(/_/g, ' ')}</span>
                      <span className="text-soil-dark/60"> · {c.verdict} by {c.expert}{c.on ? ` · ${c.on}` : ''}</span>
                      {c.notes && <span className="block text-xs text-soil-dark/70">“{c.notes}”</span>}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </Card>
      </div>
    </>
  )
}

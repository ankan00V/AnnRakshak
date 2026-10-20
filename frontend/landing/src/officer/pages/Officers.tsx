import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BadgeCheck, Loader2, UserPlus } from 'lucide-react'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { useAuth } from '../../auth/AuthContext'
import { Card, ErrorBox, Pill } from '../../ui/kit'
import { OfficerLoadPanel, PageHead, PanelBone, pct } from '../panels'

/** Staff. Who is carrying what, and who is still waiting to be let in —
 *  verification is a real decision the district office makes by hand. */
export default function Officers() {
  const { me } = useAuth()
  // The whole screen is the office's staffing: colleagues by name, what each
  // carries, who is waiting to be let in, and how fast each desk clears. An
  // officer has their own queue; this is not theirs to read.
  const mayVerify = me?.profile?.supervisor === true
  const pending = useAsync(() => (mayVerify ? api.pendingOfficers() : Promise.resolve([])), [mayVerify])
  const [busy, setBusy] = useState<number | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  const verify = async (id: number) => {
    setBusy(id)
    setFailed(null)
    try {
      await api.verifyOfficer(id, true)
      pending.reload()
    } catch (e) {
      setFailed(e instanceof Error ? e.message : 'Could not verify that officer just now.')
    } finally {
      setBusy(null)
    }
  }

  if (!mayVerify) {
    // Reached by typing the URL: the tab is not shown to an officer, the
    // server refuses each of these reads, and a page of refusals reads like a
    // fault. Say what it is instead.
    return (
      <>
        <PageHead title="Officers" purpose="The district's staffing." />
        <Card className="p-5 text-sm text-soil-dark/70">
          Who is on the books, what each desk carries and who is waiting to be let in are the
          district office's to see. Your own queue is under <Link to="/officer/queue"
            className="text-leaf-deep font-medium underline underline-offset-2">Queue</Link>.
        </Card>
      </>
    )
  }

  return (
    <>
      <PageHead title="Officers"
        purpose="Who is on the books, what each desk is carrying, and who is waiting to be let in." />
      <Card className="p-4 md:p-5">
        <h2 className="font-semibold flex items-center gap-2"><UserPlus className="w-4 h-4 text-ochre" /> Waiting to be verified</h2>
        <p className="text-xs text-soil-dark/60 mt-0.5">
          A sign-up reviews nothing and is handed no cases until the office says who they are.
        </p>
        {pending.error && <div className="mt-3"><ErrorBox error={pending.error} onRetry={pending.reload} /></div>}
        {!pending.data ? <div className="mt-4"><PanelBone rows={3} /></div>
          : pending.data.length === 0 ? (
            <p className="mt-4 text-sm text-soil-dark/70">Nobody is waiting. Every officer on the books is verified.</p>
          ) : (
            <ul className="mt-4 divide-y divide-soil-dark/10">
              {pending.data.map((o) => (
                <li key={o.user_id} className="py-3 flex flex-wrap items-center gap-3">
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm font-medium">{o.name}</span>
                    <span className="block text-xs text-soil-dark/70">
                      {o.designation.replace(/_/g, ' ')} · {o.organisation} · {o.employee_id}
                    </span>
                    <span className="mt-1 flex flex-wrap gap-1">
                      <Pill>{o.qualification.replace(/_/g, ' ')}</Pill>
                      <Pill>{o.experience_years} yrs</Pill>
                      {o.districts.slice(0, 3).map((d) => <Pill key={d} tone="leaf">{d}</Pill>)}
                      {o.districts.length > 3 && <Pill tone="leaf">+{o.districts.length - 3}</Pill>}
                    </span>
                    {/* Verifying somebody used to mean deciding from a name and
                        an employee ID. This is the office they give, and the
                        person who can confirm they work there — which is the
                        check: a phone call. */}
                    {o.office && (
                      <span className="mt-1 block text-xs text-soil-dark/60">
                        {o.office}{o.office_phone ? ` · ${o.office_phone}` : ''}
                        {o.posted_since ? ` · in post since ${o.posted_since.slice(0, 7)}` : ''}
                      </span>
                    )}
                    {o.reporting && (
                      <span className="mt-1 block text-xs">
                        <span className="text-soil-dark/55">Vouched by </span>
                        <span className="font-medium">{o.reporting.name}</span>
                        <span className="text-soil-dark/55">, {o.reporting.designation} · </span>
                        <a href={o.reporting.contact.includes('@') ? `mailto:${o.reporting.contact}` : `tel:${o.reporting.contact}`}
                          className="text-leaf-deep underline underline-offset-2">{o.reporting.contact}</a>
                      </span>
                    )}
                  </span>
                  {mayVerify ? (
                    <button onClick={() => verify(o.user_id)} disabled={busy === o.user_id}
                      className="flex items-center gap-1.5 rounded-full bg-leaf-deep text-cream text-xs font-medium px-3.5 py-2 disabled:opacity-60">
                      {busy === o.user_id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <BadgeCheck className="w-3.5 h-3.5" />}
                      Verify
                    </button>
                  ) : (
                    <span className="text-xs text-soil-dark/55">Awaiting the supervisor</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        {failed && <p className="mt-3 text-xs text-ember">{failed}</p>}
      </Card>

      <OfficerLoadPanel />
      <Performance />
      <TheRecord />
    </>
  )
}

/** What each desk actually cleared. Agreement is not a mark out of ten — an
 *  officer only ever sees what the gate was unsure about — but a desk that
 *  agrees with everything, or with nothing, is worth a conversation. */
function Performance() {
  const rows = useAsync(() => api.performance(), [])
  if (!rows.data) return <PanelBone rows={4} />
  const working = rows.data.filter((r) => r.resolved > 0)
  return (
    <Card className="p-4 md:p-5">
      <h2 className="font-semibold">How the desks are doing</h2>
      {working.length === 0 ? (
        <p className="mt-3 text-sm text-soil-dark/70">No case has been resolved yet, so there is nothing to compare.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-soil-dark/60">
              <tr className="border-b border-soil-dark/10">
                <th className="py-2 pr-3 font-medium">Officer</th>
                <th className="py-2 pr-3 font-medium text-right">Resolved</th>
                <th className="py-2 pr-3 font-medium text-right">Median wait</th>
                <th className="py-2 font-medium text-right">Agreed with the model</th>
              </tr>
            </thead>
            <tbody>
              {working.map((r) => (
                <tr key={r.user_id} className="border-b border-soil-dark/10">
                  <td className="py-2 pr-3">{r.name}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{r.resolved}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {r.median_hours == null ? '—'
                      : r.median_hours < 48 ? `${r.median_hours} h` : `${Math.round(r.median_hours / 24)} days`}
                  </td>
                  <td className="py-2 text-right tabular-nums">
                    {r.agreement == null ? '—' : `${pct(r.agreement)} of ${r.agreed + r.corrected}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

/** The office's own record: who verified whom, who moved what, what was sent. */
function TheRecord() {
  const rows = useAsync(() => api.officeActions(), [])
  if (!rows.data) return <PanelBone rows={4} />
  return (
    <Card className="p-4 md:p-5">
      <h2 className="font-semibold">The office's record</h2>
      <p className="text-xs text-soil-dark/60 mt-0.5">
        Verifying a colleague, routing a backlog and sending an advisory are decisions a district has to
        be able to answer for.
      </p>
      {rows.data.length === 0 ? (
        <p className="mt-3 text-sm text-soil-dark/70">Nothing has been done from this console yet.</p>
      ) : (
        <ul className="mt-3 divide-y divide-soil-dark/10 max-h-72 overflow-y-auto">
          {rows.data.map((a) => (
            <li key={a.id} className="py-2 flex items-center justify-between gap-3 text-sm">
              <span className="min-w-0">
                <span className="font-medium">{a.actor}</span>{' '}
                <span className="text-soil-dark/70">{a.action.replace(/_/g, ' ')}</span>
                {a.subject && <span className="text-soil-dark/50"> · {a.subject}{a.subject_id ? ` #${a.subject_id}` : ''}</span>}
              </span>
              <span className="text-[11px] text-soil-dark/50 shrink-0">{a.at?.slice(0, 16).replace('T', ' ')}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

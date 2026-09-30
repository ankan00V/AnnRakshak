import { useState } from 'react'
import { BadgeCheck, Loader2, UserPlus } from 'lucide-react'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox, Pill } from '../../ui/kit'
import { OfficerLoadPanel, PanelBone } from '../panels'

/** Staff. Who is carrying what, and who is still waiting to be let in —
 *  verification is a real decision the district office makes by hand. */
export default function Officers() {
  const pending = useAsync(() => api.pendingOfficers(), [])
  const [busy, setBusy] = useState<number | null>(null)

  const verify = async (id: number) => {
    setBusy(id)
    try {
      await api.verifyOfficer(id, true)
      pending.reload()
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
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
                  </span>
                  <button onClick={() => verify(o.user_id)} disabled={busy === o.user_id}
                    className="flex items-center gap-1.5 rounded-full bg-leaf-deep text-cream text-xs font-medium px-3.5 py-2 disabled:opacity-60">
                    {busy === o.user_id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <BadgeCheck className="w-3.5 h-3.5" />}
                    Verify
                  </button>
                </li>
              ))}
            </ul>
          )}
      </Card>

      <OfficerLoadPanel />
    </>
  )
}

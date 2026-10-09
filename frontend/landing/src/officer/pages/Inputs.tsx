import { Download, Package } from 'lucide-react'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox, Pill } from '../../ui/kit'
import { PanelBone } from '../panels'

/** Procurement. Tricho-cards are reared to order on a 45-day lead, so the week
 *  a pest starts building is the week to indent — not the week damage shows. */
export default function Inputs() {
  const indent = useAsync(() => api.indent(), [])

  return (
    <Card className="p-4 md:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold flex items-center gap-2"><Package className="w-4 h-4 text-leaf" /> Inputs to stock</h2>
          <p className="text-xs text-soil-dark/60 mt-0.5">
            From what is building this week: how many farms, how many acres, and the ICAR inputs for it.
            Quantities are a starting point for the office, not a bill.
          </p>
        </div>
        <a href="/api/officials/indent?fmt=csv" download
          className="flex items-center gap-1.5 rounded-full border border-soil-dark/20 px-3 py-1.5 text-xs font-medium hover:bg-soil-dark/5">
          <Download className="w-3.5 h-3.5" /> CSV for the indent
        </a>
      </div>

      {indent.error && <div className="mt-3"><ErrorBox error={indent.error} onRetry={indent.reload} /></div>}
      {!indent.data ? <div className="mt-4"><PanelBone rows={6} /></div>
        : indent.data.length === 0 ? (
          <p className="mt-4 text-sm text-soil-dark/70">Nothing is building, so there is nothing to order.</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-soil-dark/60">
                <tr className="border-b border-soil-dark/10">
                  <th className="py-2 pr-3 font-medium">Problem</th>
                  <th className="py-2 pr-3 font-medium">Farms</th>
                  <th className="py-2 pr-3 font-medium">Acres</th>
                  <th className="py-2 pr-3 font-medium">Districts</th>
                  <th className="py-2 font-medium">What to stock</th>
                </tr>
              </thead>
              <tbody>
                {indent.data.map((r) => (
                  <tr key={r.target} className="border-b border-soil-dark/10 align-top">
                    <td className="py-3 pr-3">
                      <span className="font-medium">{r.name}</span>
                      <span className="block text-[11px] text-soil-dark/60">{r.crop}{r.high > 0 ? ` · ${r.high} high` : ''}</span>
                    </td>
                    <td className="py-3 pr-3 tabular-nums">{r.farms}</td>
                    <td className="py-3 pr-3 tabular-nums">{r.acres}</td>
                    <td className="py-3 pr-3 text-xs text-soil-dark/70">{r.districts.join(', ')}</td>
                    <td className="py-3">
                      {r.suggested.length === 0 ? <span className="text-xs text-soil-dark/50">—</span> : (
                        <ul className="space-y-1.5">
                          {r.suggested.map((s) => (
                            <li key={s.input} className="text-xs">
                              <span className="font-medium">{s.input}</span> · {s.quantity}
                              {s.institute && <span className="text-soil-dark/60"> · {s.institute}</span>}
                              {s.order_by && <Pill tone="ochre" className="ml-1.5">order by {s.order_by}</Pill>}
                            </li>
                          ))}
                        </ul>
                      )}
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

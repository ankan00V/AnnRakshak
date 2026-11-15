import { Download, Package } from 'lucide-react'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox } from '../../ui/kit'
import { CardHead, PageHead, PanelBone } from '../panels'

/** Procurement. Tricho-cards are reared to order on a 45-day lead, so the week
 *  a pest starts building is the week to indent — not the week damage shows. */
export default function Inputs() {
  const indent = useAsync(() => api.indent(), [])

  return (
    <>
      <PageHead title="Inputs"
        purpose="What to stock, from what is building, with the lead time an ICAR bio-input actually needs.">
        <a href="/api/officials/indent?fmt=csv" download
          className="flex min-h-[44px] items-center gap-2 rounded-full bg-white px-5 text-[15px] font-semibold shadow-sm ring-1 ring-soil-dark/10 hover:bg-[#f8f6f0]">
          <Download className="h-4 w-4" aria-hidden /> CSV for the indent
        </a>
      </PageHead>
      <Card className="p-5 lg:p-6">
      <CardHead icon={Package} title="Inputs to stock"
        sub="From what is building this week: farms, acres, and the ICAR inputs for it. Quantities are a starting point for the office, not a bill; where the ICAR catalogue is silent, the problem's own biological step is shown." />

      {indent.error && <div className="mt-3"><ErrorBox error={indent.error} onRetry={indent.reload} /></div>}
      {!indent.data ? <div className="mt-4"><PanelBone rows={6} /></div>
        : indent.data.length === 0 ? (
          <p className="mt-4 rounded-2xl bg-[#f8f6f0] p-4 text-[14px] text-soil-dark/80">Nothing is building, so there is nothing to order.</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-[14px]">
              <thead className="text-left text-[13px] text-soil-dark/75">
                <tr className="border-b border-soil-dark/10">
                  <th className="py-2.5 pr-4 font-semibold">Problem</th>
                  <th className="py-2.5 pr-4 font-semibold">Farms</th>
                  <th className="py-2.5 pr-4 font-semibold">Acres</th>
                  <th className="py-2.5 pr-4 font-semibold">Districts</th>
                  <th className="py-2.5 font-semibold">What to stock</th>
                </tr>
              </thead>
              <tbody>
                {indent.data.map((r) => (
                  <tr key={r.target} className="border-b border-soil-dark/[0.07] align-top last:border-0">
                    <td className="py-3.5 pr-4">
                      <span className="font-semibold">{r.name}</span>
                      <span className="block text-[12px] text-soil-dark/70">{r.crop}{r.high > 0 ? ` · ${r.high} high` : ''}</span>
                    </td>
                    <td className="py-3.5 pr-4 tabular-nums">{r.farms}</td>
                    <td className="py-3.5 pr-4 tabular-nums">{r.acres}</td>
                    <td className="py-3.5 pr-4 text-[13px] text-soil-dark/70">{r.districts.join(', ')}</td>
                    <td className="py-3.5">
                      {/* A dash here would read as "nothing to stock", which for
                          rice blast is not what it means. Where the ICAR
                          catalogue is silent, the problem's own advice ladder
                          already says what the biological step is — and that
                          is what the office would be buying. */}
                      {r.suggested.length === 0 ? (
                        r.biological ? (
                          <div className="text-[13px]">
                            <span className="text-soil-dark/70">Biological step · not in the ICAR catalogue</span>
                            <p className="mt-0.5 text-soil-dark/80">{r.biological}</p>
                          </div>
                        ) : <span className="text-[13px] text-soil-dark/70">Nothing to stock for this one</span>
                      ) : (
                        <ul className="space-y-1.5">
                          {r.suggested.map((s) => (
                            <li key={s.input} className="text-[13px]">
                              <span className="font-medium">{s.input}</span> · {s.quantity}
                              {s.institute && <span className="text-soil-dark/70"> · {s.institute}</span>}
                              {s.order_by && <span className="ml-1.5 inline-block rounded-full bg-[#fbe5bd] px-2.5 py-0.5 text-[12px] font-semibold text-[#7a4f12]">Order by {s.order_by}</span>}
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
    </>
  )
}

import { useState } from 'react'
import { api } from '../../api/client'
import type { Hotspots } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox } from '../../ui/kit'
import HotspotMap from '../HotspotMap'
import { DistrictTable, Legend, MapSkeleton, PageHead, PanelBone } from '../panels'

const LAYERS = [['cases', 'Cases'], ['alerts', 'Risk alerts'], ['radius', '5 km spread']] as const

/** Where the problems are. The map gets a screen of its own because a
 *  surveillance map squeezed beside six panels is a picture, not a tool. */
export default function MapPage() {
  const hotspots = useAsync(() => api.hotspots(), [])
  const summary = useAsync(() => api.summary(), [], 'summary')
  const [layers, setLayers] = useState({ cases: true, alerts: true, radius: true })

  return (
    <>
      <PageHead title="Map" purpose="Where the confirmed cases and this week's alerts are, farm by farm.">
        <div className="flex gap-1 rounded-full bg-white p-1 shadow-sm ring-1 ring-soil-dark/10" role="group" aria-label="Map layers">
          {LAYERS.map(([k, l]) => (
            <button key={k} onClick={() => setLayers((s) => ({ ...s, [k]: !s[k] }))} aria-pressed={layers[k]}
              className={`min-h-[38px] rounded-full px-4 text-[14px] font-semibold transition-colors ${
                layers[k] ? 'bg-[#1d4a2c] text-white' : 'text-soil-dark/70 hover:text-soil-dark'}`}>
              {l}
            </button>
          ))}
        </div>
      </PageHead>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="flex flex-col p-2">
          <div className="h-[460px] overflow-hidden rounded-[18px] lg:h-[560px]">
            {hotspots.error ? <ErrorBox error={hotspots.error} onRetry={hotspots.reload} />
              : hotspots.data ? <HotspotMap data={hotspots.data} layers={layers} /> : <MapSkeleton />}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 px-3 py-3 text-[13px] text-soil-dark/80">
            <Legend color="#b0472a" label="Expert-confirmed" />
            <Legend color="#2f6fa8" label="Awaiting expert" />
            <Legend color="#c8862d" label="AI-advised, unconfirmed" />
            <Legend color="#c8862d" label="Risk alert (dashed)" hollow />
          </div>
        </Card>
        {hotspots.data ? <Overview h={hotspots.data} /> : !hotspots.error && <PanelBone rows={6} />}
      </div>

      {summary.data ? <DistrictTable s={summary.data} /> : !summary.error && <PanelBone rows={8} />}
    </>
  )
}

/** What the map shows, counted: the cases by how settled they are, and the
 *  week's alerts by how loud. */
function Overview({ h }: { h: Hotspots }) {
  const by = (s: string) => h.points.filter((p) => p.status === s).length
  const lvl = (l: string) => h.active_alerts.filter((a) => a.level === l).length
  const line = (dot: string, n: number, label: string) => (
    <li className="flex items-center gap-3 rounded-2xl bg-[#f8f6f0] px-3.5 py-2.5">
      <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: dot }} aria-hidden />
      <span className="w-8 text-[20px] font-semibold tabular-nums">{n}</span>
      <span className="text-[14px] text-soil-dark/80">{label}</span>
    </li>
  )
  return (
    <Card className="p-5">
      <h2 className="text-[20px] font-semibold tracking-tight">District overview</h2>
      <p className="mt-3 flex items-baseline gap-2">
        <span className="text-[34px] font-semibold leading-none tabular-nums">{h.points.length}</span>
        <span className="text-[15px] text-soil-dark/75">cases on the map</span>
      </p>
      <ul className="mt-3 space-y-2">
        {line('#b0472a', by('confirmed'), 'Expert-confirmed')}
        {line('#2f6fa8', by('awaiting_expert'), 'Awaiting expert')}
        {line('#c8862d', by('suspected'), 'AI-advised, unconfirmed')}
      </ul>
      <h3 className="mt-5 text-[15px] font-semibold">Risk alerts this week · {h.active_alerts.length}</h3>
      <ul className="mt-2 space-y-2">
        {line('#b5381c', lvl('high'), 'High risk')}
        {line('#d29a3a', lvl('medium'), 'Moderate')}
        {line('#4b8b3b', lvl('low'), 'Low risk')}
      </ul>
    </Card>
  )
}

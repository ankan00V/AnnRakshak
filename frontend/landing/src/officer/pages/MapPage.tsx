import { useState } from 'react'
import { Layers, Map as MapIcon } from 'lucide-react'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox } from '../../ui/kit'
import HotspotMap from '../HotspotMap'
import { DistrictTable, Legend, MapSkeleton, PanelBone } from '../panels'

/** Where the problems are. The map gets a screen of its own because a
 *  surveillance map squeezed beside six panels is a picture, not a tool. */
export default function MapPage() {
  const hotspots = useAsync(() => api.hotspots(), [])
  const summary = useAsync(() => api.summary(), [])
  const [layers, setLayers] = useState({ cases: true, alerts: true, radius: true })

  return (
    <>
      <Card className="p-3 flex flex-col">
        <div className="flex flex-wrap items-center justify-between gap-2 px-1 pb-2">
          <h2 className="font-semibold flex items-center gap-2"><MapIcon className="w-4 h-4 text-leaf" /> Hotspot map</h2>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <Layers className="w-3.5 h-3.5 text-soil-dark/50" />
            {([['cases', 'Cases'], ['alerts', 'Risk alerts'], ['radius', '5 km spread radius']] as const).map(([k, l]) => (
              <button key={k} onClick={() => setLayers((s) => ({ ...s, [k]: !s[k] }))}
                className={`px-2.5 py-1 rounded-full border ${layers[k] ? 'bg-leaf-deep text-cream border-leaf-deep' : 'border-soil-dark/20 text-soil-dark/60'}`}>
                {l}
              </button>
            ))}
          </div>
        </div>
        <div className="h-[560px]">
          {hotspots.error ? <ErrorBox error={hotspots.error} onRetry={hotspots.reload} />
            : hotspots.data ? <HotspotMap data={hotspots.data} layers={layers} /> : <MapSkeleton />}
        </div>
        <div className="flex flex-wrap gap-3 px-1 pt-2 text-[11px] text-soil-dark/70">
          <Legend color="#b0472a" label="Expert-confirmed" />
          <Legend color="#2f6fa8" label="Awaiting expert" />
          <Legend color="#c8862d" label="AI-advised (unconfirmed)" />
          <Legend color="#c8862d" label="Risk alert (dashed)" hollow />
        </div>
      </Card>

      {summary.data ? <DistrictTable s={summary.data} /> : !summary.error && <PanelBone rows={8} />}
    </>
  )
}

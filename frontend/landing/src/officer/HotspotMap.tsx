import 'leaflet/dist/leaflet.css'
import { Circle, CircleMarker, MapContainer, TileLayer, Tooltip } from 'react-leaflet'
import { useNavigate } from 'react-router-dom'
import type { Hotspots } from '../api/types'

const STATUS_COLOR = {
  confirmed: '#b0472a',
  awaiting_expert: '#2f6fa8',
  suspected: '#c8862d',
}

// OSM's public tiles are fine for demos; set VITE_MAP_TILE_URL for production.
const TILE_URL = import.meta.env.VITE_MAP_TILE_URL ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'

const LEVEL_COLOR: Record<string, string> = { high: '#b0472a', medium: '#c8862d', low: '#3d6b4a' }

export default function HotspotMap({ data, layers }: {
  data: Hotspots
  layers: { cases: boolean; alerts: boolean; radius: boolean }
}) {
  const navigate = useNavigate()
  return (
    <MapContainer center={[19.4, 76.6]} zoom={6.4} zoomSnap={0.2} scrollWheelZoom={false}
      className="w-full h-full rounded-2xl z-0" attributionControl>
      <TileLayer
        url={TILE_URL}
        maxZoom={18}
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      />
      {layers.alerts && data.active_alerts.map((a, i) => (
        <CircleMarker key={`a${i}`} center={[a.lat, a.lon]} radius={5}
          pathOptions={{ color: LEVEL_COLOR[a.level] ?? '#888', weight: 1, fillOpacity: 0.25, dashArray: '2 3' }}>
          <Tooltip>{a.name} — {a.level} risk ({a.trigger}) · {a.district}</Tooltip>
        </CircleMarker>
      ))}
      {layers.radius && data.points.filter((p) => p.status === 'confirmed').map((p) => (
        <Circle key={`r${p.problem_id}`} center={[p.lat, p.lon]} radius={data.radius_km * 1000}
          pathOptions={{ color: STATUS_COLOR.confirmed, weight: 1, fillOpacity: 0.06, dashArray: '4 4' }} />
      ))}
      {layers.cases && data.points.map((p) => (
        <CircleMarker key={p.problem_id} center={[p.lat, p.lon]} radius={p.status === 'confirmed' ? 9 : 7}
          pathOptions={{ color: '#fff', weight: 2, fillColor: STATUS_COLOR[p.status], fillOpacity: 0.95 }}
          // A pin is a field somebody farms: clicking it opens that field.
          eventHandlers={{ click: () => navigate(`/officer/farm/${p.farm_id}`) }}>
          <Tooltip>
            <strong>{p.name ?? 'Unknown'}</strong><br />
            {p.farmer_name} · {p.crop} · {p.district}{p.on ? ` · ${p.on}` : ''}<br />
            <span style={{ opacity: 0.7 }}>{p.status.replace('_', ' ')} — click to open the field</span>
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  )
}

import { useState } from 'react'
import { Bug, CheckCircle2, Cpu, Loader2 } from 'lucide-react'
import type { TargetView } from '../../api/types'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox, SectionTitle, Spinner } from '../../ui/kit'
import AlertCard from '../components/AlertCard'
import { NoticeInbox, NotifySettings } from '../components/NotifyPanels'
import { useFarmer } from '../FarmerContext'


export default function Alerts() {
  const { farmId, lang, t } = useFarmer()
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  const alerts = useAsync(() => api.alerts(farmId!, lang), [farmId, lang], ['alerts', farmId!, lang].join(':'))

  if ((alerts.loading && !alerts.data) || (home.loading && !home.data)) return <Spinner label={t('loading')} />
  if (alerts.error) return <ErrorBox error={alerts.error} onRetry={alerts.reload} retryLabel={t('retry')} />
  const crop = home.data?.farm.crop ?? ''
  const open = alerts.data!.filter((a) => a.outcome === null || a.outcome === 'snoozed')
  const done = alerts.data!.filter((a) => a.outcome === 'nothing_found' || a.outcome === 'found')

  return (
    <div className="space-y-6">
      <h1 className="font-instrument-serif text-3xl leading-tight">{t('alertsTitle')}</h1>

      <NoticeInbox />

      <section className="space-y-3">
        <SectionTitle sub={t('todayChecksSub')}>{t('todayChecks')}</SectionTitle>
        {open.length === 0 ? (
          <Card className="p-5 text-center text-sm text-soil-dark/60">{t('noChecks')}</Card>
        ) : (
          open.map((a) => <AlertCard key={a.id} alert={a} onDone={alerts.reload} />)
        )}
      </section>

      <NotifySettings />
      {crop && <TrapForm crop={crop} onSaved={alerts.reload} />}
      <SensorForm onSaved={alerts.reload} />

      {done.length > 0 && (
        <section>
          <SectionTitle>{t('answered')}</SectionTitle>
          <ul className="space-y-1.5">
            {done.map((a) => (
              <li key={a.id} className="flex items-center gap-2 text-sm rounded-xl bg-white/60 border border-soil-dark/10 px-3 py-2">
                <CheckCircle2 className={`w-4 h-4 ${a.outcome === 'found' ? 'text-ember' : 'text-leaf'}`} />
                <span className="flex-1 truncate">{a.name}</span>
                <span className="text-xs text-soil-dark/50">{a.outcome === 'found' ? t('foundIt') : t('nothingFound')}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function TrapForm({ crop, onSaved }: { crop: string; onSaved: () => void }) {
  const { farmId, lang, t } = useFarmer()
  const kb = useAsync(() => api.targets(lang, crop), [lang, crop], ['targets', lang, crop].join(':'))
  const pests: TargetView[] = (kb.data ?? []).filter((x) => x.kind === 'pest')
    .sort((a, b) => Number(b.trap_etl != null) - Number(a.trap_etl != null))
  const [chosen, setTarget] = useState<string | null>(null)
  const target = chosen ?? pests[0]?.id ?? ''
  const etl = pests.find((p) => p.id === target)?.trap_etl ?? null
  const [count, setCount] = useState('')
  const [traps, setTraps] = useState('3')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const readings = useAsync(() => api.traps(farmId!), [farmId], ['traps', farmId!].join(':'))

  const save = async () => {
    setBusy(true)
    setMsg(null)
    try {
      const r = await api.addTrap(farmId!, { target, count: parseInt(count, 10), traps: parseInt(traps, 10), nights: 1, trap_type: 'pheromone' })
      const fired = r.fired.some((f) => f.trigger === 'trap' && f.target === target)
      setMsg(fired ? `⚠ ${t('level_high')} — ${t('trig_trap')}` : etl == null ? t('trapNoEtl') : t('trapRecorded'))
      setCount('')
      readings.reload()
      onSaved()
    } finally {
      setBusy(false)
    }
  }

  const field = 'w-full min-h-[44px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm focus:outline-none focus:border-leaf'
  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-start gap-3">
        <span className="w-10 h-10 rounded-full bg-ochre/15 flex items-center justify-center shrink-0">
          <Bug className="w-5 h-5 text-ochre" />
        </span>
        <div>
          <h2 className="font-semibold">{t('trapsTitle')}</h2>
          <p className="text-xs text-soil-dark/60">{t('trapsSub')}</p>
        </div>
      </div>
      <label className="block text-xs text-soil-dark/60">
        {t('trapPest')}
        <select className={field} value={target} onChange={(e) => setTarget(e.target.value)}>
          {pests.map((p) => <option key={p.id} value={p.id}>{p.name}{p.trap_etl != null ? ` · ETL ${p.trap_etl}/${t('perTrapNight')}` : ''}</option>)}
        </select>
      </label>
      {etl == null && pests.length > 0 && <p className="text-[11px] text-soil-dark/50">{t('trapNoEtl')}</p>}
      <div className="grid grid-cols-2 gap-2">
        <label className="block text-xs text-soil-dark/60">
          {t('mothsCaught')}
          <input className={field} type="number" inputMode="numeric" min="0" value={count} onChange={(e) => setCount(e.target.value)} />
        </label>
        <label className="block text-xs text-soil-dark/60">
          {t('trapCount')}
          <input className={field} type="number" inputMode="numeric" min="1" value={traps} onChange={(e) => setTraps(e.target.value)} />
        </label>
      </div>
      <button onClick={save} disabled={busy || count === ''} className="w-full min-h-[44px] rounded-full bg-leaf-deep text-cream text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-2">
        {busy && <Loader2 className="w-4 h-4 animate-spin" />}
        {t('record')}
      </button>
      {msg && <p className="text-sm font-medium text-center">{msg}</p>}
      {readings.data && readings.data.length > 0 && (
        <div className="flex items-end gap-1 h-16 pt-2 border-t border-soil-dark/10">
          {readings.data.slice(0, 10).reverse().map((r) => {
            const rowEtl = pests.find((p) => p.id === r.target)?.trap_etl
            const over = rowEtl != null && r.per_trap_night >= rowEtl
            return (
              <div key={r.id} className="flex-1 flex flex-col items-center gap-0.5" title={`${r.recorded_on}: ${r.per_trap_night} ${t('perTrapNight')}`}>
                <span className={`w-full rounded-t ${over ? 'bg-ember' : 'bg-leaf/60'}`} style={{ height: `${Math.min(48, r.per_trap_night * 3)}px` }} />
                <span className="text-[9px] text-soil-dark/50">{r.per_trap_night}</span>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

/** In-field sensor or a farmer's own gauge: overrides the regional forecast for
 *  that day in the risk engine. The same endpoint takes readings from IoT
 *  devices (POST /api/farms/{id}/sensor). */
function SensorForm({ onSaved }: { onSaved: () => void }) {
  const { farmId, t } = useFarmer()
  const [open, setOpen] = useState(false)
  const [rh, setRh] = useState('')
  const [tmin, setTmin] = useState('')
  const [tmax, setTmax] = useState('')
  const [rain, setRain] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const num = (v: string) => (v === '' ? null : Number(v))
  const save = async () => {
    setBusy(true)
    try {
      await api.addSensor(farmId!, [{ on: new Date().toISOString().slice(0, 10), rh_max: num(rh), t_min: num(tmin), t_max: num(tmax), rain_mm: num(rain) }])
      await api.runRisk(farmId!)
      setDone(true)
      onSaved()
    } finally {
      setBusy(false)
    }
  }
  const field = 'w-full min-h-[44px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm focus:outline-none focus:border-leaf'
  return (
    <Card className="p-4">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-start gap-3 text-left">
        <span className="w-10 h-10 rounded-full bg-sky-100 flex items-center justify-center shrink-0">
          <Cpu className="w-5 h-5 text-sky-700" />
        </span>
        <span>
          <span className="block font-semibold">{t('sensorTitle')}</span>
          <span className="block text-xs text-soil-dark/60">{t('sensorSub')}</span>
        </span>
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-xs text-soil-dark/60">{t('humidity')} max %<input className={field} type="number" inputMode="decimal" value={rh} onChange={(e) => setRh(e.target.value)} /></label>
            <label className="block text-xs text-soil-dark/60">Rain mm<input className={field} type="number" inputMode="decimal" value={rain} onChange={(e) => setRain(e.target.value)} /></label>
            <label className="block text-xs text-soil-dark/60">Min °C<input className={field} type="number" inputMode="decimal" value={tmin} onChange={(e) => setTmin(e.target.value)} /></label>
            <label className="block text-xs text-soil-dark/60">Max °C<input className={field} type="number" inputMode="decimal" value={tmax} onChange={(e) => setTmax(e.target.value)} /></label>
          </div>
          <button onClick={save} disabled={busy || (rh === '' && tmin === '' && tmax === '' && rain === '')}
            className="w-full min-h-[44px] rounded-full bg-sky-700 text-white text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-2">
            {busy && <Loader2 className="w-4 h-4 animate-spin" />}
            {t('record')}
          </button>
          {done && <p className="text-sm text-center text-leaf-deep">{t('trapRecorded')}</p>}
        </div>
      )}
    </Card>
  )
}

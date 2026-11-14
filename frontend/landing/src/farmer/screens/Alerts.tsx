import { useState } from 'react'
import { Bug, CalendarCheck, CheckCircle2, ChevronDown, Cpu, Loader2, ShieldCheck } from 'lucide-react'
import type { TargetView } from '../../api/types'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { ErrorBox } from '../../ui/kit'
import { AlertsSkeleton } from '../components/Skeletons'
import AlertCard from '../components/AlertCard'
import LastKnown from '../components/LastKnown'
import { useReadOnlyFarm } from '../components/DemoNotice'
import { NoticeInbox, NotifySettings } from '../components/NotifyPanels'
import { useFarmer } from '../FarmerContext'
import { FIELD, LABEL, PANEL, PRIMARY } from '../tokens'
import { PanelHead } from '../ui'


export default function Alerts() {
  const { farmId, lang, t } = useFarmer()
  const readOnly = useReadOnlyFarm() !== null
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  const alerts = useAsync(() => api.alerts(farmId!, lang), [farmId, lang], ['alerts', farmId!, lang].join(':'))

  if ((alerts.loading && !alerts.data) || (home.loading && !home.data)) return <AlertsSkeleton />
  // The checks this phone kept are what a farmer with no signal came here for,
  // so the error only takes the screen when there is nothing kept to take it from.
  if (alerts.error && !alerts.data) return <ErrorBox offlineLabel={t('offline')} error={alerts.error} onRetry={alerts.reload} retryLabel={t('retry')} />
  const crop = home.data?.farm.crop ?? ''
  const open = alerts.data!.filter((a) => a.outcome === null || a.outcome === 'snoozed')
  const done = alerts.data!.filter((a) => a.outcome === 'nothing_found' || a.outcome === 'found')

  return (
    <div className="space-y-6">
      {alerts.error && <LastKnown at={alerts.savedAt} onRetry={alerts.reload} />}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 space-y-6">
          <section className={`${PANEL} p-5 lg:p-6`}>
            <PanelHead icon={CalendarCheck} title={t('todayChecks')} sub={t('todayChecksSub')} />
            {open.length === 0 ? (
              <p className="mt-4 flex items-center gap-3 rounded-[20px] bg-[#f1f6ec] p-4 text-[15px] text-soil-dark/85">
                <ShieldCheck className="h-6 w-6 shrink-0 text-[#4b8b3b]" aria-hidden /> {t('noChecks')}
              </p>
            ) : (
              // On a phone the cards take the panel's padding back, so the text is not three boxes deep.
              <div className="-mx-3 mt-4 space-y-3 sm:mx-0">
                {open.map((a) => <AlertCard key={a.id} alert={a} onDone={alerts.reload} />)}
              </div>
            )}
          </section>
          <NoticeInbox />
        </div>

        <aside className="min-w-0 space-y-6">
          <NotifySettings />
          {/* The shared demo field belongs to nobody, so the server refuses every
              write to it. Offering these two forms there is offering a farmer work
              that cannot land — the other write surfaces already say so instead. */}
          {!readOnly && (
            <>
              {crop && <TrapForm crop={crop} onSaved={alerts.reload} />}
              <SensorForm onSaved={alerts.reload} />
            </>
          )}

          {done.length > 0 && (
            <section className={`${PANEL} p-5`}>
              <PanelHead icon={CheckCircle2} title={t('answered')} />
              <ul className="mt-3 divide-y divide-soil-dark/[0.07]">
                {done.map((a) => (
                  <li key={a.id} className="flex items-center gap-3 py-2.5 text-[15px]">
                    <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${a.outcome === 'found' ? 'bg-ember' : 'bg-[#4b8b3b]'}`} aria-hidden />
                    <span className="min-w-0 flex-1 truncate">{a.name}</span>
                    <span className="shrink-0 text-[13px] text-soil-dark/70">{a.outcome === 'found' ? t('foundIt') : t('nothingFound')}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
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
  const [failed, setFailed] = useState(false)
  const readings = useAsync(() => api.traps(farmId!), [farmId], ['traps', farmId!].join(':'))

  const save = async () => {
    setBusy(true)
    setMsg(null)
    setFailed(false)
    try {
      const r = await api.addTrap(farmId!, { target, count: parseInt(count, 10), traps: parseInt(traps, 10), nights: 1, trap_type: 'pheromone' })
      const fired = r.fired.some((f) => f.trigger === 'trap' && f.target === target)
      setMsg(fired ? `⚠ ${t('level_high')} — ${t('trig_trap')}` : etl == null ? t('trapNoEtl') : t('trapRecorded'))
      setCount('')
      readings.reload()
      onSaved()
    } catch {
      setFailed(true)
      setMsg(t('notSaved'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className={`${PANEL} space-y-4 p-5`}>
      <PanelHead icon={Bug} title={t('trapsTitle')} sub={t('trapsSub')} />
      <label className={LABEL}>
        {t('trapPest')}
        <select className={FIELD} value={target} onChange={(e) => setTarget(e.target.value)}>
          {pests.map((p) => <option key={p.id} value={p.id}>{p.name}{p.trap_etl != null ? ` · ETL ${p.trap_etl}/${t('perTrapNight')}` : ''}</option>)}
        </select>
      </label>
      {etl == null && pests.length > 0 && <p className="text-[13px] text-soil-dark/70">{t('trapNoEtl')}</p>}
      <div className="grid grid-cols-2 gap-3">
        <label className={LABEL}>
          {t('mothsCaught')}
          <input className={FIELD} type="number" inputMode="numeric" min="0" value={count} onChange={(e) => setCount(e.target.value)} />
        </label>
        <label className={LABEL}>
          {t('trapCount')}
          <input className={FIELD} type="number" inputMode="numeric" min="1" value={traps} onChange={(e) => setTraps(e.target.value)} />
        </label>
      </div>
      <button onClick={save} disabled={busy || count === ''} className={PRIMARY}>
        {busy && <Loader2 className="h-5 w-5 animate-spin" />}
        {t('record')}
      </button>
      {msg && <p role={failed ? 'alert' : 'status'} className={`text-center text-[15px] font-medium ${failed ? 'text-ember' : 'text-leaf-deep'}`}>{msg}</p>}
      {readings.data && readings.data.length > 0 && (
        <div className="flex h-20 items-end gap-1.5 rounded-[20px] bg-[#f5f7f1] px-3 pb-2 pt-3">
          {readings.data.slice(0, 10).reverse().map((r) => {
            const rowEtl = pests.find((p) => p.id === r.target)?.trap_etl
            const over = rowEtl != null && r.per_trap_night >= rowEtl
            return (
              <div key={r.id} className="flex-1 flex flex-col items-center gap-0.5" title={`${r.recorded_on}: ${r.per_trap_night} ${t('perTrapNight')}`}>
                <span className={`w-full rounded-t-md ${over ? 'bg-ember' : 'bg-[#4b8b3b]/70'}`} style={{ height: `${Math.min(44, Math.max(3, r.per_trap_night * 3))}px` }} />
                <span className="text-[12px] tabular-nums text-soil-dark/75">{r.per_trap_night}</span>
              </div>
            )
          })}
        </div>
      )}
    </section>
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
  const [failed, setFailed] = useState(false)
  const num = (v: string) => (v === '' ? null : Number(v))
  const save = async () => {
    setBusy(true)
    setFailed(false)
    try {
      await api.addSensor(farmId!, [{ on: new Date().toISOString().slice(0, 10), rh_max: num(rh), t_min: num(tmin), t_max: num(tmax), rain_mm: num(rain) }])
      await api.runRisk(farmId!)
      setDone(true)
      onSaved()
    } catch {
      // setDone stays false, so the form is still there to try again with.
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className={`${PANEL} p-5`}>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="w-full text-left">
        <PanelHead icon={Cpu} title={t('sensorTitle')} sub={t('sensorSub')}
          action={<ChevronDown className={`mt-2 h-5 w-5 shrink-0 text-soil-dark/60 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />} />
      </button>
      {open && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <label className={LABEL}>{t('sensorRh')}<input className={FIELD} type="number" inputMode="decimal" value={rh} onChange={(e) => setRh(e.target.value)} /></label>
            <label className={LABEL}>{t('sensorRain')}<input className={FIELD} type="number" inputMode="decimal" value={rain} onChange={(e) => setRain(e.target.value)} /></label>
            <label className={LABEL}>{t('sensorTmin')}<input className={FIELD} type="number" inputMode="decimal" value={tmin} onChange={(e) => setTmin(e.target.value)} /></label>
            <label className={LABEL}>{t('sensorTmax')}<input className={FIELD} type="number" inputMode="decimal" value={tmax} onChange={(e) => setTmax(e.target.value)} /></label>
          </div>
          <button onClick={save} disabled={busy || (rh === '' && tmin === '' && tmax === '' && rain === '')} className={PRIMARY}>
            {busy && <Loader2 className="h-5 w-5 animate-spin" />}
            {t('record')}
          </button>
          {done && <p role="status" className="text-center text-[15px] text-leaf-deep">{t('trapRecorded')}</p>}
          {failed && <p role="alert" className="text-center text-[15px] text-ember">{t('notSaved')}</p>}
        </div>
      )}
    </section>
  )
}

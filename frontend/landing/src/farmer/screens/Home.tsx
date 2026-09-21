import { useState } from 'react'
import { Camera, ClipboardCheck, Loader2, ShieldCheck, Sparkles, Video } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import type { CropInfo, Home as HomeData } from '../../api/types'
import { useAsync, useWide } from '../../lib/hooks'
import { Card, ErrorBox, SectionTitle, Spinner } from '../../ui/kit'
import AlertCard from '../components/AlertCard'
import LocationAsk from '../components/LocationAsk'
import ProblemRow from '../components/ProblemRow'
import WeatherStrip from '../components/WeatherStrip'
import { WeatherNowCard } from './Weather'
import { useFarmer } from '../FarmerContext'

export default function Home() {
  const { farmId, lang, t } = useFarmer()
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  const crops = useAsync(() => api.crops(lang), [lang], ['crops', lang].join(':'))
  const wide = useWide()

  if (home.loading && !home.data) return <Spinner label={t('loading')} />
  if (home.error) return <ErrorBox error={home.error} onRetry={home.reload} retryLabel={t('retry')} />
  const d = home.data!
  const crop = crops.data?.find((c) => c.id === d.farm.crop)
  const openAlerts = d.alerts.filter((a) => a.outcome === null || a.outcome === 'snoozed')
  const due = d.followups_due

  const followups = (
    <>
      {due.slice(0, 2).map((f) => (
        <FollowUp key={f.id} id={f.id} name={f.name} onDone={home.reload} />
      ))}
      {due.length > 2 && (
        <Link to="/app/history" className="block text-center text-sm text-leaf-deep font-medium -mt-3">
          +{due.length - 2} · {t('allHistory')} →
        </Link>
      )}
    </>
  )
  const cta = (
    <>
        <Link
          to="/app/live"
          className="relative block w-full rounded-3xl bg-gradient-to-br from-soil-dark to-leaf-deep text-cream overflow-hidden p-5 shadow-lg shadow-leaf-deep/25 active:scale-[0.99] transition-transform"
        >
          <span aria-hidden className="absolute -bottom-14 -right-8 w-48 h-48 rounded-full bg-ochre/30 blur-2xl" />
          <span className="relative inline-flex items-center gap-1.5 rounded-full bg-ember px-2 py-0.5 text-[10px] font-bold">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" /> LIVE
          </span>
          <span className="relative mt-2 flex items-center gap-4">
            <span className="w-14 h-14 rounded-2xl bg-cream/10 ring-1 ring-ochre/50 flex items-center justify-center">
              <Video className="w-7 h-7 text-ochre" />
            </span>
            <span>
              <span className="block text-lg font-medium leading-tight">{t('liveCta')}</span>
              <span className="block text-xs text-cream/70 mt-0.5">{t('liveCtaSub')}</span>
            </span>
          </span>
        </Link>

        <Link
          to="/app/scan"
          className="relative block w-full rounded-3xl bg-leaf-deep text-cream overflow-hidden p-5 shadow-lg shadow-leaf-deep/25 active:scale-[0.99] transition-transform"
        >
          <span aria-hidden className="absolute -top-12 -right-10 w-44 h-44 rounded-full bg-leaf/40 blur-2xl" />
          <span className="relative flex items-center gap-4">
            <span className="w-14 h-14 rounded-2xl bg-cream/10 ring-1 ring-ochre/50 flex items-center justify-center">
              <Camera className="w-7 h-7 text-ochre" />
            </span>
            <span>
              <span className="block text-lg font-medium leading-tight">{t('takePhoto')}</span>
              <span className="block text-xs text-cream/70 mt-0.5">{t('takePhotoSub')}</span>
            </span>
          </span>
          <span className="relative mt-3 flex items-center gap-1.5 text-[11px] text-cream/60">
            <Sparkles className="w-3 h-3" />
            {d.model.is_stub ? t('demoModel') : t('realModel')}
          </span>
        </Link>
    </>
  )
  const todayChecks = (
        <section>
          <SectionTitle sub={t('todayChecksSub')}>
            <span className="flex items-center gap-2">
              <ClipboardCheck className="w-5 h-5 text-leaf" />
              {t('todayChecks')}
            </span>
          </SectionTitle>
          {openAlerts.length === 0 ? (
            <Card className="p-5 text-center text-sm text-soil-dark/60">
              <ShieldCheck className="w-6 h-6 mx-auto text-leaf mb-2" />
              {t('noChecks')}
            </Card>
          ) : (
            <div className="space-y-3">
              {openAlerts.slice(0, 4).map((a) => (
                <AlertCard key={a.id} alert={a} onDone={home.reload} />
              ))}
              {openAlerts.length > 4 && (
                <Link to="/app/alerts" className="block text-center text-sm text-leaf-deep font-medium py-2">
                  +{openAlerts.length - 4} {t('alerts')}
                </Link>
              )}
            </div>
          )}
        </section>
  )
  const recentProblems = (
        <section>
          <SectionTitle>
            <span className="flex items-center justify-between">
              {t('recentProblems')}
              <Link to="/app/history" className="text-xs font-medium text-leaf-deep">{t('allHistory')} →</Link>
            </span>
          </SectionTitle>
          {d.problems.filter((p) => p.gate_outcome !== 'retake').length === 0 ? (
            <p className="text-sm text-soil-dark/50">{t('noProblems')}</p>
          ) : (
            <div className="space-y-2">
              {d.problems.filter((p) => p.gate_outcome !== 'retake').slice(0, 5).map((p) => (
                <ProblemRow key={p.id} p={p} />
              ))}
            </div>
          )}
        </section>
  )
  const location = <LocationAsk farm={d.farm} onUpdated={(farm) => home.setData({ ...d, farm })} />

  // A wide screen gets two columns: the field and its weather on the left,
  // what to do now on the right. Below lg this is the phone layout, in order.
  if (wide) {
    return (
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] gap-8 items-start">
        <div className="space-y-6">
          <FarmCard data={d} crop={crop} />
          {location}
          <WeatherNowCard />
          <WeatherStrip weather={d.weather} rain={d.rain_context} />
        </div>
        <div className="space-y-6">
          {followups}
          <div className="grid grid-cols-2 gap-4 [&>a]:h-full">{cta}</div>
          {todayChecks}
          {recentProblems}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <FarmCard data={d} crop={crop} />

      {/* Everything below is read at the field's spot, so ask for it until we have one. */}
      {location}

      {followups}

      <WeatherNowCard />

      {cta}

      {todayChecks}

      <WeatherStrip weather={d.weather} rain={d.rain_context} />

      {recentProblems}
    </div>
  )
}

function FarmCard({ data, crop }: { data: HomeData; crop?: CropInfo }) {
  const { t } = useFarmer()
  const f = data.farm
  const stages = crop?.stages ?? []
  const lastDas = stages.length ? stages[stages.length - 2]?.das[1] ?? 120 : 120
  const pct = Math.min(100, Math.max(0, (f.das / lastDas) * 100))
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-soil-dark/50">{f.district} · {f.area_acres} {t('acres')}{f.variety ? ` · ${f.variety}` : ''}</p>
          <h1 className="font-instrument-serif text-3xl leading-tight">{f.crop_name}</h1>
        </div>
        <div className="text-right">
          <p className="text-3xl font-semibold text-leaf-deep leading-none">{f.das}</p>
          <p className="text-[11px] text-soil-dark/50">{t('daysOld')}</p>
        </div>
      </div>
      {stages.length > 0 && (
        <div className="mt-4">
          <div className="relative h-2 rounded-full bg-soil-dark/10">
            <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-leaf to-ochre" style={{ width: `${pct}%` }} />
            <span className="absolute -top-1 w-4 h-4 rounded-full bg-white border-2 border-ochre shadow" style={{ left: `calc(${pct}% - 8px)` }} />
          </div>
          <div className="mt-2 flex justify-between gap-1">
            {stages.slice(0, -1).map((s) => (
              <span key={s.key} className={`text-[10px] leading-tight text-center flex-1 ${s.key === f.stage ? 'text-leaf-deep font-semibold' : 'text-soil-dark/40'}`}>
                {s.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

function FollowUp({ id, name, onDone }: { id: number; name: string | null; onDone: () => void }) {
  const { t, lang } = useFarmer()
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const send = async (r: 'improved' | 'no_change' | 'got_worse') => {
    setBusy(r)
    try {
      const out = await api.followup(id, r, lang)
      if (out.message) {
        setMsg(out.message)
        setTimeout(onDone, 2500)
      } else onDone()
    } finally {
      setBusy(null)
    }
  }
  return (
    <Card className="p-4 border-ochre/40 bg-ochre/5">
      <p className="text-sm font-semibold">{t('followupDue')}</p>
      {name && <p className="text-xs text-soil-dark/60 mt-0.5">{name}</p>}
      {msg ? (
        <p className="mt-2 text-sm text-ember">{msg}</p>
      ) : (
        <div className="mt-3 grid grid-cols-3 gap-2">
          {([['improved', t('improved'), 'bg-leaf text-cream'], ['no_change', t('noChange'), 'bg-white border border-soil-dark/20'], ['got_worse', t('gotWorse'), 'bg-ember text-cream']] as const).map(([r, label, cls]) => (
            <button key={r} onClick={() => send(r)} disabled={busy !== null} className={`min-h-[44px] rounded-xl text-sm font-medium ${cls}`}>
              {busy === r ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : label}
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}

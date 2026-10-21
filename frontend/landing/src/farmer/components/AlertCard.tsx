import { useState } from 'react'
import { Bug, CalendarClock, CheckCircle2, CloudRain, Eye, Loader2, Radar, Search } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import ReportSheet from './ReportSheet'
import type { AlertView } from '../../api/types'
import { ListenButton, Pill } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'

const TRIGGER_ICON: Record<string, typeof CloudRain> = {
  weather: CloudRain,
  'weather+phenology': CloudRain,
  phenology: CalendarClock,
  trap: Bug,
  spread: Radar,
}

const LEVEL_STYLE = {
  high: { ring: 'border-ember/40', bar: 'bg-ember', tone: 'ember' as const },
  medium: { ring: 'border-ochre/50', bar: 'bg-ochre', tone: 'ochre' as const },
  low: { ring: 'border-leaf/30', bar: 'bg-leaf', tone: 'leaf' as const },
}

/** An alert is a task, not a notification: it stays until the farmer records
 *  what they found. There is no dismiss button on purpose. */
export default function AlertCard({ alert, onDone }: { alert: AlertView; onDone: () => void }) {
  const { lang, t } = useFarmer()
  const navigate = useNavigate()
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const Icon = TRIGGER_ICON[alert.trigger] ?? Eye
  const style = LEVEL_STYLE[alert.level]
  const answered = alert.outcome === 'nothing_found' || alert.outcome === 'found'

  // A pest the camera cannot name goes straight to an officer when the farmer
  // says they found it, so it asks for a photo and a sentence first. The
  // photo-diagnosable ones already go to the camera, which asks by itself.
  const [reporting, setReporting] = useState(false)
  const choose = (outcome: 'nothing_found' | 'found' | 'snoozed') =>
    outcome === 'found' && !alert.can_photo ? setReporting(true) : void answer(outcome)

  const answer = async (outcome: 'nothing_found' | 'found' | 'snoozed',
                        evidence?: { photo: Blob | null; note: string }) => {
    setBusy(outcome)
    try {
      const r = await api.alertOutcome(alert.id, outcome, lang, evidence)
      setReporting(false)
      if (outcome === 'found' && alert.can_photo) {
        navigate('/app/scan')
        return
      }
      if (r.message) setNote(r.message)
      else onDone()
      if (r.message) setTimeout(onDone, 2500)
    } finally {
      setBusy(null)
    }
  }

  const speakText = `${alert.name}. ${alert.reason} ${alert.tasks.join(' ')}`

  return (
    <article className={`relative overflow-hidden rounded-2xl bg-white border ${style.ring}`}>
      <span aria-hidden className={`absolute left-0 inset-y-0 w-1 ${style.bar}`} />
      <div className="p-4 pl-5">
        <div className="flex items-start gap-3">
          <span className="shrink-0 w-10 h-10 rounded-full bg-cream flex items-center justify-center">
            <Icon className="w-5 h-5 text-soil-dark/70" />
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <Pill tone={style.tone}>{t(`level_${alert.level}`)}</Pill>
              <Pill>{t(`trig_${alert.trigger}`)}</Pill>
            </div>
            <h3 className="mt-1.5 font-semibold leading-snug">{alert.name}</h3>
          </div>
          <ListenButton text={speakText} lang={lang} label={t('listen')} stopLabel={t('stop')} compact />
        </div>

        <p className="mt-2 text-[13px] leading-relaxed text-soil-dark/70">
          <span className="font-medium text-soil-dark">{t('why')}: </span>
          {alert.reason}
        </p>

        <div className="mt-3 rounded-xl bg-cream/70 p-3">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-leaf-deep">
            <Search className="w-3.5 h-3.5" />
            {t('whatToCheck')}
          </p>
          <ol className="mt-1.5 space-y-1.5">
            {alert.tasks.map((task, i) => (
              <li key={i} className="flex gap-2 text-[13px] leading-snug">
                <span className="shrink-0 w-5 h-5 rounded-full bg-leaf/15 text-leaf-deep text-[11px] font-semibold flex items-center justify-center">
                  {i + 1}
                </span>
                {task}
              </li>
            ))}
          </ol>
        </div>

        {note ? (
          <p className="mt-3 text-sm text-leaf-deep flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            {note}
          </p>
        ) : answered ? (
          <p className="mt-3 text-xs text-soil-dark/50">{t('answered')}</p>
        ) : (
          <div className="mt-3 grid grid-cols-3 gap-2">
            {([
              ['nothing_found', t('nothingFound'), 'border-leaf/40 text-leaf-deep'],
              ['found', t('foundIt'), 'bg-ember text-cream border-ember'],
              ['snoozed', t('remindTomorrow'), 'border-soil-dark/20 text-soil-dark/70'],
            ] as const).map(([o, label, cls]) => (
              <button
                key={o}
                onClick={() => choose(o)}
                disabled={busy !== null}
                className={`min-h-[44px] rounded-xl border text-xs font-medium leading-tight px-1.5 flex items-center justify-center ${cls} disabled:opacity-60`}
              >
                {busy === o ? <Loader2 className="w-4 h-4 animate-spin" /> : label}
              </button>
            ))}
          </div>
        )}
        {reporting && (
          <ReportSheet busy={busy !== null} onCancel={() => setReporting(false)}
            onSend={(ev) => void answer('found', ev)} />
        )}
      </div>
    </article>
  )
}

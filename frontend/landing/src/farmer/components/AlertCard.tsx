import { useState } from 'react'
import { AlertTriangle, Bug, CalendarClock, CheckCircle2, CloudRain, Eye, Loader2, Radar, Search } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import ReportSheet from './ReportSheet'
import { useReadOnlyFarm } from './DemoNotice'
import type { AlertView } from '../../api/types'
import { ListenButton } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'
import { RISK } from '../tokens'
import { PestPhoto } from '../ui'

const TRIGGER_ICON: Record<string, typeof CloudRain> = {
  weather: CloudRain,
  'weather+phenology': CloudRain,
  phenology: CalendarClock,
  trap: Bug,
  spread: Radar,
}

/** An alert is a task, not a notification: it stays until the farmer records
 *  what they found. There is no dismiss button on purpose. */
export default function AlertCard({ alert, onDone }: { alert: AlertView; onDone: () => void }) {
  // A shared demo field is everybody's, so answering its warning would edit
  // what the next visitor walks into — the server refuses it. Offering the
  // buttons anyway would be a control that can only fail.
  const readOnly = useReadOnlyFarm() !== null
  const { lang, t } = useFarmer()
  const navigate = useNavigate()
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const Icon = TRIGGER_ICON[alert.trigger] ?? Eye
  // The level is said by the card's tint and one pill, as on Home.
  const risk = RISK[alert.level]
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
    setFailed(false)
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
    } catch {
      // Walking the field and reporting what was there is the farmer's half of
      // this. Dropping it silently closes the card as though it was recorded.
      setFailed(true)
      setNote(t('notSaved'))
    } finally {
      setBusy(null)
    }
  }

  const speakText = `${alert.name}. ${alert.reason} ${alert.tasks.join(' ')}`

  return (
    <article className={`rounded-[20px] p-4 ring-1 ring-soil-dark/[0.05] sm:p-5 ${risk.row}`}>
      <div className="flex items-start gap-3">
        <PestPhoto target={alert.target} className="h-16 w-16 sm:h-[72px] sm:w-[72px]" />
        <div className="min-w-0 flex-1">
          <h3 className="text-[17px] font-semibold leading-snug sm:text-[18px]">{alert.name}</h3>
          <p className="mt-1 flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-2.5 py-0.5 text-[13px] font-medium ${risk.pill}`}>{t(risk.key)}</span>
            <span className="inline-flex items-center gap-1 text-[13px] text-soil-dark/70">
              <Icon className="h-4 w-4" aria-hidden /> {t(`trig_${alert.trigger}`)}
            </span>
          </p>
        </div>
        <ListenButton text={speakText} lang={lang} label={t('listen')} stopLabel={t('stop')} compact />
      </div>

      <p className="mt-3 text-[15px] leading-relaxed text-soil-dark/85">{alert.reason}</p>

      <div className="mt-4 rounded-[18px] bg-white/75 p-3.5 sm:p-4">
        <p className="flex items-center gap-1.5 text-[15px] font-semibold text-leaf-deep">
          <Search className="h-4 w-4" aria-hidden />
          {t('whatToCheck')}
        </p>
        <ol className="mt-2.5 space-y-2.5">
          {alert.tasks.map((task, i) => (
            <li key={i} className="flex gap-2.5 text-[15px] leading-snug text-soil-dark">
              <span className="mt-px flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#e3efd9] text-[12px] font-semibold text-[#2f6a39]">
                {i + 1}
              </span>
              {task}
            </li>
          ))}
        </ol>
      </div>

      {note ? (
        <p className={`mt-4 flex items-center gap-2 text-[15px] ${failed ? 'text-ember' : 'text-leaf-deep'}`}>
          {failed ? <AlertTriangle className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}
          {note}
        </p>
      ) : answered ? (
        <p className="mt-4 text-[14px] text-soil-dark/75">{t('answered')}</p>
      ) : readOnly ? (
        <p className="mt-4 text-[14px] text-soil-dark/75">{t('demoReadOnlyShort')}</p>
      ) : (
        <div className="mt-4 grid grid-cols-3 gap-2">
          {([
            ['found', t('foundIt'), 'bg-[#9a2f17] text-white'],
            ['nothing_found', t('nothingFound'), 'bg-white text-leaf-deep ring-1 ring-[#4b8b3b]/30'],
            ['snoozed', t('remindTomorrow'), 'bg-white/60 text-soil-dark/80 ring-1 ring-soil-dark/15'],
          ] as const).map(([o, label, cls]) => (
            <button
              key={o}
              onClick={() => choose(o)}
              disabled={busy !== null}
              className={`flex min-h-[52px] items-center justify-center rounded-2xl px-2 text-[14px] font-semibold leading-tight transition-[filter] hover:brightness-95 disabled:opacity-60 ${cls}`}
            >
              {busy === o ? <Loader2 className="h-4 w-4 animate-spin" /> : label}
            </button>
          ))}
        </div>
      )}
      {reporting && (
        <ReportSheet busy={busy !== null} onCancel={() => setReporting(false)}
          onSend={(ev) => void answer('found', ev)} />
      )}
    </article>
  )
}

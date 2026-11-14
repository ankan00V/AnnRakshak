import { ArrowLeft, Camera, Clock, FlaskConical, History as HistoryIcon, UserCheck } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { bcp47 } from '../../lib/i18n'
import { ErrorBox } from '../../ui/kit'
import { HistorySkeleton, ProblemDetailSkeleton } from '../components/Skeletons'
import AdvisoryView from '../components/AdvisoryView'
import LastKnown from '../components/LastKnown'
import ProblemRow, { problemStatus } from '../components/ProblemRow'
import { useFarmer } from '../FarmerContext'
import { PANEL, STATUS_PILL } from '../tokens'
import { PanelHead, PhotoCurve } from '../ui'

/** Every photo check on this field, newest first. */
export default function History() {
  const { farmId, lang, t } = useFarmer()
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  if (home.loading && !home.data) return <HistorySkeleton />
  if (home.error && !home.data) return <ErrorBox offlineLabel={t('offline')} error={home.error} onRetry={home.reload} retryLabel={t('retry')} />
  const problems = home.data!.problems.filter((p) => p.gate_outcome !== 'retake')
  return (
    <section className={`${PANEL} p-5 lg:p-6`}>
      <PanelHead icon={HistoryIcon} title={t('historyListTitle').replace('{n}', String(problems.length))}
        sub={home.data!.farm.crop_name} />
      {problems.length === 0 ? (
        <div className="mt-5 flex flex-col items-start gap-4 rounded-[20px] bg-[#f5f7f1] p-5 sm:flex-row sm:items-center">
          <p className="flex-1 text-[15px] text-soil-dark/80">{t('noProblems')}</p>
          <Link to="/app/scan"
            className="flex min-h-[48px] items-center gap-2 rounded-full bg-[#2f6a39] px-5 text-[15px] font-semibold text-white hover:bg-[#2a5f33]">
            <Camera className="h-5 w-5" aria-hidden /> {t('qaScan')}
          </Link>
        </div>
      ) : (
        <ul className="mt-5 grid gap-3 md:grid-cols-2">
          {problems.map((p) => <li key={p.id}><ProblemRow p={p} /></li>)}
        </ul>
      )}
    </section>
  )
}

/** One photo check: the photo, what it is, who has looked at it, and the
 *  advice that goes with it. */
export function ProblemDetail() {
  const { id } = useParams()
  const { lang, t } = useFarmer()
  // Kept on the phone like every other screen: a diagnosis the farmer already
  // received must still open when they are back in the field without signal.
  const p = useAsync(() => api.problem(Number(id), lang), [id, lang], ['problem', id, lang].join(':'))
  if (p.loading && !p.data) return <ProblemDetailSkeleton />
  if (p.error && !p.data) return <ErrorBox offlineLabel={t('offline')} error={p.error} onRetry={p.reload} retryLabel={t('retry')} />
  const d = p.data!
  const s = problemStatus(d, t)
  const Icon = s.icon
  const date = d.opened_at
    ? new Date(d.opened_at + 'Z').toLocaleDateString(bcp47(lang), { day: 'numeric', month: 'long', year: 'numeric' })
    : null
  return (
    <div className="space-y-5">
      {p.error && <LastKnown at={p.savedAt} onRetry={p.reload} />}
      <Link to="/app/history" className="inline-flex min-h-[44px] items-center gap-1.5 text-[15px] font-medium text-leaf-deep">
        <ArrowLeft className="h-5 w-5" aria-hidden /> {t('historyTitle')}
      </Link>
      {/* The photo and who has looked at it beside the advice, which is the
          long part: neither column is left empty whatever the case holds. */}
      <div className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)] xl:grid-cols-[420px_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          <section className={`${PANEL} p-2`}>
            {d.image_url && (
              <div className="relative overflow-hidden rounded-[22px] bg-[#eef3e6]">
                <img src={d.image_url} alt="" className="aspect-[4/3] w-full object-cover sm:aspect-[16/10] lg:aspect-[4/3]" />
                <PhotoCurve />
              </div>
            )}
            <div className="px-3 pb-4 pt-2 sm:px-4">
              <h1 className="font-instrument-serif text-[34px] leading-tight text-balance lg:text-[40px]">{d.name ?? t('problemUnnamed')}</h1>
              <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[14px] font-medium ${STATUS_PILL[s.tone]}`}>
                  <Icon className="h-4 w-4" aria-hidden /> {s.label}
                </span>
                {date && <span className="text-[14px] text-soil-dark/70">{date}</span>}
              </p>
            </div>
          </section>
          {d.expert && (
            <section className={`${PANEL} p-5`}>
              <PanelHead icon={UserCheck} title={t('expertVerdict')} sub={d.expert.expert_name} />
              {d.expert.notes && <p className="mt-4 rounded-[20px] bg-[#f1f6ec] p-4 text-[15px] leading-relaxed">{d.expert.notes}</p>}
              {d.expert.referred_to_lab && (
                <p className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-sky-100 px-3 py-1 text-[14px] font-medium text-sky-800">
                  <FlaskConical className="h-4 w-4" aria-hidden /> {t('sentToLab')}
                </p>
              )}
            </section>
          )}
          {d.case && d.case.status === 'open' && (
            <section className={`${PANEL} p-5`}>
              <PanelHead icon={Clock} title={t('awaitingExpert')} sub={t('caseWaitSub')} />
              <dl className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-[20px] bg-[#f5f7f1] p-4">
                  <dt className="text-[13px] text-soil-dark/75">{t('queuePosition')}</dt>
                  <dd className="mt-1 text-[26px] font-semibold tabular-nums">{d.case.queue_position}</dd>
                </div>
                <div className="rounded-[20px] bg-[#f5f7f1] p-4">
                  <dt className="text-[13px] text-soil-dark/75">{t('caseEta')}</dt>
                  <dd className="mt-1 text-[26px] font-semibold tabular-nums">~{d.case.eta_minutes} <span className="text-[15px] font-normal">{t('minutes')}</span></dd>
                </div>
              </dl>
            </section>
          )}
        </div>
        <div className="min-w-0 space-y-6">
          {d.advisory && <AdvisoryView advisory={d.advisory} />}
        </div>
      </div>
    </div>
  )
}

import { ArrowLeft, UserCheck } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import { useAsync } from '../../lib/hooks'
import { ErrorBox, Pill, Spinner } from '../../ui/kit'
import AdvisoryView from '../components/AdvisoryView'
import ProblemRow, { problemStatus } from '../components/ProblemRow'
import { useFarmer } from '../FarmerContext'

export default function History() {
  const { farmId, lang, t } = useFarmer()
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  if (home.loading && !home.data) return <Spinner label={t('loading')} />
  if (home.error) return <ErrorBox error={home.error} onRetry={home.reload} />
  const problems = home.data!.problems.filter((p) => p.gate_outcome !== 'retake')
  return (
    <div className="space-y-4">
      <h1 className="font-instrument-serif text-3xl leading-tight">{t('historyTitle')}</h1>
      {problems.length === 0 ? (
        <p className="text-sm text-soil-dark/50">{t('noProblems')}</p>
      ) : (
        <div className="space-y-2">{problems.map((p) => <ProblemRow key={p.id} p={p} />)}</div>
      )}
    </div>
  )
}

export function ProblemDetail() {
  const { id } = useParams()
  const { lang, t } = useFarmer()
  const p = useAsync(() => api.problem(Number(id), lang), [id, lang])
  if (p.loading && !p.data) return <Spinner label={t('loading')} />
  if (p.error) return <ErrorBox error={p.error} onRetry={p.reload} />
  const d = p.data!
  const s = problemStatus(d, t)
  return (
    <div className="space-y-4">
      <Link to="/app/history" className="flex items-center gap-1 text-sm text-soil-dark/60">
        <ArrowLeft className="w-4 h-4" />
        {t('back')}
      </Link>
      {d.image_url && <img src={d.image_url} alt="" className="w-full aspect-square object-cover rounded-3xl" />}
      <div className="flex items-center justify-between gap-2">
        <h1 className="font-instrument-serif text-3xl leading-tight">{d.name ?? '—'}</h1>
        <Pill tone={s.tone}>{s.label}</Pill>
      </div>
      {d.expert && (
        <div className="rounded-2xl bg-leaf/10 border border-leaf/30 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-leaf-deep">
            <UserCheck className="w-4 h-4" />
            {t('expertVerdict')} — {d.expert.expert_name}
          </p>
          {d.expert.notes && <p className="mt-1 text-sm">{d.expert.notes}</p>}
          {d.expert.referred_to_lab && <Pill tone="sky" className="mt-2">Lab referral</Pill>}
        </div>
      )}
      {d.case && d.case.status === 'open' && (
        <div className="rounded-2xl bg-sky-50 border border-sky-200 p-4 text-sm">
          {t('awaitingExpert')} · {t('queuePosition')} #{d.case.queue_position} · ~{d.case.eta_minutes} {t('minutes')}
        </div>
      )}
      {d.advisory && <AdvisoryView advisory={d.advisory} />}
    </div>
  )
}

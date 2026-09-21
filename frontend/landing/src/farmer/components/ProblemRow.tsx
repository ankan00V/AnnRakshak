import { ChevronRight, CircleCheck, Clock, HelpCircle, Stethoscope, UserCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ProblemView } from '../../api/types'
import { Pill } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'
import { bcp47 } from '../../lib/i18n'

export function problemStatus(p: ProblemView, t: (k: string) => string) {
  if (p.expert) return { label: t('advisedByExpert'), tone: 'leaf' as const, icon: UserCheck }
  if (p.case && p.case.status === 'open') return { label: t('awaitingExpert'), tone: 'sky' as const, icon: Clock }
  if (p.status === 'resolved' && p.gate_outcome !== 'retake') return { label: t('resolved'), tone: 'neutral' as const, icon: CircleCheck }
  if (p.advisory_source === 'doubt_doctor') return { label: t('advisedByDoubt'), tone: 'ochre' as const, icon: HelpCircle }
  if (p.advisory_source === 'model') return { label: t('advisedByModel'), tone: 'ochre' as const, icon: Stethoscope }
  return { label: t('open'), tone: 'neutral' as const, icon: Clock }
}

export default function ProblemRow({ p, stacked = false }: { p: ProblemView; stacked?: boolean }) {
  const { t, lang } = useFarmer()
  const s = problemStatus(p, t)
  const Icon = s.icon
  const date = p.opened_at ? new Date(p.opened_at + 'Z').toLocaleDateString(bcp47(lang), { day: 'numeric', month: 'short' }) : ''
  return (
    <Link to={`/app/history/${p.id}`} className="flex items-center gap-3 rounded-2xl bg-white border border-soil-dark/10 p-3 hover:border-leaf/40">
      <span className="shrink-0 w-12 h-12 rounded-xl overflow-hidden bg-cream">
        {p.image_url && <img src={p.image_url} alt="" className="w-full h-full object-cover" loading="lazy" />}
      </span>
      <span className="flex-1 min-w-0">
        <span className="block text-sm font-medium truncate">{p.name ?? '—'}</span>
        <span className="block text-xs text-soil-dark/50">{date}</span>
        {/* In a narrow column the status goes under the name, not beside it. */}
        {stacked && <Pill tone={s.tone} className="mt-1.5"><Icon className="w-3 h-3" />{s.label}</Pill>}
      </span>
      {!stacked && (
        <Pill tone={s.tone}>
          <Icon className="w-3 h-3" />
          {s.label}
        </Pill>
      )}
      <ChevronRight className="w-4 h-4 text-soil-dark/30" />
    </Link>
  )
}

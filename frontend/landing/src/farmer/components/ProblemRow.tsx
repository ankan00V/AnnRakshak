import { ChevronRight, CircleCheck, Clock, HelpCircle, Stethoscope, UserCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ProblemView } from '../../api/types'
import { useFarmer } from '../FarmerContext'
import { bcp47 } from '../../lib/i18n'
import { STATUS_PILL } from '../tokens'

export function problemStatus(p: ProblemView, t: (k: string) => string) {
  if (p.expert) return { label: t('advisedByExpert'), tone: 'leaf' as const, icon: UserCheck }
  if (p.case && p.case.status === 'open') return { label: t('awaitingExpert'), tone: 'sky' as const, icon: Clock }
  if (p.status === 'resolved' && p.gate_outcome !== 'retake') return { label: t('resolved'), tone: 'neutral' as const, icon: CircleCheck }
  if (p.advisory_source === 'doubt_doctor') return { label: t('advisedByDoubt'), tone: 'ochre' as const, icon: HelpCircle }
  if (p.advisory_source === 'model') return { label: t('advisedByModel'), tone: 'ochre' as const, icon: Stethoscope }
  return { label: t('open'), tone: 'neutral' as const, icon: Clock }
}

/** One photo check: the photo, what it was, when, and where it stands. */
export default function ProblemRow({ p, size = 'md' }: { p: ProblemView; size?: 'sm' | 'md' }) {
  const { t, lang } = useFarmer()
  const s = problemStatus(p, t)
  const Icon = s.icon
  const date = p.opened_at ? new Date(p.opened_at + 'Z').toLocaleDateString(bcp47(lang), { day: 'numeric', month: 'short' }) : ''
  const thumb = size === 'sm' ? 'h-16 w-16' : 'h-[72px] w-[72px]'
  return (
    <Link to={`/app/history/${p.id}`}
      className="flex items-center gap-3 rounded-[20px] bg-white p-2.5 ring-1 ring-soil-dark/[0.06] transition-colors hover:bg-[#f5f7f1] active:bg-[#eef3e6]">
      <span className={`${thumb} shrink-0 overflow-hidden rounded-2xl bg-[#eef3e6]`}>
        {p.image_url && <img src={p.image_url} alt="" loading="lazy" className="h-full w-full object-cover" />}
      </span>
      <span className="min-w-0 flex-1">
        {/* Never a dash for a name: until someone names it, say so. */}
        <span className="block truncate text-[16px] font-semibold">{p.name ?? t('problemUnnamed')}</span>
        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[13px] font-medium ${STATUS_PILL[s.tone]}`}>
            <Icon className="h-3.5 w-3.5" aria-hidden /> {s.label}
          </span>
          <span className="text-[13px] text-soil-dark/70">{date}</span>
        </span>
      </span>
      <ChevronRight className="h-5 w-5 shrink-0 text-soil-dark/50" aria-hidden />
    </Link>
  )
}

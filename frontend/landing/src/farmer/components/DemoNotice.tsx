import { Link } from 'react-router-dom'
import { Eye, Sprout } from 'lucide-react'
import { api } from '../../api/client'
import type { Farm } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { useFarmer } from '../FarmerContext'
import { Card } from '../../ui/kit'

/** What a shared demonstration field says when it is asked to do something.
 *
 *  Every visitor who tries the app is handed the same four fields. Letting one
 *  of them photograph a crop onto it, log a spray against it or put their
 *  email on its warnings would edit what the next visitor — and a judge —
 *  walks into, and would quietly give that visitor somebody else's answers.
 *
 *  So the demo is complete to read and closed to change, and the moment
 *  somebody reaches for a tool, that is the moment to offer them a field of
 *  their own: it is the first point where the app is worth more to them with
 *  their crop in it than with ours.
 */
export default function DemoNotice({ title, body, className = '' }: {
  title?: string
  body?: string
  className?: string
}) {
  const { t } = useFarmer()
  return (
    <Card className={`p-5 bg-ochre/[0.07] border-ochre/30 ${className}`}>
      <p className="flex items-center gap-2 text-sm font-semibold">
        <Eye className="w-4 h-4 text-ochre" />
        {title ?? t('demoTitle')}
      </p>
      <p className="mt-2 text-sm font-light leading-relaxed text-soil-dark/75 text-pretty">
        {body ?? t('demoBody')}
      </p>
      <Link to="/signup/farmer"
        className="mt-4 inline-flex items-center gap-2 min-h-[46px] px-5 rounded-full
                   bg-leaf-deep text-cream text-sm font-semibold">
        <Sprout className="w-4 h-4" />
        {t('demoCta')}
      </Link>
    </Card>
  )
}

/** Whether the field currently being looked at is the shared demonstration
 *  data. Reads the farm list every screen already shares, so asking costs
 *  nothing beyond the request that was happening anyway. */
export function useReadOnlyFarm(): Farm | null {
  const { farmId, lang } = useFarmer()
  const farms = useAsync(() => api.farms(lang), [lang], ['farms', lang].join(':'))
  const farm = farms.data?.find((f) => f.id === farmId)
  return farm?.read_only ? farm : null
}

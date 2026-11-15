import { WifiOff } from 'lucide-react'
import { bcp47 } from '../../lib/i18n'
import { useFarmer } from '../FarmerContext'

/** The line a screen wears when the server could not be reached and what the
 *  farmer is reading is the copy this phone kept.
 *
 *  Two things have to land at once: the app is not broken, and these words are
 *  not today's. So the moment it was saved is inside the sentence rather than a
 *  detail below it — somebody deciding whether to spray this morning needs to
 *  see that the forecast is yesterday evening's. The retry is here too, because
 *  the farmer who walks back towards the road is the one who will use it. */
export default function LastKnown({ at, onRetry }: { at: number | null; onRetry?: () => void }) {
  const { lang, t } = useFarmer()
  const when = at === null
    ? null
    : new Date(at).toLocaleString(bcp47(lang), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  return (
    <p role="status" className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl bg-ochre/10 px-2.5 py-1 text-[13px] text-[#8a5a17]">
      <WifiOff className="h-4 w-4 shrink-0" aria-hidden />
      <span>{when === null ? t('lastKnown') : t('lastKnownAt').replace('{when}', when)}</span>
      {onRetry && (
        // A full thumb's height: this is the one control a farmer out of signal needs.
        <button onClick={onRetry} className="inline-flex min-h-[44px] items-center px-2 font-medium underline underline-offset-2">{t('retry')}</button>
      )}
    </p>
  )
}

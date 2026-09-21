import { useEffect, useRef, useState } from 'react'
import { LocateFixed, Loader2, MapPin, X } from 'lucide-react'
import { api, ApiError } from '../../api/client'
import type { Farm } from '../../api/types'
import { useFarmer } from '../FarmerContext'

/** Everything the app says — the weather, the spraying window, irrigation, and
 *  warnings about an outbreak within 5 km — is read at the field's own spot.
 *  Until the farmer allows location we are using their district headquarters,
 *  so the app asks for it, says why, and keeps asking on later visits.
 *
 *  If the browser has already granted location for this site, the field's spot
 *  is refreshed quietly, without a prompt.
 */
export default function LocationAsk({ farm, onUpdated }: { farm: Farm; onUpdated: (f: Farm) => void }) {
  const { t } = useFarmer()
  const [state, setState] = useState<'idle' | 'asking' | 'saved' | 'denied' | 'failed' | 'far'>('idle')
  const [hidden, setHidden] = useState(false)
  const [far, setFar] = useState<{ lat: number; lon: number; km: number } | null>(null)
  const tried = useRef(false)

  const save = async (lat: number, lon: number, quiet: boolean, confirm = false) => {
    try {
      onUpdated(await api.setFarmLocation(farm.id, lat, lon, confirm))
      setState('saved')
    } catch (e) {
      // The phone is far from the farm's district: never saved silently, and
      // only saved at all once the farmer says the field really is here.
      const d = e instanceof ApiError && e.status === 409 ? (() => { try { return JSON.parse(e.message) } catch { return null } })() : null
      if (d?.code === 'far_from_district' && !quiet) {
        setFar({ lat, lon, km: d.km })
        setState('far')
      } else setState(quiet ? 'idle' : 'failed')
    }
  }

  const ask = (quiet = false) => {
    if (!navigator.geolocation) return setState('failed')
    if (!quiet) setState('asking')
    navigator.geolocation.getCurrentPosition(
      (p) => save(p.coords.latitude, p.coords.longitude, quiet),
      (err) => setState(quiet ? 'idle' : err.code === err.PERMISSION_DENIED ? 'denied' : 'failed'),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    )
  }

  useEffect(() => {
    if (state !== 'saved') return
    const id = window.setTimeout(() => setHidden(true), 4000)
    return () => window.clearTimeout(id)
  }, [state])

  // Already allowed on this phone: take the fix without asking again.
  useEffect(() => {
    if (tried.current || farm.location_source === 'gps' || farm.is_demo) return
    tried.current = true
    navigator.permissions?.query({ name: 'geolocation' as PermissionName })
      .then((p) => p.state === 'granted' && ask(true))
      .catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [farm.id])

  // Stay a moment after saving so the farmer sees it worked, then go.
  // Demo farms are shared showcase fields: nobody opening one is standing in it.
  if (farm.is_demo || (farm.location_source === 'gps' && state !== 'saved') || hidden) return null

  return (
    <section className="rounded-2xl border border-ochre/50 bg-ochre/10 p-4">
      <div className="flex gap-3 items-start">
        <MapPin className="w-5 h-5 text-[#8a5a17] shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <h2 className="font-semibold text-[15px] leading-snug">{t('locAskTitle')}</h2>
          <p className="mt-1 text-[13px] leading-snug text-soil-dark/75">
            {t('locAskBody').replace('{district}', farm.district)}
          </p>
        </div>
        <button onClick={() => setHidden(true)} aria-label={t('locAskLater')} className="p-1 -m-1 text-soil-dark/40">
          <X className="w-4 h-4" />
        </button>
      </div>
      {state === 'saved' ? (
        <p className="mt-3 text-[13px] font-medium text-leaf-deep">{t('locSaved')}</p>
      ) : state === 'far' && far ? (
        <div className="mt-3 rounded-xl bg-white/70 border border-ochre/40 p-3">
          <p className="text-[13px] font-semibold">
            {t('locFarTitle').replace('{km}', String(far.km)).replace('{district}', farm.district)}
          </p>
          <p className="mt-1 text-[12px] text-soil-dark/65">{t('locFarBody')}</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button onClick={() => { setFar(null); setState('idle') }}
              className="min-h-[44px] rounded-full border border-soil-dark/20 bg-white text-sm font-medium">{t('locAskLater')}</button>
            <button onClick={() => { setState('asking'); save(far.lat, far.lon, false, true) }}
              className="min-h-[44px] rounded-full bg-leaf-deep text-cream text-sm font-semibold">{t('locFarYes')}</button>
          </div>
        </div>
      ) : (
        <>
          <button onClick={() => ask()} disabled={state === 'asking'}
            className="mt-3 w-full min-h-[48px] rounded-full bg-leaf-deep text-cream text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-60">
            {state === 'asking' ? <Loader2 className="w-4 h-4 animate-spin" /> : <LocateFixed className="w-4 h-4" />}
            {t('locAskCta')}
          </button>
          <p className="mt-2 text-[12px] text-soil-dark/55">
            {state === 'denied' ? t('locDenied') : state === 'failed' ? t('locFailed') : t('locAskStanding')}
          </p>
        </>
      )}
    </section>
  )
}

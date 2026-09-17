import { useEffect, useState } from 'react'
import { Loader2, LocateFixed, MapPin, Search } from 'lucide-react'
import { api } from '../api/client'
import type { PlaceHit, StatePlaces } from '../api/types'
import { useFarmer } from '../farmer/FarmerContext'
import { useAsync } from '../lib/hooks'
import { Field, Input, Select } from './parts'

export interface Where {
  state: string
  district: string
  village: string
  taluka: string
  lat: number | null
  lon: number | null
  fromGps: boolean
}

/** Where the field is, anywhere in India.
 *
 *  Location first: one tap fills the state, district and village and gives the
 *  exact spot the weather, spray window and outbreak radius are read at. If the
 *  farmer refuses or the phone cannot get a fix, they search for their village,
 *  or pick the state and district from the Government's list — and if their
 *  district is not in it, they type it.
 */
export default function WherePicker({ value, onChange, showErrors }: {
  value: Where; onChange: (w: Where) => void; showErrors?: boolean
}) {
  const { t } = useFarmer()
  const places = useAsync(() => api.places(), [], 'places')
  const [locating, setLocating] = useState(false)
  const [locError, setLocError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<PlaceHit[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [freeDistrict, setFreeDistrict] = useState(false)

  const states: StatePlaces[] = places.data?.states ?? []
  const districts = states.find((s) => s.name === value.state)?.districts ?? []
  const set = (patch: Partial<Where>) => onChange({ ...value, ...patch })

  const locate = () => {
    if (!navigator.geolocation) return setLocError(t('locFailed'))
    setLocating(true)
    setLocError(null)
    navigator.geolocation.getCurrentPosition(
      async (p) => {
        const { latitude: lat, longitude: lon } = p.coords
        try {
          const at = await api.whereAmI(lat, lon)
          set({ lat, lon, fromGps: true, state: at.state ?? value.state, district: at.district ?? value.district,
                village: at.village ?? value.village })
        } catch {
          set({ lat, lon, fromGps: true })  // the spot is what matters; names can be typed
        } finally {
          setLocating(false)
        }
      },
      (err) => {
        setLocError(err.code === err.PERMISSION_DENIED ? t('locDenied') : t('locFailed'))
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    )
  }

  // Village search, a moment after the farmer stops typing.
  useEffect(() => {
    const q = query.trim()
    if (q.length < 3) {
      setHits(null)
      return
    }
    setSearching(true)
    const id = window.setTimeout(async () => {
      try {
        setHits((await api.findPlace(q)).results)
      } catch {
        setHits([])
      } finally {
        setSearching(false)
      }
    }, 450)
    return () => window.clearTimeout(id)
  }, [query])

  const pick = (h: PlaceHit) => {
    set({ state: h.state ?? value.state, district: h.district ?? value.district, village: h.name,
          taluka: h.taluka ?? '', lat: h.lat, lon: h.lon, fromGps: false })
    setQuery('')
    setHits(null)
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-leaf/40 bg-leaf/5 p-3">
        <button type="button" onClick={locate} disabled={locating}
          className="w-full min-h-[52px] rounded-full bg-leaf-deep text-cream text-[15px] font-semibold flex items-center justify-center gap-2 disabled:opacity-60">
          {locating ? <Loader2 className="w-5 h-5 animate-spin" /> : <LocateFixed className="w-5 h-5" />}
          {value.fromGps ? t('locationSet') : t('authUseLocation')}
        </button>
        <p className="mt-2 text-[12px] text-soil-dark/60 leading-snug">
          {locError ?? (value.fromGps ? t('authLocationFilled') : t('authFieldHint'))}
        </p>
      </div>

      <p className="text-center text-[12px] text-soil-dark/45">{t('authOrType')}</p>

      <Field label={t('authSearchVillage')}>
        <div className="relative">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('authSearchVillage')} />
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-soil-dark/35">
            {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          </span>
        </div>
        {hits && hits.length > 0 && (
          <ul className="mt-2 rounded-xl border border-soil-dark/15 bg-white divide-y divide-soil-dark/5 overflow-hidden">
            {hits.map((h, i) => (
              <li key={i}>
                <button type="button" onClick={() => pick(h)}
                  className="w-full text-left px-3 py-2.5 hover:bg-leaf/5 flex items-start gap-2">
                  <MapPin className="w-4 h-4 text-leaf-deep shrink-0 mt-0.5" />
                  <span className="text-[13px] leading-snug">
                    <span className="font-medium">{h.name}</span>
                    <span className="block text-soil-dark/55">
                      {[h.taluka, h.district, h.state].filter(Boolean).join(' · ')}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {hits && hits.length === 0 && !searching && (
          <p className="mt-2 text-[12px] text-soil-dark/55">{t('authNoPlaces')}</p>
        )}
      </Field>

      <Field label={t('authState')} error={showErrors && !value.state && t('authPickState')}>
        <Select value={value.state} onChange={(v) => set({ state: v, district: '' })}>
          <option value="">{t('authPickState')}</option>
          {states.map((s) => <option key={s.name}>{s.name}</option>)}
        </Select>
      </Field>

      <Field label={t('district')} error={showErrors && !value.district && t('authPickDistrict')}>
        {freeDistrict || (value.district && !districts.some((d) => d.name === value.district)) ? (
          <Input value={value.district} onChange={(e) => set({ district: e.target.value })}
            placeholder={t('authTypeDistrict')} />
        ) : (
          <Select value={value.district} onChange={(v) => set({ district: v })}>
            <option value="">{t('authPickDistrict')}</option>
            {districts.map((d) => (
              <option key={d.name} value={d.name}>{d.local ? `${d.name} · ${d.local}` : d.name}</option>
            ))}
          </Select>
        )}
        {!freeDistrict && (
          <button type="button" onClick={() => setFreeDistrict(true)}
            className="mt-1.5 text-[12px] text-leaf-deep underline underline-offset-2">
            {t('authOtherDistrict')}
          </button>
        )}
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label={t('authTaluka')} optional>
          <Input value={value.taluka} onChange={(e) => set({ taluka: e.target.value })} />
        </Field>
        <Field label={t('authVillage')} error={showErrors && value.village.trim().length < 2 && t('authFixField')}>
          <Input value={value.village} onChange={(e) => set({ village: e.target.value })} />
        </Field>
      </div>
    </div>
  )
}

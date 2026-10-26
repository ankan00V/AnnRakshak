import { useState } from 'react'
import { Loader2, Sprout, Trash2, Wheat } from 'lucide-react'
import { api } from '../../api/client'
import type { CropInfo, Farm } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { useFarmer } from '../FarmerContext'
import { bcp47 } from '../../lib/i18n'
import { ErrorBox } from '../../ui/kit'

/** Every field the farmer holds, with the two controls that keep the list
 *  honest: turn one off when the crop comes off it, and take one away for
 *  good.
 *
 *  A farm row is the field, never the sowing. Without somewhere to say the
 *  crop is off, a plot sown last June goes on gaining a day every morning and
 *  is still called "maturing" in March, and a farmer sowing it again registers
 *  it a second time — so the list fills with copies of one plot. Turning it
 *  off closes the season and stops the clock; turning it on starts the next
 *  season on the same row. Remove is for the copies made before any of this
 *  existed.
 */
export default function FieldManager({ farms, crops, onChange }: {
  farms: Farm[]
  crops: CropInfo[] | null
  onChange: () => void
}) {
  const { t } = useFarmer()
  if (farms.length === 0) return <p className="text-sm text-soil-dark/55">{t('profileNoFields')}</p>
  return (
    <ul className="-mt-1 divide-y divide-soil-dark/[0.08]">
      {farms.map((f) => <Row key={f.id} farm={f} crops={crops} onChange={onChange} />)}
    </ul>
  )
}

type Mode = null | 'off' | 'on' | 'remove'

function Row({ farm, crops, onChange }: { farm: Farm; crops: CropInfo[] | null; onChange: () => void }) {
  const { t, lang } = useFarmer()
  const { me } = useAuth()
  // The shared demo fields are handed to every visitor who tries the app.
  // Working one is reversible; removing it would take the demo away from the
  // next person, so the server refuses and the button does not pretend.
  const removable = !(me?.is_demo && farm.is_demo)
  const [mode, setMode] = useState<Mode>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [crop, setCrop] = useState(farm.crop)
  const [sown, setSown] = useState(() => new Date().toISOString().slice(0, 10))
  const fallow = farm.status === 'fallow'
  // Past its crop's season with nobody having said what happened. The field
  // has already stopped counting on its own; what it wants is the answer only
  // the farmer has — the crop came off (and when), or it is still standing.
  const over = !fallow && farm.season_over === true
  // Default the harvest date to the season end rather than today: a field
  // that went quiet months ago did not come off this morning.
  const [cameOff, setCameOff] = useState(
    () => farm.season_end_on ?? new Date().toISOString().slice(0, 10))

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      setMode(null)
      onChange()
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="py-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[15px] font-medium leading-snug">
            <span aria-hidden className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            fallow ? 'bg-soil-dark/25' : over ? 'bg-ochre' : 'bg-leaf'}`} />
            <span className="min-w-0">{farm.crop_name}</span>
          </p>
          <p className="mt-0.5 pl-[14px] text-[12px] leading-snug text-soil-dark/55">
            {farm.village || farm.district}
            {' · '}
            {fallow ? t('seasonRestingShort')
              : over ? t('profileSeasonOver')
              : `${farm.das} ${t('daysOld')} · ${farm.stage_name}`}
            {/* The prediction, where there is a real one to show. A farmer who
                can see the date is a farmer who can tell us it is wrong. */}
            {!fallow && !over && farm.expected_harvest && farm.expected_harvest.basis !== 'calendar'
              && ` · ${t('profileReadyAround').replace('{on}',
                   new Date(farm.expected_harvest.on).toLocaleDateString(bcp47(lang),
                     { day: 'numeric', month: 'short' }))}`}
            {!!farm.seasons && ` · ${t('seasonCount').replace('{n}', String(farm.seasons))}`}
          </p>
        </div>
        <span className={`shrink-0 whitespace-nowrap px-2.5 py-1 rounded-full text-[11px] font-medium ${
          fallow ? 'bg-soil-dark/[0.06] text-soil-dark/60' : 'bg-leaf/15 text-leaf-deep'}`}>
          {farm.area_acres} {t('acres')}
        </span>
      </div>

      {error && <div className="mt-2.5"><ErrorBox error={error} /></div>}

      {mode === null && (
        <div className="mt-2.5 pl-[14px] flex flex-wrap items-center gap-2">
          <button onClick={() => setMode(fallow ? 'on' : 'off')}
            className={`min-h-[36px] px-3.5 rounded-full text-[13px] font-medium flex items-center gap-1.5 transition-colors ${
              fallow ? 'bg-leaf-deep text-cream'
              : over ? 'bg-ochre text-cream'
              : 'border border-soil-dark/20 text-soil-dark/75 hover:bg-soil-dark/[0.04]'}`}>
            {fallow ? <Sprout className="w-3.5 h-3.5" /> : <Wheat className="w-3.5 h-3.5" />}
            {fallow ? t('profileFieldOn') : t('profileFieldOff')}
          </button>
          {over && (
            <button disabled={busy} onClick={() => run(() => api.stillStanding(farm.id))}
              className="min-h-[36px] px-3.5 rounded-full border border-leaf-deep/30 text-leaf-deep
                         text-[13px] font-medium flex items-center gap-1.5 hover:bg-leaf/10 disabled:opacity-60">
              <Sprout className="w-3.5 h-3.5" />
              {t('profileStillStanding')}
            </button>
          )}
          {removable && <button onClick={() => setMode('remove')} aria-label={t('profileFieldRemove')}
            className="min-h-[36px] px-3 rounded-full text-[13px] text-soil-dark/45 hover:text-ember hover:bg-ember/[0.07]
                       flex items-center gap-1.5 transition-colors">
            <Trash2 className="w-3.5 h-3.5" />
            {t('profileFieldRemove')}
          </button>}
        </div>
      )}

      {/* Closing the season: the crop is off, so the days stop here. */}
      {mode === 'off' && (over ? (
        <div className="mt-2.5 ml-[14px] rounded-xl bg-ochre/[0.07] p-3">
          <p className="text-[12px] leading-relaxed text-soil-dark/75">{t('seasonOverNote')}</p>
          <label className="mt-2.5 block text-[11px] text-soil-dark/60 sm:max-w-[16rem]">
            {t('profileCameOffOn')}
            <input type="date" className={FIELD} value={cameOff}
              max={new Date().toISOString().slice(0, 10)} min={farm.sowing_date}
              onChange={(e) => setCameOff(e.target.value)} />
          </label>
          <Buttons busy={busy} onCancel={() => setMode(null)} label={t('seasonConfirm')} tone="ochre"
            onYes={() => run(() => api.harvest(farm.id, { harvested_on: cameOff }))} />
        </div>
      ) : (
        <Confirm busy={busy} onCancel={() => setMode(null)} tone="ochre"
          note={t('seasonGrowingNote')}
          label={t('seasonConfirm')} onYes={() => run(() => api.harvest(farm.id, {}))} />
      ))}

      {/* The next season, on this same row rather than a new one. */}
      {mode === 'on' && (
        <div className="mt-2.5 ml-[14px] rounded-xl bg-cream/70 border border-soil-dark/10 p-3">
          <p className="text-[12px] leading-relaxed text-soil-dark/65">
            {t('seasonFallowNote').replace('{on}', farm.harvested_on ?? '')}
          </p>
          <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
            <label className="block text-[11px] text-soil-dark/60">
              {t('crop')}
              <select className={FIELD} value={crop} onChange={(e) => setCrop(e.target.value)}>
                {(crops ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <label className="block text-[11px] text-soil-dark/60">
              {t('sowingDateOnly')}
              <input type="date" className={FIELD} value={sown} max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setSown(e.target.value)} />
            </label>
          </div>
          <Buttons busy={busy} onCancel={() => setMode(null)} label={t('seasonStart')} tone="leaf"
            onYes={() => run(() => api.sow(farm.id, { crop, sowing_date: sown }))} />
        </div>
      )}

      {mode === 'remove' && (
        <Confirm busy={busy} onCancel={() => setMode(null)} tone="ember"
          note={t('profileRemoveAsk')} label={t('profileRemoveYes')}
          onYes={() => run(() => api.deleteFarm(farm.id))} />
      )}
    </li>
  )
}

const FIELD = 'mt-1 w-full min-h-[40px] rounded-xl border border-soil-dark/20 bg-white px-2.5 text-sm'

function Confirm({ note, label, onYes, onCancel, busy, tone }: {
  note: string; label: string; onYes: () => void; onCancel: () => void; busy: boolean; tone: 'ochre' | 'ember'
}) {
  return (
    <div className={`mt-2.5 ml-[14px] rounded-xl p-3 ${tone === 'ember' ? 'bg-ember/[0.06]' : 'bg-ochre/[0.07]'}`}>
      <p className="text-[12px] leading-relaxed text-soil-dark/75">{note}</p>
      <Buttons busy={busy} onCancel={onCancel} label={label} tone={tone} onYes={onYes} />
    </div>
  )
}

function Buttons({ label, onYes, onCancel, busy, tone }: {
  label: string; onYes: () => void; onCancel: () => void; busy: boolean; tone: 'ochre' | 'ember' | 'leaf'
}) {
  const { t } = useFarmer()
  const fill = tone === 'ember' ? 'bg-ember text-cream' : tone === 'leaf' ? 'bg-leaf-deep text-cream' : 'bg-ochre text-cream'
  return (
    <div className="mt-2.5 flex gap-2">
      <button disabled={busy} onClick={onYes}
        className={`min-h-[40px] px-4 rounded-full text-[13px] font-semibold flex items-center gap-2 disabled:opacity-60 ${fill}`}>
        {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
        {label}
      </button>
      <button onClick={onCancel} className="min-h-[40px] px-4 rounded-full border border-soil-dark/20 text-[13px]">
        {t('back')}
      </button>
    </div>
  )
}

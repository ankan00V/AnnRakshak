import { useState } from 'react'
import { Sprout, Wheat } from 'lucide-react'
import { api } from '../../api/client'
import type { CropInfo, Farm } from '../../api/types'
import { useFarmer } from '../FarmerContext'
import { Card, ErrorBox } from '../../ui/kit'

/** Closing a season, and opening the next one on the same field.
 *
 *  A farm row is the field. Before this it was the sowing as well, so when the
 *  crop came off there was nothing to press: the days after sowing went on
 *  counting, the stage ran past the end of the crop calendar, and a farmer
 *  sowing the same plot again had to register it a second time. One plot, two
 *  rows, and the list grew a copy every season.
 */
export default function SeasonSwitch({ farm, crops, onChange }: {
  farm: Farm; crops: CropInfo[] | null; onChange: (f: Farm) => void
}) {
  const { t } = useFarmer()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [crop, setCrop] = useState(farm.crop)
  const [sown, setSown] = useState(() => new Date().toISOString().slice(0, 10))
  const [basis, setBasis] = useState<'sown' | 'transplanted'>('sown')
  const nursery = !!crops?.find((c) => c.id === crop)?.nursery_days

  const run = async (fn: () => Promise<Farm>) => {
    setBusy(true)
    setError(null)
    try {
      onChange(await fn())
      setOpen(false)
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  const label = 'rounded-xl border border-soil-dark/20 bg-cream/50 px-3 min-h-[44px] w-full text-sm'

  if (farm.status === 'fallow') {
    return (
      <Card className="p-4 border-dashed">
        <h2 className="font-semibold flex items-center gap-2"><Sprout className="w-4 h-4 text-leaf" /> {t('seasonSowAgain')}</h2>
        <p className="mt-0.5 text-sm text-soil-dark/65">
          {t('seasonFallowNote').replace('{on}', farm.harvested_on ?? '')}
        </p>
        {error && <div className="mt-3"><ErrorBox error={error} /></div>}
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <label className="block text-xs text-soil-dark/60">
            {t('crop')}
            <select className={label} value={crop} onChange={(e) => setCrop(e.target.value)}>
              {(crops ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label className="block text-xs text-soil-dark/60">
            {nursery && basis === 'transplanted' ? t('transplantDate') : t('sowingDateOnly')}
            <input type="date" className={label} value={sown} max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setSown(e.target.value)} />
          </label>
        </div>
        {nursery && (
          <div className="mt-2 flex gap-2">
            {(['sown', 'transplanted'] as const).map((b) => (
              <button key={b} onClick={() => setBasis(b)}
                className={`flex-1 min-h-[40px] rounded-xl border text-[13px] font-medium ${
                  basis === b ? 'border-leaf-deep bg-leaf/10 text-leaf-deep' : 'border-soil-dark/15 bg-white'}`}>
                {t(b === 'sown' ? 'dateBasisSown' : 'dateBasisTransplanted')}
              </button>
            ))}
          </div>
        )}
        <button disabled={busy} onClick={() => run(() => api.sow(farm.id, { crop, sowing_date: sown, date_basis: basis }))}
          className="mt-3 w-full min-h-[46px] rounded-full bg-leaf-deep text-cream text-sm font-semibold disabled:opacity-60">
          {t('seasonStart')}
        </button>
      </Card>
    )
  }

  return (
    <Card className={`p-4 ${farm.season_over ? 'border-ochre/50 bg-ochre/[0.04]' : ''}`}>
      <h2 className="font-semibold flex items-center gap-2"><Wheat className="w-4 h-4 text-ochre" /> {t('seasonTitle')}</h2>
      <p className="mt-0.5 text-sm text-soil-dark/65">
        {farm.season_over ? t('seasonOverNote') : t('seasonGrowingNote')}
      </p>
      {error && <div className="mt-3"><ErrorBox error={error} /></div>}
      {!open ? (
        <button onClick={() => setOpen(true)}
          className={`mt-3 w-full min-h-[46px] rounded-full text-sm font-semibold ${
            farm.season_over ? 'bg-ochre text-cream' : 'border border-soil-dark/20 text-soil-dark/75'}`}>
          {t('seasonHarvested')}
        </button>
      ) : (
        <div className="mt-3 flex gap-2">
          <button disabled={busy} onClick={() => run(() => api.harvest(farm.id, {}))}
            className="flex-1 min-h-[46px] rounded-full bg-ochre text-cream text-sm font-semibold disabled:opacity-60">
            {t('seasonConfirm')}
          </button>
          <button onClick={() => setOpen(false)}
            className="min-h-[46px] px-4 rounded-full border border-soil-dark/20 text-sm">{t('back')}</button>
        </div>
      )}
      {!!farm.seasons && (
        <p className="mt-2 text-[11px] text-soil-dark/50">{t('seasonCount').replace('{n}', String(farm.seasons))}</p>
      )}
    </Card>
  )
}

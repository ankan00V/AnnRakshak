import { useEffect, useRef, useState } from 'react'
import { Camera, Loader2, Send, X } from 'lucide-react'
import { shrink } from '../../lib/image'
import { useFarmer } from '../FarmerContext'

/** What the farmer sends with an escalation.
 *
 *  Saying "it got worse" puts a case on a district officer's desk. It used to
 *  go there carrying nothing — an empty photo frame and one line of generated
 *  text — so the officer opened it blind and the farmer waited on an answer
 *  nobody could give. The farmer is the only person who has stood in that
 *  field, so this asks for what only they have before the case is sent.
 *
 *  The photo is urged, not demanded: a farmer with no light, no signal or no
 *  hand free still has to be able to report it, and a case that says "no
 *  photograph was taken" is worth more than one that pretends there is one.
 */
export default function ReportSheet({ onSend, onCancel, busy }: {
  onSend: (evidence: { photo: Blob | null; note: string }) => void
  onCancel: () => void
  busy: boolean
}) {
  const { t } = useFarmer()
  const [photo, setPhoto] = useState<Blob | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const file = useRef<HTMLInputElement>(null)

  // The raw camera file is 3-5 MB and went out as-is, so on 2G/3G the report
  // timed out after the farmer had already done the hard part. Shrunk the same
  // way a scan is; a phone that cannot decode the file still sends it whole.
  const take = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    // Held as taken straight away, so a Send pressed while the smaller copy
    // is still being made carries the photo, not nothing.
    setPhoto(f)
    setShrinking(true)
    const small = await shrink(f)
    setShrinking(false)
    if (!alive.current) return
    setPhoto(small)
    setPreview((old) => {
      if (old) URL.revokeObjectURL(old)
      return URL.createObjectURL(small)
    })
  }
  const [shrinking, setShrinking] = useState(false)
  const alive = useRef(true)
  const shown = useRef<string | null>(null)
  shown.current = preview
  useEffect(() => () => {
    alive.current = false
    if (shown.current) URL.revokeObjectURL(shown.current)
  }, [])

  return (
    <div className="mt-3 rounded-2xl border border-ember/30 bg-ember/[0.04] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold leading-snug">{t('reportTitle')}</p>
          <p className="mt-0.5 text-[13px] leading-relaxed text-soil-dark/75">{t('reportSub')}</p>
        </div>
        <button onClick={onCancel} aria-label={t('back')}
          className="shrink-0 -m-2 flex h-11 w-11 items-center justify-center rounded-full text-soil-dark/70 hover:bg-soil-dark/5 hover:text-soil-dark">
          <X className="h-5 w-5" />
        </button>
      </div>

      {preview && (
        <img src={preview} alt="" className="mt-3 w-full max-h-52 object-cover rounded-xl" />
      )}

      {/* capture="environment" opens the camera straight onto the crop rather
          than the gallery, which is where the farmer already is. */}
      <input ref={file} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => { void take(e) }} />
      <button onClick={() => file.current?.click()}
        className="mt-3 w-full min-h-[46px] rounded-xl border border-soil-dark/20 bg-white
                   flex items-center justify-center gap-2 text-sm font-medium">
        <Camera className="w-4 h-4" />
        {photo ? t('reportPhotoChange') : t('reportPhotoAdd')}
      </button>

      <label className="mt-3 block">
        <span className="block text-[13px] font-medium text-soil-dark/75">{t('reportNoteLabel')}</span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          maxLength={500}
          placeholder={t('reportNotePlaceholder')}
          className="mt-1 w-full rounded-xl border border-soil-dark/20 bg-white px-3 py-2 text-[16px]
                     focus:outline-none focus:border-leaf"
        />
      </label>

      <button disabled={busy || shrinking} onClick={() => onSend({ photo, note: note.trim() })}
        className="mt-3 w-full min-h-[48px] rounded-full bg-ember text-cream text-sm font-semibold
                   flex items-center justify-center gap-2 disabled:opacity-60">
        {busy || shrinking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        {photo ? t('reportSend') : t('reportNoPhoto')}
      </button>
    </div>
  )
}

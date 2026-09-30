import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Loader2, Megaphone, Search, Send } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { AdvisoryDraft, AdvisoryPreview, OutlookRow } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox, Pill } from '../../ui/kit'
import { OutlookPanel, PanelBone } from '../panels'

const LANGS: [string, string][] = [['mr', 'मराठी'], ['hi', 'हिन्दी'], ['en', 'English']]

/** Maharashtra has issued pest advisories this way since CROPSAP (2009-10):
 *  surveillance comes in, an officer decides, and a location-specific advisory
 *  goes out to the farmers it concerns. This is that step.
 *
 *  Nothing is sent until the officer has seen the farm count, the districts and
 *  the exact words in every language. */
export default function Advisories() {
  const [params] = useSearchParams()
  const outlook = useAsync(() => api.outlook(), [])
  const history = useAsync(() => api.advisoryHistory(), [])
  const options = useAsync(() => api.authOptions('en'), [])

  const [crop, setCrop] = useState(params.get('crop') ?? 'rice')
  const [target, setTarget] = useState(params.get('target') ?? '')
  const [districts, setDistricts] = useState<string[]>([])
  const [kind, setKind] = useState<'advisory' | 'inspection'>('advisory')
  const [level, setLevel] = useState<'low' | 'medium' | 'high'>('high')
  const [note, setNote] = useState('')
  const [lang, setLang] = useState('mr')
  const [preview, setPreview] = useState<AdvisoryPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<{ sent: number; skipped: number } | null>(null)
  const [error, setError] = useState<Error | null>(null)

  const draft: AdvisoryDraft = useMemo(
    () => ({ target, crop, districts, kind, level, note: note || null }),
    [target, crop, districts, kind, level, note])

  // The problems this crop can have, taken from what is actually building when
  // the outlook knows, and from the knowledge base otherwise.
  const targets = useMemo(() => {
    const fromOutlook = (outlook.data ?? []).filter((r: OutlookRow) => r.crop === crop)
    return fromOutlook.map((r) => ({ id: r.target, name: r.name, farms: r.farms }))
  }, [outlook.data, crop])

  useEffect(() => {
    setPreview(null)
    setSent(null)
  }, [target, crop, districts, kind, note])

  const look = async () => {
    if (!target) return
    setBusy(true)
    setError(null)
    try {
      setPreview(await api.advisoryPreview(draft))
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  const send = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await api.issueAdvisory(draft)
      setSent({ sent: r.sent, skipped: r.skipped })
      setPreview(null)
      history.reload()
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  const allDistricts: string[] = options.data?.districts ?? []

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <Card className="p-4 md:p-5">
        <h2 className="font-semibold flex items-center gap-2"><Megaphone className="w-4 h-4 text-leaf" /> Issue an advisory</h2>
        <p className="text-xs text-soil-dark/60 mt-0.5">
          Every farm of this crop in the districts you pick gets it, in their own language, with the
          inspection tasks this problem carries.
        </p>

        <div className="mt-4 grid sm:grid-cols-2 gap-3">
          <label className="block text-xs text-soil-dark/70">
            Crop
            <select value={crop} onChange={(e) => { setCrop(e.target.value); setTarget('') }}
              className="mt-1 w-full min-h-[42px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm">
              {['rice', 'maize', 'cotton', 'soybean'].map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>

          <label className="block text-xs text-soil-dark/70">
            Problem
            <select value={target} onChange={(e) => setTarget(e.target.value)}
              className="mt-1 w-full min-h-[42px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm">
              <option value="">Choose…</option>
              {targets.map((t) => (
                <option key={t.id} value={t.id}>{t.name} — {t.farms} farms alerted</option>
              ))}
            </select>
          </label>
        </div>

        <fieldset className="mt-4">
          <legend className="text-xs text-soil-dark/70">Districts <span className="text-soil-dark/50">(none = the whole state)</span></legend>
          <div className="mt-2 max-h-36 overflow-y-auto rounded-xl border border-soil-dark/15 p-2 flex flex-wrap gap-1.5">
            {allDistricts.length === 0 && <span className="text-xs text-soil-dark/50">Loading districts…</span>}
            {allDistricts.map((d: string) => {
              const on = districts.includes(d)
              return (
                <button key={d} type="button"
                  onClick={() => setDistricts((s) => on ? s.filter((x) => x !== d) : [...s, d])}
                  className={`rounded-full px-2.5 py-1 text-xs border ${on
                    ? 'bg-leaf-deep text-cream border-leaf-deep' : 'border-soil-dark/20 text-soil-dark/70'}`}>
                  {d}
                </button>
              )
            })}
          </div>
        </fieldset>

        <div className="mt-4 grid sm:grid-cols-2 gap-3">
          <label className="block text-xs text-soil-dark/70">
            Kind
            <select value={kind} onChange={(e) => setKind(e.target.value as 'advisory' | 'inspection')}
              className="mt-1 w-full min-h-[42px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm">
              <option value="advisory">Advisory — this is building, check your field</option>
              <option value="inspection">Inspection — go and look at this field</option>
            </select>
          </label>
          <label className="block text-xs text-soil-dark/70">
            Level
            <select value={level} onChange={(e) => setLevel(e.target.value as 'low' | 'medium' | 'high')}
              className="mt-1 w-full min-h-[42px] rounded-xl border border-soil-dark/20 px-3 bg-cream/50 text-sm">
              {['high', 'medium', 'low'].map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </label>
        </div>

        <label className="mt-4 block text-xs text-soil-dark/70">
          Your note (optional — the farmer reads it)
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={400}
            placeholder="e.g. Scouts found it in Sakoli block on Tuesday."
            className="mt-1 w-full rounded-xl border border-soil-dark/20 px-3 py-2 bg-cream/50 text-sm" />
        </label>

        {error && <div className="mt-3"><ErrorBox error={error} /></div>}

        {sent ? (
          <div className="mt-4 rounded-2xl border border-leaf/40 bg-leaf/5 p-4">
            <p className="flex items-center gap-2 font-semibold text-leaf-deep">
              <CheckCircle2 className="w-5 h-5" /> Sent to {sent.sent} farm{sent.sent === 1 ? '' : 's'}
            </p>
            {sent.skipped > 0 && (
              <p className="mt-1 text-xs text-soil-dark/70">
                {sent.skipped} already had this advisory today and were not sent it twice.
              </p>
            )}
          </div>
        ) : preview ? (
          <div className="mt-4 rounded-2xl border border-ochre/40 bg-ochre/[0.06] p-4">
            <p className="text-sm font-medium">
              This reaches <span className="tabular-nums">{preview.farms}</span> farm{preview.farms === 1 ? '' : 's'}
              {preview.districts.length > 0 ? ` in ${preview.districts.join(', ')}` : ' across every district'}.
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(preview.by_district).map(([d, n]) => <Pill key={d}>{d} · {n}</Pill>)}
            </div>

            <div className="mt-3 flex gap-1.5">
              {LANGS.map(([code, label]) => (
                <button key={code} onClick={() => setLang(code)}
                  className={`rounded-full px-2.5 py-1 text-xs ${lang === code ? 'bg-leaf-deep text-cream' : 'bg-white text-soil-dark/70 border border-soil-dark/15'}`}>
                  {label}
                </button>
              ))}
            </div>

            <div className="mt-2 rounded-xl bg-white p-3">
              <p lang={lang} className="text-sm">{preview.reason[lang]}</p>
              <ul lang={lang} className="mt-2 space-y-1 text-xs text-soil-dark/75">
                {(preview.tasks[lang] ?? []).map((t) => <li key={t}>• {t}</li>)}
              </ul>
            </div>

            {preview.farms === 0 ? (
              <p className="mt-3 text-xs text-ember">No farm matches — nothing to send.</p>
            ) : (
              <button onClick={send} disabled={busy}
                className="mt-3 w-full min-h-[44px] rounded-full bg-ember text-cream text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-60">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                Send to {preview.farms} farm{preview.farms === 1 ? '' : 's'}
              </button>
            )}
          </div>
        ) : (
          <button onClick={look} disabled={busy || !target}
            className="mt-4 w-full min-h-[44px] rounded-full bg-leaf-deep text-cream text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            See what would be sent
          </button>
        )}
      </Card>

      <div className="space-y-5">
        <Card className="p-4 md:p-5">
          <h2 className="font-semibold">Issued before</h2>
          {!history.data ? <div className="mt-3"><PanelBone rows={4} /></div>
            : history.data.length === 0 ? (
              <p className="mt-3 text-sm text-soil-dark/70">Nothing has been issued from this office yet.</p>
            ) : (
              <ul className="mt-3 divide-y divide-soil-dark/10">
                {history.data.map((h) => (
                  <li key={h.id} className="py-2.5 flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block text-sm font-medium truncate">
                        {h.target.replace(/_/g, ' ')} <span className="text-soil-dark/50">· {h.kind}</span>
                      </span>
                      <span className="block text-[11px] text-soil-dark/60 truncate">
                        {h.districts.length > 0 ? h.districts.join(', ') : 'every district'} · {h.issued_by}
                        {h.issued_at ? ` · ${h.issued_at.slice(0, 10)}` : ''}
                      </span>
                      {h.note && <span className="block text-[11px] text-soil-dark/50 truncate">“{h.note}”</span>}
                    </span>
                    <span className="text-right shrink-0">
                      <span className="block text-xs tabular-nums text-soil-dark/70">{h.farms} farms</span>
                      {h.farms > 0 && (
                        <span className="mt-1 block text-[11px] tabular-nums">
                          {h.inspected === 0 ? (
                            <span className="text-ember">none checked yet</span>
                          ) : (
                            <>
                              <span className="text-leaf-deep">{h.inspected} checked</span>
                              {h.found > 0 && <span className="text-ember"> · {h.found} found it</span>}
                            </>
                          )}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
        </Card>

        {outlook.data ? <OutlookPanel rows={outlook.data} /> : <PanelBone rows={6} />}
      </div>
    </div>
  )
}

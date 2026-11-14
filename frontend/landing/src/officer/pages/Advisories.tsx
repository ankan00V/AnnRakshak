import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, FileText, History, Loader2, Megaphone, Plus, Search, Send } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { AdvisoryDraft, AdvisoryPreview } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { useAsync } from '../../lib/hooks'
import { MAIN, SIDE, SPLIT } from '../../ui/layout'
import { Card, ErrorBox, Pill } from '../../ui/kit'
import { CardHead, many, OutlookPanel, PageHead, Panel, PanelBone, shortDate, targetName } from '../panels'

// Every language the app sends in. This list was three, so an officer could
// check the Marathi, Hindi and English of what they were about to send and had
// no way to read the Tamil or the Bengali a farmer would actually get.
import { LANGS as APP_LANGS } from '../../lib/i18n'

/** Maharashtra has issued pest advisories this way since CROPSAP (2009-10):
 *  surveillance comes in, an officer decides, and a location-specific advisory
 *  goes out to the farmers it concerns. This is that step.
 *
 *  Nothing is sent until the officer has seen the farm count, the districts and
 *  the exact words in every language. */
export default function Advisories() {
  const [params] = useSearchParams()
  const { me } = useAuth()
  const outlook = useAsync(() => api.outlook(), [])
  const history = useAsync(() => api.advisoryHistory(), [])
  const options = useAsync(() => api.authOptions('en'), [])

  const [crop, setCrop] = useState(params.get('crop') ?? 'rice')
  const [target, setTarget] = useState(params.get('target') ?? '')
  const [districts, setDistricts] = useState<string[]>([])
  const [kind, setKind] = useState<'advisory' | 'inspection'>('advisory')
  const [level, setLevel] = useState<'low' | 'medium' | 'high'>('high')
  const [note, setNote] = useState('')
  const [audience, setAudience] = useState<'all' | 'alerted' | 'nearby' | 'stage'>('alerted')
  const [lang, setLang] = useState('mr')
  const [preview, setPreview] = useState<AdvisoryPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<{ sent: number; skipped: number } | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const formRef = useRef<HTMLDivElement>(null)
  const [allSent, setAllSent] = useState(false)

  /* The outlook says what is building; this turns a row of it into the
     advisory about it. It used to be two screens' worth of copying a disease
     name from a table into a dropdown by hand. */
  const draftFrom = (r: { crop: string; target: string }) => {
    setCrop(r.crop)
    setTarget(r.target)
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const draft: AdvisoryDraft = useMemo(
    () => ({ target, crop, districts, kind, level, note: note || null, audience }),
    [target, crop, districts, kind, level, note, audience])

  /* Every problem this crop can have, with the farms the risk engine has
     already flagged for each. The comment here used to promise the knowledge
     base "otherwise" and the code never asked it: the list was the outlook's
     own rows, so an officer on a quiet week opened this screen, found an empty
     dropdown and could issue nothing at all. That is the week the lever matters
     — a scout's report, the next district's telephone call, a warning that has
     to go out before the first case does. The office asks for the crop's whole
     list now, and what is building sorts to the top of it instead of being the
     whole of it. */
  const choices = useAsync(() => api.advisoryTargets(crop), [crop], `advisory-targets:${crop}`)
  const targets = choices.data ?? []
  const building = targets.filter((t) => t.alerted > 0)
  const quiet = targets.filter((t) => t.alerted === 0)

  useEffect(() => {
    setPreview(null)
    setSent(null)
  }, [target, crop, districts, kind, note, audience])

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

  /* The districts this officer actually covers. It used to be the list from
     /auth/options, which is the IMD rainfall map — 36 Maharashtra districts —
     so an officer at KVK Kapurthala could not pick Kapurthala to advise into.
     Their own coverage is both the right list and a shorter one; the rainfall
     map stays behind it for an account with no districts recorded. */
  const allDistricts: string[] = me?.profile?.districts?.length
    ? me.profile.districts
    : options.data?.districts ?? []

  return (
    <>
      <PageHead title="Advisories"
        purpose="Tell every farm of one crop what is building — in their own language, with the checks it carries.">
        <button onClick={() => formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
          className="flex min-h-[44px] items-center gap-2 rounded-full bg-[#1d4a2c] px-5 text-[15px] font-semibold text-white shadow-sm hover:bg-[#245a35]">
          <Plus className="h-5 w-5" aria-hidden /> Issue an advisory
        </button>
      </PageHead>
      <div className={`gap-5 ${SPLIT}`}>
      <div ref={formRef} className={`scroll-mt-24 ${MAIN}`}>
      <Card className="p-5 lg:p-6">
        <CardHead icon={Megaphone} title="Issue an advisory"
          sub="Every farm of this crop in the districts you pick gets it, in their own language, with the inspection tasks this problem carries." />

        <div className="mt-4 grid sm:grid-cols-2 gap-3">
          <label className="block text-[13px] font-semibold text-soil-dark/80">
            Crop
            <select value={crop} onChange={(e) => { setCrop(e.target.value); setTarget('') }}
              className="mt-1.5 w-full min-h-[46px] rounded-2xl bg-[#f8f6f0] px-3.5 text-[14px] font-normal text-soil-dark ring-1 ring-soil-dark/10 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#4b8b3b]">
              {['rice', 'maize', 'cotton', 'soybean'].map((c) => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
            </select>
          </label>

          <label className="block text-[13px] font-semibold text-soil-dark/80">
            Problem
            {/* "Already alerted" is the right audience while something is
                building, and nobody at all for a problem the engine has not
                flagged — so a warning that arrives before the engine does moves
                to the stage the problem attacks, rather than previewing as a
                count of zero with no reason given. The audience cards are right
                below, so the officer sees it move and can move it back. */}
            <select value={target}
              onChange={(e) => {
                const next = e.target.value
                setTarget(next)
                if (audience === 'alerted' && !targets.some((t) => t.target === next && t.alerted > 0)) setAudience('stage')
              }}
              className="mt-1.5 w-full min-h-[46px] rounded-2xl bg-[#f8f6f0] px-3.5 text-[14px] font-normal text-soil-dark ring-1 ring-soil-dark/10 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#4b8b3b]">
              <option value="">{choices.loading ? 'Loading…' : 'Choose…'}</option>
              {building.length > 0 && (
                <optgroup label="Building now">
                  {building.map((t) => (
                    <option key={t.target} value={t.target}>{t.name} — {many(t.alerted, 'farm')} alerted</option>
                  ))}
                </optgroup>
              )}
              {quiet.length > 0 && (
                <optgroup label={building.length > 0 ? 'Anything else this crop can have' : 'Anything this crop can have'}>
                  {quiet.map((t) => (
                    <option key={t.target} value={t.target}>{t.name}</option>
                  ))}
                </optgroup>
              )}
            </select>
            {choices.error && (
              <span className="mt-1 block text-[12px] font-normal text-ember">
                The list of problems did not load — reload the page before you send anything.
              </span>
            )}
          </label>
        </div>

        <fieldset className="mt-4">
          <legend className="text-[13px] font-semibold text-soil-dark/80">Districts <span className="font-normal text-soil-dark/70">(none = the whole state)</span></legend>
          <div className="mt-2 flex max-h-40 flex-wrap gap-1.5 overflow-y-auto rounded-2xl bg-[#f8f6f0] p-2.5 ring-1 ring-soil-dark/10">
            {allDistricts.length === 0 && <span className="text-[13px] text-soil-dark/70">Loading districts…</span>}
            {allDistricts.map((d: string) => {
              const on = districts.includes(d)
              return (
                <button key={d} type="button"
                  onClick={() => setDistricts((s) => on ? s.filter((x) => x !== d) : [...s, d])}
                  aria-pressed={on}
                  className={`rounded-full px-3 py-1.5 text-[13px] font-medium ring-1 transition-colors ${on
                    ? 'bg-[#1d4a2c] text-white ring-[#1d4a2c]' : 'bg-white text-soil-dark/80 ring-soil-dark/15 hover:ring-[#4b8b3b]/50'}`}>
                  {d}
                </button>
              )
            })}
          </div>
        </fieldset>

        <fieldset className="mt-4">
          <legend className="text-[13px] font-semibold text-soil-dark/80">Who it reaches</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {([
              ['alerted', 'Already alerted', 'farms the risk engine has flagged for this problem'],
              ['nearby', 'Near a confirmed case', 'within the 5 km spread radius'],
              ['stage', 'At a susceptible stage', 'the crop is at the stage this attacks'],
              ['all', 'Every farm of this crop', 'the blunt instrument'],
            ] as const).map(([k, label, why]) => (
              <button key={k} type="button" onClick={() => setAudience(k)}
                aria-pressed={audience === k}
                className={`rounded-2xl px-3.5 py-2.5 text-left ring-1 transition-colors ${audience === k
                  ? 'bg-[#e3efd9] ring-[#4b8b3b]/50' : 'bg-white ring-soil-dark/10 hover:ring-[#4b8b3b]/40'}`}>
                <span className="block text-[14px] font-semibold">{label}</span>
                <span className="block text-[12px] text-soil-dark/70">{why}</span>
              </button>
            ))}
          </div>
        </fieldset>

        <div className="mt-4 grid sm:grid-cols-2 gap-3">
          <label className="block text-[13px] font-semibold text-soil-dark/80">
            Kind
            <select value={kind} onChange={(e) => setKind(e.target.value as 'advisory' | 'inspection')}
              className="mt-1.5 w-full min-h-[46px] rounded-2xl bg-[#f8f6f0] px-3.5 text-[14px] font-normal text-soil-dark ring-1 ring-soil-dark/10 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#4b8b3b]">
              <option value="advisory">Advisory — this is building, check your field</option>
              <option value="inspection">Inspection — go and look at this field</option>
            </select>
          </label>
          <label className="block text-[13px] font-semibold text-soil-dark/80">
            Level
            <select value={level} onChange={(e) => setLevel(e.target.value as 'low' | 'medium' | 'high')}
              className="mt-1.5 w-full min-h-[46px] rounded-2xl bg-[#f8f6f0] px-3.5 text-[14px] font-normal text-soil-dark ring-1 ring-soil-dark/10 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#4b8b3b]">
              {['high', 'medium', 'low'].map((l) => <option key={l} value={l}>{l.charAt(0).toUpperCase() + l.slice(1)}</option>)}
            </select>
          </label>
        </div>

        <label className="mt-4 block text-[13px] font-semibold text-soil-dark/80">
          Your note (optional — the farmer reads it)
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={400}
            placeholder="e.g. Scouts found it in Sakoli block on Tuesday."
            className="mt-1.5 w-full rounded-2xl bg-[#f8f6f0] px-3.5 py-2.5 text-[14px] font-normal ring-1 ring-soil-dark/10 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#4b8b3b]" />
        </label>

        {error && <div className="mt-3"><ErrorBox error={error} /></div>}

        {sent ? (
          <div className="mt-4 rounded-2xl bg-[#eef6ea] p-4">
            <p className="flex items-center gap-2 font-semibold text-leaf-deep">
              <CheckCircle2 className="w-5 h-5" /> Sent to {sent.sent} farm{sent.sent === 1 ? '' : 's'}
            </p>
            {sent.skipped > 0 && (
              <p className="mt-1 text-[13px] text-soil-dark/70">
                {sent.skipped} already had this advisory today and were not sent it twice.
              </p>
            )}
          </div>
        ) : preview ? (
          <div className="mt-4 rounded-2xl bg-[#fdf5e6] p-4 ring-1 ring-[#d29a3a]/25">
            <p className="text-sm font-medium">
              This reaches <span className="tabular-nums">{preview.farms}</span> farm{preview.farms === 1 ? '' : 's'}
              {preview.districts.length > 0 ? ` in ${preview.districts.join(', ')}` : ' across every district'}.
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(preview.by_district).map(([d, n]) => <Pill key={d}>{d} · {n}</Pill>)}
            </div>

            <div className="mt-3 flex flex-wrap gap-1.5">
              {APP_LANGS.map(({ code, label }) => (
                <button key={code} onClick={() => setLang(code)} lang={code} title={code}
                  className={`rounded-full px-3 py-1 text-[13px] ring-1 ${lang === code ? 'bg-[#1d4a2c] text-white ring-[#1d4a2c]' : 'bg-white text-soil-dark/80 ring-soil-dark/15'}`}>
                  {label}
                </button>
              ))}
            </div>

            <div className="mt-2 rounded-xl bg-white p-3">
              <p lang={lang} className="text-sm">{preview.reason[lang]}</p>
              <ul lang={lang} className="mt-2 space-y-1 text-[13px] text-soil-dark/75">
                {(preview.tasks[lang] ?? []).map((t) => <li key={t}>• {t}</li>)}
              </ul>
            </div>

            {preview.farms === 0 ? (
              <p className="mt-3 text-[13px] text-ember">No farm matches — nothing to send.</p>
            ) : (
              <button onClick={send} disabled={busy}
                className="mt-3 flex min-h-[48px] w-full items-center justify-center gap-2 rounded-full bg-[#b5381c] text-[15px] font-semibold text-white hover:brightness-110 disabled:opacity-60">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                Send to {preview.farms} farm{preview.farms === 1 ? '' : 's'}
              </button>
            )}
          </div>
        ) : (
          <button onClick={look} disabled={busy || !target}
            className="mt-5 flex min-h-[48px] w-full items-center justify-center gap-2 rounded-full bg-[#1d4a2c] text-[15px] font-semibold text-white hover:bg-[#245a35] disabled:opacity-50">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            See what would be sent
          </button>
        )}
      </Card>
      </div>

      <div className={SIDE}>
        <Card className="p-5 lg:p-6">
          <CardHead icon={History} title="Sent from this office"
            sub="What went out, to how many farms, and what came back." />
          {history.error && !history.data ? <div className="mt-4"><ErrorBox error={history.error} onRetry={history.reload} /></div>
            : !history.data ? <div className="mt-4"><PanelBone rows={4} /></div>
            : history.data.length === 0 ? (
              <p className="mt-4 rounded-2xl bg-[#f8f6f0] p-4 text-[14px] text-soil-dark/75">Nothing has been issued from this office yet.</p>
            ) : (
              <ul className="mt-3 divide-y divide-soil-dark/[0.07]">
                {(allSent ? history.data : history.data.slice(0, 5)).map((h) => {
                  const checked = h.farms > 0 ? Math.min(1, h.inspected / h.farms) : 0
                  return (
                    <li key={h.id} className="flex gap-3 py-3.5" title={`Issued by ${h.issued_by}`}>
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#eef3e6] text-[#2f6a39]">
                        <FileText className="h-5 w-5" aria-hidden />
                      </span>
                      <div className="min-w-0 flex-1">
                      {/* The name without its crop prefix, which the crop label
                          below already says: "rice brown planthopper ·
                          advis..." was cut off on every row. */}
                      <div className="flex items-start justify-between gap-3">
                        <p className="min-w-0 text-[15px] font-semibold leading-snug">
                          {targetName(h.target, h.crop)}
                        </p>
                        <Pill tone={h.kind === 'inspection' ? 'sky' : 'leaf'} className="shrink-0 !py-0.5 capitalize">{h.kind}</Pill>
                      </div>
                      <p className="mt-0.5 text-[13px] text-soil-dark/70">
                        <span className="capitalize">{h.crop}</span>
                        {' · '}{h.districts.length > 0 ? h.districts.join(', ') : 'every district'}
                        {' · '}{shortDate(h.issued_at)}
                        {h.level === 'high' && <span className="text-ember"> · high</span>}
                      </p>
                      {h.note && (
                        <p className="mt-1.5 line-clamp-2 rounded-xl bg-[#f8f6f0] px-2.5 py-1.5 text-[13px] leading-snug text-soil-dark/80">
                          {h.note}
                        </p>
                      )}
                      <div className="mt-2 flex items-center gap-2">
                        <div className="flex-1 h-1 rounded-full bg-soil-dark/[0.07]" aria-hidden>
                          <span className="block h-full rounded-full bg-leaf" style={{ width: `${checked * 100}%` }} />
                        </div>
                        <span className="shrink-0 text-[12px] tabular-nums text-soil-dark/70">
                          {h.inspected === 0
                            ? <>{many(h.farms, 'farm')} · <span className="text-ember">none checked yet</span></>
                            : <>{h.inspected} of {many(h.farms, 'farm')} checked{h.found > 0 && <span className="text-ember font-medium"> · {h.found} found it</span>}</>}
                        </span>
                      </div>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          {/* Five, so the list ends about where the form beside it does. All
              eight left a column of empty page under the form. */}
          {history.data && history.data.length > 5 && (
            <button type="button" onClick={() => setAllSent((v) => !v)}
              className="mt-2 text-[14px] font-semibold text-leaf-deep hover:underline underline-offset-2">
              {allSent ? 'Show fewer' : `Show all ${history.data.length}`}
            </button>
          )}
        </Card>
      </div>
      </div>

      {/* Full width: seven columns of what is building, and the one table on
          this page that needs the room. In the side column it squeezed until
          its own headers ran together. */}
      <Panel q={outlook} rows={6}>{(rows) => <OutlookPanel rows={rows} onDraft={draftFrom} />}</Panel>
    </>
  )
}

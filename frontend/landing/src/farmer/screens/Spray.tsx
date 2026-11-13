import { useEffect, useRef, useState } from 'react'
import { Ban, FlaskConical, HelpCircle, Info, Leaf, Loader2, Search, ShieldCheck, Sparkles, SprayCan } from 'lucide-react'
import { api } from '../../api/client'
import type { LabelVerdict } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { ErrorBox, ListenButton, VoiceButton } from '../../ui/kit'
import DemoNotice, { useReadOnlyFarm } from '../components/DemoNotice'
import { useFarmer } from '../FarmerContext'
import SprayTimes from '../components/SprayTimes'
import { PANEL } from '../tokens'

const QUICK = ['Mancozeb', 'Copper oxychloride', 'Emamectin', 'Tricyclazole', 'Chlorantraniliprole', 'Glyphosate']

export default function Spray() {
  const { farmId, lang, t } = useFarmer()
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [v, setV] = useState<LabelVerdict | null>(null)
  // The AI note loads after the verdict: 'loading' | a sentence | 'none' (asked, nothing usable came back).
  const [note, setNote] = useState<string | null>(null)
  const asked = useRef(0) // a note that arrives after a newer check is dropped
  const [error, setError] = useState<Error | null>(null)
  const home = useAsync(() => api.home(farmId!, lang), [farmId, lang], ['home', farmId!, lang].join(':'))
  const weather = useAsync(() => api.weather(farmId!, lang), [farmId, lang], ['weather', farmId!, lang].join(':'))
  const readOnly = useReadOnlyFarm() !== null
  const [logged, setLogged] = useState<string | null>(null)
  const logSpray = async () => {
    const r = await api.logSpray(farmId!, v?.product ?? (q.trim() || null), lang)
    const c = r.check
    setLogged(c && c.status !== 'good' ? `${t(`spray_${c.status}`)} — ${c.reasons_text ?? ''}. ${t('sprayLogged')}` : t('sprayLogged'))
  }
  const current = home.data?.problems.find((p) => p.status === 'open' && p.name)

  // Language switched with a verdict on screen: check the same product again,
  // so the verdict and the AI note come back in the new language.
  const checked = useRef<string | null>(null)
  useEffect(() => {
    if (checked.current) void check(checked.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang])

  const check = async (text = q) => {
    if (!text.trim()) return
    setBusy(true)
    setError(null)
    try {
      const id = ++asked.current
      checked.current = text.trim()
      const verdict = await api.labelCheck(farmId!, text.trim(), lang)
      if (id !== asked.current) return
      setV(verdict)
      setNote(verdict.note_available ? 'loading' : null)
      if (verdict.note_available) {
        api.labelNote(farmId!, text.trim(), lang)
          .then((r) => id === asked.current && setNote(r.suggestion ?? 'none'))
          .catch(() => id === asked.current && setNote('none'))
      }
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }

  const waiting = v?.tone === 'unknown' && note === 'loading'

  // The answer this screen gives is only worth having when it is about a real
  // field: whether a product suits *your* crop, against *your* diagnosis, at a
  // dose for *your* plot. On the shared demonstration field there is no such
  // crop and no such diagnosis, so a verdict here would be a guess wearing the
  // clothes of advice — and this is the screen where a wrong answer is bought
  // at the counter and sprayed. The camera and the live check already stop
  // here; this was the one that did not.
  if (readOnly) return <DemoNotice />

  const tone = v ? TONE[v.tone === 'stop' ? 'stop' : v.tone === 'unknown' ? 'unknown' : 'ok'] : null

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
      <div className="min-w-0 space-y-6">
        <section className={`${PANEL} p-5 lg:p-6`}>
          {/* What the product is being checked against: the field's own open problem. */}
          <div className="flex items-center gap-3 rounded-[20px] bg-[#f5f7f1] p-2.5">
            <span className="h-14 w-14 shrink-0 overflow-hidden rounded-2xl bg-[#e3efd9]">
              {current?.image_url
                ? <img src={current.image_url} alt="" className="h-full w-full object-cover" />
                : <span className="flex h-full w-full items-center justify-center text-[#2f6a39]"><Leaf className="h-6 w-6" aria-hidden /></span>}
            </span>
            <span className="min-w-0">
              <span className="block text-[13px] text-soil-dark/75">{t('forProblem')}</span>
              <span className="block truncate text-[16px] font-semibold">
                {current?.name ?? (home.data ? t('noDiagnosisYet') : '…')}
              </span>
            </span>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              check()
            }}
            className="mt-5"
          >
            <label className="block text-[17px] font-semibold" htmlFor="spray-product">{t('sprayAsk')}</label>
            <div className="mt-3 flex gap-2">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-soil-dark/50" aria-hidden />
                <input
                  id="spray-product"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder={t('productName')}
                  className="min-h-[56px] w-full rounded-full bg-[#f5f7f1] pl-12 pr-4 text-[16px] ring-1 ring-soil-dark/10 placeholder:text-soil-dark/55 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#4b8b3b]"
                />
              </div>
              <VoiceButton lang={lang} label={t('speak')} recordingLabel={t('recording')} onText={(txt) => {
                setQ(txt)
                check(txt)
              }} />
            </div>
            <button type="submit" disabled={busy || !q.trim()}
              className="mt-3 flex min-h-[56px] w-full items-center justify-center gap-2 rounded-full bg-[#2f6a39] text-[17px] font-semibold text-white shadow-[0_12px_24px_-14px_rgba(29,74,44,0.8)] transition-colors hover:bg-[#2a5f33] disabled:opacity-50 disabled:shadow-none">
              {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <FlaskConical className="h-5 w-5" aria-hidden />}
              {t('check')}
            </button>
          </form>

          <p className="mt-5 text-[14px] text-soil-dark/75">{t('sprayCommon')}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {QUICK.map((p) => (
              <button key={p} onClick={() => {
                setQ(p)
                check(p)
              }} className="min-h-[40px] rounded-full bg-white px-4 text-[14px] font-medium ring-1 ring-soil-dark/15 transition-colors hover:bg-[#f5f7f1]">
                {p}
              </button>
            ))}
          </div>
        </section>

        {error && <ErrorBox error={error} />}

        {/* An unknown product: the AI note is the useful part, so the card waits
            for it and both appear together. A veto never waits. */}
        {waiting && (
          <section className={`${PANEL} flex items-center gap-3 p-5 text-[15px] text-soil-dark/75 animate-fadein`}>
            <Loader2 className="h-5 w-5 shrink-0 animate-spin text-ochre" />
            {t('aiNoteLoading')}
          </section>
        )}

        {v && tone && !waiting && (
          <section className={`rounded-[28px] p-5 animate-fadein lg:p-6 ${tone.box}`}>
            <div className="flex items-start gap-3">
              <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl ${tone.icon}`}>
                {v.tone === 'stop' ? <Ban className="h-7 w-7" /> : v.tone === 'unknown' ? <HelpCircle className="h-7 w-7" /> : <ShieldCheck className="h-7 w-7" />}
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="text-[22px] font-semibold leading-tight">
                  {v.title ?? (v.tone === 'stop' ? t('vetoTitle') : v.tone === 'unknown' ? t('unknownTitle') : t('noObjectionTitle'))}
                </h2>
                {v.product && <p className={`mt-1 text-[14px] ${tone.sub}`}>{v.product}</p>}
              </div>
              <ListenButton text={v.message} lang={lang} label={t('listen')} stopLabel={t('stop')} compact tone={v.tone === 'stop' ? 'light' : 'dark'} />
            </div>
            <p className="mt-4 text-[16px] leading-relaxed">{v.message}</p>
            {note && (
              <div className={`mt-4 rounded-[20px] p-4 ${v.tone === 'stop' ? 'bg-white/10' : 'bg-white/80'}`}>
                <p className={`flex items-center gap-1.5 text-[13px] font-semibold ${tone.sub}`}>
                  <Sparkles className="h-4 w-4" aria-hidden /> {t('aiNote')}
                </p>
                {note === 'loading' ? (
                  <p className={`mt-1.5 flex items-center gap-2 text-[14px] ${tone.sub}`}>
                    <Loader2 className="h-4 w-4 animate-spin" /> {t('aiNoteLoading')}
                  </p>
                ) : note === 'none' ? (
                  <p className={`mt-1.5 text-[14px] ${tone.sub}`}>{t('aiNoteNone')}</p>
                ) : (
                  <p className="mt-1.5 text-[15px] leading-snug">{note}</p>
                )}
              </div>
            )}
            {!v.is_veto && (
              logged
                ? <p className="mt-4 rounded-[20px] bg-white/80 p-3.5 text-[15px] text-leaf-deep">{logged}</p>
                : <button onClick={logSpray}
                    className="mt-4 flex min-h-[52px] w-full items-center justify-center gap-2 rounded-full bg-[#2f6a39] text-[16px] font-semibold text-white hover:bg-[#2a5f33]">
                    <SprayCan className="h-5 w-5" /> {t('sprayingNow')}
                  </button>
            )}
          </section>
        )}
      </div>

      <aside className="min-w-0 space-y-6">
        {weather.data && <SprayTimes v={weather.data} toCheck={false} />}
        <section className={`${PANEL} flex items-start gap-3 p-5`}>
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#e3efd9] text-[#2f6a39]">
            <Info className="h-6 w-6" aria-hidden />
          </span>
          <p className="text-[15px] leading-relaxed text-soil-dark/85">{t('neverSafeNote')}</p>
        </section>
      </aside>
    </div>
  )
}

/** How a verdict looks: a refusal is the loudest thing on the screen. */
const TONE = {
  stop: { box: 'bg-[#9a2f17] text-white', icon: 'bg-white/15 text-white', sub: 'text-white/80' },
  unknown: { box: 'bg-[#fbf0dc] text-soil-dark ring-1 ring-ochre/30', icon: 'bg-[#f6e2bb] text-[#8a5a17]', sub: 'text-soil-dark/70' },
  ok: { box: 'bg-white text-soil-dark ring-2 ring-[#4b8b3b]/30', icon: 'bg-[#e3efd9] text-[#2f6a39]', sub: 'text-soil-dark/70' },
} as const

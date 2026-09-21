import { useRef, useState } from 'react'
import { Ban, FlaskConical, HelpCircle, Info, Loader2, ShieldCheck, Sparkles, SprayCan } from 'lucide-react'
import { api } from '../../api/client'
import type { LabelVerdict } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { ErrorBox, ListenButton, VoiceButton } from '../../ui/kit'
import { useFarmer } from '../FarmerContext'

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
  const [logged, setLogged] = useState<string | null>(null)
  const logSpray = async () => {
    const r = await api.logSpray(farmId!, v?.product ?? (q.trim() || null), lang)
    const c = r.check
    setLogged(c && c.status !== 'good' ? `${t(`spray_${c.status}`)} — ${c.reasons_text ?? ''}. ${t('sprayLogged')}` : t('sprayLogged'))
  }
  const now = weather.data?.spray.now
  const best = weather.data?.spray.windows[0]
  const current = home.data?.problems.find((p) => p.status === 'open' && p.name)

  const check = async (text = q) => {
    if (!text.trim()) return
    setBusy(true)
    setError(null)
    try {
      const id = ++asked.current
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

  return (
    <div className="space-y-5">
      <div>
        <FlaskConical className="w-8 h-8 text-ochre" />
        <h1 className="mt-2 font-instrument-serif text-3xl leading-tight">{t('sprayTitle')}</h1>
        <p className="mt-1 text-sm text-soil-dark/60">{t('spraySub')}</p>
      </div>

      {now && (
        <div className={`rounded-2xl p-3 flex gap-3 items-start ${now.status === 'good' ? 'bg-leaf/10 text-leaf-deep' : now.status === 'caution' ? 'bg-ochre/10 text-[#8a5a17]' : 'bg-ember/10 text-ember'}`}>
          <SprayCan className="w-5 h-5 shrink-0 mt-0.5" />
          <p className="text-sm">
            <span className="font-semibold">{t(`spray_${now.status}`)}</span>
            {weather.data?.spray.reasons_text && <span className="block text-xs opacity-80">{weather.data.spray.reasons_text}</span>}
            <span className="block text-xs mt-0.5 opacity-80">
              {best ? t('sprayBest').replace('{when}', `${best.start.slice(11, 16)}–${best.end.slice(11, 16)}`) : t('sprayNoneShort')}
            </span>
          </p>
        </div>
      )}

      <p className="text-xs rounded-xl bg-white border border-soil-dark/10 px-3 py-2">
        <span className="text-soil-dark/50">{t('forProblem')}: </span>
        <span className="font-medium">{current?.name ?? t('noDiagnosisYet')}</span>
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          check()
        }}
        className="space-y-2"
      >
        <div className="flex gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('productName')}
            className="flex-1 min-w-0 min-h-[48px] rounded-xl border border-soil-dark/20 px-3 bg-white text-sm focus:outline-none focus:border-leaf"
          />
          <VoiceButton lang={lang} label={t('speak')} recordingLabel={t('recording')} onText={(txt) => {
            setQ(txt)
            check(txt)
          }} />
        </div>
        <button type="submit" disabled={busy || !q.trim()} className="w-full min-h-[48px] rounded-full bg-leaf-deep text-cream text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-2">
          {busy && <Loader2 className="w-4 h-4 animate-spin" />}
          {t('check')}
        </button>
      </form>

      <div className="flex flex-wrap gap-1.5">
        {QUICK.map((p) => (
          <button key={p} onClick={() => {
            setQ(p)
            check(p)
          }} className="px-3 py-1.5 rounded-full bg-white border border-soil-dark/15 text-xs">
            {p}
          </button>
        ))}
      </div>

      {error && <ErrorBox error={error} />}

      {v && (
        <section className={`rounded-2xl p-5 animate-fadein ${
          v.tone === 'stop' ? 'bg-ember text-cream'
            : v.tone === 'unknown' ? 'bg-ochre/15 border-2 border-ochre/50'
            : 'bg-white border-2 border-leaf/40'}`}>
          <div className="flex items-start justify-between gap-3">
            <p className="flex items-center gap-2 text-xl font-semibold">
              {v.tone === 'stop' ? <Ban className="w-6 h-6" />
                : v.tone === 'unknown' ? <HelpCircle className="w-6 h-6 text-[#8a5a17]" />
                : <ShieldCheck className="w-6 h-6 text-leaf" />}
              {v.tone === 'stop' ? t('vetoTitle') : v.tone === 'unknown' ? t('unknownTitle') : t('noObjectionTitle')}
            </p>
            <ListenButton text={v.message} lang={lang} label={t('listen')} stopLabel={t('stop')} compact />
          </div>
          {v.product && <p className={`mt-1 text-xs ${v.tone === 'stop' ? 'text-cream/80' : 'text-soil-dark/60'}`}>{v.product}</p>}
          <p className="mt-3 text-[15px] leading-snug">{v.message}</p>
          {note && (
            <div className="mt-3 rounded-xl bg-white/70 border border-soil-dark/10 p-3">
              <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-soil-dark/45">
                <Sparkles className="w-3.5 h-3.5" /> {t('aiNote')}
              </p>
              {note === 'loading' ? (
                <p className="mt-1 flex items-center gap-2 text-[13px] text-soil-dark/55">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> {t('aiNoteLoading')}
                </p>
              ) : note === 'none' ? (
                <p className="mt-1 text-[13px] text-soil-dark/55">{t('aiNoteNone')}</p>
              ) : (
                <p className="mt-1 text-[14px] leading-snug">{note}</p>
              )}
            </div>
          )}
          {!v.is_veto && (
            logged
              ? <p className="mt-3 text-sm rounded-xl bg-leaf/10 text-leaf-deep p-2.5">{logged}</p>
              : <button onClick={logSpray} className="mt-3 w-full min-h-[44px] rounded-full bg-leaf-deep text-cream text-sm font-medium flex items-center justify-center gap-2">
                  <SprayCan className="w-4 h-4" /> {t('sprayingNow')}
                </button>
          )}
        </section>
      )}

      <p className="flex gap-2 text-xs text-soil-dark/60">
        <Info className="w-4 h-4 shrink-0" />
        {t('neverSafeNote')}
      </p>
    </div>
  )
}

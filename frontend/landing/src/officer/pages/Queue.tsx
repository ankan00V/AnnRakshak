import { useMemo, useState } from 'react'
import { CheckSquare, Filter, Loader2, Search, Square, Timer, Users, X } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { CaseQuery } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox } from '../../ui/kit'
import { CaseRow, CaseView, QueueSkeleton } from '../../expert/ExpertConsole'

const CROPS = ['rice', 'maize', 'cotton', 'soybean']
const SLA_HOURS = 24

/** The queue, inside the console rather than in a separate app.
 *
 *  An officer narrows it the way they actually would — my desk, this district,
 *  this crop, only what is overdue — and moves a morning's triage in one press
 *  instead of opening twenty cases to hand each one on. Every filter lives in
 *  the URL, so the tiles on Today and the district table link straight into a
 *  filtered queue. */
export default function Queue() {
  const [params, setParams] = useSearchParams()
  const [selected, setSelected] = useState<number | null>(null)
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [said, setSaid] = useState<string | null>(null)

  const query: CaseQuery = useMemo(() => ({
    status: (params.get('status') as CaseQuery['status']) ?? 'open',
    scope: (params.get('scope') as CaseQuery['scope']) ?? 'all',
    district: params.get('district') ?? undefined,
    crop: params.get('crop') ?? undefined,
    target: params.get('target') ?? undefined,
    overdue: params.get('overdue') === '1',
    q_text: params.get('q') ?? undefined,
    sort: (params.get('sort') as CaseQuery['sort']) ?? 'oldest',
  }), [params])

  const key = JSON.stringify(query)
  const list = useAsync(() => api.cases(query), [key])
  const officers = useAsync(() => api.officers(query.district), [query.district])

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params)
    if (v === null || v === '') next.delete(k)
    else next.set(k, v)
    setParams(next, { replace: true })
    setPicked(new Set())
    setSaid(null)
  }

  const rows = list.data ?? []
  const districts = useMemo(
    () => [...new Set(rows.map((c) => c.district))].sort(), [rows])

  const toggle = (id: number) => setPicked((s) => {
    const next = new Set(s)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const move = async (toUserId: number | null) => {
    setBusy(true)
    try {
      const r = await api.bulkAssign([...picked], toUserId)
      setSaid(`${r.moved} case${r.moved === 1 ? '' : 's'} moved${r.skipped ? `, ${r.skipped} skipped` : ''}.`)
      setPicked(new Set())
      list.reload()
    } finally {
      setBusy(false)
    }
  }

  const activeFilters = ['district', 'crop', 'target', 'overdue', 'q'].filter((k) => params.get(k))

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(320px,400px)_1fr] items-start">
      <div className="space-y-3">
        <Card className="p-3 space-y-3">
          <div className="flex rounded-full bg-cream/60 p-0.5 text-xs">
            {([['all', 'All'], ['mine', 'My desk'], ['unassigned', 'Unassigned']] as const).map(([k, label]) => (
              <button key={k} onClick={() => set('scope', k)}
                className={`flex-1 rounded-full py-1.5 font-medium ${query.scope === k ? 'bg-leaf-deep text-cream' : 'text-soil-dark/60'}`}>
                {label}
              </button>
            ))}
          </div>

          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-soil-dark/40" />
            <input value={params.get('q') ?? ''} onChange={(e) => set('q', e.target.value)}
              placeholder="Farmer, village or district"
              className="w-full min-h-[38px] rounded-xl border border-soil-dark/15 bg-cream/40 pl-9 pr-3 text-sm" />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <select value={params.get('district') ?? ''} onChange={(e) => set('district', e.target.value)}
              className="min-h-[36px] rounded-xl border border-soil-dark/15 bg-cream/40 px-2 text-xs">
              <option value="">Every district</option>
              {districts.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
            <select value={params.get('crop') ?? ''} onChange={(e) => set('crop', e.target.value)}
              className="min-h-[36px] rounded-xl border border-soil-dark/15 bg-cream/40 px-2 text-xs">
              <option value="">Every crop</option>
              {CROPS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div className="flex items-center justify-between gap-2">
            <button onClick={() => set('overdue', query.overdue ? null : '1')}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium border ${
                query.overdue ? 'bg-ember/10 text-ember border-ember/30' : 'border-soil-dark/15 text-soil-dark/70'}`}>
              <Timer className="w-3.5 h-3.5" /> Past {SLA_HOURS} h
            </button>
            <select value={params.get('status') ?? 'open'} onChange={(e) => set('status', e.target.value)}
              className="min-h-[32px] rounded-full border border-soil-dark/15 bg-cream/40 px-2.5 text-xs">
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
              <option value="all">All</option>
            </select>
          </div>

          {activeFilters.length > 0 && (
            <button onClick={() => { setParams(new URLSearchParams(), { replace: true }); setPicked(new Set()) }}
              className="flex items-center gap-1 text-xs text-soil-dark/60 hover:text-soil-dark">
              <X className="w-3 h-3" /> Clear {activeFilters.length} filter{activeFilters.length === 1 ? '' : 's'}
            </button>
          )}
        </Card>

        {picked.size > 0 && (
          <Card className="p-3 border-leaf/40 bg-leaf/5">
            <p className="text-xs font-medium flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" /> {picked.size} selected
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button onClick={() => move(null)} disabled={busy}
                className="rounded-full bg-leaf-deep text-cream text-xs font-medium px-3 py-1.5 disabled:opacity-60 flex items-center gap-1.5">
                {busy && <Loader2 className="w-3 h-3 animate-spin" />} Route to whoever is freest
              </button>
              {(officers.data ?? []).slice(0, 3).map((o) => (
                <button key={o.user_id} onClick={() => move(o.user_id)} disabled={busy}
                  className="rounded-full border border-soil-dark/20 text-xs px-3 py-1.5 disabled:opacity-60">
                  → {o.name} <span className="text-soil-dark/50">({o.open_cases})</span>
                </button>
              ))}
            </div>
          </Card>
        )}

        {said && <p className="px-1 text-xs text-leaf-deep">{said}</p>}

        <div className="flex items-center justify-between px-1">
          <span className="text-xs text-soil-dark/60 flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5" />
            {list.data ? `${rows.length} case${rows.length === 1 ? '' : 's'}` : 'Loading…'}
          </span>
          {rows.length > 0 && (
            <button onClick={() => setPicked(picked.size === rows.length ? new Set() : new Set(rows.map((c) => c.id)))}
              className="text-xs text-soil-dark/60 hover:text-soil-dark flex items-center gap-1">
              {picked.size === rows.length ? <CheckSquare className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
              Select all
            </button>
          )}
        </div>

        {list.error && <ErrorBox error={list.error} onRetry={list.reload} />}
        {list.loading && !list.data && <QueueSkeleton />}
        {list.data && rows.length === 0 && (
          <Card className="p-6 text-center text-sm text-soil-dark/60">
            Nothing matches. {activeFilters.length > 0 ? 'Try clearing a filter.' : 'The queue is clear.'}
          </Card>
        )}

        <ul className="space-y-2">
          {rows.map((c) => (
            <li key={c.id} className="flex items-start gap-2">
              <button onClick={() => toggle(c.id)} aria-label={`Select case ${c.id}`}
                className="mt-4 shrink-0 text-soil-dark/40 hover:text-leaf-deep">
                {picked.has(c.id) ? <CheckSquare className="w-4 h-4 text-leaf-deep" /> : <Square className="w-4 h-4" />}
              </button>
              <span className="flex-1 min-w-0">
                <CaseRow c={c} active={selected === c.id} onClick={() => setSelected(c.id)} />
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="lg:sticky lg:top-4">
        {selected === null ? (
          <Card className="p-10 text-center">
            <p className="font-instrument-serif text-2xl">Pick a case</p>
            <p className="mt-1 text-sm text-soil-dark/60 max-w-md mx-auto">
              It arrives pre-packed: photos, the model's ranked guesses, the farmer's field answers,
              trap counts, the field's greenness and the alerts it has already had.
            </p>
          </Card>
        ) : (
          <CaseView id={selected} onBack={() => setSelected(null)} onResolved={() => { list.reload() }} />
        )}
      </div>
    </div>
  )
}


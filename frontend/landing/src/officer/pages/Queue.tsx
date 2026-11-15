import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, ArrowRight, ArrowUpDown, Bell, BookmarkPlus, CheckSquare, Clock, Filter, Keyboard, Loader2, Search, Square, Timer, Users, X,
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { CaseBrief, CaseListItem, CaseQuery } from '../../api/types'
import { useAsync } from '../../lib/hooks'
import { Card, ErrorBox } from '../../ui/kit'
import { useToast } from '../../ui/Toast'
import { many, PageHead } from '../panels'
import { useAuth } from '../../auth/AuthContext'
import { CaseView, QueueSkeleton, reasonText, RespondBy } from '../../expert/ExpertConsole'

const VIEWS_KEY = 'ar.officer.views'
const POLL_MS = 30000

type SavedView = { name: string; query: string }

function savedViews(): SavedView[] {
  try {
    return JSON.parse(localStorage.getItem(VIEWS_KEY) || '[]') as SavedView[]
  } catch {
    return []
  }
}

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
  const [views, setViews] = useState<SavedView[]>(savedViews)
  const [fresh, setFresh] = useState(0)
  const [showKeys, setShowKeys] = useState(false)
  const { say, complain } = useToast()
  const { me } = useAuth()
  // Moving somebody else's cases is a supervisor's call, so an ordinary desk
  // gets "take it" rather than a bulk control the server declines. Taking a
  // case onto your own desk is everybody's.
  const cursor = useRef(0)

  const query: CaseQuery = useMemo(() => ({
    status: (params.get('status') as CaseQuery['status']) ?? 'open',
    scope: (params.get('scope') as CaseQuery['scope']) ?? 'all',
    district: params.get('district') ?? undefined,
    crop: params.get('crop') ?? undefined,
    target: params.get('target') ?? undefined,
    overdue: params.get('overdue') === '1',
    // Without this the "Set aside" button wrote a URL parameter nobody read,
    // so a snoozed case could be hidden and never looked at again.
    snoozed: params.get('snoozed') === '1',
    q_text: params.get('q') ?? undefined,
    sort: (params.get('sort') as CaseQuery['sort']) ?? 'oldest',
  }), [params])

  const key = JSON.stringify(query)
  const list = useAsync(() => api.cases(query), [key])
  // Only a supervisor may place a case by name, so only a supervisor asks
  // who is on the books.
  const mayMoveOthers = me?.profile?.supervisor === true
  const officers = useAsync(
    () => (mayMoveOthers ? api.officers(query.district) : Promise.resolve([])),
    [query.district, mayMoveOthers])

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params)
    if (v === null || v === '') next.delete(k)
    else next.set(k, v)
    setParams(next, { replace: true })
    setPicked(new Set())
  }

  // A new [] every render restarts the poll timer and re-binds the keys below.
  const rows = useMemo(() => list.data ?? [], [list.data])
  const districts = useMemo(
    () => [...new Set(rows.map((c) => c.district))].sort(), [rows])

  const toggle = (id: number) => setPicked((s) => {
    const next = new Set(s)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const move = async (toUserId: number | null) => {
    const ids = [...picked]
    const before = new Map(rows.filter((c) => picked.has(c.id)).map((c) => [c.id, c.assigned_to]))
    setBusy(true)
    try {
      const r = await api.bulkAssign(ids, toUserId)
      setPicked(new Set())
      list.reload()
      say(`${r.moved} case${r.moved === 1 ? '' : 's'} moved${r.skipped ? `, ${r.skipped} skipped` : ''}.`,
        async () => {
          // Put each one back where it was, one call per previous holder.
          const groups = new Map<number | null, number[]>()
          for (const [id, holder] of before) groups.set(holder, [...(groups.get(holder) ?? []), id])
          for (const [holder, list_] of groups) await api.bulkAssign(list_, holder)
          list.reload()
        })
    } catch (e) {
      complain((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const snooze = useCallback(async (id: number) => {
    try {
      await api.snoozeCase(id, 24)
      list.reload()
      say('Set aside until tomorrow.', async () => { await api.wakeCase(id); list.reload() })
    } catch (e) {
      complain((e as Error).message)
    }
  }, [list, say, complain])

  const takeIt = useCallback(async (id: number) => {
    try {
      const me = await api.me()
      await api.reassignCase(id, me.id)
      list.reload()
      say('On your desk.')
    } catch (e) {
      complain((e as Error).message)
    }
  }, [list, say, complain])

  // A case handed on is no longer this desk's to read, so there is nothing
  // left to show in the pane: close it and say where the case went. It used to
  // ask the server for the case again, which answered "case not found" to the
  // officer who had just passed it to the right person.
  const handedOff = useCallback((to: CaseBrief) => {
    list.reload()
    if (to.assigned_to !== null && to.assigned_to === me?.id) {
      // One officer covers this district, so the router had nowhere to send it
      // and gave it back. Saying "handed on" there would be a lie.
      say(`Nobody else covers this district — case #${to.id} is still on your desk.`)
      return
    }
    setSelected(null)
    say(to.assigned_name
      ? `Case #${to.id} is now with ${to.assigned_name}.`
      : `Case #${to.id} is back in the queue — no officer covers that district yet.`)
  }, [list, me, say])

  const activeFilters = ['district', 'crop', 'target', 'overdue', 'snoozed', 'q'].filter((k) => params.get(k))

  // A queue that never changes while you watch it looks broken. Ask quietly,
  // only while the tab is in front of somebody.
  const newest = rows[rows.length - 1]?.id ?? 0
  useEffect(() => {
    if (!newest) return
    const tick = async () => {
      if (document.hidden) return
      try {
        const { new_cases } = await api.newCasesSince(newest)
        setFresh(new_cases)
      } catch { /* a queue that cannot count is still a queue */ }
    }
    const id = setInterval(tick, POLL_MS)
    return () => clearInterval(id)
  }, [newest])

  // Triage is a keyboard job: j and k walk the list, a takes the case, s sets
  // it aside, x picks it for a bulk move, and ? says so.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (el && ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const at = Math.max(0, rows.findIndex((c) => c.id === selected))
      const go = (i: number) => {
        const next = rows[Math.min(Math.max(i, 0), rows.length - 1)]
        if (next) {
          setSelected(next.id)
          cursor.current = rows.indexOf(next)
        }
      }
      if (e.key === 'j') { e.preventDefault(); go(selected == null ? 0 : at + 1) }
      else if (e.key === 'k') { e.preventDefault(); go(selected == null ? 0 : at - 1) }
      else if (e.key === '?') { e.preventDefault(); setShowKeys((v) => !v) }
      else if (e.key === 'Escape') setSelected(null)
      else if (selected != null && e.key === 'a') { e.preventDefault(); void takeIt(selected) }
      else if (selected != null && e.key === 's') { e.preventDefault(); void snooze(selected) }
      else if (selected != null && e.key === 'x') { e.preventDefault(); toggle(selected) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [rows, selected, takeIt, snooze])

  const saveView = () => {
    const name = window.prompt('Name this view', params.toString() ? 'My district, overdue' : 'Everything')
    if (!name) return
    const next = [...views.filter((v) => v.name !== name), { name, query: params.toString() }]
    setViews(next)
    try {
      localStorage.setItem(VIEWS_KEY, JSON.stringify(next))
    } catch { /* private mode: the view lasts this session */ }
    say(`Saved “${name}”.`)
  }

  const split = selected !== null

  const field = 'min-h-[44px] w-full rounded-2xl bg-[#f8f6f0] px-3.5 text-[14px] ring-1 ring-soil-dark/10 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#4b8b3b]'
  const chip = (on: boolean, tone = 'leaf') => `flex min-h-[44px] items-center justify-center gap-1.5 rounded-2xl px-4 text-[14px] font-medium ring-1 transition-colors ${
    on ? (tone === 'ember' ? 'bg-[#fdf0ed] text-[#b5381c] ring-[#b5381c]/30' : 'bg-[#e3efd9] text-leaf-deep ring-[#4b8b3b]/40') : 'bg-white text-soil-dark/80 ring-soil-dark/10 hover:bg-[#f8f6f0]'}`

  return (
    <>
      <PageHead title="Queue" purpose="Every case a farmer escalated, pre-packed: the photographs, the model's guesses, the farmer's own answers and the field's history.">
        <button onClick={() => setShowKeys((v) => !v)}
          className="flex min-h-[40px] items-center gap-2 rounded-full bg-white px-4 text-[13px] font-medium text-soil-dark/80 shadow-sm ring-1 ring-soil-dark/10 hover:bg-[#f8f6f0]">
          <Keyboard className="h-4 w-4" aria-hidden /> Shortcuts
        </button>
      </PageHead>
    <div className={`grid items-start gap-5 ${split ? 'lg:grid-cols-[minmax(340px,420px)_1fr]' : ''}`}>
      {/* With a case open, the list stays in view and scrolls on its own, so a
          long case does not leave an empty column beside it. */}
      <div className={`min-w-0 space-y-4 ${split ? 'no-scrollbar lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:pb-4' : ''}`}>
        <Card className="space-y-3 p-4 lg:p-5">
          <div className="grid grid-cols-3 gap-1 rounded-full bg-[#f1ede2] p-1">
            {([['all', 'All'], ['mine', 'My desk'], ['unassigned', 'Unassigned']] as const).map(([k, label]) => (
              <button key={k} onClick={() => set('scope', k)}
                className={`min-h-[40px] rounded-full text-[14px] font-semibold transition-colors ${
                  query.scope === k ? 'bg-[#1d4a2c] text-white shadow-sm' : 'text-soil-dark/70 hover:text-soil-dark'}`}>
                {label}{query.scope === k && list.data ? ` (${rows.length})` : ''}
              </button>
            ))}
          </div>

          <div className="relative">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-soil-dark/70" aria-hidden />
            <input value={params.get('q') ?? ''} onChange={(e) => set('q', e.target.value)}
              placeholder="Search by farmer, village or district" aria-label="Search cases"
              className={`${field} pl-10`} />
          </div>

          <div className={`grid gap-2 ${split ? 'grid-cols-2' : 'grid-cols-2 md:grid-cols-[1fr_1fr_auto_auto_auto]'}`}>
            <select value={params.get('district') ?? ''} onChange={(e) => set('district', e.target.value)} aria-label="District" className={field}>
              <option value="">Every district</option>
              {districts.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
            <select value={params.get('crop') ?? ''} onChange={(e) => set('crop', e.target.value)} aria-label="Crop" className={field}>
              <option value="">Every crop</option>
              {CROPS.map((c) => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
            </select>
            <button onClick={() => set('overdue', query.overdue ? null : '1')} className={chip(!!query.overdue, 'ember')}>
              <Timer className="h-4 w-4" aria-hidden /> Past {SLA_HOURS} h
            </button>
            <button onClick={() => set('sort', query.sort === 'newest' ? null : 'newest')} className={chip(query.sort === 'newest')}>
              <ArrowUpDown className="h-4 w-4" aria-hidden /> {query.sort === 'newest' ? 'Newest' : 'Oldest'}
            </button>
            <select value={params.get('status') ?? 'open'} onChange={(e) => set('status', e.target.value)} aria-label="Status" className={field}>
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
              <option value="all">All</option>
            </select>
          </div>

          {(activeFilters.length > 0 || views.length > 0) && (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {activeFilters.length > 0 && (
                <button onClick={() => { setParams(new URLSearchParams(), { replace: true }); setPicked(new Set()) }}
                  className="flex min-h-[34px] items-center gap-1 rounded-full bg-soil-dark/5 px-3 text-[13px] text-soil-dark/80 hover:bg-soil-dark/10">
                  <X className="h-3.5 w-3.5" /> Clear {many(activeFilters.length, 'filter')}
                </button>
              )}
              {views.map((v) => (
                <button key={v.name} onClick={() => { setParams(new URLSearchParams(v.query), { replace: true }) }}
                  className="min-h-[34px] rounded-full bg-white px-3 text-[13px] ring-1 ring-soil-dark/15 hover:ring-[#4b8b3b]/50">
                  {v.name}
                </button>
              ))}
              <button onClick={saveView}
                className="flex min-h-[34px] items-center gap-1 rounded-full px-2 text-[13px] text-soil-dark/70 hover:text-soil-dark">
                <BookmarkPlus className="h-4 w-4" /> Save this view
              </button>
            </div>
          )}
        </Card>

        {fresh > 0 && (
          <button onClick={() => { setFresh(0); list.reload() }}
            className="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-full bg-[#2f6a39] text-[14px] font-semibold text-white">
            <Bell className="h-4 w-4" /> {many(fresh, 'new case')} — show
          </button>
        )}

        {picked.size > 0 && (
          <Card className="bg-[#eef6ea] p-4">
            <p className="flex items-center gap-1.5 text-[14px] font-semibold">
              <Users className="h-4 w-4" /> {picked.size} selected
            </p>
            {mayMoveOthers ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <button onClick={() => move(null)} disabled={busy}
                  className="flex min-h-[38px] items-center gap-1.5 rounded-full bg-[#2f6a39] px-4 text-[13px] font-semibold text-white disabled:opacity-60">
                  {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Route to whoever is freest
                </button>
                {(officers.data ?? []).slice(0, 3).map((o) => (
                  <button key={o.user_id} onClick={() => move(o.user_id)} disabled={busy}
                    className="min-h-[38px] rounded-full bg-white px-4 text-[13px] ring-1 ring-soil-dark/15 disabled:opacity-60">
                    → {o.name} <span className="text-soil-dark/70">({o.open_cases})</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-[13px] text-soil-dark/75">
                Only a supervisor — the Agriculture Officer or the KVK scientist — can hand these to
                another desk. Open a case and press <span className="font-medium">Take it</span> to
                put it on yours.
              </p>
            )}
          </Card>
        )}

        {showKeys && (
          <Card className="space-y-1.5 p-4 text-[13px] text-soil-dark/80">
            <p><kbd className="font-semibold">j</kbd> / <kbd className="font-semibold">k</kbd> — next, previous case</p>
            <p><kbd className="font-semibold">a</kbd> — put it on my desk · <kbd className="font-semibold">s</kbd> — set aside until tomorrow</p>
            <p><kbd className="font-semibold">x</kbd> — pick for a bulk move · <kbd className="font-semibold">Esc</kbd> — close the case</p>
          </Card>
        )}

        <Card className="p-2 sm:p-3">
          <div className="flex items-center justify-between px-2 pb-2 pt-1">
            <span className="flex items-center gap-1.5 text-[14px] font-medium text-soil-dark/80">
              <Filter className="h-4 w-4" aria-hidden />
              {list.data ? many(rows.length, 'case') : 'Loading…'}
            </span>
            <span className="flex items-center gap-3">
              <button onClick={() => set('snoozed', params.get('snoozed') ? null : '1')}
                className={`flex items-center gap-1 text-[13px] ${params.get('snoozed') ? 'font-semibold text-[#9a6210]' : 'text-soil-dark/70 hover:text-soil-dark'}`}>
                <Clock className="h-4 w-4" /> Set aside
              </button>
              {rows.length > 0 && (
                <button onClick={() => setPicked(picked.size === rows.length ? new Set() : new Set(rows.map((c) => c.id)))}
                  className="flex items-center gap-1 text-[13px] text-soil-dark/70 hover:text-soil-dark">
                  {picked.size === rows.length ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4" />}
                  Select all
                </button>
              )}
            </span>
          </div>

          {list.error && <ErrorBox error={list.error} onRetry={list.reload} />}
          {list.loading && !list.data && <QueueSkeleton />}
          {list.data && rows.length === 0 && (
            <p className="m-2 rounded-2xl bg-[#f8f6f0] p-6 text-center text-[14px] text-soil-dark/75">
              Nothing matches. {activeFilters.length > 0 ? 'Try clearing a filter.' : 'The queue is clear.'}
            </p>
          )}

          <ul className="divide-y divide-soil-dark/[0.06]">
            {rows.map((c) => (
              <li key={c.id}>
                <QueueRow c={c} compact={split} active={selected === c.id} picked={picked.has(c.id)}
                  onPick={() => toggle(c.id)} onOpen={() => setSelected(c.id)} />
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {split && (
        <div className="min-w-0">
          <CaseView id={selected!} onBack={() => setSelected(null)} onHandedOff={handedOff}
            onResolved={() => { list.reload() }} />
        </div>
      )}
    </div>
    </>
  )
}

const RISK = {
  high: { cls: 'bg-[#fdf0ed] text-[#b5381c]', label: 'High risk' },
  medium: { cls: 'bg-[#fdf5e6] text-[#9a6210]', label: 'Moderate' },
  low: { cls: 'bg-[#eef6ea] text-[#2f6a39]', label: 'Low' },
} as const

/** "54 min ago", "3 h ago", "2 days ago". */
function ago(iso: string | null) {
  if (!iso) return ''
  const m = (Date.now() - new Date(iso).getTime()) / 6e4
  if (m < 60) return `${Math.max(1, Math.round(m))} min ago`
  if (m < 48 * 60) return `${Math.round(m / 60)} h ago`
  return `${Math.round(m / 1440)} days ago`
}

/** One case on the list: the photo, who and where, why it is here, how long it
 *  has waited, and the way into it. */
function QueueRow({ c, compact, active, picked, onPick, onOpen }: {
  c: CaseListItem; compact: boolean; active: boolean; picked: boolean; onPick: () => void; onOpen: () => void
}) {
  const risk = RISK[(c.severity as keyof typeof RISK)] ?? RISK.medium
  const hours = c.created_at ? (Date.now() - new Date(c.created_at).getTime()) / 3.6e6 : 0
  const late = c.status === 'open' && hours > SLA_HOURS
  return (
    <div className={`flex items-center gap-3 rounded-2xl px-2 py-2.5 transition-colors ${active ? 'bg-[#e3efd9]' : 'hover:bg-[#f8f6f0]'}`}>
      <button onClick={onPick} aria-label={`Select case ${c.id}`} aria-pressed={picked}
        className="shrink-0 text-soil-dark/70 hover:text-leaf-deep">
        {picked ? <CheckSquare className="h-5 w-5 text-leaf-deep" /> : <Square className="h-5 w-5" />}
      </button>
      <button onClick={onOpen} className="flex min-w-0 flex-1 items-center gap-3 text-left">
        <span className="h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-[#eef3e6]">
          {c.photo && <img src={c.photo} alt="" loading="lazy" className="h-full w-full object-cover" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-semibold">#{c.id} · {c.farmer_name}</span>
          <span className="block truncate text-[13px] text-soil-dark/70">
            <span className="capitalize">{c.crop}</span> · {c.district}
            {c.model_top ? ` · ${c.model_top.name} ${Math.round((c.model_top.confidence ?? 0) * 100)}%` : ''}
          </span>
          <span className="mt-1 flex flex-wrap gap-1.5">
            <span className="rounded-full bg-sky-50 px-2.5 py-0.5 text-[12px] font-medium text-sky-800">{reasonText(c.reason)}</span>
            <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-medium ${c.assigned_name ? 'bg-[#eef6ea] text-[#2f6a39]' : 'bg-[#fdf5e6] text-[#9a6210]'}`}>
              {c.assigned_name ?? 'Unassigned'}
            </span>
            <RespondBy c={c} />
          </span>
        </span>
      </button>
      {!compact && (
        <>
          <span className={`hidden w-24 shrink-0 text-right text-[13px] tabular-nums md:block ${late ? 'font-semibold text-[#b5381c]' : 'text-soil-dark/70'}`}>
            {ago(c.created_at)}
          </span>
          <span className={`hidden shrink-0 items-center gap-1 rounded-full px-3 py-1 text-[13px] font-semibold sm:inline-flex ${risk.cls}`}>
            {c.severity === 'high' && <AlertTriangle className="h-3.5 w-3.5" aria-hidden />}{risk.label}
          </span>
          <button onClick={onOpen}
            className="hidden min-h-[40px] shrink-0 items-center gap-1.5 rounded-full bg-[#1d4a2c] px-4 text-[14px] font-semibold text-white hover:bg-[#245a35] sm:flex">
            Review <ArrowRight className="h-4 w-4" aria-hidden />
          </button>
        </>
      )}
    </div>
  )
}

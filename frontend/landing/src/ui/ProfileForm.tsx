import { useState, type ReactNode } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { api } from '../api/client'
import type { Me } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Card, ErrorBox } from './kit'

/** One record, one screen, both roles.
 *
 *  A farmer and an officer give a page of details at sign-up and then had
 *  nowhere to read them back, let alone correct a village spelt wrong or a
 *  patch that has since grown. This is that page: it sends only the lines that
 *  changed, so saving one field cannot blank another.
 */
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[12px] font-medium text-soil-dark/70">{label}</span>
      {children}
      {hint && <span className="block mt-0.5 text-[11px] text-soil-dark/50">{hint}</span>}
    </label>
  )
}

export const input =
  'mt-1 w-full min-h-[44px] rounded-xl border border-soil-dark/20 bg-cream/50 px-3 text-sm focus:outline-none focus:border-leaf'

/** Locked lines: what the district office checked, which is not the holder's
 *  to rewrite. Shown, because a profile that hides them is harder to trust. */
export function Fixed({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <div className="rounded-xl bg-soil-dark/[0.04] px-3 py-2">
      <p className="text-[11px] text-soil-dark/50">{label}</p>
      <p className="text-sm">{value}</p>
    </div>
  )
}

export function useProfileSave() {
  const { update } = useAuth()
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const save = async (patch: Record<string, unknown>) => {
    setBusy(true)
    setError(null)
    setDone(false)
    try {
      update(await api.saveProfile(patch))
      setDone(true)
      window.setTimeout(() => setDone(false), 2500)
    } catch (e) {
      setError(e as Error)
    } finally {
      setBusy(false)
    }
  }
  return { save, busy, done, error }
}

export function SaveBar({ busy, done, error, onSave, label }: {
  busy: boolean; done: boolean; error: Error | null; onSave: () => void; label: string
}) {
  return (
    <>
      {error && <ErrorBox error={error} />}
      <div className="flex items-center gap-3">
        <button onClick={onSave} disabled={busy}
          className="min-h-[46px] px-5 rounded-full bg-leaf-deep text-cream text-sm font-semibold flex items-center gap-2 disabled:opacity-60">
          {busy && <Loader2 className="w-4 h-4 animate-spin" />}
          {label}
        </button>
        {done && (
          <span className="flex items-center gap-1.5 text-sm text-leaf-deep">
            <Check className="w-4 h-4" /> Saved
          </span>
        )}
      </div>
    </>
  )
}

export function ProfileCard({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <Card className="p-4 md:p-5 space-y-3">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {sub && <p className="text-xs text-soil-dark/60 mt-0.5">{sub}</p>}
      </div>
      {children}
    </Card>
  )
}

export type { Me }

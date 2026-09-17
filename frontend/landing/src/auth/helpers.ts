import type { Role } from '../api/types'

export const PHONE_RE = /^(?:\+?91[\s-]?|0)?[6-9]\d{9}$/
export const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/
export const phoneOk = (v: string) => PHONE_RE.test(v.replace(/[\s-]/g, ''))
export const emailOk = (v: string) => EMAIL_RE.test(v.trim())

/** Where each role lands after signing in. */
export const homeOf = (role: Role) => (role === 'expert' ? '/expert' : '/app')

/** A `next=` path from the query string, only if it stays on this site. */
export function safeNext(raw: string | null): string | null {
  return raw && raw.startsWith('/') && !raw.startsWith('//') ? raw : null
}

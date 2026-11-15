import type { Role } from '../api/types'

export const PHONE_RE = /^(?:\+?91[\s-]?|0)?[6-9]\d{9}$/
export const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/
export const phoneOk = (v: string) => PHONE_RE.test(v.replace(/[\s-]/g, ''))
export const emailOk = (v: string) => EMAIL_RE.test(v.trim())

/** Whether this server sends a farmer's sign-in code by SMS (`otp.sms` on
 *  /api/auth/options). When it does, a mobile number is all a farmer needs and
 *  the email is optional; when it does not, the code can only go by email.
 *  Read loosely, so an older server that never sent the flag means "no SMS". */
export const smsCodes = (options: unknown): boolean =>
  (options as { otp?: { sms?: boolean } } | null | undefined)?.otp?.sms === true

/** Whether a code that was just sent went by SMS. The server says which channel
 *  it really took: a farmer's SMS that failed falls back to their email. */
export const wentBySms = (sent: { channel: string } | null | undefined): boolean => sent?.channel === 'sms'

/** A farmer's mobile number as the screen shows it: +91 and the ten digits. */
export const showPhone = (v: string): string => `+91 ${v.replace(/\D/g, '').slice(-10)}`

/** Where each role lands after signing in. */
export const homeOf = (role: Role) => (role === 'expert' ? '/officer' : '/app')

/** A `next=` path from the query string, only if it stays on this site. */
export function safeNext(raw: string | null): string | null {
  return raw && raw.startsWith('/') && !raw.startsWith('//') ? raw : null
}

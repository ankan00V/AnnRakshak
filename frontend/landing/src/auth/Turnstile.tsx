import { useEffect, useRef, useState } from 'react'
import { useAsync } from '../lib/hooks'
import { api } from '../api/client'

/** Cloudflare's "are you a person" box, above the button that asks for a code.
 *
 *  The request for a one-time code is the thing worth protecting: it costs
 *  money and reaches a real inbox, and a script could work through a list of
 *  addresses at the rate limit. The widget is what makes that cost something.
 *
 *  The sitekey comes from the server, so taking the box off is a config change
 *  and not a deploy: no key, nothing rendered, and the form works as before.
 *  A token expires after a few minutes, so the widget refreshes itself and
 *  hands back a fresh one rather than letting a slow form submit a stale token.
 */

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => string
      remove: (id: string) => void
      reset: (id?: string) => void
    }
    onloadTurnstileCallback?: () => void
  }
}

const SCRIPT = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
let loading: Promise<void> | null = null

/** Load Cloudflare's script once, however many forms ask for it. */
function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve()
  if (loading) return loading
  loading = new Promise<void>((resolve, reject) => {
    const el = document.createElement('script')
    el.src = SCRIPT
    el.async = true
    el.defer = true
    el.onload = () => resolve()
    el.onerror = () => {
      loading = null
      reject(new Error('turnstile script blocked'))
    }
    document.head.appendChild(el)
  })
  return loading
}

export default function Turnstile({ onToken, lang }: {
  /** Called with a fresh token, and with null when it expires or errors. */
  onToken: (token: string | null) => void
  lang?: string
}) {
  const options = useAsync(() => api.authOptions('en'), [], 'auth-options')
  const sitekey = options.data?.turnstile_sitekey ?? null
  const box = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)
  // The widget is rendered once and lives on; the callback it was given may
  // not. The latest one goes in a ref so a token always reaches the current
  // form rather than tearing the box down on every parent render.
  const hand = useRef(onToken)
  useEffect(() => {
    hand.current = onToken
  }, [onToken])

  useEffect(() => {
    if (!sitekey || !box.current) return
    let widget: string | null = null
    let gone = false

    loadScript()
      .then(() => {
        if (gone || !box.current || !window.turnstile) return
        widget = window.turnstile.render(box.current, {
          sitekey,
          language: lang ?? 'auto',
          callback: (token: string) => hand.current(token),
          'expired-callback': () => hand.current(null),
          'error-callback': () => hand.current(null),
        })
      })
      .catch(() => {
        // Blocked by a network, an extension or a captive portal. The server
        // decides what to do about a missing token; the farmer is not left
        // looking at a box that never loads.
        if (!gone) {
          setFailed(true)
          hand.current(null)
        }
      })

    return () => {
      gone = true
      if (widget && window.turnstile) window.turnstile.remove(widget)
    }
  }, [sitekey, lang])

  if (!sitekey || failed) return null
  return <div ref={box} className="flex justify-center" data-testid="turnstile" />
}

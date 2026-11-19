import { Component, type ErrorInfo, type ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'
import BrandMark from './BrandMark'
import { makeT, savedLang } from '../lib/i18n'

/** The last thing between a bug and a white screen.
 *
 *  A render error anywhere in the tree unmounts the whole app: the farmer is
 *  left holding a blank phone in a field, with no way to tell whether it is the
 *  app, the signal or their own doing. This says which, in plain words, and
 *  offers the two things that actually help — try again, or go back to the
 *  start. The Kisan Call Centre number is there because a farmer who cannot get
 *  past this screen still has a question about their crop.
 */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // The console is where a developer looks; the user gets the card below.
    console.error('AnnRakshak crashed:', error, info.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    // Outside every provider, so the language comes from where the app keeps it.
    // A language whose strings had loaded shows in it; otherwise English.
    const t = makeT(savedLang())
    return (
      <div className="min-h-screen bg-cream text-soil-dark flex flex-col items-center justify-center px-6 text-center">
        <BrandMark size={44} />
        <h1 className="font-instrument-serif text-3xl mt-4">{t('crashTitle')}</h1>
        <p className="mt-2 text-sm text-soil-dark/70 max-w-sm">
          {t('crashBody')}
        </p>
        <div className="mt-6 flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => window.location.reload()}
            className="inline-flex items-center justify-center gap-2 min-h-[48px] px-6 rounded-full bg-leaf-deep text-cream text-sm font-semibold"
          >
            <RefreshCw className="w-4 h-4" />
            {t('crashRetry')}
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center min-h-[48px] px-6 rounded-full border border-soil-dark/20 text-sm font-medium"
          >
            {t('crashHome')}
          </a>
        </div>
        <a href="tel:18001801551" className="mt-8 text-xs text-soil-dark/60 underline underline-offset-2">
          {t('crashKcc')}
        </a>
      </div>
    )
  }
}

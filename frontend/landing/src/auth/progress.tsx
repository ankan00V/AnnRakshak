import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export interface Progress {
  step: number
  titles: string[]
}

/** One field of a farmer's sign-up, as it stands in the form. */
export interface DraftField {
  crop: string
  cropName: string
  /** Acres, as typed; empty while the box is empty. */
  area: string
  sowing: string
  irrigation: string
}

/** What a sign-up has collected so far, for the phone beside the form that
 *  shows the profile filling in. */
export interface Draft {
  role: 'farmer' | 'expert'
  name: string
  phone: string
  /** Farmer: village · district · state. Expert: the state they cover. */
  place: string
  fields: DraftField[]
  /** Expert: designation · organisation. */
  post?: string
  covers?: string[]
  crops?: string[]
}

const Ctx = createContext<{
  progress: Progress | null; publish: (p: Progress | null) => void
  draft: Draft | null; publishDraft: (d: Draft | null) => void
}>({ progress: null, publish: () => {}, draft: null, publishDraft: () => {} })

/** Where a stepped sign-up has got to, and what it holds. It is the form that
 *  knows both; the layout draws the step bar's neighbours and the preview
 *  phone — hence the one line of plumbing. */
export function ProgressProvider({ children }: { children: ReactNode }) {
  const [progress, setProgress] = useState<Progress | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  return <Ctx.Provider value={{ progress, publish: setProgress, draft, publishDraft: setDraft }}>{children}</Ctx.Provider>
}

export const useProgress = () => useContext(Ctx).progress
export const useDraft = () => useContext(Ctx).draft

export function usePublishProgress(step: number, titles: string[]) {
  const { publish } = useContext(Ctx)
  // The titles are rebuilt on every render; comparing them by value keeps the
  // effect from firing on each keystroke.
  const joined = titles.join('\u0000')
  useEffect(() => {
    publish({ step, titles: joined.split('\u0000') })
    return () => publish(null)
  }, [step, joined, publish])
}

/** Hands the form's current answers to the preview. Compared by value, so a
 *  render that changed nothing does not redraw the phone. */
export function usePublishDraft(draft: Draft) {
  const { publishDraft } = useContext(Ctx)
  const json = JSON.stringify(draft)
  useEffect(() => { publishDraft(JSON.parse(json) as Draft) }, [json, publishDraft])
  useEffect(() => () => publishDraft(null), [publishDraft])
}

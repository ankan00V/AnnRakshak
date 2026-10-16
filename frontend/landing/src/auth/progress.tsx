import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export interface Progress {
  step: number
  titles: string[]
}

const Ctx = createContext<{ progress: Progress | null; publish: (p: Progress | null) => void }>({
  progress: null,
  publish: () => {},
})

/** Where a stepped sign-up has got to. On a phone the form carries its own
 *  bar; on a laptop the side panel draws the whole walk, and it is the form
 *  that knows which step is open — hence the one line of plumbing. */
export function ProgressProvider({ children }: { children: ReactNode }) {
  const [progress, setProgress] = useState<Progress | null>(null)
  return <Ctx.Provider value={{ progress, publish: setProgress }}>{children}</Ctx.Provider>
}

export const useProgress = () => useContext(Ctx).progress

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

import { useEffect } from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { DiagnoseResult, GateOutcome } from '../../api/types'
import { FarmerProvider, useFarmer } from '../FarmerContext'
import Result from './Result'

// "Never a confident wrong answer" and "labelled stub" are the two promises
// this screen keeps. Advice belongs to one gate outcome only, and a stub must
// never look like a diagnosis.
vi.mock('../../api/client', async (orig) => {
  const real = await orig<typeof import('../../api/client')>()
  return { ...real, api: { ...real.api, farms: async () => [], problemResult: async () => ({}) } }
})

const result = (outcome: GateOutcome, over: Partial<DiagnoseResult> = {}): DiagnoseResult => ({
  problem_id: 1, image_url: null, is_stub: false, model_version: 'test',
  gate: {
    outcome, reason: 'OK', confidence: 0.91, threshold: 0.7,
    alternatives: [{ id: 'rice_blast', name: 'Rice blast', confidence: 0.91 }],
  },
  message: 'A message for this outcome.',
  clarify: { cue_id: 'c1', question: 'Are the spots spindle-shaped?', candidates: [] },
  advisory: {
    target: 'rice_blast', name: 'Rice blast', signature: 'Spindle lesions with grey centres',
    what_to_check: 'Check the upper leaves of 10 plants.', what_to_avoid: [],
    ladder: [], expert_trigger: '', citations: [], icar_options: [],
  },
  ...over,
} as unknown as DiagnoseResult)

function Seed({ r }: { r: DiagnoseResult }) {
  const { setResult } = useFarmer()
  useEffect(() => { setResult(r) }, [r, setResult])
  return null
}

function show(r: DiagnoseResult) {
  return render(
    <MemoryRouter>
      <FarmerProvider><Seed r={r} /><Result /></FarmerProvider>
    </MemoryRouter>,
  )
}

describe('what the confidence gate is allowed to show', () => {
  it('gives the advisory when the gate says advise', async () => {
    show(result('advise'))
    expect(await screen.findByText('Rice blast')).toBeInTheDocument()
    expect(screen.getByText(/spindle lesions/i)).toBeInTheDocument()
  })

  it.each<GateOutcome>(['clarify', 'escalate', 'retake'])(
    'shows no advisory when the gate says %s', async (outcome) => {
      // The advisory object is present on the result either way — the gate,
      // not the payload, decides whether a farmer is told to act on it.
      show(result(outcome))
      // Every outcome renders the way back, so that is what says the screen
      // has settled — each branch below it shows something different.
      await screen.findByRole('button', { name: /back|पीछे|मागे/i })
      expect(screen.queryByText(/spindle lesions/i)).not.toBeInTheDocument()
    },
  )

  it('marks a stub model, so a demo never reads as a diagnosis', async () => {
    show(result('advise', { is_stub: true, image_url: '/media/x.jpg' }))
    expect(await screen.findByText(/demo|stub/i)).toBeInTheDocument()
  })
})

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ApiError } from '../../api/client'
import type { AlertView, Farm } from '../../api/types'
import { clearCache } from '../../lib/hooks'
import AlertCard from '../components/AlertCard'
import { FarmerProvider } from '../FarmerContext'
import { FollowUp } from './Home'

// A farmer answering "how is your crop?" or "did you find it?" used to watch
// the buttons sit there until the whole screen had reloaded — and on a slow
// line tap again, which the server refused as already answered and the card
// reported as "did not save". The answer is said at once now, and the card goes.
const followup = vi.fn()
const alertOutcome = vi.fn()
vi.mock('../../api/client', async (orig) => {
  const real = await orig<typeof import('../../api/client')>()
  return {
    ...real,
    api: {
      ...real.api,
      farms: async () => [{ id: 7, read_only: false }] as Farm[],
      followup: (...a: unknown[]) => followup(...a),
      alertOutcome: (...a: unknown[]) => alertOutcome(...a),
    },
  }
})

const ALERT: AlertView = {
  id: 3, farm_id: 7, target: 'rice_blast', name: 'Rice blast', crop: 'rice', tier: 'diagnosable',
  trigger: 'weather', level: 'high', reason: 'Humid nights.', tasks: ['Look at the leaves'],
  issued_on: '2026-11-24', outcome: null, can_photo: true,
}

function inApp(node: React.ReactNode) {
  localStorage.setItem('ar.farm', '7')
  return render(<MemoryRouter><FarmerProvider>{node}</FarmerProvider></MemoryRouter>)
}

beforeEach(() => {
  followup.mockReset()
  alertOutcome.mockReset()
  clearCache()
})

describe('answering a question on Home', () => {
  it('says it is saved at once and leaves, without waiting for a reload', async () => {
    followup.mockResolvedValue({ followup_id: 1, response: 'improved' })
    const done = vi.fn()
    inApp(<FollowUp id={1} name="False smut" dueOn="2026-11-21" onDone={done} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Better' }))
    expect(await screen.findByText('Saved. Good to hear it is better.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Better' })).not.toBeInTheDocument()
    await waitFor(() => expect(done).toHaveBeenCalledOnce(), { timeout: 2000 })
  })

  it('takes "already answered" as saved: the first tap got through', async () => {
    followup.mockRejectedValue(new ApiError(409, 'follow-up already answered'))
    const done = vi.fn()
    inApp(<FollowUp id={2} name="False smut" dueOn="2026-11-21" onDone={done} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Same' }))
    expect(await screen.findByText('Saved. We will ask again in a few days.')).toBeInTheDocument()
    expect(screen.queryByText('That did not save. Try again.')).not.toBeInTheDocument()
    await waitFor(() => expect(done).toHaveBeenCalledOnce(), { timeout: 2000 })
  })

  it('keeps the buttons when the answer really did not save', async () => {
    followup.mockRejectedValue(new ApiError(0, 'offline'))
    const done = vi.fn()
    inApp(<FollowUp id={3} name="False smut" dueOn="2026-11-21" onDone={done} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Better' }))
    expect(await screen.findByText('That did not save. Try again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Better' })).toBeEnabled()
    expect(done).not.toHaveBeenCalled()
  })
})

describe('answering a field check', () => {
  it('says it is saved at once and tells the list which answer it was', async () => {
    alertOutcome.mockResolvedValue({})
    const done = vi.fn()
    inApp(<AlertCard alert={ALERT} onDone={done} />)
    await userEvent.click(await screen.findByRole('button', { name: /nothing/i }))
    expect(await screen.findByText('Saved. Thank you for checking.')).toBeInTheDocument()
    await waitFor(() => expect(done).toHaveBeenCalledWith('nothing_found'), { timeout: 2000 })
  })
})

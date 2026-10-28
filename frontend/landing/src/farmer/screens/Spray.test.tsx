import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Farm, Home, LabelVerdict, WeatherView } from '../../api/types'
import { FarmerProvider } from '../FarmerContext'
import Spray from './Spray'

// "Veto, never endorse" is the rule this screen exists to keep: the spray
// check has no vocabulary for "safe", and a refusal must never be dressed as
// an answer the farmer can act on.
const labelCheck = vi.fn()
const labelNote = vi.fn()
const logSpray = vi.fn()
vi.mock('../../api/client', async (orig) => {
  const real = await orig<typeof import('../../api/client')>()
  return {
    ...real,
    api: {
      ...real.api,
      // Only the parts this screen reads; the rest of these shapes is not
      // what the spray check is about.
      farms: async () => [{ id: 7, read_only: false }] as unknown as Farm[],
      home: async () => ({ problems: [] }) as unknown as Home,
      weather: async () => ({
        spray: { now: null, windows: [], reasons_text: null },
      }) as unknown as WeatherView,
      labelCheck: (...a: unknown[]) => labelCheck(...a),
      labelNote: (...a: unknown[]) => labelNote(...a),
      logSpray: (...a: unknown[]) => logSpray(...a),
    },
  }
})

const verdict = (over: Partial<LabelVerdict>): LabelVerdict => ({
  code: 'x', message: 'A sentence about this product.', ingredient: null, product: 'Mancozeb',
  is_veto: false, tone: 'ok', target: null, ...over,
})

function screenUnderTest() {
  localStorage.setItem('ar.farm', '7')
  return render(
    <MemoryRouter>
      <FarmerProvider><Spray /></FarmerProvider>
    </MemoryRouter>,
  )
}

async function check(product = 'Mancozeb') {
  const box = await screen.findByRole('textbox')
  await userEvent.type(box, product)
  await userEvent.keyboard('{Enter}')
}

beforeEach(() => {
  labelCheck.mockReset()
  labelNote.mockReset()
  logSpray.mockReset()
})

describe('the spray check', () => {
  it('never offers to log a spray it just vetoed', async () => {
    // The button says "I am spraying now". Offering it under a refusal would
    // turn a veto into a step on the way to spraying anyway.
    labelCheck.mockResolvedValue(verdict({ tone: 'stop', is_veto: true, message: 'Do not spray this.' }))
    screenUnderTest()
    await check()

    expect(await screen.findByText('Do not spray this.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /spraying now/i })).not.toBeInTheDocument()
    expect(logSpray).not.toHaveBeenCalled()
  })

  it('shows a veto straight away, without waiting on the AI note', async () => {
    // Only an unrecognised product waits for the note. A refusal that waited
    // would leave a farmer holding a sprayer and looking at a spinner.
    labelCheck.mockResolvedValue(verdict({ tone: 'stop', is_veto: true, message: 'Do not spray this.' }))
    labelNote.mockReturnValue(new Promise(() => {})) // never answers
    screenUnderTest()
    await check()

    expect(await screen.findByText('Do not spray this.')).toBeInTheDocument()
  })

  it('offers the spray log only when nothing was found against the product', async () => {
    labelCheck.mockResolvedValue(verdict({ tone: 'ok', is_veto: false, message: 'No objection found in our records.' }))
    screenUnderTest()
    await check()

    expect(await screen.findByText('No objection found in our records.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /spraying now/i })).toBeInTheDocument()
  })

  it('does not call an unrecognised product safe', async () => {
    // 'unknown' means no record, which is not approval. Nothing on the card
    // may read as one.
    labelCheck.mockResolvedValue(verdict({
      tone: 'unknown', is_veto: false, note_available: false,
      message: 'I do not have a record of this product. Ask an expert before using it.',
    }))
    screenUnderTest()
    await check('Something made up')

    const message = await screen.findByText(/do not have a record/i)
    // The screen's own footnote says the app never calls a pesticide safe, so
    // the check is on the verdict card, not the page.
    const card = message.closest('section')
    expect(card).not.toBeNull()
    expect(card!.textContent).not.toMatch(/\bsafe\b/i)
  })
})

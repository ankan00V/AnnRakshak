import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Me } from '../../api/types'
import { AuthProvider } from '../../auth/AuthContext'
import { clearCache } from '../../lib/hooks'
import { makeT } from '../../lib/i18n'
import { FarmerProvider } from '../FarmerContext'
import Profile from './Profile'

// Two things on this screen exist only for some farmers, so the demo account
// never shows them: the SMS switch (only where the server can send SMS) and
// the card that confirms an email typed at an SMS sign-up.
const t = makeT('en')
let me: Me
const saveProfile = vi.fn()
const addEmail = vi.fn()
const verifyEmail = vi.fn()

vi.mock('../../api/client', async (orig) => {
  const real = await orig<typeof import('../../api/client')>()
  return {
    ...real,
    api: {
      ...real.api,
      me: async () => me,
      farms: async () => [],
      crops: async () => [],
      saveProfile: (...a: unknown[]) => saveProfile(...a),
      addEmail: (...a: unknown[]) => addEmail(...a),
      verifyEmail: (...a: unknown[]) => verifyEmail(...a),
    },
  }
})

const farmer = (over: Partial<Me>): Me => ({
  id: 1, role: 'farmer', name: 'Asha Patil', phone: '+919876543210', email: null, lang: 'en', is_demo: false,
  email_pref: 'warnings', pending_email: null, sms_pref: 'warnings', sms_available: true, created_at: null,
  profile: { district: 'Bhandara', village: 'Lakhni' }, ...over,
}) as Me

function open() {
  return render(
    <MemoryRouter>
      <AuthProvider><FarmerProvider><Profile /></FarmerProvider></AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  saveProfile.mockReset()
  addEmail.mockReset()
  verifyEmail.mockReset()
  clearCache()
})

describe('the farmer profile', () => {
  it('lets a farmer turn SMS warnings off, where the server can send them', async () => {
    me = farmer({})
    saveProfile.mockImplementation(async (patch: Record<string, unknown>) => ({ ...me, ...patch }))
    open()
    const off = await screen.findByRole('radio', { name: t('smsOff') })
    expect(screen.getByRole('radio', { name: t('smsOn') })).toHaveAttribute('aria-checked', 'true')
    await userEvent.click(off)
    expect(saveProfile).toHaveBeenCalledWith({ sms_pref: 'off' })
  })

  it('offers no SMS switch where SMS cannot be sent', async () => {
    me = farmer({ sms_available: false })
    open()
    await screen.findByText(t('profileYou'))
    expect(screen.queryByText(t('smsTitle'))).not.toBeInTheDocument()
  })

  it('confirms an email given at an SMS sign-up with a code sent to it', async () => {
    me = farmer({ pending_email: 'asha@example.com' })
    addEmail.mockResolvedValue({ challenge_id: 'c9', channel: 'email', sent_to: 'a•••@example.com', expires_in: 300, resend_in: 30, digits: 6 })
    verifyEmail.mockResolvedValue(farmer({ email: 'asha@example.com', pending_email: null }))
    open()
    expect(await screen.findByText(t('emailConfirmBody').replace('{email}', 'asha@example.com'))).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: t('emailSendCode') }))
    // The address waiting on the account is the server's to use, not retyped.
    expect(addEmail).toHaveBeenCalledWith(null, 'en')
    await userEvent.type(await screen.findByLabelText(t('authEnterCode')), '123456')
    await userEvent.click(screen.getByRole('button', { name: t('emailConfirmBtn') }))
    expect(verifyEmail).toHaveBeenCalledWith('c9', '123456', 'en')
    // Confirmed: the card goes, and the address is shown as the account's.
    expect(await screen.findByText('asha@example.com')).toBeInTheDocument()
    expect(screen.queryByText(t('emailConfirmTitle'))).not.toBeInTheDocument()
  })
})

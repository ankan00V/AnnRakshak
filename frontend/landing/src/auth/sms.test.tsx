import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { OtpSent } from '../api/types'
import { FarmerProvider } from '../farmer/FarmerContext'
import { makeT } from '../lib/i18n'
import { AuthProvider } from './AuthContext'
import { showPhone, smsCodes, wentBySms } from './helpers'
import { CodePanel } from './parts'
import SignupFarmer from './SignupFarmer'

// The strings as the farmer reads them, whichever table they come from.
const t = makeT('en')

const authOptions = vi.fn()
vi.mock('../api/client', async (orig) => {
  const real = await orig<typeof import('../api/client')>()
  return {
    ...real,
    api: {
      ...real.api,
      me: () => Promise.reject(new real.ApiError(401, 'Please sign in.')),
      authOptions: () => authOptions(),
      crops: () => Promise.resolve([{ id: 'rice', name: 'Rice', photo_diagnosis: true, nursery_days: 21 }]),
      places: () => new Promise(() => {}),
    },
  }
})

const OPTIONS = (sms: boolean) => ({
  districts: [], crops: [], languages: [], irrigation: [], designations: [], departments: [],
  qualifications: [], specialities: [], demo_login: false, turnstile_sitekey: null,
  otp: { digits: 6, minutes: 5, channel: sms ? 'sms' : 'email', sms },
})

function sent(channel: string, to: string): OtpSent {
  return { challenge_id: 'c1', channel, sent_to: to, expires_in: 300, resend_in: 30, digits: 6 } as unknown as OtpSent
}

function panel(answer: OtpSent, note?: string) {
  return render(
    <FarmerProvider>
      <CodePanel sendLabel="Send code" request={() => Promise.resolve(answer)} verify={async () => {}}
        submitLabel="Verify" note={note} />
    </FarmerProvider>,
  )
}

beforeEach(() => authOptions.mockReset())

describe('the code panel says where the code really went', () => {
  it('names the SMS and the masked number when the code went by SMS', async () => {
    panel(sent('sms', '+91 ••••••3210'), t('authSmsNote'))
    expect(screen.getByText(t('authSmsNote'))).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
    expect(await screen.findByText(t('authCodeSentSms').replace('{to}', '+91 ••••••3210'))).toBeInTheDocument()
    // No talk of spam folders to somebody holding a basic phone.
    expect(screen.queryByText(t('authCodeCheckSpam'))).not.toBeInTheDocument()
  })

  it('says email when an SMS that failed fell back to email', async () => {
    panel(sent('email', 'su••••@example.in'), t('authSmsNote'))
    await userEvent.click(screen.getByRole('button', { name: 'Send code' }))
    expect(await screen.findByText(t('authCodeSent').replace('{to}', 'su••••@example.in'))).toBeInTheDocument()
    expect(screen.getByText(t('authCodeCheckSpam'))).toBeInTheDocument()
  })
})

describe('helpers', () => {
  it('reads the server, and an older server without the flag means no SMS', () => {
    expect(smsCodes(OPTIONS(true))).toBe(true)
    expect(smsCodes({ otp: { channel: 'email' } })).toBe(false)
    expect(smsCodes(null)).toBe(false)
    expect(wentBySms({ channel: 'sms' })).toBe(true)
    expect(wentBySms({ channel: 'email' })).toBe(false)
    expect(showPhone('098765 43210')).toBe('+91 9876543210')
  })
})

function signup() {
  const view = render(
    <MemoryRouter>
      <FarmerProvider>
        <AuthProvider>
          <SignupFarmer />
        </AuthProvider>
      </FarmerProvider>
    </MemoryRouter>,
  )
  const name = view.container.querySelector('input[autocomplete="name"]') as HTMLInputElement
  return { name, mobile: screen.getByPlaceholderText('98XXXXXXXX'), email: screen.getByPlaceholderText('name@gmail.com') }
}

describe('a farmer signs up with a mobile number', () => {
  it('needs no email when the code can go by SMS', async () => {
    authOptions.mockResolvedValue(OPTIONS(true))
    const { name, mobile } = signup()
    expect(await screen.findByText(t('authEmailHintOptional'))).toBeInTheDocument()
    await userEvent.type(name, 'Sunita Bhoyar')
    await userEvent.type(mobile, '9876543210')
    await userEvent.click(screen.getByRole('button', { name: t('authNext') }))
    expect(await screen.findByRole('heading', { name: t('authFarmerStep2') })).toBeInTheDocument()
  })

  it('still refuses an email that is typed wrong', async () => {
    authOptions.mockResolvedValue(OPTIONS(true))
    const { name, mobile, email } = signup()
    await screen.findByText(t('authEmailHintOptional'))
    await userEvent.type(name, 'Sunita Bhoyar')
    await userEvent.type(mobile, '9876543210')
    await userEvent.type(email, 'sunita@')
    await userEvent.click(screen.getByRole('button', { name: t('authNext') }))
    expect(screen.getByText(t('authBadEmail'))).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: t('authFarmerStep1') })).toBeInTheDocument()
  })

  it('asks for an email while the server cannot send SMS', async () => {
    authOptions.mockResolvedValue(OPTIONS(false))
    const { name, mobile } = signup()
    await waitFor(() => expect(authOptions).toHaveBeenCalled())
    expect(await screen.findByText(t('authEmailHint'))).toBeInTheDocument()
    await userEvent.type(name, 'Sunita Bhoyar')
    await userEvent.type(mobile, '9876543210')
    await userEvent.click(screen.getByRole('button', { name: t('authNext') }))
    expect(screen.getByText(t('authBadEmail'))).toBeInTheDocument()
  })
})

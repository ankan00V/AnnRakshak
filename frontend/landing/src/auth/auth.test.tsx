import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { ApiError } from '../api/client'
import type { Me } from '../api/types'
import { AuthProvider, useAuth } from './AuthContext'
import RequireRole from './RequireRole'

// The real client talks to the network on mount; the tests decide what it says.
const me = vi.fn()
const logout = vi.fn()
vi.mock('../api/client', async (orig) => {
  const real = await orig<typeof import('../api/client')>()
  return { ...real, api: { ...real.api, me: () => me(), logout: () => logout() } }
})

const FARMER: Me = {
  id: 1, role: 'farmer', name: 'Sunita Bhoyar', phone: '+919876543210',
  email: 'sunita@example.in', lang: 'mr', is_demo: false, farm_ids: [7],
  profile: { district: 'Bhandara', village: 'Mohadi' },
}

/** The address bar, so a test can assert where a redirect sent someone. */
function Where() {
  const { pathname, search } = useLocation()
  return <span data-testid="where">{pathname + search}</span>
}

function LogOutButton() {
  const { logout: signOut } = useAuth()
  return <button onClick={() => { void signOut() }}>Log out</button>
}

function app(start: string) {
  return render(
    <MemoryRouter initialEntries={[start]}>
      <AuthProvider>
        <Where />
        <Routes>
          <Route path="/" element={<p>Front page</p>} />
          <Route path="/login" element={<p>Sign in</p>} />
          <Route path="/app/*" element={
            <RequireRole role="farmer"><p>Your fields</p><LogOutButton /></RequireRole>
          } />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  me.mockReset()
  logout.mockReset()
})

describe('logging out', () => {
  it('forgets this browser without waiting for the server', async () => {
    // The fault this covers: the handler asked the server first and cleared
    // nothing until it answered, so on a weak signal the farmer's name and
    // fields stayed on screen after the tap — long enough to hand the phone
    // over still signed in.
    me.mockResolvedValue(FARMER)
    let answer: () => void = () => {}
    logout.mockReturnValue(new Promise<void>((resolve) => { answer = resolve }))

    app('/app')
    expect(await screen.findByText('Your fields')).toBeInTheDocument()
    localStorage.setItem('ar.farm', '7')

    await userEvent.click(screen.getByRole('button', { name: 'Log out' }))

    // Still nothing back from the server.
    expect(logout).toHaveBeenCalledOnce()
    await waitFor(() => expect(screen.queryByText('Your fields')).not.toBeInTheDocument())
    expect(localStorage.getItem('ar.me')).toBeNull()
    expect(localStorage.getItem('ar.farm')).toBeNull()

    answer()
  })

  it('lands on the front page, not the sign-in screen', async () => {
    me.mockResolvedValue(FARMER)
    logout.mockResolvedValue(undefined)

    app('/app')
    expect(await screen.findByText('Your fields')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Log out' }))

    expect(await screen.findByText('Front page')).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('/')
  })

  it('still sends an expired session to sign-in, keeping where it was going', async () => {
    // The other half of the same rule: somebody who never signed in, or whose
    // session ran out, was trying to reach a page and should get it back.
    me.mockRejectedValue(new ApiError(401, 'Please sign in.'))

    app('/app/scan')

    expect(await screen.findByText('Sign in')).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('/login?role=farmer&next=%2Fapp%2Fscan')
  })

  it('offers sign-in again after a log-out, rather than the front page for ever', async () => {
    me.mockResolvedValue(FARMER)
    logout.mockResolvedValue(undefined)

    const { unmount } = app('/app')
    expect(await screen.findByText('Your fields')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Log out' }))
    expect(await screen.findByText('Front page')).toBeInTheDocument()
    unmount()

    // A fresh load with no session is not a log-out: the destination is kept.
    me.mockRejectedValue(new ApiError(401, 'Please sign in.'))
    app('/app/scan')
    expect(await screen.findByText('Sign in')).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('next=%2Fapp%2Fscan')
  })
})

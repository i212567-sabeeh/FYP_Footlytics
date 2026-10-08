import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { AppProviders } from '../../components/AppProviders'
import { getAccessToken, setAccessToken } from '../auth/tokenStorage'
import type { User } from '../auth/types'
import type { SignupRequest } from './signupApi'

// Synthetic fixtures only; product screens always call the protected API.
const admin: User = {
  id: 1, email: 'admin@example.com', full_name: 'Test Admin', is_active: true,
  roles: ['admin'], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}
const applicant: SignupRequest = {
  id: 12, email: 'new@example.com', full_name: 'New Applicant', status: 'pending', requested_role: 'coach',
  created_at: '2026-01-01T00:00:00Z', reviewed_at: null, reviewed_by_user_id: null, approved_user_id: null,
}
const receipt = 'New signup requests require administrator approval before sign-in.'
const fetchMock = vi.fn<typeof fetch>()
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

function renderApp(path = '/signup') {
  return render(<AppProviders><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AppProviders>)
}
function fillSignup() {
  fireEvent.change(screen.getByLabelText('Requested role'), { target: { value: 'coach' } })
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: ' New Applicant ' } })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Test-password-123' } })
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'Test-password-123' } })
}
function mockAdmin(currentUser = admin, failure = false, initialRequest: SignupRequest = applicant) {
  let requests = [{ ...initialRequest }]
  fetchMock.mockImplementation(async (input, options) => {
    const url = String(input)
    if (url === '/api/auth/me') return response(currentUser)
    if (url.startsWith('/api/signup-requests?')) {
      const status = new URL(url, 'http://localhost').searchParams.get('status')
      const items = requests.filter((item) => item.status === status)
      return response({ items, total: items.length, offset: 0, limit: 25 })
    }
    if (url.startsWith('/api/clubs?')) return response({ items: [{ id: 3, name: 'Approved Club', is_active: true }], total: 1, offset: 0, limit: 100 })
    if (/^\/api\/(teams|players|matches)\?/.test(url)) return response({ items: [], total: 0, offset: 0, limit: 1 })
    if (url === '/api/signup-requests/12/approve') {
      if (failure) return response({ detail: 'This signup request has already been reviewed. Refresh the list.' }, 409)
      requests = [{ ...initialRequest, status: 'approved', reviewed_at: '2026-01-02T00:00:00Z', reviewed_by_user_id: 1, approved_user_id: 7 }]
      const fields = JSON.parse(String(options?.body)) as { roles: User['roles'] }
      return response({ ...admin, id: 7, roles: fields.roles, email: applicant.email, full_name: applicant.full_name }, 201)
    }
    if (url === '/api/signup-requests/12/reject') {
      requests = [{ ...initialRequest, status: 'rejected', reviewed_at: '2026-01-02T00:00:00Z', reviewed_by_user_id: 1 }]
      return response(requests[0])
    }
    throw new Error(`Unexpected test request: ${url}`)
  })
}
async function openReview() {
  setAccessToken('test-admin-token')
  renderApp('/admin/signup-requests')
  fireEvent.click(await screen.findByRole('button', { name: 'Review New Applicant' }))
  await screen.findByRole('option', { name: 'Approved Club' })
  return screen.getByRole('form', { name: 'Review New Applicant' })
}

beforeEach(() => { setAccessToken(null); fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock) })
afterEach(() => { vi.unstubAllGlobals() })

describe('public signup', () => {
  it('offers signup from login and a route back to sign in', () => {
    renderApp('/login')
    fireEvent.click(screen.getByRole('link', { name: 'Sign up' }))
    expect(screen.getByRole('heading', { name: 'Sign up for FOOTLYTICS' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('validates fields and matching passwords without submitting', () => {
    renderApp()
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Enter your full name and a valid email address.')
    fillSignup()
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'short' } })
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }))
    expect(screen.getByRole('alert')).toHaveTextContent('8 and 128')
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Different-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Passwords do not match')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('submits once without roles or authorization and waits for approval without signing in', async () => {
    let finish: (value: Response) => void = () => undefined
    fetchMock.mockImplementation(() => new Promise((resolve) => { finish = resolve }))
    renderApp()
    fillSignup()
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }))
    expect(screen.getByLabelText('Email')).toBeDisabled()
    expect(screen.getByRole('button', { name: /Submitting/ })).toBeDisabled()
    const call = fetchMock.mock.calls[0]
    expect(call).toBeDefined()
    if (!call) throw new Error("Expected signup request")
    const [url, options] = call
    expect(url).toBe('/api/auth/signup')
    expect(JSON.parse(String(options?.body))).toEqual({ full_name: 'New Applicant', email: 'new@example.com', password: 'Test-password-123', requested_role: 'coach' })
    expect(options?.headers).not.toHaveProperty('Authorization')
    await act(async () => { finish(response({ message: receipt }, 202)) })
    expect(await screen.findByRole('status')).toHaveTextContent(receipt)
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    expect(getAccessToken()).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('shows connection errors and allows a retry', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValue(response({ message: receipt }, 202))
    renderApp()
    fillSignup()
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach the server')
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }))
    expect(await screen.findByRole('status')).toHaveTextContent(receipt)
  })

  it('redirects an existing signed-in user home', async () => {
    setAccessToken('existing-token')
    mockAdmin()
    renderApp()
    expect(await screen.findByRole('heading', { name: 'Welcome, Test Admin' })).toBeVisible()
    expect(screen.queryByLabelText('Confirm password')).not.toBeInTheDocument()
  })
})

describe('admin access review', () => {
  it('protects the route for anonymous users', () => {
    renderApp('/admin/signup-requests')
    expect(screen.getByRole('heading', { name: 'Sign in to FOOTLYTICS' })).toBeVisible()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each(['coach', 'analyst', 'club_management', 'player'] as const)('denies %s navigation and direct requests', async (role) => {
    setAccessToken('non-admin-token')
    mockAdmin({ ...admin, roles: [role] })
    renderApp('/admin/signup-requests')
    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeVisible()
    expect(screen.queryByRole('link', { name: 'Access requests' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith('/api/signup-requests'))).toBe(false)
  })

  it('approves exactly the requested role with club access and exposes reviewed history', async () => {
    mockAdmin()
    const form = await openReview()
    expect(within(form).getByText('Requested role: Coach')).toBeVisible()
    expect(within(form).getByText('Approval grants the requested Coach role.')).toBeVisible()
    expect(within(form).queryByRole('checkbox')).not.toBeInTheDocument()
    fireEvent.change(within(form).getByLabelText('Club access (optional)'), { target: { value: '3' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Approve access' }))
    expect(await screen.findByText('Access approved. The applicant can now sign in.')).toBeVisible()
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/approve'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ roles: ['coach'], club_id: 3 })
    expect(call?.[1]?.headers).toMatchObject({ Authorization: 'Bearer test-admin-token' })
    expect(await screen.findByText('No pending signup requests.')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Request status'), { target: { value: 'approved' } })
    expect(await screen.findByText('Approved account #7')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Review New Applicant' })).not.toBeInTheDocument()
  })

  it('explains optional club and player profile requirements', async () => {
    mockAdmin(admin, false, { ...applicant, requested_role: 'player' })
    const form = await openReview()
    expect(within(form).getByText(/Without a club assignment/)).toBeVisible()
    expect(within(form).getByText(/linked active player profile and squad membership/)).toBeVisible()
    fireEvent.click(within(form).getByRole('button', { name: 'Approve access' }))
    await screen.findByText('Access approved. The applicant can now sign in.')
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/approve'))
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ roles: ['player'], club_id: null })
  })

  it('confirms rejection without requiring roles and updates history', async () => {
    mockAdmin()
    const form = await openReview()
    fireEvent.click(within(form).getByRole('button', { name: 'Reject request' }))
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/reject'))).toBe(false)
    fireEvent.click(within(form).getByRole('button', { name: 'Confirm rejection' }))
    expect(await screen.findByText('Signup request rejected. No account was created.')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Request status'), { target: { value: 'rejected' } })
    expect(await screen.findByRole('heading', { name: 'New Applicant' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Review New Applicant' })).not.toBeInTheDocument()
  })

  it('displays a stale review conflict and refreshes server state', async () => {
    mockAdmin(admin, true)
    const form = await openReview()
    fireEvent.click(within(form).getByRole('button', { name: 'Approve access' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('already been reviewed')
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).startsWith('/api/signup-requests?')).length).toBeGreaterThan(1))
  })

  it('shows list errors with a retry action', async () => {
    setAccessToken('admin-token')
    fetchMock.mockImplementation(async (url) => String(url) === '/api/auth/me' ? response(admin) : response({}, 503))
    renderApp('/admin/signup-requests')
    expect(await screen.findByRole('alert')).toHaveTextContent('server could not complete')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeVisible()
  })
})

describe('signup role selection', () => {
  it('requires a role and offers exactly the four non-admin choices', () => {
    renderApp()
    const role = screen.getByLabelText('Requested role')
    expect(role).toBeRequired()
    expect(role).toHaveValue('')
    expect(within(role).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Select your role', 'Coach', 'Analyst', 'Player', 'Club Management',
    ])
    expect(screen.queryByRole('option', { name: 'Admin' })).not.toBeInTheDocument()
    fillSignup()
    fireEvent.change(role, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose the role you are requesting.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each(['coach', 'analyst', 'player', 'club_management'])('submits the selected %s role as a pending request', async (role) => {
    fetchMock.mockResolvedValue(response({ message: receipt }, 202))
    renderApp()
    fillSignup()
    fireEvent.change(screen.getByLabelText('Requested role'), { target: { value: role } })
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }))
    expect(await screen.findByRole('status')).toHaveTextContent(receipt)
    const call = fetchMock.mock.calls.find(([url]) => url === '/api/auth/signup')
    expect(JSON.parse(String(call?.[1]?.body)).requested_role).toBe(role)
    expect(getAccessToken()).toBeNull()
  })

  it('keeps a legacy request unspecified until the admin selects approval roles', async () => {
    mockAdmin(admin, false, { ...applicant, requested_role: null })
    const form = await openReview()
    expect(within(form).getByText('Requested role: Not specified')).toBeVisible()
    expect(within(form).getByLabelText('Approved role')).toHaveValue('')
    expect(within(form).queryByRole('option', { name: 'Admin' })).not.toBeInTheDocument()
    fireEvent.click(within(form).getByRole('button', { name: 'Approve access' }))
    expect(within(form).getByRole('alert')).toHaveTextContent('Choose a role')
    fireEvent.change(within(form).getByLabelText('Approved role'), { target: { value: 'analyst' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Approve access' }))
    expect(await screen.findByText('Access approved. The applicant can now sign in.')).toBeVisible()
  })
})

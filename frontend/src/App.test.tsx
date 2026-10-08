import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { AppProviders } from './components/AppProviders'
import { getAccessToken, setAccessToken } from './features/auth/tokenStorage'
import type { User } from './features/auth/types'

// Explicit test fixtures; product pages always obtain users from the backend.
const admin: User = {
  id: 1, email: 'admin@example.com', full_name: 'Test Admin', is_active: true,
  roles: ['admin'], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}
const coach: User = { ...admin, id: 2, email: 'coach@example.com', full_name: 'Test Coach', roles: ['coach'] }
const fetchMock = vi.fn<typeof fetch>()

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
}

function mockApi(currentUser = admin) {
  let users = [admin, coach]
  fetchMock.mockImplementation(async (input, options) => {
    const path = String(input)
    if (path === '/api/auth/login') return jsonResponse({ access_token: 'fixture-token', token_type: 'bearer' })
    if (path === '/api/auth/me') return jsonResponse(currentUser)
    if (/^\/api\/(clubs|teams|players|matches)\?/.test(path)) return jsonResponse({ items: [], total: 0, offset: 0, limit: 1 })
    if (path.startsWith('/api/users?')) return jsonResponse({ items: users, total: users.length, offset: 0, limit: 25 })
    if (path === '/api/users' && options?.method === 'POST') {
      const data = JSON.parse(String(options.body)) as Pick<User, 'email' | 'full_name' | 'roles'>
      const created = { ...coach, ...data, id: 3 }
      users = [...users, created]
      return jsonResponse(created, 201)
    }
    if (path === '/api/users/2' && options?.method === 'PATCH') {
      const updated = { ...coach, ...JSON.parse(String(options.body)) as Partial<User> }
      users = users.map((user) => user.id === 2 ? updated : user)
      return jsonResponse(updated)
    }
    throw new Error(`Unexpected test request: ${path}`)
  })
}

function renderApp(path = '/') {
  return render(<AppProviders><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AppProviders>)
}

beforeEach(() => {
  setAccessToken(null)
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { vi.unstubAllGlobals() })

describe('login and protected routes', () => {
  it('redirects anonymous protected requests to the login form', () => {
    renderApp('/admin/users')
    expect(screen.getByRole('heading', { name: 'Sign in to FOOTLYTICS' })).toBeVisible()
    expect(screen.getByLabelText('Email')).toBeVisible()
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('validates login inputs before sending credentials', () => {
    renderApp('/login')
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a valid email address and your password.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('signs in, verifies /me and logs out', async () => {
    mockApi()
    renderApp('/login')
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'admin@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Test-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    expect(await screen.findByRole('heading', { name: 'Welcome, Test Admin' })).toBeVisible()
    expect(getAccessToken()).toBe('fixture-token')
    expect(screen.getByRole('link', { name: 'User management' })).toBeVisible()
    expect(fetchMock.mock.calls.find(([url]) => url === '/api/auth/me')?.[1]?.headers)
      .toMatchObject({ Authorization: 'Bearer fixture-token' })
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }))
    expect(await screen.findByRole('button', { name: 'Sign In' })).toBeVisible()
    expect(getAccessToken()).toBeNull()
    expect(sessionStorage.getItem('footlytics.access-token')).toBeNull()
  })

  it.each([
    [401, 'Invalid email or password.'],
    [500, 'The server could not complete the request. Please try again.'],
  ])('shows a useful error for HTTP %s', async (status, message) => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Internal details' }, status))
    renderApp('/login')
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'admin@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Test-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(getAccessToken()).toBeNull()
  })

  it('shows loading and network errors', async () => {
    let rejectRequest: (reason: Error) => void = () => undefined
    fetchMock.mockImplementation(() => new Promise((_resolve, reject) => { rejectRequest = reject }))
    renderApp('/login')
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'admin@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Test-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    expect(screen.getByRole('button', { name: 'Signing in…' })).toBeDisabled()
    await act(async () => { rejectRequest(new TypeError('Failed to fetch')) })
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach the server')
  })

  it('verifies a restored token before showing protected content', async () => {
    setAccessToken('restored-token')
    let resolveRequest: (response: Response) => void = () => undefined
    fetchMock.mockImplementation(() => new Promise((resolve) => { resolveRequest = resolve }))
    renderApp()
    expect(screen.getByRole('status')).toHaveTextContent('Checking your session')
    expect(screen.queryByText('Welcome, Test Admin')).not.toBeInTheDocument()
    await act(async () => { resolveRequest(jsonResponse(admin)) })
    expect(await screen.findByRole('heading', { name: 'Welcome, Test Admin' })).toBeVisible()
  })

  it('clears an invalid restored token and redirects to login', async () => {
    setAccessToken('expired-token')
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Invalid credentials' }, 401))
    renderApp()
    expect(await screen.findByRole('button', { name: 'Sign In' })).toBeVisible()
    expect(getAccessToken()).toBeNull()
  })

  it('retains the session during temporary server failure and supports retry', async () => {
    setAccessToken('saved-token')
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 503)).mockResolvedValue(jsonResponse(admin))
    renderApp()
    expect(await screen.findByRole('heading', { name: 'Unable to verify your session' })).toBeVisible()
    expect(getAccessToken()).toBe('saved-token')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Welcome, Test Admin' })).toBeVisible()
  })

  it('denies non-admin navigation and direct user-screen access', async () => {
    setAccessToken('coach-token')
    mockApi(coach)
    renderApp('/admin/users')
    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeVisible()
    expect(screen.queryByRole('link', { name: 'User management' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith('/api/users'))).toBe(false)
  })

  it('describes completed match analysis tools without starting processing', async () => {
    setAccessToken('coach-token')
    mockApi(coach)
    renderApp()
    expect(await screen.findByRole('heading', { name: 'Welcome, Test Coach' })).toBeVisible()
    expect(screen.getByText(/player and team analytics, PDF reports and CSV exports/)).toBeVisible()
    expect(screen.getByText(/Available actions depend on your role and completed processing/)).toBeVisible()
    expect(screen.queryByText(/Match analytics are not available yet/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^Matches$/ })).toHaveAttribute('href', '/matches')
    expect(fetchMock.mock.calls.some(([url, options]) => String(url).includes('/jobs/') || options?.method === 'POST')).toBe(false)
  })

  it('provides a way home from unknown routes', () => {
    renderApp('/unavailable')
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Return home' })).toHaveAttribute('href', '/')
  })
})

describe('admin user management', () => {
  beforeEach(() => { setAccessToken('admin-token'); mockApi() })

  it('lists API data and creates a user with multiple roles', async () => {
    renderApp('/admin/users')
    expect(await screen.findByRole('cell', { name: 'Test Coach' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Create user' }))
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'New Analyst' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } })
    fireEvent.change(screen.getByLabelText('Initial password'), { target: { value: 'New-password' } })
    fireEvent.click(screen.getByLabelText('Coach'))
    fireEvent.click(screen.getByLabelText('Analyst'))
    fireEvent.click(screen.getByRole('button', { name: 'Save user' }))
    expect(await screen.findByRole('cell', { name: 'New Analyst' })).toBeVisible()
    expect(screen.getByRole('status')).toHaveTextContent('User saved.')
  })

  it('edits identity, roles and status without sending a password', async () => {
    renderApp('/admin/users')
    fireEvent.click(await screen.findByRole('button', { name: 'Edit Test Coach' }))
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Updated Coach' } })
    fireEvent.click(screen.getByLabelText('Analyst'))
    fireEvent.click(screen.getByLabelText('Active account'))
    expect(screen.queryByLabelText('Initial password')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save user' }))
    expect(await screen.findByRole('cell', { name: 'Updated Coach' })).toBeVisible()
    const row = screen.getByRole('cell', { name: 'Updated Coach' }).closest('tr')!
    expect(within(row).getByText('Inactive')).toBeVisible()
    const request = fetchMock.mock.calls.find(([url, options]) => url === '/api/users/2' && options?.method === 'PATCH')
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({ is_active: false, roles: ['coach', 'analyst'] })
    expect(String(request?.[1]?.body)).not.toContain('password')
  })

  it('validates password and role requirements', async () => {
    renderApp('/admin/users')
    await screen.findByRole('cell', { name: 'Test Admin' })
    fireEvent.click(screen.getByRole('button', { name: 'Create user' }))
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'New User' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } })
    fireEvent.change(screen.getByLabelText('Initial password'), { target: { value: 'short' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save user' }))
    expect(screen.getByRole('alert')).toHaveTextContent('between 8 and 128')
    fireEvent.change(screen.getByLabelText('Initial password'), { target: { value: 'Long-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save user' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose at least one role')
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
  })
})

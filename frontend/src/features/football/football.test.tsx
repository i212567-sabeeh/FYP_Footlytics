import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from '../../App'
import { AppProviders } from '../../components/AppProviders'
import { setAccessToken } from '../auth/tokenStorage'
import type { User } from '../auth/types'
import { MatchForm } from './MatchForm'
import type { FootballMatch } from './types'

// Only test fixtures use synthetic accounts and domain records.
const user: User = { id: 1, email: 'test@example.com', full_name: 'Test Coach', roles: ['coach'], is_active: true, created_at: '', updated_at: '' }
const club = { id: 1, name: 'North Club', is_active: true }
const teams = [1, 2].map((id) => ({ id, club_id: 1, club, name: `Team ${id}`, is_active: true }))
const fetchMock = vi.fn<typeof fetch>()
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const page = (items: unknown[], total = items.length) => ({ items, total, offset: 0, limit: 25 })
function mockApi(current = user) {
  fetchMock.mockImplementation(async (url) => {
    const path = String(url)
    if (path === '/api/auth/me') return response(current)
    if (path.startsWith('/api/clubs?')) return response(page([club, { ...club, id: 2, name: 'South Club' }]))
    if (path.startsWith('/api/teams?')) return response(page(path.includes('club_id=2') ? [{ ...teams[0], id: 3, club_id: 2, name: 'South Team' }] : teams))
    if (path.startsWith('/api/players?') || path.startsWith('/api/matches?')) return response(page([]))
    return response({ detail: 'Record not found' }, 404)
  })
}
function renderApp(path: string) {
  setAccessToken('test-token')
  return render(<AppProviders><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AppProviders>)
}
function renderMatch(onSave = vi.fn(), initial?: FootballMatch) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MatchForm initial={initial} saving={false} error={null} onSave={onSave} onCancel={vi.fn()} /></QueryClientProvider>)
  return onSave
}
beforeEach(() => { setAccessToken(null); fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); mockApi() })
afterEach(() => { vi.unstubAllGlobals() })

describe('match form integrity', () => {
  it('sets editable format defaults and clears teams when the club changes', async () => {
    renderMatch()
    await screen.findByRole('option', { name: 'North Club' })
    fireEvent.change(screen.getByLabelText('Club'), { target: { value: '1' } })
    await screen.findAllByRole('option', { name: 'Team 1' })
    fireEvent.change(screen.getByLabelText('Team A'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Team B'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('Match format'), { target: { value: '5v5' } })
    expect(screen.getByLabelText('Pitch length (X, metres)')).toHaveValue(40)
    expect(screen.getByLabelText('Pitch width (Y, metres)')).toHaveValue(20)
    fireEvent.change(screen.getByLabelText('Pitch length (X, metres)'), { target: { value: '42' } })
    expect(screen.getByLabelText('Pitch length (X, metres)')).toHaveValue(42)
    fireEvent.change(screen.getByLabelText('Club'), { target: { value: '2' } })
    expect(screen.getByLabelText('Team A')).toHaveValue('')
    expect(screen.getByLabelText('Team B')).toHaveValue('')
    await screen.findAllByRole('option', { name: 'South Team' })
    expect(screen.queryByRole('option', { name: 'Team 1' })).not.toBeInTheDocument()
  })

  it('submits actual measurements and a UTC timestamp, preventing equal teams and reversed axes', async () => {
    const save = renderMatch()
    await screen.findByRole('option', { name: 'North Club' })
    fireEvent.change(screen.getByLabelText('Club'), { target: { value: '1' } })
    await screen.findAllByRole('option', { name: 'Team 1' })
    fireEvent.change(screen.getByLabelText('Match title'), { target: { value: 'Recorded match' } })
    fireEvent.change(screen.getByLabelText('Match date and time (local)'), { target: { value: '2026-09-01T17:00' } })
    fireEvent.change(screen.getByLabelText('Team A'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Team B'), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save match' }))
    expect(screen.getByRole('alert')).toHaveTextContent('must be different')
    fireEvent.change(screen.getByLabelText('Team B'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('Pitch length (X, metres)'), { target: { value: '40' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save match' }))
    expect(screen.getByRole('alert')).toHaveTextContent('length must be at least width')
    fireEvent.change(screen.getByLabelText('Pitch width (Y, metres)'), { target: { value: '22' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save match' }))
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ club_id: 1, pitch_length_metres: 40, pitch_width_metres: 22, match_date: new Date('2026-09-01T17:00').toISOString() }))
  })
})

describe('scoped football screens', () => {
  it('renders API totals rather than the current page size', async () => {
    fetchMock.mockImplementation(async (url) => String(url) === '/api/auth/me' ? response(user) : response(page([], 47)))
    renderApp('/')
    await waitFor(() => expect(screen.getAllByText('47')).toHaveLength(4))
  })

  it('shows unavailable counts during server failure without logging out', async () => {
    fetchMock.mockImplementation(async (url) => String(url) === '/api/auth/me' ? response(user) : response({}, 500))
    renderApp('/')
    await waitFor(() => expect(screen.getAllByText('Unavailable')).toHaveLength(4))
    expect(screen.getByRole('button', { name: 'Logout' })).toBeVisible()
  })

  it.each(['club_management', 'player'] as const)('hides write actions for %s and denies the create-match route', async (role) => {
    mockApi({ ...user, roles: [role] })
    renderApp('/matches/new')
    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeVisible()
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith('/api/matches'))).toBe(false)
  })

  it('offers no roster creation to analysts', async () => {
    mockApi({ ...user, roles: ['analyst'] })
    renderApp('/teams')
    await screen.findByRole('link', { name: 'Team 1' })
    expect(screen.queryByRole('button', { name: 'Create team' })).not.toBeInTheDocument()
  })

  it('preserves access errors and offers retry for inaccessible detail IDs', async () => {
    renderApp('/teams/999')
    expect(await screen.findByRole('alert')).toHaveTextContent('Record not found')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Edit team' })).not.toBeInTheDocument()
  })

  it('handles empty player data without inventing profiles', async () => {
    renderApp('/players')
    expect(await screen.findByText(/No football players found/)).toBeVisible()
    expect(screen.queryByRole('link', { name: /Test Player/ })).not.toBeInTheDocument()
  })

  it('lists club records while keeping club administration hidden from coaches', async () => {
    renderApp('/clubs')
    expect(await screen.findByRole('link', { name: 'North Club' })).toHaveAttribute('href', '/clubs/1')
    expect(screen.queryByRole('button', { name: 'Create club' })).not.toBeInTheDocument()
  })

  it('lets a Coach submit a team for an assigned club', async () => {
    const getRequest = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (url, options) => options?.method === 'POST' ? response(teams[0], 201) : getRequest(url, options))
    renderApp('/teams')
    fireEvent.click(await screen.findByRole('button', { name: 'Create team' }))
    const clubSelect = screen.getAllByLabelText('Club')[0]!
    await within(clubSelect).findByRole('option', { name: 'North Club' })
    fireEvent.change(clubSelect, { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Under 18' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save team' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/teams', expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: 'Under 18', short_name: null, description: null, club_id: 1 }) })))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Save team' })).not.toBeInTheDocument())
  })

  it('creates a football profile without requiring a login account or birth date', async () => {
    const getRequest = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (url, options) => {
      if (String(url).includes('player-account-options')) return response(page([]))
      if (options?.method === 'POST') return response({ id: 7 }, 201)
      return getRequest(url, options)
    })
    renderApp('/players')
    fireEvent.click(await screen.findByRole('button', { name: 'Create player' }))
    const clubSelect = screen.getAllByLabelText('Club')[0]!
    await within(clubSelect).findByRole('option', { name: 'North Club' })
    fireEvent.change(clubSelect, { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('First name'), { target: { value: 'Test' } })
    fireEvent.change(screen.getByLabelText('Last name'), { target: { value: 'Footballer' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save player' }))
    await waitFor(() => {
      const request = fetchMock.mock.calls.find(([url, options]) => url === '/api/players' && options?.method === 'POST')
      expect(request).toBeDefined()
      expect(JSON.parse(String(request![1]?.body))).toMatchObject({ club_id: 1, first_name: 'Test', last_name: 'Footballer', user_id: null, date_of_birth: null })
    })
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Save player' })).not.toBeInTheDocument())
  })

  it.each(['coach', 'club_management'] as const)('enforces %s squad controls and handles soft removal', async (role) => {
    const footballer = { id: 7, first_name: 'Test', last_name: 'Forward', display_name: null, preferred_position: 'forward', is_active: true }
    const membership = { id: 9, team_id: 1, player_id: 7, team: teams[0], player: footballer, shirt_number: 10, is_active: true, joined_at: '2026-09-01T12:00:00Z', left_at: null }
    let removed = false
    const getRequest = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (url, options) => {
      const path = String(url)
      if (path === '/api/auth/me') return response({ ...user, roles: [role] })
      if (path === '/api/teams/1') return response({ ...teams[0], description: null })
      if (path === '/api/teams/1/squad/9' && options?.method === 'DELETE') { removed = true; return new Response(null, { status: 204 }) }
      if (path.startsWith('/api/teams/1/squad?')) return response(page(removed ? [] : [membership]))
      return getRequest(url, options)
    })
    renderApp('/teams/1')
    await screen.findByRole('link', { name: 'Test Forward' })
    if (role === 'club_management') {
      expect(screen.queryByRole('button', { name: 'Edit team' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Remove Test Forward from squad' })).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Player to add')).not.toBeInTheDocument()
    } else {
      fireEvent.click(screen.getByRole('button', { name: 'Remove Test Forward from squad' }))
      expect(await screen.findByText('No squad memberships found.')).toBeVisible()
      expect(fetchMock).toHaveBeenCalledWith('/api/teams/1/squad/9', expect.objectContaining({ method: 'DELETE' }))
      expect(fetchMock.mock.calls.some(([url, options]) => String(url).startsWith('/api/players/') && options?.method === 'DELETE')).toBe(false)
      expect(screen.getByRole('button', { name: 'Logout' })).toBeVisible()
    }
  })

  it('loads every page of club options', async () => {
    fetchMock.mockImplementation(async (url) => {
      if (String(url).includes('offset=100')) return response(page([{ ...club, id: 101, name: 'Last Club' }], 101))
      return response(page(Array.from({ length: 100 }, (_, index) => ({ ...club, id: index + 1, name: `Club ${index + 1}` })), 101))
    })
    renderMatch()
    await waitFor(() => expect(screen.getByRole('option', { name: 'Last Club' })).toBeVisible())
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

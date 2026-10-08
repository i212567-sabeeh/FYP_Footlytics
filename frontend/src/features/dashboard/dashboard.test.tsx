import { act, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { AppProviders } from '../../components/AppProviders'
import { job, match } from '../analytics/__fixtures__/analytics'
import { setAccessToken } from '../auth/tokenStorage'
import type { Role } from '../auth/types'
import type { FootballMatch } from '../football/types'
import type { JobStatus, ProcessingJob } from '../media/types'
import { countStates } from './summary'

// Explicit test fixtures; the dashboard only renders backend responses.
const derby: FootballMatch = { ...match, id: 21, title: 'Derby Day', match_date: '2026-09-20T15:00:00Z', is_archived: false,
  team_a: { ...match.team_a, name: 'North FC' }, team_b: { ...match.team_b, name: 'South FC' } }
const cup: FootballMatch = { ...match, id: 22, title: 'Cup Tie', match_date: '2026-09-13T15:00:00Z', match_format: '5v5', is_archived: true }
const running: ProcessingJob = { ...job, id: 31, match_id: 21, job_type: 'player_tracking', status: 'running', progress_percent: 40 }
const fetchMock = vi.fn<typeof fetch>()
const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } })
const page = (items: unknown[], total = items.length) => ({ items, total, offset: 0, limit: Math.max(1, items.length) })
const TOTALS: Record<string, number> = { clubs: 2, teams: 4, players: 37 }

function renderDashboard(roles: Role[], matches = [derby, cup]) {
  setAccessToken('dashboard-token')
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    if (url === '/api/auth/me') return json({ id: 5, email: 'dash@example.com', full_name: 'Dana Analyst', is_active: true, roles,
      created_at: match.created_at, updated_at: match.updated_at })
    if (url.startsWith('/api/matches?')) return json(page(matches, 9))
    const total = /^\/api\/(clubs|teams|players)\?/.exec(url)?.[1]
    if (total) return json(page([], TOTALS[total]))
    if (url === '/api/matches/21/jobs?offset=0&limit=1') return json(page([running], 6))
    if (url === '/api/matches/22/jobs?offset=0&limit=1') return json(page([]))
    throw new Error(`Unexpected test request: ${url}`)
  })
  return render(<AppProviders><MemoryRouter initialEntries={['/']}><App /></MemoryRouter></AppProviders>)
}
const jobRequests = () => fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes('/jobs'))
const actionLinks = async () => within(await screen.findByRole('list', { name: 'Quick actions' })).getAllByRole('link').map((link) => link.getAttribute('href'))

beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock) })
afterEach(() => { vi.unstubAllGlobals(); setAccessToken(null) })

describe('dashboard', () => {
  it('shows real totals and the latest matches with their genuine job states', async () => {
    renderDashboard(['coach'])
    const totals = await screen.findByRole('region', { name: 'Record totals' })
    await waitFor(() => expect(within(totals).getAllByRole('link').map((link) => link.textContent))
      .toEqual(['Clubs2', 'Teams4', 'Players37', 'Matches9']))
    const latest = screen.getByRole('region', { name: 'Latest matches' })
    const [first, second] = within(latest).getAllByRole('listitem')
    expect(first).toHaveTextContent('Derby Day')
    expect(first).toHaveTextContent('North FC vs South FC')
    expect(await within(first!).findByText('Processing')).toBeVisible()
    expect(within(first!).getByText('Player tracking · 40%')).toBeVisible()
    expect(within(first!).getByRole('link', { name: 'Analytics for Derby Day' })).toHaveAttribute('href', '/matches/21/analytics')
    expect(second).toHaveTextContent('Cup Tie')
    expect(within(second!).getByText('Archived')).toBeVisible()
    expect(await within(second!).findByText('No processing yet')).toBeVisible()
    const processing = screen.getByRole('region', { name: 'Processing' })
    expect(within(processing).getByText('Queued or running').closest('li')).toHaveTextContent('1')
    expect(within(processing).getByText('No processing yet').closest('li')).toHaveTextContent('1')
    expect(jobRequests()).toEqual(['/api/matches/21/jobs?offset=0&limit=1', '/api/matches/22/jobs?offset=0&limit=1'])
  })

  it.each<[Role, string[]]>([
    ['admin', ['/matches/new', '/matches', '/matches/21/analytics', '/teams', '/players', '/admin/signup-requests']],
    ['coach', ['/matches/new', '/matches', '/matches/21/analytics', '/teams', '/players']],
    ['analyst', ['/matches/new', '/matches', '/matches/21/analytics']],
    ['club_management', ['/matches', '/matches/21/analytics']],
    ['player', ['/matches']],
  ])('offers only authorised quick actions to %s', async (role, expected) => {
    renderDashboard([role])
    await within(await screen.findByRole('region', { name: 'Latest matches' })).findByText('Derby Day')
    expect(await actionLinks()).toEqual(expected)
  })

  it('never requests jobs for roles without job access', async () => {
    renderDashboard(['player'])
    const latest = await screen.findByRole('region', { name: 'Latest matches' })
    await within(latest).findByText('Derby Day')
    expect(within(latest).queryByRole('link', { name: /^Analytics/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Processing' })).not.toBeInTheDocument()
    expect(jobRequests()).toEqual([])
  })

  it('loads each listed match job once without polling active work', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      renderDashboard(['coach'])
      await within(await screen.findByRole('region', { name: 'Processing' })).findByText('Queued or running')
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
      expect(jobRequests()).toHaveLength(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows honest empty states without requesting jobs', async () => {
    renderDashboard(['coach'], [])
    expect(await screen.findByText('No matches are available yet.')).toBeVisible()
    expect(screen.getByText('No matches to summarise yet.')).toBeVisible()
    expect(await actionLinks()).not.toContain('/matches/21/analytics')
    expect(jobRequests()).toEqual([])
  })

  it('groups queued and running jobs and counts matches without jobs', () => {
    const withStatus = (status: JobStatus): ProcessingJob => ({ ...job, status })
    expect(countStates([withStatus('queued'), withStatus('running'), withStatus('failed'), withStatus('completed_with_warnings'), undefined]))
      .toEqual({ active: 2, failed: 1, completed_with_warnings: 1, completed: 0, cancelled: 0, none: 1 })
  })
})

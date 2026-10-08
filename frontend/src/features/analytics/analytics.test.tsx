import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { AppProviders } from '../../components/AppProviders'
import { setAccessToken } from '../auth/tokenStorage'
import type { Role } from '../auth/types'
import type { ProcessingJob } from '../media/types'
import * as fixture from './__fixtures__/analytics'
import { HeatmapView } from './HeatmapPanel'
import { seriesPoints } from './series'
import type { TeamAssignment, TrackTeam } from './types'

const fetchMock = vi.fn<typeof fetch>()
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const page = <T,>(items: T[], url: URL, defaultLimit = 25) => {
  const offset = Number(url.searchParams.get('offset') ?? 0), limit = Number(url.searchParams.get('limit') ?? defaultLimit)
  return { items: items.slice(offset, offset + limit), total: items.length, offset, limit }
}
let state: {
  role: Role; matchStatus: number; missingPlayers: boolean; missingTactics: boolean; missingTrajectories: boolean
  assignments: TeamAssignment[]; jobs: ProcessingJob[]; stale: boolean
}
async function defaultApi(input: RequestInfo | URL, options?: RequestInit): Promise<Response> {
  const url = new URL(String(input), 'http://localhost'), path = url.pathname
  if (path === '/api/auth/me') return json({ ...fixture.user, roles: [state.role] })
  if (path === '/api/matches/1') return state.matchStatus === 200 ? json(fixture.match) : json({ detail: 'Match is not accessible.' }, state.matchStatus)
  if (path === '/api/matches/1/video') return json(fixture.video)
  if (path === '/api/matches/1/jobs/video-preparation') return json(null)
  if (path === '/api/matches/1/jobs') return json(page(state.jobs, url))
  if (path === '/api/matches/1/report') return json({ available: false, current: false, stale: false, job_id: null, summary: null })
  if (path === '/api/matches/1/calibration') return json(null)
  if (path === '/api/matches/1/player-analytics') return state.missingPlayers
    ? json({ detail: 'Generate player analytics first.' }, 409) : json(page(fixture.players, url))
  if (/\/player-analytics\/\d+$/.test(path)) {
    const result = fixture.players.find((row) => row.track_id === Number(path.split('/').at(-1)))
    return result ? json(result) : json({ detail: 'Track not found.' }, 404)
  }
  if (path.endsWith('/heatmap')) return path.includes('/3/') ? json(fixture.heatmap)
    : json({ ...fixture.heatmap, track_id: 17, total_occupancy_seconds: 0, observed_coverage_percent: 0, coverage_warning: 'No usable observed intervals.', cells: [] })
  if (path === '/api/matches/1/trajectories/summary') return state.missingTrajectories
    ? json({ detail: 'Current cleaned trajectories are required.' }, 409) : json(fixture.trajectories)
  if (path === '/api/matches/1/team-assignments') return json(page(state.assignments, url, 100))
  if (path === '/api/matches/1/team-analytics') return state.stale
    ? json({ detail: 'Team analytics are stale after team assignments changed.' }, 409)
    : state.missingTactics ? json({ detail: 'Generate team tactical analytics first.' }, 409) : json(fixture.tactics)
  if (path.endsWith('/series')) return json(page(path.includes('team_a') ? fixture.seriesA : fixture.seriesB, url, 100))
  if (options?.method === 'PATCH' && /\/tracks\/\d+\/team$/.test(path)) {
    const trackId = Number(path.split('/').at(-2))
    const { team } = JSON.parse(String(options.body)) as { team: TrackTeam | null }
    state.assignments = state.assignments.map((row) => row.track_id === trackId
      ? { ...row, manual_team: team, effective_team: team ?? row.automatic_team, updated_by_user_id: 1, updated_at: '2026-10-04T13:00:00Z' } : row)
    state.stale = true
    return json(state.assignments.find((row) => row.track_id === trackId))
  }
  if (options?.method === 'POST' && path.includes('/jobs/')) {
    const job: ProcessingJob = { ...fixture.job, id: 13, job_type: path.endsWith('team-tactical-analytics') ? 'team_tactical_analytics' : 'player_analytics',
      status: 'queued', progress_percent: 0, current_stage: 'queued' }
    state.jobs = [job, ...state.jobs]
    return json(job, 202)
  }
  return json({ detail: 'Unexpected fixture request.' }, 404)
}
function Navigation() {
  const navigate = useNavigate()
  return <button onClick={() => void navigate('/matches/2/analytics')}>Test: another match</button>
}
function renderPage(path = '/matches/1/analytics', authenticated = true) {
  setAccessToken(authenticated ? 'analytics-test-token' : null)
  return render(<AppProviders><MemoryRouter initialEntries={[path]}><App /><Navigation /></MemoryRouter></AppProviders>)
}
async function openTab(name: string) { fireEvent.click(await screen.findByRole('tab', { name })) }
const panel = (name: string) => within(screen.getByRole('region', { name }))
const requests = (pattern: RegExp) => fetchMock.mock.calls.filter(([url]) => pattern.test(String(url)))
function expectMetric(region: ReturnType<typeof within>, label: string, value: string) {
  expect(region.getByText(label).nextElementSibling).toHaveTextContent(value)
}
beforeEach(() => {
  state = { role: 'coach', matchStatus: 200, missingPlayers: false, missingTactics: false, missingTrajectories: false,
    assignments: structuredClone(fixture.assignments), jobs: [fixture.job, { ...fixture.job, id: 12, job_type: 'team_tactical_analytics' }], stale: false }
  setAccessToken(null)
  fetchMock.mockReset().mockImplementation(defaultApi)
  vi.stubGlobal('fetch', fetchMock)
  // The browser integration check uses real layout; jsdom has no layout observer.
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    return new DOMRect(0, 0, 640, this.classList.contains('recharts-legend-wrapper') ? 20 : 280)
  })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('analytics routing and authorization', () => {
  it('requires authentication without fetching any match analytics', async () => {
    renderPage(undefined, false)
    expect(await screen.findByRole('heading', { name: 'Sign in to FOOTLYTICS' })).toBeVisible()
    expect(requests(/\/matches\//)).toHaveLength(0)
  })
  it('opens the authorized dashboard from Match Details without starting jobs', async () => {
    renderPage('/matches/1')
    fireEvent.click(await screen.findByRole('link', { name: 'View Analytics' }))
    await vi.dynamicImportSettled()
    expect(await screen.findByRole('heading', { name: 'Analysis overview' })).toBeVisible()
    await waitFor(() => expectMetric(panel('Analysis overview'), 'Analyzed tracks', '2'))
    expectMetric(panel('Analysis overview'), 'Pitch dimensions', '40 × 20 m')
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
  })
  it.each([403, 404])('handles denied/cross-club match status %s without fetching analytics', async (status) => {
    state.matchStatus = status
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Match is not accessible.')
    expect(requests(/\/(player-analytics|team-analytics|team-assignments)/)).toHaveLength(0)
  })
  it('rejects the Player role before requesting match data', async () => {
    state.role = 'player'; renderPage()
    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeVisible()
    expect(requests(/\/matches\//)).toHaveLength(0)
  })
  it('does not show Players an analytics entry point', async () => {
    state.role = 'player'; renderPage('/matches/1')
    await screen.findByRole('heading', { name: fixture.match.title })
    expect(screen.queryByRole('link', { name: 'View Analytics' })).not.toBeInTheDocument()
  })
  it('supports keyboard tab navigation', async () => {
    renderPage()
    const overview = await screen.findByRole('tab', { name: 'Overview' })
    overview.focus(); fireEvent.keyDown(overview, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'Players' })).toHaveFocus()
    expect(screen.getByRole('tab', { name: 'Players' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Players' }), { key: 'End' })
    expect(screen.getByRole('tab', { name: 'Team Assignments' })).toHaveFocus()
  })
  it('clears analytics on session expiry', async () => {
    fetchMock.mockImplementation((input, options) => String(input).includes('/player-analytics')
      ? Promise.resolve(json({ detail: 'Expired session.' }, 401)) : defaultApi(input, options))
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Sign in to FOOTLYTICS' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Match Analytics' })).not.toBeInTheDocument()
  })
})

describe('player metrics and selection', () => {
  it('renders API values, null speeds, effective teams and Unknown without invented identities', async () => {
    renderPage(); await openTab('Players')
    await screen.findByRole('button', { name: 'View Track 3' })
    const row3 = within(screen.getByRole('button', { name: 'View Track 3' }).closest('tr')!)
    expect(row3.getByText('123.5 m')).toBeVisible()
    expect(row3.getByText('1:05')).toBeVisible()
    expect(row3.getByText('6.8 km/h')).toBeVisible()
    expect(row3.getByText('27.0 km/h')).toBeVisible()
    expect(row3.getByText('30.5 m')).toBeVisible()
    expect(row3.getByText('Team A')).toBeVisible()
    const row17 = within(screen.getByRole('button', { name: 'View Track 17' }).closest('tr')!)
    expect(row17.getAllByText('Unavailable')).toHaveLength(2)
    expect(row17.getByText('Unknown')).toBeVisible()
  })
  it('sorts the current page without changing backend metrics and leaves nulls last', async () => {
    renderPage(); await openTab('Players')
    fireEvent.change(await screen.findByLabelText('Sort current page'), { target: { value: 'total_distance_metres' } })
    const order = () => panel('Player metrics table').getAllByRole('button').map((button) => button.textContent)
    expect(order()).toEqual(['Track 17', 'Track 3'])
    fireEvent.click(screen.getByRole('button', { name: 'Reverse sort order' }))
    expect(order()).toEqual(['Track 3', 'Track 17'])
    fireEvent.change(screen.getByLabelText('Sort current page'), { target: { value: 'max_speed_kmh' } })
    expect(order()).toEqual(['Track 3', 'Track 17'])
    expect(requests(/\/player-analytics\?/)).toHaveLength(1)
  })
  it('selects the correct track details and does not retain the preceding track during loading', async () => {
    renderPage(); await openTab('Players')
    fireEvent.click(await screen.findByRole('button', { name: 'View Track 3' }))
    await screen.findByRole('button', { name: 'View Track 3 heatmap' })
    const details = panel('Track 3 details')
    for (const [label, value] of [['Total distance', '123.5 m'], ['Active duration', '1:05'], ['Average speed', '6.8 km/h'],
      ['Maximum speed', '27.0 km/h'], ['Sprint count', '2'], ['Sprint distance', '30.5 m'], ['Sprint duration', '4.2 s'], ['Segments', '2'], ['Usable observations', '101']]) {
      expectMetric(details, label!, value!)
    }
    let finish!: (response: Response) => void
    fetchMock.mockImplementation((input, options) => String(input).endsWith('/player-analytics/17')
      ? new Promise((resolve) => { finish = resolve }) : defaultApi(input, options))
    fireEvent.click(screen.getByRole('button', { name: 'View Track 17' }))
    expect(await screen.findByText('Loading track details…')).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Track 3 details' })).not.toBeInTheDocument()
    expect(panel('Track 17 details').queryByText('123.5 m')).not.toBeInTheDocument()
    finish(json(fixture.players[1]))
    await screen.findByRole('button', { name: 'View Track 17 heatmap' })
    expectMetric(panel('Track 17 details'), 'Total distance', '0.0 m')
    expect(requests(/\/player-analytics\/17$/)).toHaveLength(1)
  })
  it('does not reuse a previous match or selected track on navigation', async () => {
    renderPage(); await openTab('Players')
    fireEvent.click(await screen.findByRole('button', { name: 'View Track 3' }))
    await screen.findByRole('button', { name: 'View Track 3 heatmap' })
    fetchMock.mockImplementation((input, options) => {
      const path = new URL(String(input), 'http://localhost').pathname
      if (path === '/api/matches/2') return Promise.resolve(json({ ...fixture.match, id: 2, title: 'Other match' }))
      if (path === '/api/matches/2/video') return Promise.resolve(json({ ...fixture.video, id: 22, match_id: 2 }))
      if (path === '/api/matches/2/jobs') return Promise.resolve(json({ items: [], total: 0, offset: 0, limit: 25 }))
      return defaultApi(input, options)
    })
    fireEvent.click(screen.getByRole('button', { name: 'Test: another match' }))
    expect(await screen.findByText('Other match')).toBeVisible()
    await openTab('Players')
    expect(await screen.findByText('Player analytics have not been generated yet.')).toBeVisible()
    expect(screen.queryByText('123.5 m')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Track 3 details' })).not.toBeInTheDocument()
  })
  it('distinguishes unavailable assignment data from known Unknown labels', async () => {
    fetchMock.mockImplementation((input, options) => String(input).includes('/team-assignments')
      ? Promise.resolve(json({ detail: 'Assignments are stale.' }, 409)) : defaultApi(input, options))
    renderPage(); await openTab('Players')
    expect(await screen.findAllByText('Team unavailable')).toHaveLength(2)
    expect(panel('Player metrics table').queryByText('Unknown')).not.toBeInTheDocument()
  })
})

describe('observed occupancy heatmaps', () => {
  it('uses the backend pitch dimensions and cell bounds without swapping X and Y', () => {
    render(<HeatmapView data={fixture.heatmap} />)
    const pitch = screen.getByRole('img', { name: 'Track 3 occupancy heatmap, 40 by 20 metres' })
    expect(pitch).toHaveAttribute('viewBox', '0 0 40 20')
    const cells = pitch.querySelectorAll('rect[data-x-bin]')
    expect(cells).toHaveLength(2)
    expect(cells[0]).toHaveAttribute('x', '10'); expect(cells[0]).toHaveAttribute('y', '10')
    expect(cells[0]).toHaveAttribute('width', '10'); expect(cells[0]).toHaveAttribute('height', '5')
    expect(cells[1]).toHaveAttribute('x', '30'); expect(cells[1]).toHaveAttribute('y', '0')
    expect(cells[1]).toHaveAttribute('data-occupancy-fraction', '0.8')
    expect(cells[0]?.getAttribute('fill')).not.toEqual(cells[1]?.getAttribute('fill'))
    expect(screen.getByLabelText('Occupancy intensity legend')).toHaveTextContent('0–80.0%')
  })
  it('loads only the selected track heatmap and explicitly handles empty occupancy', async () => {
    renderPage(); await openTab('Players')
    fireEvent.click(await screen.findByRole('button', { name: 'View Track 3' }))
    fireEvent.click(await screen.findByRole('button', { name: 'View Track 3 heatmap' }))
    expect(await screen.findByRole('img', { name: /Track 3 occupancy heatmap/ })).toBeVisible()
    fireEvent.change(screen.getByLabelText('Heatmap Track ID'), { target: { value: '17' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load heatmap' }))
    expect(await screen.findByText('No observed heatmap occupancy is available for Track 17.')).toBeVisible()
    expect(screen.queryByRole('img', { name: /occupancy heatmap/ })).not.toBeInTheDocument()
    expect(requests(/\/player-analytics\/17\/heatmap$/)).toHaveLength(1)
  })
  it('does not request an invalid track ID', async () => {
    renderPage(); await openTab('Heatmap')
    fireEvent.change(screen.getByLabelText('Heatmap Track ID'), { target: { value: '-2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load heatmap' }))
    expect(screen.getByRole('alert')).toHaveTextContent('positive whole Track ID')
    expect(requests(/\/heatmap$/)).toHaveLength(0)
  })
  it('reports an absent track without reusing another track heatmap', async () => {
    fetchMock.mockImplementation((input, options) => String(input).endsWith('/player-analytics/999/heatmap')
      ? Promise.resolve(json({ detail: 'Track not found in current player analytics.' }, 404)) : defaultApi(input, options))
    renderPage(); await openTab('Heatmap')
    fireEvent.change(screen.getByLabelText('Heatmap Track ID'), { target: { value: '999' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load heatmap' }))
    expect(await screen.findByText('Track not found in current player analytics.')).toBeVisible()
    expect(screen.queryByRole('img', { name: /occupancy heatmap/ })).not.toBeInTheDocument()
  })
})

describe('descriptive team tactics', () => {
  it('shows width along Y, depth along X and separate geometric metrics for both teams', async () => {
    renderPage(); await openTab('Team Tactics')
    await screen.findByRole('region', { name: 'Team A' })
    for (const [label, value] of [['Average width', '9.2 m'], ['Average depth', '16.8 m'], ['Average centroid (X, Y)', '14.25, 8.50 m'],
      ['Compactness radius', '6.4 m'], ['Average player spacing', '10.8 m'], ['Team footprint (convex hull)', '50.5 m²'], ['Bounding-box area', '154.6 m²']]) {
      expectMetric(panel('Team A'), label!, value!)
    }
    expectMetric(panel('Team B'), 'Average width', '5.6 m')
    expectMetric(panel('Team B'), 'Average depth', '11.2 m')
    expectMetric(panel('Team B'), 'Team footprint (convex hull)', 'Unavailable')
    expect(panel('Team A').getByText('Range along pitch width (Y).')).toBeVisible()
    expect(panel('Team A').getByText('Range along pitch length (X).')).toBeVisible()
  })
  it('maps observed frames without interpolation and keeps insufficient/null metrics as gaps', () => {
    expect(seriesPoints(fixture.seriesA, fixture.seriesB, 'width_metres')).toEqual([
      { frame: 0, seconds: 0, a: 9.2, b: 5.6 }, { frame: 30, seconds: 1, a: null, b: 5.6 },
      { frame: 60, seconds: 2, a: 12.8, b: 5.6 }, { frame: 90, seconds: 3, a: 10.6, b: 5.6 },
    ])
    expect(seriesPoints([{ ...fixture.snapshot, sufficient_players: false }], [], 'centroid_x')[0]?.a).toBeNull()
    expect(seriesPoints([{ ...fixture.snapshot, width_metres: null }], [], 'width_metres')[0]?.a).toBeNull()
  })
  it('renders bounded series with a real null gap and changes centroid axes using backend values', async () => {
    renderPage(); await openTab('Team Tactics')
    await screen.findByText('View chart values')
    const chart = screen.getByRole('region', { name: 'Width over time' })
    await waitFor(() => expect(chart.querySelectorAll('.recharts-line')).toHaveLength(2))
    // Team A has one isolated point and one two-point segment, separated by null.
    const curve = chart.querySelector('.recharts-line-curve')?.getAttribute('d')
    expect(curve?.match(/M/g)).toHaveLength(2)
    expect(requests(/\/series\?/)).toHaveLength(2)
    for (const [url] of requests(/\/series\?/)) {
      expect(String(url)).toContain('limit=100'); expect(String(url)).toContain('offset=0')
    }
    const values = screen.getByText('View chart values').closest('details')!
    fireEvent.click(screen.getByText('View chart values')); values.open = true
    expect(within(values).getByRole('row', { name: '30 1.00 s Unavailable 5.60 m' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Tactical series metric'), { target: { value: 'centroid_x' } })
    expect(screen.getByRole('region', { name: 'Centroid X (length axis) over time' })).toBeInTheDocument()
    expect(within(values).getByRole('row', { name: '0 0.00 s 14.25 m 25.50 m' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Tactical series metric'), { target: { value: 'centroid_y' } })
    expect(within(values).getByRole('row', { name: '0 0.00 s 8.50 m 12.25 m' })).toBeInTheDocument()
    expect(requests(/\/series\?/)).toHaveLength(2)
  })
  it('rejects series when a different tactical publication appears during loading', async () => {
    let summaries = 0
    fetchMock.mockImplementation((input, options) => String(input).endsWith('/team-analytics')
      ? Promise.resolve(json({ ...fixture.tactics, job_id: ++summaries === 1 ? 12 : 99 })) : defaultApi(input, options))
    renderPage(); await openTab('Team Tactics')
    expect(await screen.findByText('Team tactics changed. Refresh analytics to load the current result.')).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Width over time' })).not.toBeInTheDocument()
  })
  it('handles empty series without fake chart points', async () => {
    fetchMock.mockImplementation((input, options) => String(input).includes('/series?')
      ? Promise.resolve(json({ items: [], total: 0, offset: 0, limit: 100 })) : defaultApi(input, options))
    renderPage(); await openTab('Team Tactics')
    expect(await screen.findByText('No observed snapshots are available in this result.')).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Width over time' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next window' })).toBeDisabled()
  })
})

describe('manual team assignment review', () => {
  it.each([['team_a', 'Team A'], ['team_b', 'Team B'], ['unknown', 'Unknown']] as const)('saves an explicit %s override for the selected track', async (team, label) => {
    renderPage(); await openTab('Team Assignments')
    fireEvent.change(await screen.findByLabelText('Override Track 17'), { target: { value: team } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Track 17 override' }))
    expect(await screen.findByText(`Saved Track 17 assignment. Effective team: ${label}.`)).toBeVisible()
    expect(screen.getByText(`Manual: ${label}`)).toBeVisible()
    const mutation = fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')!
    expect(String(mutation[0])).toMatch(/\/tracks\/17\/team$/)
    expect(JSON.parse(String(mutation[1]?.body))).toEqual({ team })
  })
  it.each(['admin', 'coach', 'analyst'] as const)('lets %s intentionally edit a track', async (role) => {
    state.role = role; renderPage(); await openTab('Team Assignments')
    expect(await screen.findByLabelText('Override Track 3')).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Save Track 3 override' })).toBeDisabled()
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'PATCH')).toHaveLength(0)
  })
  it('gives Club Management read-only assignments and processing', async () => {
    state.role = 'club_management'; renderPage()
    expect(await screen.findByText(/Read-only analytics/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Generate Player Analytics' })).not.toBeInTheDocument()
    await openTab('Team Assignments')
    expect(await screen.findByText('Read-only assignment review.')).toBeVisible()
    expect(screen.queryByLabelText('Override Track 3')).not.toBeInTheDocument()
    expect(panel('Team assignment table').getByText('90.0%')).toBeVisible()
  })
  it('refreshes effective labels, clears overrides and invalidates tactics without refetching physical analytics', async () => {
    renderPage(); await openTab('Players')
    await screen.findByRole('button', { name: 'View Track 3' })
    const physicalRequests = requests(/\/player-analytics/).length
    const tacticalRequests = requests(/\/team-analytics$/).length
    await openTab('Team Assignments')
    fireEvent.change(await screen.findByLabelText('Override Track 3'), { target: { value: 'team_b' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Track 3 override' }))
    expect(await screen.findByText('Saved Track 3 assignment. Effective team: Team B.')).toBeVisible()
    expect(screen.getByText('Manual: Team B')).toBeVisible()
    const mutation = fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')!
    expect(String(mutation[0])).toMatch(/\/matches\/1\/tracks\/3\/team$/)
    expect(JSON.parse(String(mutation[1]?.body))).toEqual({ team: 'team_b' })
    expect(requests(/\/team-analytics$/).length).toBeGreaterThan(tacticalRequests)
    await openTab('Team Tactics')
    expect(await screen.findByText('Team assignments changed. Regenerate team tactical analytics.')).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Team A' })).not.toBeInTheDocument()
    await openTab('Players')
    expect(await screen.findByRole('button', { name: 'View Track 3' })).toBeVisible()
    expect(requests(/\/player-analytics/)).toHaveLength(physicalRequests)
    await openTab('Team Assignments')
    fireEvent.click(await screen.findByRole('button', { name: 'Clear Track 3 override' }))
    expect(await screen.findByText('Saved Track 3 assignment. Effective team: Team A.')).toBeVisible()
    const last = fetchMock.mock.calls.filter(([, options]) => options?.method === 'PATCH').at(-1)!
    expect(JSON.parse(String(last[1]?.body))).toEqual({ team: null })
    expect(screen.queryByRole('button', { name: 'Clear Track 3 override' })).not.toBeInTheDocument()
  })
  it('keeps automatic/effective labels unchanged while saving and on a rejected mutation', async () => {
    let finish!: (response: Response) => void
    fetchMock.mockImplementation((input, options) => options?.method === 'PATCH'
      ? new Promise((resolve) => { finish = resolve }) : defaultApi(input, options))
    renderPage(); await openTab('Team Assignments')
    fireEvent.change(await screen.findByLabelText('Override Track 17'), { target: { value: 'team_a' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save Track 17 override' }))
    expect(await screen.findByText('Saving Track 17 assignment…')).toBeVisible()
    expect(screen.queryByText('Manual: Team A')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Override Track 3')).toBeDisabled()
    finish(json({ detail: 'This match is read-only.' }, 403))
    expect(await screen.findByRole('alert')).toHaveTextContent('Assignment was not saved. This match is read-only.')
    expect(screen.queryByText(/Saved Track/)).not.toBeInTheDocument()
    expect(screen.queryByText('Manual: Team A')).not.toBeInTheDocument()
    expect(requests(/\/team-analytics$/)).toHaveLength(1)
  })
})

describe('availability and queued analytics', () => {
  it('shows missing prerequisites and missing analytics rather than fabricated zero metrics', async () => {
    state.missingPlayers = state.missingTactics = state.missingTrajectories = true
    renderPage()
    expect(await screen.findByText('Player analytics have not been generated yet.')).toBeVisible()
    expect(await screen.findByText('Team tactical analytics have not been generated yet.')).toBeVisible()
    expectMetric(panel('Analysis overview'), 'Analyzed tracks', 'Unavailable')
    expect(screen.getByText(/Current trajectory cleaning must be completed first/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Generate Player Analytics' })).toBeDisabled()
  })
  it('requires team assignments for team tactics while leaving physical analytics available', async () => {
    state.assignments = []; renderPage()
    expect(await screen.findByText(/Current team assignments are required/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Generate Team Tactical Analytics' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Generate Player Analytics' })).toBeEnabled()
  })
  it.each(['Player Analytics', 'Team Tactical Analytics'] as const)('explicitly queues %s and prevents overlapping jobs', async (type) => {
    renderPage()
    const button = await screen.findByRole('button', { name: `Generate ${type}` })
    await waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button)
    await waitFor(() => expect(requests(new RegExp(`/jobs/${type.toLowerCase().replaceAll(' ', '-')}$`))).toHaveLength(1))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Generate Player Analytics' })).toBeDisabled())
    expect(screen.getByRole('button', { name: 'Generate Team Tactical Analytics' })).toBeDisabled()
  })
  it('polls real progress and refreshes physical results once a job completes', async () => {
    state.jobs = [{ ...fixture.job, id: 13, status: 'running', current_stage: 'reading_trajectories', progress_percent: 42 }]
    renderPage()
    const progress = await screen.findByRole('progressbar', { name: 'Player analytics progress' })
    expect(progress).toHaveAttribute('value', '42')
    expect(screen.getByText('Stage: reading trajectories')).toBeVisible()
    await waitFor(() => expect(requests(/\/player-analytics\?/)).toHaveLength(1))
    state.jobs = [{ ...state.jobs[0]!, status: 'completed', progress_percent: 100, current_stage: 'completed' }]
    await waitFor(() => expect(requests(/\/player-analytics\?/)).toHaveLength(2), { timeout: 4000 })
    expect(screen.queryByRole('progressbar', { name: 'Player analytics progress' })).not.toBeInTheDocument()
    const terminalRequests = requests(/\/jobs\?/).length
    await new Promise((resolve) => setTimeout(resolve, 2200))
    expect(requests(/\/jobs\?/)).toHaveLength(terminalRequests)
  })
  it('does not submit duplicate analytics jobs while the first request is pending', async () => {
    let finish!: (response: Response) => void
    fetchMock.mockImplementation((input, options) => options?.method === 'POST'
      ? new Promise((resolve) => { finish = resolve }) : defaultApi(input, options))
    renderPage()
    const button = await screen.findByRole('button', { name: 'Generate Player Analytics' })
    await waitFor(() => expect(button).toBeEnabled()); fireEvent.click(button)
    expect(await screen.findByRole('button', { name: 'Submitting…' })).toBeDisabled()
    fireEvent.click(button)
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
    finish(json({ ...fixture.job, id: 13, status: 'queued', progress_percent: 0 }, 202))
    await screen.findByRole('button', { name: 'Generate Player Analytics' })
  })
  it('shows safe job failures and retries through the existing job API', async () => {
    state.jobs = [{ ...fixture.job, status: 'failed', error_message: 'Source changed. Regenerate analytics.' }]
    renderPage()
    expect(await screen.findByText('Source changed. Regenerate analytics.')).toBeVisible()
    const retry = await screen.findByRole('button', { name: 'Retry Player analytics job 11' })
    await waitFor(() => expect(retry).toBeEnabled()); fireEvent.click(retry)
    await waitFor(() => expect(requests(/\/jobs\/11\/retry$/)).toHaveLength(1))
  })
  it('reports queue failure without claiming generation succeeded', async () => {
    fetchMock.mockImplementation((input, options) => options?.method === 'POST'
      ? Promise.resolve(json({ detail: 'Do not show internal server trace /storage/private.csv' }, 503)) : defaultApi(input, options))
    renderPage()
    const button = await screen.findByRole('button', { name: 'Generate Player Analytics' })
    await waitFor(() => expect(button).toBeEnabled()); fireEvent.click(button)
    expect(await screen.findByRole('alert')).toHaveTextContent('The processing queue is unavailable.')
    expect(screen.queryByText(/private.csv/)).not.toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
  it('removes displayed stale metrics on refresh', async () => {
    renderPage(); await openTab('Players')
    await screen.findByRole('button', { name: 'View Track 3' })
    fetchMock.mockImplementation((input, options) => String(input).includes('/player-analytics')
      ? Promise.resolve(json({ detail: 'Player analytics are stale after source replacement.' }, 409)) : defaultApi(input, options))
    fireEvent.click(screen.getByRole('button', { name: 'Refresh analytics' }))
    await openTab('Players')
    expect(await screen.findByText('Player analytics need to be regenerated.')).toBeVisible()
    expect(screen.queryByText('123.5 m')).not.toBeInTheDocument()
  })
})


describe('honest observed coverage', () => {
  it('displays the backend percentage without recomputing it and labels a short fragment', () => {
    render(<HeatmapView data={{ ...fixture.heatmap, total_occupancy_seconds: 12, observed_coverage_percent: 4.1,
      coverage_warning: 'Short track fragment (under 15 seconds); this is not complete player positioning.' }} />)
    expect(screen.getByText('12.0 s / 300.0 s')).toBeVisible()
    expect(screen.getByText('4.1%')).toBeVisible()
    expect(screen.getByText(/Short track fragment/)).toBeVisible()
  })
  it('keeps coverage visible for empty heatmaps and unknown video duration', () => {
    render(<HeatmapView data={{ ...fixture.heatmap, cells: [], total_occupancy_seconds: 0,
      video_duration_seconds: null, observed_coverage_percent: null, coverage_warning: 'No usable observed intervals.' }} />)
    expect(screen.getByText('0.0 s / Unavailable')).toBeVisible()
    expect(screen.getByText('Unavailable')).toBeVisible()
    expect(screen.getByText(/No observed heatmap occupancy/)).toBeVisible()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})


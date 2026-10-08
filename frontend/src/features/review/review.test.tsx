import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { AppProviders } from '../../components/AppProviders'
import { setAccessToken } from '../auth/tokenStorage'
import type { Role, User } from '../auth/types'
import type { FootballMatch } from '../football/types'
import type { MatchVideo, ProcessingJob } from '../media/types'
import type { DetectionReviewSummary, TrackingReviewSummary } from './types'

// Synthetic API/image fixtures only. Backend review tests decode and annotate real frames.
const date = '2026-10-01T12:00:00Z'
const user: User = { id: 1, email: 'review@example.com', full_name: 'Review Coach', roles: ['coach'], is_active: true, created_at: date, updated_at: date }
const club = { id: 1, name: 'Review Club', is_active: true }
const match: FootballMatch = { id: 1, club_id: 1, club, title: 'Review Test Match', team_a_id: 1, team_b_id: 2,
  team_a: { id: 1, club_id: 1, name: 'Team A', is_active: true }, team_b: { id: 2, club_id: 1, name: 'Team B', is_active: true },
  match_format: '11v11', match_date: date, pitch_length_metres: 105, pitch_width_metres: 68, venue: null, notes: null,
  is_archived: false, created_by_user_id: 1, created_by: { id: 1, full_name: 'Review Coach' }, created_at: date, updated_at: date }
const video: MatchVideo = { id: 2, match_id: 1, original_filename: 'match.mp4', file_size_bytes: 1024,
  width: 640, height: 480, fps: 30, duration_seconds: 1, frame_count: 30, mime_type: 'video/mp4',
  codec: 'h264', container_format: 'mp4', uploaded_by_user_id: 1, sha256: null, warning_message: null, created_at: date, updated_at: date }
const base = { job_updated_at: date, status: 'completed' as const, video_id: 2, processed_frames: 15, frame_stride: 2,
  first_frame: 0, last_frame: 28, frame_width: 640, frame_height: 480 }
const detection: DetectionReviewSummary = { ...base, job_id: 3, total_detections: 30, average_detections_per_processed_frame: 2 }
const tracking: TrackingReviewSummary = { ...base, job_id: 4, unique_tracks: 2, tracked_rows: 28, average_visible_tracks_per_frame: 28 / 15 }
const job: ProcessingJob = { id: 3, match_id: 1, video_id: 2, job_type: 'player_detection', status: 'completed', progress_percent: 100,
  current_stage: 'completed', created_by_user_id: 1, started_at: date, finished_at: date, error_message: null, warning_message: null,
  retry_count: 0, created_at: date, updated_at: date }
const fetchMock = vi.fn<typeof fetch>()
const createObjectURL = vi.fn<(blob: Blob) => string>()
const revokeObjectURL = vi.fn<(url: string) => void>()
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
let state: { role: Role; video: MatchVideo | null; detection: DetectionReviewSummary | null; tracking: TrackingReviewSummary | null; jobs: ProcessingJob[] }
function frameResponse(frame: number, trackingFrame: boolean, override: Record<string, string> = {}) {
  return new Response(new Uint8Array([0xff, 0xd8, 0xff, 0xd9]), { headers: {
    'Content-Type': 'image/jpeg', 'X-Video-Id': '2', 'X-Job-Id': trackingFrame ? '4' : '3', 'X-Job-Updated-At': date,
    'X-Frame-Number': String(frame), 'X-Frame-Timestamp-Seconds': String(frame / 30), 'X-Frame-Width': '640', 'X-Frame-Height': '480', ...override,
  } })
}
async function defaultApi(input: RequestInfo | URL, options?: RequestInit): Promise<Response> {
  const url = new URL(String(input), 'http://localhost')
  const path = url.pathname
  if (path === '/api/auth/me') return json({ ...user, roles: [state.role] })
  if (path === '/api/matches/1') return json(match)
  if (path === '/api/matches/1/video') return json(state.video)
  if (path === '/api/matches/1/calibration') return json({ video_id: 2, pitch_length_metres: 105, pitch_width_metres: 68 })
  if (path === '/api/matches/1/jobs/video-preparation') return json(null)
  if (path === '/api/matches/1/jobs') return json({ items: state.jobs, total: state.jobs.length, offset: 0, limit: 25 })
  if (path.endsWith('/summary')) {
    const result = path.includes('/tracking/') ? state.tracking : state.detection
    return result ? json(result) : json({ detail: 'No current results are available. Run processing first.' }, 409)
  }
  if (path.endsWith('/preview')) return frameResponse(Number(url.searchParams.get('frame_number') ?? 0), path.includes('/tracking/'))
  if (options?.method === 'POST' && path.includes('/jobs/player-')) {
    const created: ProcessingJob = { ...job, id: 5, job_type: path.endsWith('player-tracking') ? 'player_tracking' : 'player_detection', status: 'queued', progress_percent: 0, current_stage: 'queued' }
    state.jobs = [created, ...state.jobs]
    return json(created, 202)
  }
  return json({ detail: 'Unexpected fixture request' }, 404)
}
function renderPage(path = '/matches/1/review') {
  setAccessToken('review-test-token')
  return render(<AppProviders><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AppProviders>)
}
const panel = (name: string) => within(screen.getByRole('region', { name }))
beforeEach(() => {
  state = { role: 'coach', video, detection, tracking, jobs: [job, { ...job, id: 4, job_type: 'player_tracking' }] }
  setAccessToken(null)
  fetchMock.mockReset().mockImplementation(defaultApi)
  createObjectURL.mockReset().mockImplementation(() => `blob:review-${createObjectURL.mock.calls.length}`)
  revokeObjectURL.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', class extends URL { static createObjectURL = createObjectURL; static revokeObjectURL = revokeObjectURL })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('detection and tracking review', () => {
  it('opens from Match Details and displays real response summaries and protected previews', async () => {
    const page = renderPage('/matches/1')
    fireEvent.click(await screen.findByRole('link', { name: 'Player Detection & Tracking Review' }))
    expect(await screen.findByRole('img', { name: 'Player detection preview' })).toBeVisible()
    expect(await screen.findByRole('img', { name: 'Player tracking preview' })).toBeVisible()
    expect(panel('Player Detection').getByText('30')).toBeVisible()
    expect(panel('Player Tracking').getByText('28')).toBeVisible()
    expect(panel('Player Tracking').getByText('Unique tracks')).toBeVisible()
    expect(panel('Player Tracking').getByText('2')).toBeVisible()
    const request = fetchMock.mock.calls.find(([url]) => String(url).includes('/tracking/preview'))!
    expect(request[1]?.headers).toEqual({ Accept: 'image/jpeg', Authorization: 'Bearer review-test-token' })
    expect(String(request[0])).toContain('job_id=4')
    page.unmount()
    expect(revokeObjectURL).toHaveBeenCalledTimes(2)
  })

  it('steps only through processed frames and releases the preceding image', async () => {
    renderPage()
    const image = await screen.findByRole('img', { name: 'Player tracking preview' })
    const original = image.getAttribute('src')
    fireEvent.click(panel('Player Tracking').getByRole('button', { name: 'Next frame' }))
    expect(await panel('Player Tracking').findByText('Frame 2 at 0.067 s · 640 × 480 pixels')).toBeVisible()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('frame_number=2'))).toBe(true)
    expect(revokeObjectURL).toHaveBeenCalledWith(original)
  })

  it('shows missing results clearly without requesting previews or inventing totals', async () => {
    state.detection = state.tracking = null
    state.jobs = []
    renderPage()
    expect(await screen.findByText('No player detection results are available yet.')).toBeVisible()
    expect(await screen.findByText('No player tracking results are available yet.')).toBeVisible()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/preview'))).toBe(false)
    expect(screen.queryByText('Unique tracks')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run tracking' })).toBeDisabled()
  })

  it.each(['admin', 'coach', 'analyst', 'club_management'] as const)('allows review for %s with the correct action visibility', async (role) => {
    state.role = role
    renderPage()
    expect(await screen.findByRole('img', { name: 'Player tracking preview' })).toBeVisible()
    if (role === 'club_management') {
      expect(screen.getByText('Read-only review.')).toBeVisible()
      expect(screen.queryByRole('button', { name: 'Run detection' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Run tracking' })).not.toBeInTheDocument()
    } else {
      expect(screen.getByRole('button', { name: 'Run detection' })).toBeEnabled()
      expect(screen.getByRole('button', { name: 'Run tracking' })).toBeEnabled()
    }
  })

  it('denies a Player direct access without requesting CV results', async () => {
    state.role = 'player'
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeVisible()
    expect(fetchMock.mock.calls.some(([url]) => /\/(summary|preview)(\?|$)/.test(String(url)))).toBe(false)
  })

  it('hides the review link from Players', async () => {
    state.role = 'player'
    renderPage('/matches/1')
    await screen.findByRole('heading', { name: match.title })
    expect(screen.queryByRole('link', { name: 'Player Detection & Tracking Review' })).not.toBeInTheDocument()
  })

  it('removes a displayed result when refresh reports it as stale', async () => {
    renderPage()
    const image = await screen.findByRole('img', { name: 'Player tracking preview' })
    const oldUrl = image.getAttribute('src')
    fetchMock.mockImplementation((input, options) => String(input).endsWith('/tracking/summary')
      ? Promise.resolve(json({ detail: 'Tracking results are stale. Run tracking with current detections.' }, 409)) : defaultApi(input, options))
    fireEvent.click(screen.getByRole('button', { name: 'Refresh review' }))
    expect(await screen.findByText('Tracking results are stale. Run tracking with current detections.')).toBeVisible()
    expect(screen.queryByRole('img', { name: 'Player tracking preview' })).not.toBeInTheDocument()
    expect(revokeObjectURL).toHaveBeenCalledWith(oldUrl)
  })

  it('rejects preview metadata belonging to a replaced video', async () => {
    fetchMock.mockImplementation((input, options) => String(input).includes('/detections/preview')
      ? Promise.resolve(frameResponse(0, false, { 'X-Video-Id': '99' })) : defaultApi(input, options))
    renderPage()
    expect(await screen.findByText(/The source or results changed/)).toBeVisible()
    expect(screen.queryByRole('img', { name: 'Player detection preview' })).not.toBeInTheDocument()
  })

  it.each(['detection', 'tracking'] as const)('queues %s through the existing job API and disables overlapping work', async (kind) => {
    renderPage()
    await screen.findByRole('img', { name: 'Player tracking preview' })
    fireEvent.click(screen.getByRole('button', { name: `Run ${kind}` }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, options]) => String(url).endsWith(`/jobs/player-${kind}`) && options?.method === 'POST')).toBe(true))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Run detection' })).toBeDisabled())
    expect(screen.getByRole('button', { name: 'Run tracking' })).toBeDisabled()
  })

  it('labels detection and tracking jobs correctly in Match Details', async () => {
    renderPage('/matches/1')
    fireEvent.click(await screen.findByText('Processing History', { exact: true }))
    expect(await screen.findByRole('article', { name: 'Player detection job 3' })).toBeVisible()
    expect(await screen.findByRole('article', { name: 'Player tracking job 4' })).toBeVisible()
    expect(screen.queryByRole('article', { name: 'Video preparation job 3' })).not.toBeInTheDocument()
  })
})

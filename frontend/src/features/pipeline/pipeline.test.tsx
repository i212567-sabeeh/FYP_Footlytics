import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { ApiError } from '../../api/client'
import { AppProviders } from '../../components/AppProviders'
import { job, match, user, video } from '../analytics/__fixtures__/analytics'
import { setAccessToken } from '../auth/tokenStorage'
import type { Role } from '../auth/types'
import type { JobType, ProcessingJob } from '../media/types'
import { nextAction, resolveCalibration, resolveJobStage, resolveReport, type StageKey, type StageState, type StageView } from './model'

// Explicit fixtures; production stage states always come from backend responses.
const at = (type: JobType, status: ProcessingJob['status'], extra: Partial<ProcessingJob> = {}): ProcessingJob =>
  ({ ...job, id: 40, job_type: type, status, video_id: video.id, error_message: null, warning_message: null, ...extra })
const ok = <T,>(data: T) => ({ data, error: null })
const fail = (status: number, message: string) => ({ data: undefined, error: new ApiError(status, message) })
const views = (states: Partial<Record<StageKey, StageState>>, base: StageState = 'completed') => Object.fromEntries(
  (['video', 'video_preparation', 'calibration', 'player_detection', 'player_tracking', 'team_classification', 'coordinate_mapping',
    'trajectory_cleaning', 'player_analytics', 'team_tactical_analytics', 'match_report'] as StageKey[])
    .map((key): [StageKey, StageView] => [key, { key, state: states[key] ?? base, job: at('player_tracking', 'failed', { id: 9 }) }])) as Record<StageKey, StageView>

describe('pipeline status interpretation', () => {
  it('trusts current results, not old successful jobs', () => {
    const done = at('player_detection', 'completed')
    expect(resolveJobStage('player_detection', [done], ok({ status: 'completed', video_id: video.id }), video.id).state).toBe('completed')
    expect(resolveJobStage('player_detection', [done], ok({ status: 'completed_with_warnings', video_id: video.id }), video.id).state).toBe('completed_with_warnings')
    expect(resolveJobStage('player_detection', [at('player_detection', 'completed_with_warnings', { warning_message: 'Weak calibration.' })], ok({ video_id: video.id }), video.id))
      .toMatchObject({ state: 'completed_with_warnings', detail: 'Weak calibration.' })
    expect(resolveJobStage('player_detection', [done], fail(409, 'The current result artifact or source video is missing or invalid.'), video.id).state).toBe('stale')
    expect(resolveJobStage('player_detection', [], fail(409, 'Detections are stale for this calibration.'), video.id).state).toBe('stale')
    expect(resolveJobStage('player_detection', [done], ok({ status: 'completed', video_id: 99 }), video.id).state).toBe('stale')
    expect(resolveJobStage('player_detection', [], fail(404, 'Not generated'), video.id).state).toBe('not_started')
    expect(resolveJobStage('player_detection', [], fail(500, 'Server error'), video.id)).toMatchObject({ state: 'unknown', detail: 'Server error' })
    expect(resolveJobStage('player_detection', [], { data: undefined, error: null }, video.id).state).toBe('checking')
  })

  it('reports running, failed and superseded attempts from the latest job', () => {
    const running = resolveJobStage('player_tracking', [at('player_tracking', 'running', { progress_percent: 45, current_stage: 'tracking_players' })], fail(404, 'x'), video.id)
    expect(running).toMatchObject({ state: 'running', detail: '45% complete · tracking players' })
    expect(resolveJobStage('player_tracking', [at('player_tracking', 'failed', { error_message: 'Worker stopped.' })], fail(409, 'No tracking yet'), video.id))
      .toMatchObject({ state: 'failed', detail: 'Worker stopped.' })
    expect(resolveJobStage('player_tracking', [at('player_tracking', 'failed')], ok({ video_id: video.id }), video.id))
      .toMatchObject({ state: 'completed', detail: 'The latest attempt did not finish; the saved result is still current.' })
  })

  it('checks calibration and report currency', () => {
    const saved = { video_id: video.id, pitch_length_metres: match.pitch_length_metres, pitch_width_metres: match.pitch_width_metres }
    expect(resolveCalibration(ok(saved) as never, video, match).state).toBe('completed')
    expect(resolveCalibration(ok({ ...saved, pitch_length_metres: 90 }) as never, video, match).state).toBe('stale')
    expect(resolveCalibration(ok(null), video, match).state).toBe('not_started')
    const report = (status: { current: boolean; stale: boolean; available: boolean }) => resolveReport([], ok({ ...status, job_id: null }) as never).state
    expect([report({ current: true, stale: false, available: true }), report({ current: false, stale: true, available: true }),
      report({ current: false, stale: false, available: false })]).toEqual(['completed', 'stale', 'not_started'])
  })

  it('suggests only the first runnable stage and never guesses', () => {
    expect(nextAction(views({ video: 'not_started' }), undefined)).toEqual({ kind: 'upload' })
    expect(nextAction(views({}), at('player_detection', 'running'))).toMatchObject({ kind: 'wait' })
    expect(nextAction(views({ video: 'completed', calibration: 'stale' }, 'not_started'), undefined)).toEqual({ kind: 'calibrate', stale: true })
    expect(nextAction(views({ player_tracking: 'stale', team_classification: 'not_started' }), undefined)).toEqual({ kind: 'run', stage: 'player_tracking', stale: true })
    expect(nextAction(views({ player_tracking: 'failed' }), undefined)).toMatchObject({ kind: 'retry', stage: 'player_tracking' })
    expect(nextAction(views({ team_classification: 'not_started', coordinate_mapping: 'not_started' }), undefined)).toMatchObject({ kind: 'run', stage: 'coordinate_mapping' })
    expect(nextAction(views({ player_detection: 'checking' }), undefined)).toEqual({ kind: 'unknown' })
    expect(nextAction(views({ video_preparation: 'failed' }), undefined)).toEqual({ kind: 'done' })
  })
})

const fetchMock = vi.fn<typeof fetch>()
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const missing = (detail: string) => json({ detail }, 404)
let jobs: ProcessingJob[]
let tracking: Response

function renderMatch(role: Role) {
  setAccessToken('pipeline-token')
  fetchMock.mockImplementation(async (input, options) => {
    const url = String(input)
    if (options?.method === 'POST') return json(at('player_tracking', 'queued', { id: 50 }), 202)
    if (url === '/api/auth/me') return json({ ...user, roles: [role] })
    if (url === '/api/matches/1') return json(match)
    if (url === '/api/matches/1/video') return json(video)
    if (url.startsWith('/api/matches/1/jobs?')) return json({ items: jobs, total: jobs.length, offset: 0, limit: 25 })
    if (url === '/api/matches/1/jobs/video-preparation') return json(null)
    if (url === '/api/matches/1/calibration') return json({ id: 5, video_id: video.id, pitch_length_metres: match.pitch_length_metres, pitch_width_metres: match.pitch_width_metres })
    if (url === '/api/matches/1/detections/summary') return json({ job_id: 7, status: 'completed', video_id: video.id })
    if (url === '/api/matches/1/tracking/summary') return tracking.clone()
    if (url === '/api/matches/1/report') return json({ available: false, current: false, stale: false, job_id: null, summary: null })
    return missing('Not generated yet.')
  })
  return render(<AppProviders><MemoryRouter initialEntries={['/matches/1']}><App /></MemoryRouter></AppProviders>)
}
const stage = (region: HTMLElement, label: string) => within(region).getByText(label).closest('li')!
const posts = () => fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST').map(([url]) => String(url))

beforeEach(() => {
  fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock)
  jobs = [at('player_tracking', 'completed', { id: 8 }), at('player_detection', 'completed', { id: 7 })]
  tracking = json({ detail: 'Tracking results are stale. Run tracking with current detections.' }, 409)
})
afterEach(() => { vi.unstubAllGlobals(); setAccessToken(null) })

describe('match processing pipeline', () => {
  it('shows evidence-based stages and starts the suggested stage', async () => {
    renderMatch('coach')
    const region = await screen.findByRole('region', { name: 'Processing pipeline' })
    await waitFor(() => expect(stage(region, 'Player tracking')).toHaveTextContent('Status: Needs regeneration'))
    expect(stage(region, 'Pitch calibration')).toHaveTextContent('Status: Completed')
    expect(stage(region, 'Player detection')).toHaveTextContent('Status: Completed')
    expect(stage(region, 'Pitch coordinate mapping')).toHaveTextContent('Needs current pitch calibration and player tracking')
    expect(within(stage(region, 'Pitch coordinate mapping')).queryByRole('button')).not.toBeInTheDocument()
    expect(within(region).queryByRole('status')).not.toBeInTheDocument()
    expect(within(region).queryByRole('alert')).not.toBeInTheDocument()
    expect(within(region).queryByRole('progressbar')).not.toBeInTheDocument()
    fireEvent.click(within(region).getByRole('button', { name: 'Start Player tracking' }))
    await waitFor(() => expect(posts()).toEqual(['/api/matches/1/jobs/player-tracking']))
  })

  it('retries a failed latest attempt through the existing retry endpoint', async () => {
    jobs = [at('player_tracking', 'failed', { id: 9, error_message: 'Worker stopped.' }), at('player_detection', 'completed', { id: 7 })]
    tracking = json({ detail: 'No player tracking results are available yet.' }, 409)
    renderMatch('analyst')
    const region = await screen.findByRole('region', { name: 'Processing pipeline' })
    await waitFor(() => expect(stage(region, 'Player tracking')).toHaveTextContent('Status: Failed'))
    expect(within(region).getByText('Retry player tracking')).toBeVisible()
    fireEvent.click(within(region).getByRole('button', { name: 'Retry Player tracking now' }))
    await waitFor(() => expect(posts()).toEqual(['/api/jobs/9/retry']))
  })

  it('keeps read-only roles informed without processing controls', async () => {
    renderMatch('club_management')
    const region = await screen.findByRole('region', { name: 'Processing pipeline' })
    await waitFor(() => expect(within(region).getByText(/Read-only: an Admin, Coach or Analyst/)).toBeVisible())
    expect(within(region).queryAllByRole('button', { name: /^(Run|Regenerate|Retry|Start)/ })).toEqual([])
  })

  it('shows players no pipeline and requests no processing evidence', async () => {
    renderMatch('player')
    expect(await screen.findByRole('heading', { name: match.title })).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Processing pipeline' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => /\/(jobs|summary|report|calibration|team-assignments|player-analytics|team-analytics)/.test(String(url)))).toBe(false)
  })
})

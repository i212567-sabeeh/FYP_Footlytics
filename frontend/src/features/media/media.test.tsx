import { act, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PropsWithChildren } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { AppProviders } from '../../components/AppProviders'
import { getAccessToken, setAccessToken } from '../auth/tokenStorage'
import type { Role, User } from '../auth/types'
import type { FootballMatch } from '../football/types'
import { useMatchJobs } from './api'
import type { MatchVideo, ProcessingJob } from './types'

// Synthetic records and file bytes are confined to UI tests. Backend tests decode real fixtures.
const date = '2026-09-01T12:00:00Z'
const user: User = { id: 1, email: 'coach@example.com', full_name: 'Test Coach', roles: ['coach'], is_active: true, created_at: date, updated_at: date }
const club = { id: 1, name: 'Test Club', is_active: true }
const match: FootballMatch = { id: 1, club_id: 1, club, title: 'Test Match', team_a_id: 1, team_b_id: 2,
  team_a: { id: 1, club_id: 1, name: 'Team A', is_active: true }, team_b: { id: 2, club_id: 1, name: 'Team B', is_active: true },
  match_format: '11v11', match_date: date, pitch_length_metres: 105, pitch_width_metres: 68, venue: null, notes: null,
  is_archived: false, created_by_user_id: 1, created_by: { id: 1, full_name: 'Test Coach' }, created_at: date, updated_at: date }
const video: MatchVideo = { id: 2, match_id: 1, original_filename: 'match.mp4', file_size_bytes: 2 * 1024 ** 2,
  width: 1920, height: 1080, fps: 29.97, duration_seconds: 5534.8, frame_count: null, mime_type: 'video/mp4',
  codec: 'h264', container_format: 'mov,mp4', uploaded_by_user_id: 1, sha256: null, warning_message: null, created_at: date, updated_at: date }
const job: ProcessingJob = { id: 3, match_id: 1, video_id: 2, job_type: 'video_preparation', status: 'queued',
  progress_percent: 0, current_stage: 'queued', created_by_user_id: 1, started_at: null, finished_at: null,
  error_message: null, warning_message: null, retry_count: 0, created_at: date, updated_at: date }
const fetchMock = vi.fn<typeof fetch>()
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const page = (items: ProcessingJob[], total = items.length, offset = 0) => ({ items, total, offset, limit: 25 })

interface TestState { video: MatchVideo | null; jobs: ProcessingJob[]; role: Role; match: FootballMatch }
let state: TestState
function defaultApi(url: RequestInfo | URL, options?: RequestInit): Promise<Response> {
  const path = String(url)
  if (path === '/api/auth/me') return Promise.resolve(response({ ...user, roles: [state.role] }))
  if (path === '/api/matches/1') return Promise.resolve(response(state.match))
  if (path === '/api/matches/1/video') {
    if (options?.method === 'POST' || options?.method === 'PUT') state.video = video
    return Promise.resolve(response(state.video, options?.method === 'POST' ? 201 : 200))
  }
  if (path.startsWith('/api/matches/1/jobs?')) return Promise.resolve(response(page(state.jobs)))
  if (path === '/api/matches/1/jobs/video-preparation' && options?.method !== 'POST') {
    const rank = (item: ProcessingJob) => ['queued', 'running'].includes(item.status) ? 0 : ['completed', 'completed_with_warnings'].includes(item.status) ? 1 : 2
    const current = state.jobs.filter((item) => item.video_id === state.video?.id && item.job_type === 'video_preparation').sort((a, b) => rank(a) - rank(b) || b.id - a.id)[0] ?? null
    return Promise.resolve(response(current))
  }
  if (path === '/api/matches/1/jobs/video-preparation' || path === '/api/jobs/3/retry') {
    state.jobs = [{ ...job, retry_count: path.endsWith('retry') ? 1 : 0 }]
    return Promise.resolve(response(state.jobs[0], 202))
  }
  return Promise.resolve(response({ detail: 'Unexpected test request' }, 404))
}
function renderMatch() {
  setAccessToken('media-test-token')
  return render(<AppProviders><MemoryRouter initialEntries={['/matches/1']}><App /></MemoryRouter></AppProviders>)
}
function selectFile(name = 'match.mp4', contents = 'fixture') {
  const file = new File([contents], name, { type: 'video/mp4' })
  fireEvent.change(screen.getByLabelText(/^(Video file|Replacement video file)$/), { target: { files: [file] } })
  return file
}
beforeEach(() => {
  state = { video: null, jobs: [], role: 'coach', match }
  setAccessToken(null)
  fetchMock.mockReset().mockImplementation(defaultApi)
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('match video', () => {
  it('uploads the selected file with bearer auth and displays actual server metadata', async () => {
    let finish: (value: Response) => void = () => undefined
    fetchMock.mockImplementation((url, options) => options?.method === 'POST'
      ? new Promise((resolve) => { finish = resolve }) : defaultApi(url, options))
    renderMatch()
    expect(await screen.findByText('No match video uploaded.')).toBeVisible()
    const file = selectFile()
    expect(screen.getByText(/Selected: match.mp4 · 7 bytes/)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Upload Video' }))
    expect(await screen.findByRole('button', { name: 'Uploading…' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Uploading and validating')
    const request = fetchMock.mock.calls.find(([, options]) => options?.method === 'POST')!
    expect((request[1]?.body as FormData).get('file')).toBe(file)
    expect(request[1]?.headers).toEqual({ Accept: 'application/json', Authorization: 'Bearer media-test-token' })
    await act(async () => finish(response(video, 201)))
    expect(await screen.findByText('Video uploaded successfully.')).toBeVisible()
    expect(screen.getByText('1920 × 1080')).toBeVisible()
    expect(screen.getByText('29.97 FPS')).toBeVisible()
    expect(screen.getByText('01:32:14')).toBeVisible()
    expect(screen.getByText('2.0 MiB')).toBeVisible()
    expect(screen.getByText('h264')).toBeVisible()
    expect(screen.getByRole('link', { name: 'View Analytics' })).toHaveAttribute('href', '/matches/1/analytics')
  })

  it.each([['clip.exe', 'fixture', 'Choose an MP4'], ['empty.mp4', '', 'selected file is empty']])('rejects %s before sending it', async (name, content, message) => {
    renderMatch()
    await screen.findByLabelText('Video file')
    selectFile(name, content)
    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(screen.getByRole('button', { name: 'Upload Video' })).toBeDisabled()
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
  })

  it('requires explicit replacement and preserves the current metadata after invalid upload', async () => {
    state.video = video
    fetchMock.mockImplementation((url, options) => options?.method === 'PUT'
      ? Promise.resolve(response({ detail: 'The video does not contain a readable frame.' }, 422)) : defaultApi(url, options))
    renderMatch()
    fireEvent.click(await screen.findByRole('button', { name: 'Replace Video' }))
    expect(screen.getByText(/require future calibration and analysis/)).toBeVisible()
    selectFile('replacement.mov')
    fireEvent.click(screen.getByRole('button', { name: 'Upload replacement' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('readable frame')
    expect(screen.getByText('match.mp4')).toBeVisible()
    expect(screen.getByText('1920 × 1080')).toBeVisible()
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PUT')).toBe(true)
  })

  it.each(['admin', 'coach', 'analyst'] as const)('shows management actions for %s', async (role) => {
    state.role = role
    state.video = video
    renderMatch()
    expect(await screen.findByRole('button', { name: 'Replace Video' })).toBeVisible()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Prepare Video' })).toBeEnabled())
  })

  it.each(['club_management', 'player'] as const)('keeps video metadata read-only for %s', async (role) => {
    state.role = role
    state.video = video
    state.jobs = [{ ...job, status: 'failed', error_message: 'Stored video is missing.' }]
    renderMatch()
    expect(await screen.findByText('match.mp4')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Replace Video' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Prepare Video' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry Preparation' })).not.toBeInTheDocument()
    if (role === 'player') {
      expect(screen.queryByRole('heading', { name: 'Processing' })).not.toBeInTheDocument()
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/jobs'))).toBe(false)
    } else await waitFor(() => expect(screen.getByText('Error: Stored video is missing.')).toBeVisible())
  })

  it('keeps archived match video readable without allowing management', async () => {
    state.match = { ...match, is_archived: true }
    state.video = video
    renderMatch()
    expect(await screen.findByText('match.mp4')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Replace Video' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Prepare Video' })).not.toBeInTheDocument()
    expect(screen.getByText(/Video changes and preparation are unavailable/)).toBeVisible()
  })
})

describe('processing jobs', () => {
  beforeEach(() => { state.video = video })

  it('starts preparation and blocks duplicate preparation and replacement while queued', async () => {
    renderMatch()
    await screen.findByText('No processing jobs yet.')
    fireEvent.click(screen.getByRole('button', { name: 'Prepare Video' }))
    expect(await screen.findByText('Queued')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Preparing…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Replace Video' })).toBeDisabled()
    expect(screen.getByRole('progressbar', { name: 'Job 3 progress' })).toHaveAttribute('value', '0')
    expect(fetchMock).toHaveBeenCalledWith('/api/matches/1/jobs/video-preparation', expect.objectContaining({ method: 'POST' }))
  })

  it('displays actual stages, progress and safe errors and retries a failed job', async () => {
    state.jobs = [{ ...job, status: 'failed', progress_percent: 30, current_stage: 'validating_video', error_message: 'Stored video is missing.' }]
    renderMatch()
    await waitFor(() => expect(screen.getByText('Error: Stored video is missing.')).toBeVisible())
    expect(screen.getByText('validating video')).toBeVisible()
    expect(screen.getByText('30%')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Retry Preparation' }))
    expect(await screen.findByText('Queued')).toBeVisible()
    expect(screen.getByText(/Retries: 1/)).toBeVisible()
    expect(fetchMock).toHaveBeenCalledWith('/api/jobs/3/retry', expect.objectContaining({ method: 'POST' }))
  })

  it('refreshes persisted failures after queue unavailability and preserves the session', async () => {
    fetchMock.mockImplementation((url, options) => {
      if (options?.method === 'POST') {
        state.jobs = [{ ...job, status: 'failed', error_message: 'Queue service is unavailable.' }]
        return Promise.resolve(response({ detail: 'Internal connection information must not leak.' }, 503))
      }
      return defaultApi(url, options)
    })
    renderMatch()
    await screen.findByText('No processing jobs yet.')
    fireEvent.click(screen.getByRole('button', { name: 'Prepare Video' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('processing queue is unavailable')
    expect(await screen.findByText('Error: Queue service is unavailable.')).toBeVisible()
    expect(screen.queryByText(/Internal connection/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry Preparation' })).toBeEnabled()
    expect(getAccessToken()).toBe('media-test-token')
  })

  it('shows terminal warnings and hides retry for a replaced source video', async () => {
    state.jobs = [{ ...job, status: 'completed_with_warnings', progress_percent: 100, warning_message: 'Codec metadata is unavailable.', finished_at: date },
      { ...job, id: 4, video_id: 1, status: 'failed', error_message: 'Old source failed.' }]
    renderMatch()
    await waitFor(() => expect(screen.getByText('Completed with warnings')).toBeVisible())
    expect(screen.getByText('Warning: Codec metadata is unavailable.')).toBeVisible()
    fireEvent.click(screen.getByText('Processing History'))
    expect(screen.getByText('Earlier source video')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Retry job 4' })).not.toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('paginates older jobs without dropping the match scope', async () => {
    fetchMock.mockImplementation((url, options) => String(url).includes('/jobs?')
      ? Promise.resolve(response(page([{ ...job, id: String(url).includes('offset=25') ? 29 : 3, status: 'completed' }], 26))) : defaultApi(url, options))
    renderMatch()
    const processing = await screen.findByRole('region', { name: 'Processing' })
    fireEvent.click(await within(processing).findByText('Processing History'))
    fireEvent.click(await within(processing).findByRole('button', { name: 'Next' }))
    await waitFor(() => expect(screen.getByRole('article', { name: 'Video preparation job 29' })).toBeVisible())
    expect(fetchMock).toHaveBeenCalledWith('/api/matches/1/jobs?offset=25&limit=25', expect.anything())
  })

  it('polls queued and running jobs, then stops after completion', async () => {
    vi.useFakeTimers()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    fetchMock.mockResolvedValueOnce(response(page([job])))
      .mockResolvedValueOnce(response(page([{ ...job, status: 'running', progress_percent: 55 }])))
      .mockResolvedValue(response(page([{ ...job, status: 'completed', progress_percent: 100, finished_at: date }])))
    const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
    const { result, unmount } = renderHook(() => useMatchJobs(1, 0, true), { wrapper })
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(result.current.data?.items[0]?.status).toBe('queued')
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(result.current.data?.items[0]).toMatchObject({ status: 'running', progress_percent: 55 })
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(result.current.data?.items[0]?.status).toBe('completed')
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    unmount()
    client.clear()
  })

  it('keeps replacement and job actions blocked while browsing history with an active job', async () => {
    state.jobs = [job]
    fetchMock.mockImplementation((url, options) => String(url).includes('/jobs?')
      ? Promise.resolve(response(page(String(url).includes('offset=25')
        ? [{ ...job, id: 29, status: 'failed' }] : [job], 26))) : defaultApi(url, options))
    renderMatch()
    const processing = await screen.findByRole('region', { name: 'Processing' })
    fireEvent.click(await within(processing).findByText('Processing History'))
    fireEvent.click(await within(processing).findByRole('button', { name: 'Next' }))
    await waitFor(() => expect(screen.getByRole('article', { name: 'Video preparation job 29' })).toBeVisible())
    expect(screen.getByRole('button', { name: 'Preparing…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Replace Video' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Retry job 29' })).not.toBeInTheDocument()
  })
})


describe('current preparation state', () => {
  beforeEach(() => { state.video = video })

  it.each(['completed', 'completed_with_warnings'] as const)('keeps a %s source prepared even if it is outside the history page', async (status) => {
    state.jobs = [{ ...job, status, progress_percent: 100 }]
    fetchMock.mockImplementation((url, options) => String(url).includes('/jobs?')
      ? Promise.resolve(response(page([{ ...job, id: 44, job_type: 'player_detection', status: 'failed' }], 44))) : defaultApi(url, options))
    renderMatch()
    expect(await screen.findByRole('button', { name: 'Video Prepared ✓' })).toBeDisabled()
    expect(screen.getByRole('article', { name: 'Video preparation job 3' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Replace Video' })).toBeEnabled()
    expect(screen.getByText('Processing History').closest('details')).not.toHaveAttribute('open')
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
  })

  it('sends only one request for a rapid double click', async () => {
    let finish: (value: Response) => void = () => undefined
    fetchMock.mockImplementation((url, options) => options?.method === 'POST'
      ? new Promise((resolve) => { finish = resolve }) : defaultApi(url, options))
    renderMatch()
    const button = await screen.findByRole('button', { name: 'Prepare Video' })
    await waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button)
    fireEvent.click(button)
    expect(await screen.findByRole('button', { name: 'Preparing…' })).toBeDisabled()
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
    state.jobs = [job]
    await act(async () => finish(response(job, 202)))
    expect(await screen.findByText('Queued')).toBeVisible()
  })

  it('offers preparation for a replaced source and retains the earlier completed job in history', async () => {
    state.video = { ...video, id: 8 }
    state.jobs = [{ ...job, status: 'completed', progress_percent: 100 }]
    renderMatch()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Prepare Video' })).toBeEnabled())
    expect(screen.queryByRole('button', { name: 'Video Prepared ✓' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Processing History'))
    expect(screen.getByText('Earlier source video')).toBeVisible()
  })

  it('shows processing with a disabled action for a running preparation', async () => {
    state.jobs = [{ ...job, status: 'running', progress_percent: 55, current_stage: 'validating_video' }]
    renderMatch()
    expect(await screen.findByRole('button', { name: 'Preparing…' })).toBeDisabled()
    expect(screen.getByText('55%')).toBeVisible()
    expect(screen.getByRole('progressbar')).toHaveAttribute('value', '55')
  })
})

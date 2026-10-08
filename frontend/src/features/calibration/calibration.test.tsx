import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { AppProviders } from '../../components/AppProviders'
import { setAccessToken } from '../auth/tokenStorage'
import type { Role, User } from '../auth/types'
import type { FootballMatch } from '../football/types'
import type { MatchVideo } from '../media/types'
import type { CalibrationWrite, PitchCalibration } from './types'

// Synthetic API records and image bytes are UI fixtures only. Phase 5A tests
// verify actual JPEG decoding and homography; this suite verifies browser behavior.
const date = '2026-09-01T12:00:00Z'
const user: User = { id: 1, email: 'coach@example.com', full_name: 'Test Coach', roles: ['coach'], is_active: true, created_at: date, updated_at: date }
const club = { id: 1, name: 'Test Club', is_active: true }
const match: FootballMatch = { id: 1, club_id: 1, club, title: 'Calibration Test Match', team_a_id: 1, team_b_id: 2,
  team_a: { id: 1, club_id: 1, name: 'Team A', is_active: true }, team_b: { id: 2, club_id: 1, name: 'Team B', is_active: true },
  match_format: '5v5', match_date: date, pitch_length_metres: 60, pitch_width_metres: 36, venue: null, notes: null,
  is_archived: false, created_by_user_id: 1, created_by: { id: 1, full_name: 'Test Coach' }, created_at: date, updated_at: date }
const video: MatchVideo = { id: 2, match_id: 1, original_filename: 'match.mp4', file_size_bytes: 1024,
  width: 1920, height: 1080, fps: 30, duration_seconds: 120, frame_count: 3600, mime_type: 'video/mp4',
  codec: 'h264', container_format: 'mp4', uploaded_by_user_id: 1, sha256: null, warning_message: null, created_at: date, updated_at: date }
const calibration: PitchCalibration = { id: 3, match_id: 1, video_id: 2, source_timestamp_seconds: 12.5, source_frame_number: 375,
  image_width: 1920, image_height: 1080, pitch_length_metres: 60, pitch_width_metres: 36,
  image_points: [{ x: 192, y: 108 }, { x: 1728, y: 108 }, { x: 1728, y: 972 }, { x: 192, y: 972 }],
  pitch_points: [{ x: 0, y: 0 }, { x: 60, y: 0 }, { x: 60, y: 36 }, { x: 0, y: 36 }],
  homography_matrix: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], reprojection_error: 0.347,
  created_by_user_id: 1, created_at: date, updated_at: date }
const fetchMock = vi.fn<typeof fetch>()
const createObjectURL = vi.fn<(blob: Blob) => string>()
const revokeObjectURL = vi.fn<(url: string) => void>()
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function frameResponse(timestamp = 0, headers: Record<string, string> = {}) {
  return new Response(new Uint8Array([0xff, 0xd8, 0xff, 0xd9]), { headers: {
    'Content-Type': 'image/jpeg', 'X-Video-Id': '2', 'X-Frame-Number': String(Math.round(timestamp * 30)),
    'X-Frame-Timestamp-Seconds': String(timestamp), 'X-Frame-Width': '1920', 'X-Frame-Height': '1080', ...headers,
  } })
}
interface TestState { role: Role; video: MatchVideo | null; calibration: PitchCalibration | null; match: FootballMatch }
let state: TestState
async function defaultApi(url: RequestInfo | URL, options?: RequestInit): Promise<Response> {
  const path = String(url)
  if (path === '/api/auth/me') return response({ ...user, roles: [state.role] })
  if (path === '/api/matches/1') return response(state.match)
  if (path === '/api/matches/1/video') return response(state.video)
  if (path === '/api/matches/1/jobs/video-preparation') return response(null)
  if (path.startsWith('/api/matches/1/jobs?')) return response({ items: [], total: 0, limit: 25, offset: 0 })
  if (path.startsWith('/api/matches/1/calibration/frame?')) return frameResponse(Number(new URL(path, 'http://localhost').searchParams.get('timestamp_seconds')))
  if (path === '/api/matches/1/calibration') {
    if (options?.method === 'POST' || options?.method === 'PUT') {
      const body = JSON.parse(options.body as string) as CalibrationWrite
      state.calibration = { ...calibration, ...body, source_frame_number: Math.round(body.source_timestamp_seconds * 30) }
    }
    return response(state.calibration, options?.method === 'POST' ? 201 : 200)
  }
  return response({ detail: 'Unexpected test request' }, 404)
}
function renderPage(path = '/matches/1/calibration') {
  setAccessToken('calibration-test-token')
  return render(<AppProviders><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AppProviders>)
}
async function readyFrame(width = 1920, height = 1080) {
  const image = await screen.findByRole('img', { name: 'Calibration video frame' })
  await waitFor(() => expect(image).toHaveAttribute('src', expect.stringContaining('blob:calibration-')))
  Object.defineProperties(image, { naturalWidth: { value: width, configurable: true }, naturalHeight: { value: height, configurable: true } })
  vi.spyOn(image, 'getBoundingClientRect').mockReturnValue(new DOMRect(20, 40, 480, 270))
  fireEvent.load(image)
  const imageControl = screen.getByRole('button', { name: 'Select image landmark' })
  const pitchControl = screen.getByRole('button', { name: 'Select pitch landmark' })
  vi.spyOn(pitchControl, 'getBoundingClientRect').mockReturnValue(new DOMRect(600, 40, 400, 240))
  return { image, imageControl, pitchControl }
}
function choosePair(imageX: number, imageY: number, pitchX: number, pitchY: number) {
  fireEvent.click(screen.getByRole('button', { name: 'Select image landmark' }), { clientX: 20 + 480 * imageX, clientY: 40 + 270 * imageY })
  fireEvent.click(screen.getByRole('button', { name: 'Select pitch landmark' }), { clientX: 600 + 400 * pitchX, clientY: 40 + 240 * pitchY })
}
function chooseFour() {
  choosePair(0.1, 0.1, 0, 0)
  choosePair(0.9, 0.1, 1, 0)
  choosePair(0.9, 0.9, 1, 1)
  choosePair(0.1, 0.9, 0, 1)
}
function writes() { return fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST' || options?.method === 'PUT') }
beforeEach(() => {
  state = { role: 'coach', video, calibration: null, match }
  setAccessToken(null)
  fetchMock.mockReset().mockImplementation(defaultApi)
  createObjectURL.mockReset().mockImplementation(() => `blob:calibration-${createObjectURL.mock.calls.length}`)
  revokeObjectURL.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', class extends URL { static createObjectURL = createObjectURL; static revokeObjectURL = revokeObjectURL })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('calibration page', () => {
  it('opens from Match Details, loads an authenticated JPEG and releases its object URL on departure', async () => {
    const page = renderPage('/matches/1')
    // Match Details also renders the processing pipeline, whose result checks
    // settle one by one; allow for that under a loaded parallel test run.
    fireEvent.click(await screen.findByRole('link', { name: 'Calibrate Pitch' }, { timeout: 3000 }))
    expect(await screen.findByRole('heading', { name: 'Pitch calibration' })).toBeVisible()
    const { image } = await readyFrame()
    expect(image).toHaveAttribute('width', '1920')
    expect(screen.getByText('Frame 0 at 0.000 s · 1920 × 1080 pixels')).toBeVisible()
    expect(screen.getByRole('img', { name: 'Football pitch, 60 metres long and 36 metres wide' })).toHaveAttribute('viewBox', '0 0 60 36')
    expect(fetchMock).toHaveBeenCalledWith('/api/matches/1/calibration/frame?timestamp_seconds=0', expect.objectContaining({ headers: { Accept: 'image/jpeg', Authorization: 'Bearer calibration-test-token' } }))
    expect(createObjectURL.mock.calls[0]?.[0]).toMatchObject({ type: 'image/jpeg', size: 4 })
    const url = image.getAttribute('src')
    page.unmount()
    expect(revokeObjectURL).toHaveBeenCalledWith(url)
  })

  it('hides the Match Details link without an uploaded video', async () => {
    state.video = null
    renderPage('/matches/1')
    await screen.findByText('No match video uploaded.')
    expect(screen.queryByRole('link', { name: 'Calibrate Pitch' })).not.toBeInTheDocument()
  })

  it('handles a direct visit without video without requesting a frame', async () => {
    state.video = null
    renderPage()
    expect(await screen.findByText('Upload a match video before calibrating the pitch.')).toBeVisible()
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/calibration'))).toBe(false)
  })

  it('maps scaled frame clicks to original pixels and pitch clicks to Match metres with matching numbers', async () => {
    // Container metadata may have a different orientation from the decoded frame.
    state.video = { ...video, width: 1080, height: 1920 }
    renderPage()
    const { imageControl, pitchControl } = await readyFrame()
    expect(pitchControl).toBeDisabled()
    fireEvent.click(imageControl, { clientX: 140, clientY: 107.5 })
    expect(screen.getByText(/Point 1: image x=480.00, y=270.00 px/)).toBeVisible()
    expect(imageControl).toBeDisabled()
    expect(pitchControl).toBeEnabled()
    fireEvent.click(pitchControl, { clientX: 700, clientY: 100 })
    expect(screen.getByText('Image: x=480.00, y=270.00 px')).toBeVisible()
    expect(screen.getByText('Pitch: x=15.00, y=9.00 m')).toBeVisible()
    expect(imageControl.querySelector('text')).toHaveTextContent('1')
    expect(pitchControl.querySelector('text')).toHaveTextContent('1')
    choosePair(1, 1, 1, 1)
    expect(screen.getByText('Image: x=1919.00, y=1079.00 px')).toBeVisible()
    expect(screen.getByText('Pitch: x=60.00, y=36.00 m')).toBeVisible()
  })

  it('requires four complete pairs, accepts more, and saves ordered points for the loaded frame', async () => {
    let finish: (value: Response) => void = () => undefined
    fetchMock.mockImplementation((url, options) => options?.method === 'POST'
      ? new Promise((resolve) => { finish = resolve }) : defaultApi(url, options))
    renderPage()
    await readyFrame()
    const button = screen.getByRole('button', { name: 'Save Calibration' })
    expect(button).toBeDisabled()
    expect(screen.getByText(/4 points required minimum/)).toBeVisible()
    choosePair(0.1, 0.1, 0, 0)
    choosePair(0.9, 0.1, 1, 0)
    choosePair(0.9, 0.9, 1, 1)
    expect(button).toBeDisabled()
    choosePair(0.1, 0.9, 0, 1)
    expect(button).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Select image landmark' }), { clientX: 260, clientY: 175 })
    expect(button).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Select pitch landmark' }), { clientX: 800, clientY: 160 })
    // Editing the input alone must not silently change the frame used for these points.
    fireEvent.change(screen.getByLabelText('Timestamp (seconds)'), { target: { value: '20' } })
    fireEvent.click(button)
    expect(await screen.findByRole('button', { name: 'Saving calibration...' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Load Frame' })).toBeDisabled()
    const request = writes()[0]!
    expect(request[0]).toBe('/api/matches/1/calibration')
    const body = JSON.parse(request[1]?.body as string) as CalibrationWrite
    expect(body).toEqual({ video_id: 2, source_timestamp_seconds: 0,
      image_points: [...calibration.image_points, { x: 960, y: 540 }], pitch_points: [...calibration.pitch_points, { x: 30, y: 18 }] })
    await act(async () => finish(response({ ...calibration, ...body, source_frame_number: 0 }, 201)))
    expect(await screen.findByText('Calibration saved.')).toBeVisible()
    expect(screen.getByText('Mean reprojection error: 0.35 m')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Update Calibration' })).toBeEnabled()
  })

  it('removes incomplete or complete last points and resets both surfaces together', async () => {
    renderPage()
    const { imageControl, pitchControl } = await readyFrame()
    chooseFour()
    fireEvent.click(imageControl, { clientX: 260, clientY: 175 })
    fireEvent.click(screen.getByRole('button', { name: 'Remove last point' }))
    expect(screen.getByText(/4 complete point pairs/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Save Calibration' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Remove last point' }))
    expect(within(screen.getByRole('list', { name: 'Selected landmark pairs' })).getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByRole('button', { name: 'Save Calibration' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Reset points' }))
    expect(screen.getByText('No landmarks selected.')).toBeVisible()
    expect(imageControl.querySelectorAll('text')).toHaveLength(0)
    expect(pitchControl.querySelectorAll('text')).toHaveLength(0)
    expect(writes()).toHaveLength(0)
  })

  it('loads saved timestamp, points and backend quality, then updates only on an explicit click', async () => {
    state.calibration = calibration
    renderPage()
    await readyFrame()
    expect(screen.getByLabelText('Timestamp (seconds)')).toHaveValue(12.5)
    expect(screen.getByText('Frame 375 at 12.500 s · 1920 × 1080 pixels')).toBeVisible()
    expect(within(screen.getByRole('list', { name: 'Selected landmark pairs' })).getAllByRole('listitem')).toHaveLength(4)
    expect(screen.getByText('Mean reprojection error: 0.35 m')).toBeVisible()
    expect(writes()).toHaveLength(0)
    choosePair(0.5, 0.5, 0.5, 0.5)
    expect(screen.getByText(/This error describes the saved calibration/)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Update Calibration' }))
    expect(await screen.findByText('Calibration updated.')).toBeVisible()
    expect(writes()[0]?.[1]?.method).toBe('PUT')
    expect(screen.queryByText(/This error describes the saved calibration/)).not.toBeInTheDocument()
  })

  it('loads a selected timestamp, clears prior landmarks and revokes the old image URL', async () => {
    let finish: (value: Response) => void = () => undefined
    renderPage()
    const { image } = await readyFrame()
    const oldUrl = image.getAttribute('src')
    chooseFour()
    fetchMock.mockImplementation((url, options) => String(url).includes('timestamp_seconds=12.5')
      ? new Promise((resolve) => { finish = resolve }) : defaultApi(url, options))
    fireEvent.change(screen.getByLabelText('Timestamp (seconds)'), { target: { value: '12.5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load Frame' }))
    expect(await screen.findByText('Loading calibration frame...')).toBeVisible()
    expect(screen.getByText('No landmarks selected.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Save Calibration' })).toBeDisabled()
    expect(revokeObjectURL).toHaveBeenCalledWith(oldUrl)
    await act(async () => finish(frameResponse(12.5)))
    await readyFrame()
    chooseFour()
    fireEvent.click(screen.getByRole('button', { name: 'Save Calibration' }))
    await screen.findByText('Calibration saved.')
    expect(JSON.parse(writes()[0]?.[1]?.body as string)).toMatchObject({ source_timestamp_seconds: 12.5 })
  })

  it.each(['-1', '', '120'])('rejects invalid timestamp %s without requesting another frame', async (timestamp) => {
    renderPage()
    await readyFrame()
    fireEvent.change(screen.getByLabelText('Timestamp (seconds)'), { target: { value: timestamp } })
    fireEvent.submit(screen.getByRole('form', { name: 'Load calibration frame' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a timestamp from 0')
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/frame?'))).toHaveLength(1)
  })

  it.each(['club_management', 'player'] as const)('shows saved calibration read-only for %s', async (role) => {
    state.role = role
    state.calibration = calibration
    renderPage()
    const { imageControl, pitchControl } = await readyFrame()
    expect(screen.getByText(/Read-only calibration/)).toBeVisible()
    expect(screen.getByText('Mean reprojection error: 0.35 m')).toBeVisible()
    expect(imageControl).toBeDisabled()
    expect(pitchControl).toBeDisabled()
    expect(screen.queryByRole('button', { name: /Save Calibration|Update Calibration|Reset points|Remove last point|Load Frame/ })).not.toBeInTheDocument()
    fireEvent.click(imageControl, { clientX: 260, clientY: 175 })
    expect(writes()).toHaveLength(0)
  })

  it.each(['admin', 'coach', 'analyst'] as const)('allows accessible calibration editing for %s', async (role) => {
    state.role = role
    renderPage()
    await readyFrame()
    chooseFour()
    expect(screen.getByRole('button', { name: 'Save Calibration' })).toBeEnabled()
  })

  it.each(['archived', 'inactive'])('keeps an %s match read-only', async (condition) => {
    state.match = condition === 'archived' ? { ...match, is_archived: true } : { ...match, club: { ...club, is_active: false } }
    renderPage()
    const { imageControl } = await readyFrame()
    expect(imageControl).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save Calibration' })).not.toBeInTheDocument()
  })

  it('shows frame validation errors and allows a fresh frame request', async () => {
    fetchMock.mockImplementation((url, options) => String(url).includes('/frame?')
      ? Promise.resolve(response({ detail: 'The video does not contain a readable frame.' }, 422)) : defaultApi(url, options))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('does not contain a readable frame')
    expect(screen.getByRole('button', { name: 'Save Calibration' })).toBeDisabled()
    fetchMock.mockImplementation(defaultApi)
    fireEvent.click(screen.getByRole('button', { name: 'Load Frame' }))
    const { imageControl } = await readyFrame()
    expect(imageControl).toBeEnabled()
  })

  it('blocks points from a replaced video instead of submitting its frame under the old video ID', async () => {
    fetchMock.mockImplementation((url, options) => String(url).includes('/frame?')
      ? Promise.resolve(frameResponse(0, { 'X-Video-Id': '9' })) : defaultApi(url, options))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('source video has changed')
    expect(screen.queryByRole('img', { name: 'Calibration video frame' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save Calibration' })).toBeDisabled()
  })

  it('shows backend geometry validation without losing the selected pairs', async () => {
    fetchMock.mockImplementation((url, options) => options?.method === 'POST'
      ? Promise.resolve(response({ detail: 'Selected points cannot form a valid calibration.' }, 422)) : defaultApi(url, options))
    renderPage()
    await readyFrame()
    chooseFour()
    fireEvent.click(screen.getByRole('button', { name: 'Save Calibration' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Selected points cannot form a valid calibration.')
    expect(screen.getByText(/4 complete point pairs/)).toBeVisible()
    expect(screen.getByText('Unavailable until a calibration is saved.')).toBeVisible()
  })

  it('requires an explicit update after a create conflict for an existing stale calibration', async () => {
    fetchMock.mockImplementation((url, options) => options?.method === 'POST'
      ? Promise.resolve(response({ detail: 'A calibration already exists for this video. Use PUT to replace it.' }, 409)) : defaultApi(url, options))
    renderPage()
    await readyFrame()
    chooseFour()
    fireEvent.click(screen.getByRole('button', { name: 'Save Calibration' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('already exists')
    expect(writes()).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Update Calibration' }))
    expect(await screen.findByText('Calibration updated.')).toBeVisible()
    expect(writes().map(([, options]) => options?.method)).toEqual(['POST', 'PUT'])
  })

  it('respects a denied Match request without fetching calibration or frames', async () => {
    fetchMock.mockImplementation((url, options) => String(url) === '/api/matches/1'
      ? Promise.resolve(response({ detail: 'Match not found' }, 404)) : defaultApi(url, options))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Match not found')
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/calibration'))).toBe(false)
  })
})

describe('calibration workspace guidance', () => {
  const currentStep = () => within(screen.getByRole('list', { name: 'Calibration steps' })).getAllByRole('listitem')
    .find((item) => item.getAttribute('aria-current') === 'step')?.textContent

  it('highlights the current step and keeps frame and pitch landmarks visually distinct', async () => {
    renderPage()
    const { imageControl, pitchControl } = await readyFrame()
    expect(currentStep()).toContain('Click a landmark on the frame')
    choosePair(0.5, 0.5, 0.5, 0.5)
    expect(imageControl.querySelectorAll('circle[fill="#0f172a"]')).toHaveLength(1)
    expect(pitchControl.querySelectorAll('rect[fill="#0f172a"]')).toHaveLength(1)
    expect(pitchControl.querySelector('text')).toHaveTextContent('1')
    fireEvent.click(imageControl, { clientX: 140, clientY: 107.5 })
    expect(currentStep()).toContain('Click the same landmark on the pitch')
    fireEvent.click(pitchControl, { clientX: 700, clientY: 100 })
    choosePair(0.9, 0.1, 1, 0); choosePair(0.9, 0.9, 1, 1)
    expect(currentStep()).toContain('Save or update the calibration')
    expect(screen.getByText('Top-left (0, 0)')).toBeVisible()
    expect(screen.getByText('Bottom-right (60, 36)')).toBeVisible()
  })
  it('shows saved calibration details from the backend, including the homography', async () => {
    state.calibration = calibration
    renderPage()
    await readyFrame()
    const quality = within(screen.getByRole('region', { name: 'Saved calibration quality' }))
    for (const [label, value] of [['Landmark pairs', '4'], ['Source frame', '375 (12.500 s)'], ['Image size', '1920 × 1080 px'], ['Pitch', '60 × 36 m']]) {
      expect(quality.getByText(label!).nextElementSibling).toHaveTextContent(value!)
    }
    fireEvent.click(quality.getByText('Homography matrix (image pixels → pitch metres)'))
    expect(quality.getAllByRole('row').map((row) => row.textContent)).toEqual(['1.000000.000000.00000', '0.000001.000000.00000', '0.000000.000001.00000'])
  })
})

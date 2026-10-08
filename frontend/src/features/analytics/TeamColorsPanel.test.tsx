// Synthetic crop/API fixtures only. Real JPEG decoding is verified by backend tests.
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TeamColorsPanel, type ColorSelection } from './TeamColorsPanel'
import { job } from './__fixtures__/analytics'

const version = 'a'.repeat(64)
const fetchMock = vi.fn<typeof fetch>()
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
let samples: ColorSelection[], saved: boolean, weak: boolean, running: boolean
beforeEach(() => {
  samples = []; saved = false; weak = false; running = false
  fetchMock.mockReset().mockImplementation(async (input, options) => {
    const url = new URL(String(input), 'http://localhost')
    if (url.pathname.endsWith('/jobs')) return json({ items: running ? [{ ...job, job_type: 'team_classification', status: 'queued' }] : [], total: running ? 1 : 0, offset: 0, limit: 25 })
    if (url.pathname.endsWith('/team-colors/preview')) return json({ tracking_version: version, track_id: Number(url.searchParams.get('track_id')), frame_number: Number(url.searchParams.get('frame_number')), quality: weak ? .2 : .9, usable: !weak, rejection_reason: weak ? 'Weak color evidence.' : null, crop_data_url: 'data:image/jpeg;base64,fixture' })
    if (url.pathname.endsWith('/jobs/team-classification')) { running = true; return json({ ...job, job_type: 'team_classification', status: 'queued' }, 202) }
    if (url.pathname.endsWith('/team-colors')) {
      if (options?.method === 'PUT') { const data = JSON.parse(String(options.body)) as { samples: ColorSelection[] }; samples = data.samples; saved = true }
      if (options?.method === 'DELETE') { saved = false; return new Response(null, { status: 204 }) }
      return json({ tracking_job_id: 7, tracking_version: version, current: saved ? { id: 4, classification_mode: 'user_seeded', samples: samples.map((s, i) => ({ ...s, id: String(i), quality: .9, color: [50, 10, 20] })), prototypes: [] } : null })
    }
    return json({ detail: 'Unexpected fixture request' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())
function show(canManage = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><TeamColorsPanel matchId={1} canManage={canManage} /></QueryClientProvider>)
}
async function choose(team: string, id: number, frame: number) {
  fireEvent.change(await screen.findByLabelText('Example team'), { target: { value: team } })
  fireEvent.change(screen.getByLabelText('Example Track ID'), { target: { value: String(id) } })
  fireEvent.change(screen.getByLabelText('Example frame number'), { target: { value: String(frame) } })
  fireEvent.click(screen.getByRole('button', { name: 'Preview crop' }))
  await screen.findByRole('img', { name: `Torso crop for Track ${id}, frame ${frame}` })
}

it('previews several examples for both teams, saves versioned selections and queues classification', async () => {
  show()
  await screen.findByText('Classification mode: Automatic clustering')
  expect(screen.getByRole('button', { name: 'Save prototypes' })).toBeDisabled()
  for (const [team, id] of [['team_a', 3], ['team_b', 7]] as const) {
    for (const frame of [0, 15]) {
      await choose(team, id, frame)
      fireEvent.click(screen.getByRole('button', { name: team === 'team_a' ? 'Add to Team A' : 'Add to Team B' }))
    }
  }
  fireEvent.click(screen.getByRole('button', { name: 'Save prototypes' }))
  expect(await screen.findByText('Classification mode: User-seeded team colors')).toBeVisible()
  expect(samples).toEqual([{ team: 'team_a', track_id: 3, frame_number: 0 }, { team: 'team_a', track_id: 3, frame_number: 15 }, { team: 'team_b', track_id: 7, frame_number: 0 }, { team: 'team_b', track_id: 7, frame_number: 15 }])
  const body = JSON.parse(String(fetchMock.mock.calls.find(([, o]) => o?.method === 'PUT')?.[1]?.body))
  expect(body.tracking_version).toBe(version)
  fireEvent.click(screen.getByRole('button', { name: 'Re-run classification' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Classification queued')
  expect(screen.getByRole('button', { name: 'Classification / processing in progress…' })).toBeDisabled()
})

it('rejects weak crops and duplicate selections without granting a team', async () => {
  weak = true; show()
  await choose('team_a', 3, 0)
  expect(screen.getByText('Weak color evidence.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Add to Team A' })).toBeDisabled()
  weak = false
  await choose('team_a', 3, 1)
  fireEvent.click(screen.getByRole('button', { name: 'Add to Team A' }))
  expect(screen.getByRole('button', { name: 'Add to Team A' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Save prototypes' })).toBeDisabled()
})

it('keeps team-color setup read-only for management', async () => {
  show(false)
  expect(await screen.findByText(/Read-only. A coach or analyst/)).toBeVisible()
  expect(screen.queryByLabelText('Example Track ID')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save prototypes' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Re-run classification' })).not.toBeInTheDocument()
})

it('shows stale-input errors and prevents duplicate classification actions', async () => {
  running = true; show()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Classification / processing in progress…' })).toBeDisabled())
  fetchMock.mockImplementation(async () => json({ detail: 'Tracking changed. Refresh team-color setup.' }, 409))
  fireEvent.change(screen.getByLabelText('Example Track ID'), { target: { value: '3' } })
  fireEvent.change(screen.getByLabelText('Example frame number'), { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: 'Preview crop' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Tracking changed')
})

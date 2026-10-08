import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setAccessToken } from '../auth/tokenStorage'
import { useMatchJobs } from '../media/api'
import type { ProcessingJob } from '../media/types'
import { job as fixtureJob } from '../analytics/__fixtures__/analytics'
import { ReportsPanel } from './ReportsPanel'
import { downloadReportFile, type ReportStatus } from './api'

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const empty: ReportStatus = { available: false, current: false, stale: false, job_id: null, summary: null }
const current: ReportStatus = { available: true, current: true, stale: false, job_id: 31,
  summary: { generated_at: '2026-10-04T12:00:00Z', page_count: 8, size_bytes: 50000, player_rows: 7, team_rows: 2, heatmaps: 4, sections: ['Match information'] } }
const reportJob: ProcessingJob = { ...fixtureJob, id: 31, job_type: 'match_report', status: 'running', current_stage: 'building_pdf', progress_percent: 45 }
const fetchMock = vi.fn<typeof fetch>()
const createUrl = vi.fn(() => 'blob:report-download')
const revokeUrl = vi.fn()
let status: ReportStatus
let jobs: ProcessingJob[]
let downloadStatus: number
let downloads: string[]

function Harness({ canManage = true, poll = false, playersReady = true, teamsReady = true }: {
  canManage?: boolean; poll?: boolean; playersReady?: boolean; teamsReady?: boolean
}) {
  const query = useMatchJobs(1, 0, poll)
  return <ReportsPanel matchId={1} version="fixture" jobs={poll ? query.data?.items ?? [] : jobs} canManage={canManage} playersReady={playersReady} teamsReady={teamsReady} />
}
function panel(props: Parameters<typeof Harness>[0] = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><Harness {...props} /></QueryClientProvider>)
}
beforeEach(() => {
  status = { ...empty }; jobs = []; downloadStatus = 200; downloads = []
  setAccessToken('reports-test-token')
  createUrl.mockClear(); revokeUrl.mockClear()
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = createUrl
    static revokeObjectURL = revokeUrl
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    downloads.push(this.download)
    expect(this.href).toBe('blob:report-download')
  })
  fetchMock.mockReset().mockImplementation(async (input, options) => {
    const path = String(input)
    if (options?.method === 'POST') { jobs = [reportJob]; return json(reportJob, 202) }
    if (path.endsWith('/report')) return json(status)
    if (path.includes('/jobs?')) return json({ items: jobs, total: jobs.length, offset: 0, limit: 25 })
    if (path.endsWith('/report/file') || path.endsWith('.csv')) {
      if (downloadStatus !== 200) return json({ detail: downloadStatus >= 500 ? '/private/trace' : 'Analytics are stale. Regenerate first.' }, downloadStatus)
      const pdf = path.endsWith('/report/file')
      return new Response(pdf ? '%PDF-1.4 synthetic binary fixture' : 'track_id,effective_team\r\n1,Team A\r\n', { headers: { 'Content-Type': pdf ? 'application/pdf' : 'text/csv; charset=utf-8' } })
    }
    return json({ detail: 'Unexpected fixture request' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); setAccessToken(null) })

describe('report states and actions', () => {
  it('renders missing state and never generates automatically', async () => {
    panel()
    expect(await screen.findByText('No report generated yet.')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Reports / Exports' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Generate PDF Report' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Download PDF Report' })).toBeDisabled()
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
  })
  it('keeps Management read-only while allowing downloads', async () => {
    status = current
    panel({ canManage: false })
    expect(await screen.findByText(/Current report ·/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Generate PDF Report' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download PDF Report' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Download Player Analytics CSV' })).toBeEnabled()
  })
  it('blocks duplicate jobs and shows measured stage/progress', async () => {
    jobs = [reportJob]
    panel()
    expect(await screen.findByText(/building pdf · 45%/)).toBeVisible()
    expect(screen.getByRole('progressbar', { name: 'PDF report progress' })).toHaveAttribute('value', '45')
    expect(screen.getByRole('button', { name: 'Generate PDF Report' })).toBeDisabled()
  })
  it('keeps a current prior PDF available while regeneration runs', async () => {
    status = current; jobs = [reportJob]
    panel()
    expect(await screen.findByText(/Current report ·/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Download PDF Report' })).toBeEnabled()
  })
  it('labels stale historical reports and disables their download', async () => {
    status = { ...current, current: false, stale: true }
    panel()
    expect(await screen.findByText('Analytics have changed. Regenerate the report to include current results.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Download PDF Report' })).toBeDisabled()
  })
  it('starts a job only from an explicit Generate action', async () => {
    panel({ poll: true })
    await screen.findByText('No report generated yet.')
    fireEvent.click(screen.getByRole('button', { name: 'Generate PDF Report' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/matches/1/jobs/match-report', expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ Authorization: 'Bearer reports-test-token' }) })))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Generate PDF Report' })).toBeDisabled())
  })
  it('shows safe failure and retries the existing job', async () => {
    jobs = [{ ...reportJob, status: 'failed', error_message: 'Report generation failed. Check worker logs and storage, then retry.' }]
    panel()
    expect(await screen.findByText(/Report generation failed/)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Retry PDF Report' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/jobs/31/retry', expect.objectContaining({ method: 'POST' })))
  })
  it('refreshes report status on polled completion without requesting analytics', async () => {
    jobs = [reportJob]
    panel({ poll: true })
    await screen.findByRole('progressbar', { name: 'PDF report progress' })
    status = current
    jobs = [{ ...reportJob, status: 'completed', progress_percent: 100, current_stage: 'completed' }]
    expect(await screen.findByText(/Current report ·/, {}, { timeout: 4500 })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Download PDF Report' })).toBeEnabled()
    expect(fetchMock.mock.calls.some(([url]) => /player-analytics|team-analytics/.test(String(url)))).toBe(false)
    const count = fetchMock.mock.calls.filter(([url]) => String(url).includes('/jobs?')).length
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 2200)) })
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/jobs?'))).toHaveLength(count)
  }, 9000)
  it('summarises the current PDF and which exports are ready', async () => {
    status = current
    panel({ teamsReady: false })
    await screen.findByText(/Current report ·/)
    for (const [label, value] of [['File size', '49 KB'], ['Player rows', '7'], ['Team rows', '2'], ['Heatmaps', '4']]) {
      expect(screen.getByText(label!).nextElementSibling).toHaveTextContent(value!)
    }
    expect(screen.getByText('Needs current analytics')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Download Team Analytics CSV' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Download Player Analytics CSV' })).toBeEnabled()
  })
  it.each([['missing', empty, 'Not generated'], ['stale', { ...current, current: false, stale: true }, 'Needs regeneration'], ['current', current, 'Available']] as const)(
    'labels a %s PDF report', async (_, value, label) => {
      status = value
      panel()
      expect(await within(screen.getByRole('article', { name: 'Match PDF report' })).findByText(label)).toBeVisible()
    })
  it('disables CSV exports without their current analytics', async () => {
    panel({ playersReady: false, teamsReady: false })
    await screen.findByText('No report generated yet.')
    expect(screen.getByRole('button', { name: 'Download Player Analytics CSV' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Download Team Analytics CSV' })).toBeDisabled()
  })
})

describe('authenticated downloads', () => {
  it.each([
    ['Download PDF Report', 'report/file', 'footlytics-match-1-report.pdf'],
    ['Download Player Analytics CSV', 'exports/player-analytics.csv', 'footlytics-match-1-player-analytics.csv'],
    ['Download Team Analytics CSV', 'exports/team-analytics.csv', 'footlytics-match-1-team-analytics.csv'],
  ])('downloads %s through the protected client', async (button, route, filename) => {
    status = current
    panel()
    await screen.findByText(/Current report ·/)
    fireEvent.click(screen.getByRole('button', { name: button }))
    await waitFor(() => expect(downloads).toEqual([filename]))
    expect(fetchMock).toHaveBeenCalledWith(`/api/matches/1/${route}`, expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer reports-test-token' }) }))
    expect(createUrl).toHaveBeenCalledWith(expect.any(Blob))
    expect(document.querySelector('a[download]')).toBeNull()
    await waitFor(() => expect(revokeUrl).toHaveBeenCalledWith('blob:report-download'), { timeout: 2000 })
  })
  it.each([409, 503])('shows a safe download error for status %s', async (code) => {
    status = current; downloadStatus = code
    panel()
    await screen.findByText(/Current report ·/)
    fireEvent.click(screen.getByRole('button', { name: 'Download PDF Report' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(code === 409 ? 'Analytics are stale' : 'The server could not complete the request')
    expect(alert).not.toHaveTextContent('/private/trace')
    expect(createUrl).not.toHaveBeenCalled()
  })
  it('rejects successful responses with the wrong content type', async () => {
    fetchMock.mockResolvedValue(json({ message: 'Not a PDF' }))
    await expect(downloadReportFile(1, 'report')).rejects.toThrow('unexpected format')
    expect(createUrl).not.toHaveBeenCalled()
  })
})

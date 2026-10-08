import { apiBlobRequest } from '../../api/client'
import { mediaKey } from '../media/api'

export const reportKey = (matchId: number) => [...mediaKey(matchId), 'report'] as const
export interface ReportStatus {
  available: boolean
  current: boolean
  stale: boolean
  job_id: number | null
  summary: {
    generated_at: string
    page_count: number
    size_bytes: number
    player_rows: number
    team_rows: number
    heatmaps: number
    sections: string[]
  } | null
}
export type DownloadKind = 'report' | 'player-analytics' | 'team-analytics'

export async function downloadReportFile(matchId: number, kind: DownloadKind) {
  const pdf = kind === 'report'
  const { blob, headers } = await apiBlobRequest(`matches/${matchId}/${pdf ? 'report/file' : `exports/${kind}.csv`}`, { accept: pdf ? 'application/pdf' : 'text/csv' })
  if (!headers.get('Content-Type')?.toLowerCase().startsWith(pdf ? 'application/pdf' : 'text/csv') || blob.size === 0) {
    throw new Error('The download was empty or in an unexpected format. Refresh and try again.')
  }
  // Filenames are generated locally, never derived from untrusted response paths.
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `footlytics-match-${matchId}-${kind}.${pdf ? 'pdf' : 'csv'}`
  document.body.append(link)
  try { link.click() } finally {
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}

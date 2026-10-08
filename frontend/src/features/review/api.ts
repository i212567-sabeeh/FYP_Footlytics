import { useQuery } from '@tanstack/react-query'
import { apiBlobRequest, apiRequest } from '../../api/client'
import { mediaKey } from '../media/api'
import type { ReviewFrame, ReviewKind, ReviewSummary } from './types'

export const reviewKey = (matchId: number) => [...mediaKey(matchId), 'review'] as const

export function useReviewSummary(matchId: number, kind: ReviewKind, videoId: number | undefined, jobsVersion: string, enabled: boolean) {
  return useQuery({
    queryKey: [...reviewKey(matchId), kind, 'summary', videoId, jobsVersion],
    queryFn: ({ signal }) => apiRequest<ReviewSummary>(`matches/${matchId}/${kind}/summary`, { signal }),
    enabled: enabled && videoId !== undefined,
    retry: false,
    gcTime: 0,
  })
}

function headerNumber(headers: Headers, name: string, integer = true): number {
  const raw = headers.get(name)
  const value = raw?.trim() ? Number(raw) : NaN
  if (!Number.isFinite(value) || value < 0 || (integer && !Number.isSafeInteger(value))) {
    throw new Error('The preview metadata is incomplete. Refresh the review.')
  }
  return value
}

export async function loadReviewFrame(matchId: number, kind: ReviewKind, summary: ReviewSummary, frame: number | null, signal?: AbortSignal): Promise<ReviewFrame> {
  const params = new URLSearchParams({ job_id: String(summary.job_id), job_updated_at: summary.job_updated_at })
  if (frame !== null) params.set('frame_number', String(frame))
  const { blob, headers } = await apiBlobRequest(`matches/${matchId}/${kind}/preview?${params}`, { accept: 'image/jpeg', signal })
  if (blob.type !== 'image/jpeg' || blob.size === 0) throw new Error('The preview did not return a readable JPEG.')
  const number = headerNumber(headers, 'X-Frame-Number')
  const width = headerNumber(headers, 'X-Frame-Width'), height = headerNumber(headers, 'X-Frame-Height')
  if (headerNumber(headers, 'X-Video-Id') !== summary.video_id
    || headerNumber(headers, 'X-Job-Id') !== summary.job_id
    || Date.parse(headers.get('X-Job-Updated-At') ?? '') !== Date.parse(summary.job_updated_at)
    || width !== summary.frame_width || height !== summary.frame_height
    || number < summary.first_frame || number > summary.last_frame || (number - summary.first_frame) % summary.frame_stride !== 0
    || (frame !== null && number !== frame)) {
    throw new Error('The source or results changed. Refresh the review before loading another frame.')
  }
  return { blob, frameNumber: number, timestamp: headerNumber(headers, 'X-Frame-Timestamp-Seconds', false), width, height }
}

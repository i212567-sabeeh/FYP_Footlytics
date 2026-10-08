import { useQuery } from '@tanstack/react-query'
import { apiBlobRequest, apiRequest } from '../../api/client'
import { mediaKey } from '../media/api'
import type { CalibrationFrameData, CalibrationWrite, PitchCalibration } from './types'

export const calibrationKey = (matchId: number) => [...mediaKey(matchId), 'calibration'] as const

export function useCalibration(matchId: number, videoId: number | undefined) {
  return useQuery({
    queryKey: [...calibrationKey(matchId), videoId],
    enabled: videoId !== undefined,
    queryFn: ({ signal }) => apiRequest<PitchCalibration | null>(`matches/${matchId}/calibration`, { signal }),
    // Reopening the editor must load current saved landmarks; background refreshes
    // must not replace a user's draft while they are choosing correspondences.
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}

function frameHeader(headers: Headers, name: string, minimum: number, integer = true): number {
  const raw = headers.get(name)
  const value = raw?.trim() ? Number(raw) : NaN
  if (!Number.isFinite(value) || value < minimum || (integer && !Number.isSafeInteger(value))) {
    throw new Error('The frame metadata is incomplete. Load the frame again.')
  }
  return value
}

export async function loadCalibrationFrame(matchId: number, videoId: number, timestamp: number, signal?: AbortSignal): Promise<CalibrationFrameData> {
  const { blob, headers } = await apiBlobRequest(`matches/${matchId}/calibration/frame?timestamp_seconds=${timestamp}`, { signal, accept: 'image/jpeg' })
  if (blob.type !== 'image/jpeg' || blob.size === 0) throw new Error('The server did not return a readable JPEG frame.')
  const activeVideoId = frameHeader(headers, 'X-Video-Id', 1)
  if (activeVideoId !== videoId) throw new Error('The source video has changed. Return to Match Details and reopen calibration.')
  return {
    blob, videoId: activeVideoId,
    frameNumber: frameHeader(headers, 'X-Frame-Number', 0),
    timestamp: frameHeader(headers, 'X-Frame-Timestamp-Seconds', 0, false),
    width: frameHeader(headers, 'X-Frame-Width', 1),
    height: frameHeader(headers, 'X-Frame-Height', 1),
  }
}

export function saveCalibration(matchId: number, data: CalibrationWrite, replace: boolean) {
  return apiRequest<PitchCalibration>(`matches/${matchId}/calibration`, { method: replace ? 'PUT' : 'POST', body: data })
}

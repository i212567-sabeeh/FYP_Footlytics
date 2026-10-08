import { useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../../hooks/useAuth'
import { hasAnyRole } from '../auth/types'
import { useCapabilities } from '../football/hooks'
import type { FootballMatch } from '../football/types'
import { useMatchJobs, useMatchVideo, usePreparation } from './api'
import { isActiveJob } from './types'
import { ProcessingPanel } from './ProcessingPanel'
import { VideoPanel } from './VideoPanel'

export function MatchMediaSections({ match }: { match: FootballMatch }) {
  const { user } = useAuth()
  const capabilities = useCapabilities()
  const [offset, setOffset] = useState(0)
  const canReadJobs = hasAnyRole(user, ['admin', 'coach', 'analyst', 'club_management'])
  const canManage = capabilities.match && match.club.is_active && !match.is_archived
  const video = useMatchVideo(match.id)
  // The API puts active jobs first. Keep that page subscribed while browsing
  // history so polling and mutation guards still follow the current attempt.
  const firstPage = useMatchJobs(match.id, 0, canReadJobs)
  const historyPage = useMatchJobs(match.id, offset, canReadJobs && offset !== 0)
  const jobs = offset === 0 ? firstPage : historyPage
  const preparation = usePreparation(match.id, video.data?.id, canReadJobs && video.isSuccess)
  const active = (firstPage.data?.items.some(isActiveJob) ?? false) || Boolean(preparation.data && isActiveJob(preparation.data))

  return <>
    <VideoPanel matchId={match.id} query={video} canManage={canManage} hasActiveJob={active} />
    {video.data && !video.error && <Link className="button-secondary mt-4 inline-block" to={`/matches/${match.id}/calibration`}>Calibrate Pitch</Link>}
    {canReadJobs && <Link className="button-secondary mt-4 inline-block sm:ml-3" to={`/matches/${match.id}/review`}>Player Detection &amp; Tracking Review</Link>}
    {capabilities.match && !canManage && <p className="mt-3 text-sm text-slate-400">Video changes and preparation are unavailable for archived matches or inactive clubs.</p>}
    {canReadJobs && <ProcessingPanel matchId={match.id} videoId={video.data?.id} canManage={canManage && !video.error} hasActiveJob={active} preparation={preparation} query={jobs} offset={offset} onOffsetChange={setOffset} />}
  </>
}

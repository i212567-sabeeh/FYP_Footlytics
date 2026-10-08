import type { UseQueryResult } from '@tanstack/react-query'
import { ApiError } from '../../api/client'
import type { TeamAssignment, TrackTeam } from './types'

export type Availability = 'checking' | 'available' | 'stale' | 'missing' | 'denied' | 'error'

// Current-result endpoints answer 404/409 when no current result exists; their
// message names stale/changed/replaced inputs when regeneration is required.
const STALE = /stale|changed|replaced/i
export function availabilityOf(query: Pick<UseQueryResult, 'isPending' | 'isFetching' | 'error'>): Availability {
  const { error } = query
  if (!error) return query.isPending || query.isFetching ? 'checking' : 'available'
  if (!(error instanceof ApiError)) return 'error'
  if (error.status === 403) return 'denied'
  return [404, 409].includes(error.status) ? STALE.test(error.message) ? 'stale' : 'missing' : 'error'
}

export function resultMessage(state: Availability, name: string, assignmentsChanged = false): string {
  if (assignmentsChanged && (state === 'missing' || state === 'stale')) return 'Team assignments changed. Regenerate team tactical analytics.'
  if (state === 'stale') return `${name} need to be regenerated.`
  if (state === 'missing') return `${name} have not been generated yet.`
  return state === 'denied' ? 'Access denied for these analytics.' : `${name} could not be loaded.`
}

/** Effective-team counts over the complete assignment list (every page is loaded). */
export function assignmentCounts(rows: TeamAssignment[]) {
  const by = (team: TrackTeam) => rows.filter((row) => row.effective_team === team).length
  return { total: rows.length, team_a: by('team_a'), team_b: by('team_b'), unknown: by('unknown'), manual: rows.filter((row) => row.manual_team !== null).length }
}

/** Team identity colours used across analytics: Team A sky, Team B amber, Unknown slate. */
export const TEAM_TONES: Record<TrackTeam, { badge: string; dot: string; bar: string; text: string }> = {
  team_a: { badge: 'border-sky-400/35 bg-sky-400/10 text-sky-200', dot: 'bg-sky-400', bar: 'bg-sky-400', text: 'text-sky-200' },
  team_b: { badge: 'border-amber-400/35 bg-amber-400/10 text-amber-200', dot: 'bg-amber-400', bar: 'bg-amber-400', text: 'text-amber-200' },
  unknown: { badge: 'border-slate-500/40 bg-slate-500/10 text-slate-300', dot: 'bg-slate-400', bar: 'bg-slate-400', text: 'text-slate-300' },
}

import { useState } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Field } from '../football/ui'
import { SERIES_LIMIT, useTeamSeries } from './api'
import { metric } from './format'
import { Metric, ResultState } from './ResultState'
import { SERIES_METRICS, seriesPoints, type SeriesMetric } from './series'
import { TEAM_LABELS, type TeamAnalytics, type TeamTacticalSummary } from './types'

function TeamSummary({ team }: { team: TeamTacticalSummary }) {
  const a = team.team === 'team_a'
  return <section className="panel min-w-0" aria-labelledby={`${team.team}-summary`}>
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 id={`${team.team}-summary`} className={`text-xl font-semibold ${a ? 'text-sky-300' : 'text-amber-200'}`}>{TEAM_LABELS[team.team]}</h3>
      <span className="text-sm text-slate-400">{team.valid_snapshots ? 'Geometry available' : 'Insufficient visibility'}</span></div>
    <dl className="mt-6 grid grid-cols-2 gap-x-5 gap-y-7">
      <Metric label="Valid snapshots" value={team.valid_snapshots} /><Metric label="Insufficient snapshots" value={team.insufficient_snapshots} />
      <Metric label="Average visible players" value={metric(team.avg_visible_players, '', 1)} />
      <Metric label="Average centroid (X, Y)" value={team.avg_centroid_x === null || team.avg_centroid_y === null ? 'Unavailable' : `${metric(team.avg_centroid_x, '', 2)}, ${metric(team.avg_centroid_y, 'm', 2)}`} />
      <Metric label="Average width" value={metric(team.avg_width_metres, 'm')} hint="Range along pitch width (Y)." />
      <Metric label="Average depth" value={metric(team.avg_depth_metres, 'm')} hint="Range along pitch length (X)." />
      <Metric label="Compactness radius" value={metric(team.avg_compactness_radius_metres, 'm')} hint="Mean distance of visible players from their centroid." />
      <Metric label="Average player spacing" value={metric(team.avg_pairwise_distance_metres, 'm')} hint="Mean distance over unique player pairs." />
      <Metric label="Team footprint (convex hull)" value={metric(team.avg_convex_hull_area_m2, 'm²')} hint={`${team.hull_snapshots} snapshots with a nondegenerate hull.`} />
      <Metric label="Bounding-box area" value={metric(team.avg_bounding_box_area_m2, 'm²')} hint="Width × depth; distinct from hull area." />
      <Metric label="Centroid separation" value={metric(team.avg_centroid_distance_to_opponent_metres, 'm')} hint={`${team.both_teams_valid_snapshots} snapshots with both teams sufficient.`} />
    </dl>
  </section>
}

function TeamSeries({ matchId, version, jobId }: { matchId: number; version: string; jobId: number }) {
  const [offset, setOffset] = useState(0)
  const [selectedMetric, setMetric] = useState<SeriesMetric>('width_metres')
  const query = useTeamSeries(matchId, version, jobId, offset)
  const points = query.data ? seriesPoints(query.data.a.items, query.data.b.items, selectedMetric) : []
  const title = `${SERIES_METRICS[selectedMetric]} over time`
  return <section className="panel min-w-0" aria-labelledby="team-series-heading">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h3 id="team-series-heading" className="text-xl font-semibold">Tactical time series</h3>
      <p className="mt-2 text-sm text-slate-400">Up to {SERIES_LIMIT} observed snapshots per window. Missing values remain gaps.</p></div>
      <Field label="Tactical series metric"><select className="field-input" value={selectedMetric} onChange={(e) => setMetric(e.target.value as SeriesMetric)}>
        {Object.entries(SERIES_METRICS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></Field></div>
    <ResultState query={query} name="Team time series">{query.data && <>
      {!points.length ? <p className="analytics-state">No observed snapshots are available in this result.</p> : <>
        <h4 className="mt-6 font-medium">{title}</h4><p className="mt-1 text-xs text-slate-400">Horizontal: time (seconds) · Vertical: {SERIES_METRICS[selectedMetric].toLowerCase()} (metres)</p>
        {!points.some((p) => p.a !== null || p.b !== null) && <p className="mt-3 text-sm text-amber-200">Neither team has sufficient geometry in this window.</p>}
        <div className="mt-5 min-w-0" role="region" aria-label={title}>
          <ResponsiveContainer width="100%" height={280} minWidth={0} initialDimension={{ width: 640, height: 280 }}>
            <LineChart data={points} accessibilityLayer margin={{ top: 10, right: 12, bottom: 10, left: 0 }}>
              <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
              <XAxis dataKey="seconds" type="number" domain={['dataMin', 'dataMax']} tick={{ fill: '#94a3b8', fontSize: 12 }} tickFormatter={(value: number) => value.toFixed(1)} />
              <YAxis width={45} tick={{ fill: '#94a3b8', fontSize: 12 }} tickFormatter={(value: number) => value.toFixed(1)} />
              <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#475569', borderRadius: 8 }}
                formatter={(value) => metric(typeof value === 'number' ? value : null, 'm')}
                labelFormatter={(label) => `${Number(label).toFixed(2)} seconds`} />
              <Legend />
              <Line name="Team A" dataKey="a" stroke="#38bdf8" strokeWidth={2} dot={{ r: 2 }} connectNulls={false} isAnimationActive={false} />
              <Line name="Team B" dataKey="b" stroke="#fbbf24" strokeWidth={2} strokeDasharray="5 3" dot={{ r: 2 }} connectNulls={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <details className="mt-4"><summary className="cursor-pointer text-sm text-emerald-300">View chart values</summary>
          <div className="analytics-scroll mt-3" tabIndex={0} role="region" aria-label="Tactical series values"><table className="analytics-table">
            <caption className="sr-only">{title}; insufficient values are unavailable</caption><thead><tr><th scope="col">Frame</th><th scope="col">Time</th><th scope="col">Team A</th><th scope="col">Team B</th></tr></thead>
            <tbody>{points.map((p) => <tr key={p.frame}><th scope="row">{p.frame}</th><td>{metric(p.seconds, 's', 2)}</td><td>{metric(p.a, 'm', 2)}</td><td>{metric(p.b, 'm', 2)}</td></tr>)}</tbody>
          </table></div>
        </details>
      </>}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-400">
        <span>{points.length ? `${offset + 1}–${offset + points.length} of ${query.data.a.total} snapshots` : '0 snapshots'}</span>
        <div className="flex gap-3"><button className="button-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - SERIES_LIMIT))}>Previous window</button>
          <button className="button-secondary" disabled={offset + SERIES_LIMIT >= query.data.a.total} onClick={() => setOffset(offset + SERIES_LIMIT)}>Next window</button></div>
      </div>
    </>}</ResultState>
  </section>
}

export function TeamTacticsPanel({ matchId, version, query, assignmentsChanged }: {
  matchId: number; version: string; query: UseQueryResult<TeamAnalytics>; assignmentsChanged: boolean
}) {
  return <section aria-labelledby="tactics-heading" className="space-y-6 min-w-0">
    <div><h2 id="tactics-heading" className="text-xl font-semibold">Team tactics</h2><p className="mt-2 text-sm leading-6 text-slate-400">Descriptive geometry of visible, assigned tracks. These values do not measure tactical quality or infer attacking direction.</p></div>
    <ResultState query={query} name="Team tactical analytics" assignmentsChanged={assignmentsChanged}>{query.data && <>
      <p className="text-sm text-slate-400">Result #{query.data.job_id} · Minimum {query.data.summary.min_players_per_team} visible players per team · Equal weight per valid snapshot; insufficient snapshots are excluded.</p>
      <div className="grid min-w-0 gap-5 lg:grid-cols-2">{query.data.teams.map((team) => <TeamSummary key={team.team} team={team} />)}</div>
      <TeamSeries key={`${version}:${query.data.job_id}`} matchId={matchId} version={version} jobId={query.data.job_id} />
    </>}</ResultState>
  </section>
}

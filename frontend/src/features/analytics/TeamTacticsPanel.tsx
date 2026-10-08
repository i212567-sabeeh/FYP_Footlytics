import { useState } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartLine, Database, Network, Scale } from 'lucide-react'
import { Field } from '../football/ui'
import { SERIES_LIMIT, useTeamSeries } from './api'
import { metric } from './format'
import { TEAM_TONES } from './results'
import { Metric, MetricRow, ResultState } from './ResultState'
import { SERIES_METRICS, seriesPoints, type SeriesMetric } from './series'
import { TEAM_LABELS, type TeamAnalytics, type TeamTacticalSummary } from './types'

const count = (value: number) => value.toLocaleString('en-GB')

function DataBasis({ data }: { data: TeamAnalytics }) {
  const { summary } = data
  return <section className="panel min-w-0" aria-labelledby="tactics-basis-heading">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <h3 id="tactics-basis-heading" className="flex items-center gap-2 text-lg font-semibold"><Database aria-hidden="true" className="size-5 text-emerald-300" />Data basis</h3>
      <ul className="flex flex-wrap gap-2 text-xs text-slate-300">
        {[`Result #${data.job_id}`, `Minimum ${summary.min_players_per_team} visible players per team`, 'Equal weight per valid snapshot'].map((item) =>
          <li key={item} className="rounded-full border border-line-strong px-2.5 py-1">{item}</li>)}
      </ul>
    </div>
    <dl className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-5">
      <Metric label="Observed frames" value={count(summary.observed_frames)} hint="Frames with usable positions." />
      <Metric label="Usable positions" value={count(summary.usable_rows)} hint={`Of ${count(summary.source_rows)} trajectory rows.`} />
      <Metric label="Assigned to a team" value={count(summary.assigned_rows)} hint="Positions of Team A or Team B tracks." />
      <Metric label="Unknown team" value={count(summary.unknown_rows)} hint="Excluded from both teams' geometry." />
      <Metric label="Rejected rows" value={count(summary.rejected_rows)} hint="Not usable; excluded from every metric." />
    </dl>
  </section>
}

// Shape measures compared side by side. Bars are relative within a row only.
const COMPARISON = [
  ['Average visible players', 'avg_visible_players', ''], ['Average width', 'avg_width_metres', 'm'], ['Average depth', 'avg_depth_metres', 'm'],
  ['Compactness radius', 'avg_compactness_radius_metres', 'm'], ['Average player spacing', 'avg_pairwise_distance_metres', 'm'],
  ['Team footprint (convex hull)', 'avg_convex_hull_area_m2', 'm²'],
] as const satisfies readonly (readonly [string, keyof TeamTacticalSummary, string])[]

function TeamComparison({ teams }: { teams: TeamTacticalSummary[] }) {
  const sides = (['team_a', 'team_b'] as const).map((team) => [team, teams.find((row) => row.team === team)] as const)
  return <section className="panel min-w-0" aria-labelledby="team-comparison-heading">
    <h3 id="team-comparison-heading" className="flex items-center gap-2 text-lg font-semibold"><Scale aria-hidden="true" className="size-5 text-emerald-300" />Team comparison</h3>
    <p className="mt-1 text-sm text-slate-400">Bars compare the two teams within each row. Larger is not better: these values describe shape, not quality.</p>
    <dl className="mt-5 grid gap-x-10 gap-y-6 lg:grid-cols-2">{COMPARISON.map(([label, key, unit]) => {
      const values = sides.map(([, team]) => team?.[key] ?? null) as (number | null)[]
      const largest = Math.max(0, ...values.filter((value): value is number => value !== null && Number.isFinite(value)))
      return <div key={key} className="min-w-0">
        <dt className="text-sm font-medium text-slate-200">{label}</dt>
        <dd className="mt-2 space-y-2">{sides.map(([team], index) => {
          const value = values[index] ?? null
          return <div key={team} className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-3 text-xs">
            <span className={`font-medium ${TEAM_TONES[team].text}`}>{TEAM_LABELS[team]}</span>
            <span aria-hidden="true" className="h-2 overflow-hidden rounded-full bg-slate-800">
              {value !== null && largest > 0 && <span className={`block h-full rounded-full ${TEAM_TONES[team].bar}`} style={{ width: `${(value / largest) * 100}%` }} />}</span>
            <span className={`min-w-16 text-right tabular-nums ${value === null ? 'text-slate-500' : 'text-slate-100'}`}>{metric(value, unit, 1)}</span>
          </div>
        })}</dd>
      </div>
    })}</dl>
  </section>
}

function TeamSummary({ team, minimum }: { team: TeamTacticalSummary; minimum: number }) {
  const tone = TEAM_TONES[team.team]
  const snapshots = team.valid_snapshots + team.insufficient_snapshots
  return <section className="panel min-w-0" aria-labelledby={`${team.team}-summary`}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 id={`${team.team}-summary`} className={`flex items-center gap-2 text-xl font-semibold ${tone.text}`}>
        <span aria-hidden="true" className={`size-2.5 rounded-full ${tone.dot}`} />{TEAM_LABELS[team.team]}</h3>
      <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${team.valid_snapshots
        ? 'border-emerald-400/30 bg-emerald-400/5 text-emerald-200' : 'border-amber-400/30 bg-amber-400/5 text-amber-200'}`}>
        {team.valid_snapshots ? 'Geometry available' : 'Insufficient visibility'}</span>
    </div>
    {snapshots > 0 && <div className="mt-4">
      <span aria-hidden="true" className="flex h-2 overflow-hidden rounded-full bg-slate-800"><span className={`h-full ${tone.bar}`} style={{ width: `${(team.valid_snapshots / snapshots) * 100}%` }} /></span>
      <p className="mt-2 text-xs text-slate-400">{count(team.valid_snapshots)} of {count(snapshots)} snapshots had at least {minimum} visible players and count towards averages.</p>
    </div>}
    <dl className="mt-3 divide-y divide-line">
      <MetricRow label="Valid snapshots" value={team.valid_snapshots} /><MetricRow label="Insufficient snapshots" value={team.insufficient_snapshots} />
      <MetricRow label="Average visible players" value={metric(team.avg_visible_players, '', 1)} />
      <MetricRow label="Average centroid (X, Y)" value={team.avg_centroid_x === null || team.avg_centroid_y === null ? 'Unavailable' : `${metric(team.avg_centroid_x, '', 2)}, ${metric(team.avg_centroid_y, 'm', 2)}`} />
      <MetricRow label="Average width" value={metric(team.avg_width_metres, 'm')} hint="Range along pitch width (Y)." />
      <MetricRow label="Average depth" value={metric(team.avg_depth_metres, 'm')} hint="Range along pitch length (X)." />
      <MetricRow label="Compactness radius" value={metric(team.avg_compactness_radius_metres, 'm')} hint="Mean distance of visible players from their centroid." />
      <MetricRow label="Average player spacing" value={metric(team.avg_pairwise_distance_metres, 'm')} hint="Mean distance over unique player pairs." />
      <MetricRow label="Team footprint (convex hull)" value={metric(team.avg_convex_hull_area_m2, 'm²')} hint={`${team.hull_snapshots} snapshots with a nondegenerate hull.`} />
      <MetricRow label="Bounding-box area" value={metric(team.avg_bounding_box_area_m2, 'm²')} hint="Width × depth; distinct from hull area." />
      <MetricRow label="Centroid separation" value={metric(team.avg_centroid_distance_to_opponent_metres, 'm')} hint={`${team.both_teams_valid_snapshots} snapshots with both teams sufficient.`} />
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
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h3 id="team-series-heading" className="flex items-center gap-2 text-lg font-semibold">
      <ChartLine aria-hidden="true" className="size-5 text-emerald-300" />Tactical time series</h3>
      <p className="mt-1 text-sm text-slate-400">Up to {SERIES_LIMIT} observed snapshots per window. Missing values remain gaps.</p></div>
      <Field label="Tactical series metric"><select className="field-input" value={selectedMetric} onChange={(e) => setMetric(e.target.value as SeriesMetric)}>
        {Object.entries(SERIES_METRICS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></Field></div>
    <ResultState query={query} name="Team time series">{query.data && <>
      {!points.length ? <p className="analytics-state">No observed snapshots are available in this result.</p> : <>
        <h4 className="mt-6 font-medium">{title}</h4><p className="mt-1 text-xs text-slate-400">Horizontal: time (seconds) · Vertical: {SERIES_METRICS[selectedMetric].toLowerCase()} (metres)</p>
        {!points.some((p) => p.a !== null || p.b !== null) && <p className="mt-3 text-sm text-amber-200">Neither team has sufficient geometry in this window.</p>}
        <div className="mt-5 min-w-0 rounded-xl border border-line bg-canvas/40 p-3" role="region" aria-label={title}>
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
        <span className="tabular-nums">{points.length ? `${offset + 1}–${offset + points.length} of ${query.data.a.total} snapshots` : '0 snapshots'}</span>
        <div className="flex gap-2"><button className="button-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - SERIES_LIMIT))}>Previous window</button>
          <button className="button-secondary" disabled={offset + SERIES_LIMIT >= query.data.a.total} onClick={() => setOffset(offset + SERIES_LIMIT)}>Next window</button></div>
      </div>
    </>}</ResultState>
  </section>
}

export function TeamTacticsPanel({ matchId, version, query, assignmentsChanged }: {
  matchId: number; version: string; query: UseQueryResult<TeamAnalytics>; assignmentsChanged: boolean
}) {
  return <section aria-labelledby="tactics-heading" className="min-w-0 space-y-6">
    <div className="panel"><h2 id="tactics-heading" className="flex items-center gap-2 text-xl font-semibold"><Network aria-hidden="true" className="size-5 text-emerald-300" />Team tactics</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Descriptive geometry of visible, assigned tracks. These values do not measure tactical quality or infer attacking direction.</p>
      <ResultState query={query} name="Team tactical analytics" assignmentsChanged={assignmentsChanged} />
    </div>
    {query.data && !query.error && !query.isFetching && <>
      <DataBasis data={query.data} />
      <TeamComparison teams={query.data.teams} />
      <div className="grid min-w-0 gap-5 lg:grid-cols-2">{query.data.teams.map((team) => <TeamSummary key={team.team} team={team} minimum={query.data.summary.min_players_per_team} />)}</div>
      <TeamSeries key={`${version}:${query.data.job_id}`} matchId={matchId} version={version} jobId={query.data.job_id} />
    </>}
  </section>
}

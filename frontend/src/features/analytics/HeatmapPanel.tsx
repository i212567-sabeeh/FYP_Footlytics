import { useState } from 'react'
import { FootballPitch } from '../../components/FootballPitch'
import { Field } from '../football/ui'
import { useHeatmap } from './api'
import { duration, metric } from './format'
import { ResultState, TeamBadge } from './ResultState'
import type { ObservationCoverage, TeamAssignment, TrackHeatmap } from './types'

const COLORS = ['#164e63', '#0369a1', '#38bdf8', '#fde68a', '#f59e0b'] as const

export function CoverageSummary({ observed, data }: { observed: number; data: ObservationCoverage }) {
  return <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-4">
    <dl className="flex flex-wrap gap-x-8 gap-y-3 text-sm">
      <div><dt className="text-slate-400">Observed / video duration</dt><dd className="mt-1 font-medium tabular-nums">{metric(observed, 's')} / {metric(data.video_duration_seconds, 's')}</dd></div>
      <div><dt className="text-slate-400">Observed coverage</dt><dd className="mt-1 font-medium tabular-nums">{metric(data.observed_coverage_percent, '%')}</dd></div>
    </dl>
    {data.coverage_warning && <p className="mt-3 text-sm text-amber-200">{data.coverage_warning}</p>}
    <p className="mt-2 text-xs text-slate-400">Only usable cleaned intervals count. Unseen periods and rejected movement add no occupancy.</p>
  </div>
}

export function HeatmapView({ data }: { data: TrackHeatmap }) {
  return <><CoverageSummary observed={data.total_occupancy_seconds} data={data} /><HeatmapPlot data={data} /></>
}

function HeatmapPlot({ data }: { data: TrackHeatmap }) {
  if (!data.cells.length || data.total_occupancy_seconds <= 0) return <p className="analytics-state" role="status">No observed heatmap occupancy is available for Track {data.track_id}.</p>
  const maximum = Math.max(...data.cells.map((cell) => cell.occupancy_fraction))
  return <figure className="mt-6 min-w-0">
    <p className="mb-3 text-sm text-slate-400">X → pitch length · Y ↓ pitch width · Origin (0, 0) at top-left</p>
    <FootballPitch length={data.pitch_length_metres} width={data.pitch_width_metres}
      label={`Track ${data.track_id} occupancy heatmap, ${data.pitch_length_metres} by ${data.pitch_width_metres} metres`}
      overlay={<g aria-label="Observed occupancy cells">{data.cells.map((cell) => <rect key={`${cell.x_bin}:${cell.y_bin}`}
        data-x-bin={cell.x_bin} data-y-bin={cell.y_bin} data-occupancy-fraction={cell.occupancy_fraction}
        x={cell.x_min} y={cell.y_min} width={cell.x_max - cell.x_min} height={cell.y_max - cell.y_min}
        fill={COLORS[Math.min(4, Math.floor(cell.occupancy_fraction / maximum * 4))]}>
        <title>{`X ${cell.x_min}–${cell.x_max} m, Y ${cell.y_min}–${cell.y_max} m: ${metric(cell.occupancy_seconds, 's')} (${metric(cell.occupancy_fraction * 100, '%')})`}</title>
      </rect>)}</g>} />
    <figcaption className="mt-5 space-y-3 text-sm text-slate-400">
      <div className="flex flex-wrap items-center justify-between gap-3"><span>{data.pitch_length_metres} m length × {data.pitch_width_metres} m width · Grid {data.bins_x} × {data.bins_y}</span>
        <span>Observed occupancy: {duration(data.total_occupancy_seconds)}</span></div>
      <div aria-label="Occupancy intensity legend" className="flex flex-wrap items-center gap-3">
        <span>Low</span><span className="flex overflow-hidden rounded" aria-hidden="true">{COLORS.map((color) => <span key={color} style={{ backgroundColor: color }} className="h-3 w-8" />)}</span><span>High</span>
        <span>0–{metric(maximum * 100, '%')} of observed time per cell</span>
      </div>
      <p>Color shows relative occupancy, not performance. Empty cells have no observed occupancy. The backend assigns each valid movement interval to its starting cell; missing periods are not reconstructed. Interior pitch markings are schematic.</p>
    </figcaption>
  </figure>
}

export function HeatmapPanel({ matchId, version, selected, assignments, onSelect }: {
  matchId: number; version: string; selected: number | null; assignments: TeamAssignment[] | undefined; onSelect: (id: number) => void
}) {
  const [input, setInput] = useState(selected === null ? '' : String(selected))
  const [error, setError] = useState('')
  const query = useHeatmap(matchId, version, selected)
  return <section className="panel min-w-0" aria-labelledby="heatmap-heading">
    <h2 id="heatmap-heading" className="text-xl font-semibold">Player heatmap</h2>
    <p className="mt-2 text-sm text-slate-400">Choose a track from Players or enter a match Track ID.</p>
    <form className="mt-5 flex flex-wrap items-end gap-3" onSubmit={(event) => {
      event.preventDefault()
      const id = Number(input)
      if (!Number.isSafeInteger(id) || id <= 0) { setError('Enter a positive whole Track ID.'); return }
      setError(''); onSelect(id)
    }}>
      <Field label="Heatmap Track ID"><input className="field-input" inputMode="numeric" value={input} onChange={(event) => setInput(event.target.value)} /></Field>
      <button className="button-secondary" type="submit">Load heatmap</button>
    </form>
    {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}
    {selected === null ? <p className="analytics-state">Select a track to view its observed occupancy.</p> : <>
      <div className="mt-6 flex flex-wrap items-center gap-3"><h3 className="font-semibold">Track {selected}</h3><TeamBadge trackId={selected} assignments={assignments} /></div>
      <ResultState query={query} name="Heatmap data">{query.data && <HeatmapView data={query.data} />}</ResultState>
    </>}
  </section>
}

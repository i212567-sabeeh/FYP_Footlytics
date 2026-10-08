import { useState } from 'react'
import { Flame } from 'lucide-react'
import { FootballPitch } from '../../components/FootballPitch'
import { Field } from '../football/ui'
import { useHeatmap } from './api'
import { duration, metric } from './format'
import { ResultState, TeamBadge } from './ResultState'
import type { HeatmapCell, ObservationCoverage, TeamAssignment, TrackHeatmap } from './types'

// Five steps of a cell's occupancy relative to the busiest cell, low to high.
const COLORS = ['rgb(254 240 138 / 0.45)', 'rgb(250 204 21 / 0.62)', 'rgb(251 146 60 / 0.74)', 'rgb(239 68 68 / 0.82)', 'rgb(190 18 60 / 0.9)'] as const
const STEPS = ['< 25% of peak', '25–50%', '50–75%', '75–100%', 'Peak cell'] as const
// Bin bounds are fractions of the pitch (for example 56.666… m); show one decimal.
const bound = (metres: number) => String(Number(metres.toFixed(1)))
const cellArea = (cell: HeatmapCell) => `X ${bound(cell.x_min)}–${bound(cell.x_max)} m, Y ${bound(cell.y_min)}–${bound(cell.y_max)} m`

export function CoverageSummary({ observed, data }: { observed: number; data: ObservationCoverage }) {
  return <div className="mt-4 rounded-xl border border-line bg-canvas/40 p-4">
    <dl className="grid gap-3 text-sm sm:grid-cols-2">
      <div className="rounded-lg border border-line bg-surface px-3 py-2"><dt className="text-xs text-slate-400">Observed / video duration</dt><dd className="mt-1 font-semibold tabular-nums text-slate-100">{metric(observed, 's')} / {metric(data.video_duration_seconds, 's')}</dd></div>
      <div className="rounded-lg border border-line bg-surface px-3 py-2"><dt className="text-xs text-slate-400">Observed coverage</dt><dd className="mt-1 font-semibold tabular-nums text-slate-100">{metric(data.observed_coverage_percent, '%')}</dd></div>
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
  const busiest = [...data.cells].sort((a, b) => b.occupancy_seconds - a.occupancy_seconds).slice(0, 3)
  const line = Math.min(data.pitch_length_metres, data.pitch_width_metres) / 400
  return <figure className="mt-6 min-w-0 max-w-5xl">
    <p className="mb-2 flex flex-wrap justify-between gap-x-4 gap-y-1 text-xs text-slate-400"><span>X → pitch length · Y ↓ pitch width · Origin (0, 0) at top-left</span>
      <span className="tabular-nums">Grid {data.bins_x} × {data.bins_y} cells</span></p>
    <div className="overflow-hidden rounded-xl border border-line">
      <FootballPitch muted length={data.pitch_length_metres} width={data.pitch_width_metres}
        label={`Track ${data.track_id} occupancy heatmap, ${data.pitch_length_metres} by ${data.pitch_width_metres} metres`}
        overlay={<g aria-label="Observed occupancy cells">{data.cells.map((cell) => <rect key={`${cell.x_bin}:${cell.y_bin}`}
          data-x-bin={cell.x_bin} data-y-bin={cell.y_bin} data-occupancy-fraction={cell.occupancy_fraction}
          x={cell.x_min} y={cell.y_min} width={cell.x_max - cell.x_min} height={cell.y_max - cell.y_min}
          fill={COLORS[Math.min(4, Math.floor(cell.occupancy_fraction / maximum * 4))]} stroke="rgb(2 6 23 / 0.35)" strokeWidth={line}>
          <title>{`${cellArea(cell)}: ${metric(cell.occupancy_seconds, 's')} (${metric(cell.occupancy_fraction * 100, '%')})`}</title>
        </rect>)}</g>} />
    </div>
    <figcaption className="mt-5 grid gap-5 text-sm text-slate-400 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
      <div className="min-w-0 space-y-3">
        <div aria-label="Occupancy intensity legend">
          <div className="flex overflow-hidden rounded-md">{COLORS.map((color) => <span key={color} aria-hidden="true" style={{ backgroundColor: color }} className="h-3 flex-1" />)}</div>
          <div className="mt-1.5 grid grid-cols-5 gap-1 text-[11px] text-slate-500">{STEPS.map((step) => <span key={step}>{step}</span>)}</div>
          <p className="mt-2">0–{metric(maximum * 100, '%')} of observed time per cell</p>
        </div>
        <p className="tabular-nums">{data.pitch_length_metres} m length × {data.pitch_width_metres} m width · Observed occupancy: {duration(data.total_occupancy_seconds)}</p>
        <p className="text-xs leading-5">Color shows relative occupancy, not performance. Empty cells have no observed occupancy. The backend assigns each valid movement interval to its starting cell; missing periods are not reconstructed. Interior pitch markings are schematic.</p>
      </div>
      <div className="min-w-0 rounded-xl border border-line bg-canvas/40 p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-300">Most occupied cells</p>
        <ol className="mt-2 space-y-2">{busiest.map((cell) => <li key={`${cell.x_bin}:${cell.y_bin}`} className="flex items-center gap-3">
          <span aria-hidden="true" className="size-3 shrink-0 rounded-sm" style={{ backgroundColor: COLORS[Math.min(4, Math.floor(cell.occupancy_fraction / maximum * 4))] }} />
          <span className="min-w-0 flex-1 tabular-nums">{cellArea(cell)}</span>
          <span className="shrink-0 tabular-nums text-slate-200">{`${metric(cell.occupancy_seconds, 's')} · ${metric(cell.occupancy_fraction * 100, '%')}`}</span>
        </li>)}</ol>
      </div>
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
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h2 id="heatmap-heading" className="flex items-center gap-2 text-xl font-semibold"><Flame aria-hidden="true" className="size-5 text-emerald-300" />Player heatmap</h2>
        <p className="mt-2 text-sm text-slate-400">Choose a track from Players or enter a match Track ID.</p>
      </div>
      <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => {
        event.preventDefault()
        const id = Number(input)
        if (!Number.isSafeInteger(id) || id <= 0) { setError('Enter a positive whole Track ID.'); return }
        setError(''); onSelect(id)
      }}>
        <Field label="Heatmap Track ID"><input className="field-input w-36 py-2" inputMode="numeric" value={input} onChange={(event) => setInput(event.target.value)} /></Field>
        <button className="button-secondary" type="submit">Load heatmap</button>
      </form>
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}
    {selected === null ? <p className="analytics-state">Select a track to view its observed occupancy.</p> : <>
      <div className="mt-6 flex flex-wrap items-center gap-3"><h3 className="text-lg font-semibold">Track {selected}</h3><TeamBadge trackId={selected} assignments={assignments} /></div>
      <ResultState query={query} name="Heatmap data">{query.data && <HeatmapView data={query.data} />}</ResultState>
    </>}
  </section>
}

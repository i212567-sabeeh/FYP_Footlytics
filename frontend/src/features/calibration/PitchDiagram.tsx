import type { MouseEvent } from 'react'
import { FootballPitch } from '../../components/FootballPitch'
import { displayToPoint } from './coordinates'
import { MarkerLegend, PointMarkers } from './PointMarkers'
import type { Point } from './types'

interface Props {
  length: number
  width: number
  points: Point[]
  canSelect: boolean
  onSelect: (point: Point) => void
}

export function PitchDiagram({ length, width, points, canSelect, onSelect }: Props) {
  function select(event: MouseEvent<HTMLButtonElement>) {
    if (!canSelect) return
    const point = displayToPoint(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect(), length, width)
    if (point) onSelect(point)
  }
  // Orientation labels sit outside the button: its box must equal the pitch for click mapping.
  return <>
    <div className="flex items-end justify-between gap-2 text-[11px] tabular-nums text-slate-500">
      <span>Top-left (0, 0)</span><span className="text-slate-400">X → length, {length} m</span><span>({length}, 0)</span>
    </div>
    <button type="button" aria-label="Select pitch landmark" disabled={!canSelect} onClick={select}
      className={`mt-1 block w-full ring-1 ring-emerald-300/20 ${canSelect ? 'cursor-crosshair ring-2 ring-amber-300/70' : 'cursor-default'}`}>
      <FootballPitch length={length} width={width}>
        <PointMarkers points={points} width={length} height={width} shape="square" />
      </FootballPitch>
    </button>
    <div className="mt-1 flex items-start justify-between gap-2 text-[11px] tabular-nums text-slate-500">
      <span>(0, {width})</span><span className="text-slate-400">Y ↓ width, {width} m</span><span>Bottom-right ({length}, {width})</span>
    </div>
    <MarkerLegend shape="square" />
    <p className="mt-2 text-xs text-slate-400">Interior markings are schematic, especially for 5v5. Use known, measured landmarks on your pitch.</p>
  </>
}

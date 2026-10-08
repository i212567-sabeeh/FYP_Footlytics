import type { MouseEvent } from 'react'
import { FootballPitch } from '../../components/FootballPitch'
import { displayToPoint } from './coordinates'
import { PointMarkers } from './PointMarkers'
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
  return <>
    <p className="mb-3 text-sm text-slate-400">Top-left (0, 0) · X = length, Y = width</p>
    <button type="button" aria-label="Select pitch landmark" disabled={!canSelect} onClick={select} className="block w-full cursor-crosshair disabled:cursor-default">
      <FootballPitch length={length} width={width}>
        <PointMarkers points={points} width={length} height={width} />
      </FootballPitch>
    </button>
    <p className="mt-3 text-sm text-slate-300">{length} m length × {width} m width · Bottom-right ({length}, {width})</p>
    <p className="mt-2 text-xs text-slate-400">Interior markings are schematic, especially for 5v5. Use known, measured landmarks on your pitch.</p>
  </>
}

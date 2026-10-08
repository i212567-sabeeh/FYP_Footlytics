import { useEffect, useRef, type MouseEvent } from 'react'
import { displayToPoint } from './coordinates'
import { MarkerLegend, PointMarkers } from './PointMarkers'
import type { CalibrationFrameData, Point } from './types'

interface Props {
  frame: CalibrationFrameData
  points: Point[]
  pending: Point | null
  canSelect: boolean
  onSelect: (point: Point) => void
  onReady: () => void
  onError: (error: Error) => void
}

export function CalibrationFrame({ frame, points, pending, canSelect, onSelect, onReady, onError }: Props) {
  const image = useRef<HTMLImageElement>(null)
  useEffect(() => {
    const url = URL.createObjectURL(frame.blob)
    const element = image.current
    if (element) element.src = url
    return () => { URL.revokeObjectURL(url) }
  }, [frame.blob])

  function select(event: MouseEvent<HTMLButtonElement>) {
    if (!canSelect || !image.current) return
    const point = displayToPoint(event.clientX, event.clientY, image.current.getBoundingClientRect(), frame.width, frame.height)
    // Pixel indices end at width-1/height-1, unlike the pitch's continuous metres.
    if (point) onSelect({ x: Math.min(frame.width - 1, point.x), y: Math.min(frame.height - 1, point.y) })
  }

  return <>
    <button type="button" aria-label="Select image landmark" disabled={!canSelect} onClick={select}
      className={`relative block w-full overflow-hidden rounded-lg bg-black ring-1 ${canSelect ? 'cursor-crosshair ring-2 ring-emerald-300/60' : 'cursor-default ring-line'}`}>
      <img ref={image} alt="Calibration video frame" width={frame.width} height={frame.height} className="block h-auto w-full" draggable={false}
        onLoad={(event) => {
          if (event.currentTarget.naturalWidth !== frame.width || event.currentTarget.naturalHeight !== frame.height) {
            onError(new Error('The decoded image dimensions do not match the frame metadata. Load the frame again.'))
          } else onReady()
        }}
        onError={() => onError(new Error('The calibration frame could not be displayed. Load the frame again.'))} />
      <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox={`0 0 ${frame.width} ${frame.height}`} preserveAspectRatio="none" aria-hidden="true">
        <PointMarkers points={points} pending={pending} width={frame.width} height={frame.height} />
      </svg>
    </button>
    <p className="mt-3 text-sm tabular-nums text-slate-400">Frame {frame.frameNumber} at {frame.timestamp.toFixed(3)} s · {frame.width} × {frame.height} pixels</p>
    <MarkerLegend shape="circle" />
  </>
}

import type { ReactNode } from 'react'
import { pitchMarkings } from './pitchGeometry'

interface Props { length: number; width: number; label?: string; overlay?: ReactNode; children?: ReactNode; muted?: boolean }

/**
 * A pitch drawn in Match metres: the viewBox is exactly the playing area, X along
 * the length, Y along the width, origin top-left. Overlays and selections use the
 * same coordinates. Grass bands and interior markings are decorative/schematic.
 * `muted` dims the grass and lines so data overlays stand out.
 */
export function FootballPitch({ length, width, label, overlay, children, muted = false }: Props) {
  const marks = pitchMarkings(length, width)
  const bands = Math.max(4, Math.round(length / 7.5))
  const band = length / bands, mid = width / 2, inset = marks.line / 2
  const stroke = muted ? 'rgb(236 253 245 / 0.42)' : 'rgb(236 253 245 / 0.78)'
  const { penalty, goal } = marks
  return <svg className="block w-full" style={{ aspectRatio: `${length} / ${width}` }}
    viewBox={`0 0 ${length} ${width}`} role="img" aria-label={label ?? `Football pitch, ${length} metres long and ${width} metres wide`}>
    <desc>X runs horizontally along pitch length. Y runs vertically along pitch width. Origin is top-left. Interior markings are schematic.</desc>
    <g aria-hidden="true" pointerEvents="none">
      <rect width={length} height={width} fill={muted ? '#0a2a1a' : '#0f3a23'} />
      {Array.from({ length: bands }, (_, index) => index % 2 === 1 && <rect key={index} x={index * band} width={band} height={width} fill="rgb(255 255 255 / 0.035)" />)}
    </g>
    {overlay}
    <g fill="none" stroke={stroke} strokeWidth={marks.line} pointerEvents="none" aria-hidden="true">
      <rect x={inset} y={inset} width={length - marks.line} height={width - marks.line} />
      <line x1={length / 2} y1="0" x2={length / 2} y2={width} />
      <circle cx={length / 2} cy={mid} r={marks.centreRadius} />
      <circle cx={length / 2} cy={mid} r={marks.spot} fill={stroke} stroke="none" />
      {/* Corner arcs: the SVG viewport clips each circle to its quarter inside the pitch. */}
      {[[0, 0], [length, 0], [0, width], [length, width]].map(([x, y]) => <circle key={`${x}:${y}`} cx={x} cy={y} r={marks.corner} />)}
      {([1, -1] as const).map((direction) => {
        const goalLine = direction === 1 ? 0 : length
        const edge = goalLine + direction * penalty.depth, spot = goalLine + direction * penalty.spot
        return <g key={direction}>
          <rect x={Math.min(goalLine, edge)} y={(width - penalty.width) / 2} width={penalty.depth} height={penalty.width} />
          <rect x={Math.min(goalLine, goalLine + direction * goal.depth)} y={(width - goal.width) / 2} width={goal.depth} height={goal.width} />
          <circle cx={spot} cy={mid} r={marks.spot} fill={stroke} stroke="none" />
          {penalty.arc && <path d={`M ${edge} ${mid - penalty.arc.half} A ${marks.centreRadius} ${marks.centreRadius} 0 0 ${direction === 1 ? 1 : 0} ${edge} ${mid + penalty.arc.half}`} />}
        </g>
      })}
    </g>
    {children}
  </svg>
}

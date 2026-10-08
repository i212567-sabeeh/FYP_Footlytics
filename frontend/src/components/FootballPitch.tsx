import type { ReactNode } from 'react'

interface Props { length: number; width: number; label?: string; overlay?: ReactNode; children?: ReactNode }

export function FootballPitch({ length, width, label, overlay, children }: Props) {
  // Interior markings are schematic guides capped to fit non-standard pitches.
  // Only the supplied Match dimensions define the coordinate system.
  const penaltyDepth = Math.min(16.5, length / 4), penaltyWidth = Math.min(40.32, width * 0.8)
  const goalDepth = Math.min(5.5, length / 10), goalWidth = Math.min(18.32, width * 0.45)
  return <svg className="block w-full bg-emerald-950" style={{ aspectRatio: `${length} / ${width}` }}
    viewBox={`0 0 ${length} ${width}`} role="img" aria-label={label ?? `Football pitch, ${length} metres long and ${width} metres wide`}>
    <desc>X runs horizontally along pitch length. Y runs vertically along pitch width. Origin is top-left. Interior markings are schematic.</desc>
    {overlay}
    <g fill="none" stroke="#a7f3d0" strokeWidth={Math.min(length, width) / 200} pointerEvents="none">
      <rect x="0" y="0" width={length} height={width} />
      <line x1={length / 2} y1="0" x2={length / 2} y2={width} />
      <circle cx={length / 2} cy={width / 2} r={Math.min(9.15, length / 6, width / 4)} />
      <circle cx={length / 2} cy={width / 2} r={width / 150} fill="#a7f3d0" />
      {[0, length - penaltyDepth].map((x) => <rect key={x} x={x} y={(width - penaltyWidth) / 2} width={penaltyDepth} height={penaltyWidth} />)}
      {[0, length - goalDepth].map((x) => <rect key={x} x={x} y={(width - goalWidth) / 2} width={goalDepth} height={goalWidth} />)}
    </g>
    {children}
  </svg>
}

import type { Point } from './types'

export function PointMarkers({ points, width, height, pending = null }: { points: Point[]; width: number; height: number; pending?: Point | null }) {
  const radius = Math.max(width, height) * 0.018
  return <g pointerEvents="none" aria-hidden="true">
    {[...points, ...(pending ? [pending] : [])].map((point, index) => {
      // Keep numbers legible even when a landmark lies on a pitch/image corner.
      const cx = Math.max(radius, Math.min(width - radius, point.x))
      const cy = Math.max(radius, Math.min(height - radius, point.y))
      const color = index === points.length ? '#fbbf24' : '#34d399'
      return <g key={index}>
        <line x1={point.x} y1={point.y} x2={cx} y2={cy} stroke={color} strokeWidth={radius / 5} />
        <circle cx={point.x} cy={point.y} r={radius / 4} fill={color} />
        <circle cx={cx} cy={cy} r={radius} fill="#0f172a" stroke={color} strokeWidth={radius / 7} />
        <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central" fill="white" fontSize={radius * 1.25} fontWeight="600">{index + 1}</text>
      </g>
    })}
  </g>
}

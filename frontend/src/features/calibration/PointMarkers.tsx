import type { Point } from './types'

/** Numbered landmarks: frame points are circles, pitch points squares; amber marks the pending point. */
export function PointMarkers({ points, width, height, pending = null, shape = 'circle' }: {
  points: Point[]; width: number; height: number; pending?: Point | null; shape?: 'circle' | 'square'
}) {
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
        {shape === 'square'
          ? <rect x={cx - radius} y={cy - radius} width={radius * 2} height={radius * 2} rx={radius * 0.3} fill="#0f172a" stroke={color} strokeWidth={radius / 7} />
          : <circle cx={cx} cy={cy} r={radius} fill="#0f172a" stroke={color} strokeWidth={radius / 7} />}
        <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central" fill="white" fontSize={radius * 1.25} fontWeight="600">{index + 1}</text>
      </g>
    })}
  </g>
}

/** Text legend for the marker shapes and colours. */
export function MarkerLegend({ shape }: { shape: 'circle' | 'square' }) {
  const mark = shape === 'square' ? 'rounded-[3px]' : 'rounded-full'
  return <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
    <li className="flex items-center gap-1.5"><span aria-hidden="true" className={`size-3 border-2 border-emerald-400 bg-slate-900 ${mark}`} />{shape === 'square' ? 'Pitch landmark (metres)' : 'Frame landmark (pixels)'}</li>
    <li className="flex items-center gap-1.5"><span aria-hidden="true" className={`size-3 border-2 border-amber-400 bg-slate-900 ${mark}`} />Awaiting its pair</li>
    <li>Matching numbers form one pair.</li>
  </ul>
}

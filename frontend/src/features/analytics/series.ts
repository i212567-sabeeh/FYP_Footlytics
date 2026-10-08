import type { TeamSnapshot } from './types'

export const SERIES_METRICS = {
  width_metres: 'Width', depth_metres: 'Depth', compactness_radius_metres: 'Compactness radius',
  centroid_x: 'Centroid X (length axis)', centroid_y: 'Centroid Y (width axis)',
} as const
export type SeriesMetric = keyof typeof SERIES_METRICS
export interface ChartPoint { frame: number; seconds: number; a: number | null; b: number | null }

export interface PathPoint { x: number; y: number; frame: number }

/**
 * A team's centroid positions (pitch metres) split into continuous runs.
 * Insufficient or missing snapshots break the path; nothing is interpolated.
 */
export function centroidSegments(rows: TeamSnapshot[]): PathPoint[][] {
  const segments: PathPoint[][] = []
  let run: PathPoint[] = []
  for (const row of [...rows].sort((first, second) => first.frame_number - second.frame_number)) {
    const { centroid_x: x, centroid_y: y } = row
    if (row.sufficient_players && x !== null && y !== null && Number.isFinite(x) && Number.isFinite(y)) run.push({ x, y, frame: row.frame_number })
    else if (run.length) { segments.push(run); run = [] }
  }
  if (run.length) segments.push(run)
  return segments
}

export function seriesPoints(a: TeamSnapshot[], b: TeamSnapshot[], key: SeriesMetric): ChartPoint[] {
  const frames = new Map<number, ChartPoint>()
  for (const [rows, team] of [[a, 'a'], [b, 'b']] as const) {
    for (const row of rows) {
      const point = frames.get(row.frame_number) ?? { frame: row.frame_number, seconds: row.timestamp_seconds, a: null, b: null }
      // Presentation only: preserve backend values, never fill missing geometry.
      point[team] = row.sufficient_players ? row[key] : null
      frames.set(row.frame_number, point)
    }
  }
  return [...frames.values()].sort((first, second) => first.frame - second.frame)
}

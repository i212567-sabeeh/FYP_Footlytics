import { Gauge } from 'lucide-react'
import type { PitchCalibration } from './types'

export function CalibrationQuality({ calibration, dirty }: { calibration: PitchCalibration | null; dirty: boolean }) {
  return <section className="panel mt-6 min-w-0" aria-labelledby="quality-heading">
    <h2 id="quality-heading" className="flex items-center gap-2 text-xl font-semibold"><Gauge aria-hidden="true" className="size-5 text-emerald-300" />Saved calibration quality</h2>
    {calibration ? <>
      <p className="mt-3 font-medium text-emerald-300">Mean reprojection error: {calibration.reprojection_error.toFixed(2)} m</p>
      {dirty && <p className="mt-2 text-sm text-amber-200">This error describes the saved calibration. Save your changes to update it.</p>}
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm lg:grid-cols-4">
        {[['Landmark pairs', String(calibration.image_points.length)], ['Source frame', `${calibration.source_frame_number} (${calibration.source_timestamp_seconds.toFixed(3)} s)`],
          ['Image size', `${calibration.image_width} × ${calibration.image_height} px`], ['Pitch', `${calibration.pitch_length_metres} × ${calibration.pitch_width_metres} m`]].map(([label, value]) =>
          <div key={label} className="min-w-0 rounded-lg border border-line bg-canvas/40 px-3 py-2"><dt className="text-xs text-slate-400">{label}</dt><dd className="mt-0.5 font-semibold tabular-nums text-slate-100">{value}</dd></div>)}
      </dl>
      <p className="mt-4 text-sm leading-6 text-slate-400">The backend reports the mean fitting error across all submitted pairs. A small error does not independently verify accuracy.
        {' '}With more than four pairs it fits robustly (RANSAC, 0.5 m threshold) and the error still includes any outliers; four pairs always fit exactly.</p>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-emerald-300">Homography matrix (image pixels → pitch metres)</summary>
        <div className="analytics-scroll mt-2 w-fit"><table className="analytics-table font-mono text-xs"><caption className="sr-only">Saved 3 by 3 homography matrix</caption>
          <tbody>{calibration.homography_matrix.map((row, index) => <tr key={index}>{row.map((value, column) => <td key={column} className="text-right">{value.toPrecision(6)}</td>)}</tr>)}</tbody>
        </table></div>
      </details>
    </> : <p className="mt-3 text-sm text-slate-400">Unavailable until a calibration is saved.</p>}
    <p className="mt-3 text-sm text-slate-400">Calibration assumes a flat pitch and a fixed camera. Camera pan, zoom or cuts require recalibration.</p>
  </section>
}

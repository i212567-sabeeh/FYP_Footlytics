import type { PitchCalibration } from './types'

export function CalibrationQuality({ calibration, dirty }: { calibration: PitchCalibration | null; dirty: boolean }) {
  return <section className="panel mt-6" aria-labelledby="quality-heading">
    <h2 id="quality-heading" className="text-xl font-semibold">Saved calibration quality</h2>
    {calibration ? <>
      <p className="mt-3 font-medium text-emerald-300">Mean reprojection error: {calibration.reprojection_error.toFixed(2)} m</p>
      {dirty && <p className="mt-2 text-sm text-amber-200">This error describes the saved calibration. Save your changes to update it.</p>}
      <p className="mt-2 text-sm text-slate-400">The backend reports the mean fitting error across all submitted pairs. A small error does not independently verify accuracy.</p>
    </> : <p className="mt-3 text-sm text-slate-400">Unavailable until a calibration is saved.</p>}
    <p className="mt-3 text-sm text-slate-400">Calibration assumes a flat pitch and a fixed camera. Camera pan, zoom or cuts require recalibration.</p>
  </section>
}

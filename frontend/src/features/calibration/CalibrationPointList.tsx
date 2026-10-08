import type { Point, PointPair } from './types'

export function CalibrationPointList({ pairs, pending, canEdit, onRemove, onReset }: { pairs: PointPair[]; pending: Point | null; canEdit: boolean; onRemove: () => void; onReset: () => void }) {
  return <section className="panel mt-6" aria-labelledby="landmarks-heading">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="landmarks-heading" className="text-xl font-semibold">Landmark pairs</h2>
      {canEdit && <div className="flex flex-wrap gap-3">
        <button type="button" className="button-secondary" disabled={!pending && !pairs.length} onClick={onRemove}>Remove last point</button>
        <button type="button" className="button-secondary" disabled={!pending && !pairs.length} onClick={onReset}>Reset points</button>
      </div>}
    </div>
    <p className="mt-3 text-sm text-slate-300">{pairs.length} complete point pairs{pairs.length < 4 ? ' · 4 points required minimum' : ' · Up to 64 pairs'}</p>
    {pairs.length > 0 && <ol aria-label="Selected landmark pairs" className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
      {pairs.map((pair, index) => <li key={index} className="rounded-lg border border-slate-800 p-3">
        <span className="font-semibold text-emerald-300">Point {index + 1}</span>
        <p>Image: x={pair.image.x.toFixed(2)}, y={pair.image.y.toFixed(2)} px</p>
        <p>Pitch: x={pair.pitch.x.toFixed(2)}, y={pair.pitch.y.toFixed(2)} m</p>
      </li>)}
    </ol>}
    {pending && <p className="mt-4 text-sm text-amber-200">Point {pairs.length + 1}: image x={pending.x.toFixed(2)}, y={pending.y.toFixed(2)} px — select its pitch location.</p>}
    {!pairs.length && !pending && <p className="mt-4 text-sm text-slate-400">No landmarks selected.</p>}
  </section>
}

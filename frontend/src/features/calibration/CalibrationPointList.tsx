import type { ReactNode } from 'react'
import { ListOrdered, RotateCcw, Undo2 } from 'lucide-react'
import type { Point, PointPair } from './types'

export function CalibrationPointList({ pairs, pending, canEdit, onRemove, onReset, footer }: {
  pairs: PointPair[]; pending: Point | null; canEdit: boolean; onRemove: () => void; onReset: () => void; footer?: ReactNode
}) {
  return <section className="panel mt-6 min-w-0" aria-labelledby="landmarks-heading">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="landmarks-heading" className="flex items-center gap-2 text-xl font-semibold"><ListOrdered aria-hidden="true" className="size-5 text-emerald-300" />Landmark pairs</h2>
      {canEdit && <div className="flex flex-wrap gap-2">
        <button type="button" className="button-secondary" disabled={!pending && !pairs.length} onClick={onRemove}><Undo2 aria-hidden="true" className="size-4" />Remove last point</button>
        <button type="button" className="button-secondary" disabled={!pending && !pairs.length} onClick={onReset}><RotateCcw aria-hidden="true" className="size-4" />Reset points</button>
      </div>}
    </div>
    <p className="mt-2 text-sm text-slate-300">{pairs.length} complete point pairs{pairs.length < 4 ? ' · 4 points required minimum' : ' · Up to 64 pairs'}</p>
    {pairs.length > 0 && <ol aria-label="Selected landmark pairs" className="mt-4 grid gap-2 text-sm sm:grid-cols-2 2xl:grid-cols-3">
      {pairs.map((pair, index) => <li key={index} className="flex items-start gap-3 rounded-lg border border-line bg-canvas/40 p-3">
        <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center rounded-full bg-emerald-400/15 text-xs font-semibold tabular-nums text-emerald-200">{index + 1}</span>
        <div className="min-w-0 tabular-nums"><span className="sr-only">{`Point ${index + 1}`}</span>
          <p className="text-slate-200">Image: x={pair.image.x.toFixed(2)}, y={pair.image.y.toFixed(2)} px</p>
          <p className="text-slate-400">Pitch: x={pair.pitch.x.toFixed(2)}, y={pair.pitch.y.toFixed(2)} m</p>
        </div>
      </li>)}
    </ol>}
    {pending && <p className="mt-4 text-sm text-amber-200">Point {pairs.length + 1}: image x={pending.x.toFixed(2)}, y={pending.y.toFixed(2)} px — select its pitch location.</p>}
    {!pairs.length && !pending && <p className="mt-4 text-sm text-slate-400">No landmarks selected.</p>}
    {footer}
  </section>
}

import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../../api/client'
import { useCapabilities } from '../football/hooks'
import type { FootballMatch } from '../football/types'
import { ErrorMessage, Field } from '../football/ui'
import type { MatchVideo } from '../media/types'
import { calibrationKey, loadCalibrationFrame, saveCalibration } from './api'
import { CalibrationFrame } from './CalibrationFrame'
import { CalibrationPointList } from './CalibrationPointList'
import { CalibrationQuality } from './CalibrationQuality'
import { PitchDiagram } from './PitchDiagram'
import type { CalibrationWrite, PitchCalibration, Point, PointPair } from './types'

function pairsFrom(calibration: PitchCalibration | null): PointPair[] {
  return calibration?.image_points.map((image, index) => ({ image, pitch: calibration.pitch_points[index]! })) ?? []
}

export function CalibrationEditor({ match, video, initial }: { match: FootballMatch; video: MatchVideo; initial: PitchCalibration | null }) {
  const client = useQueryClient()
  const capability = useCapabilities()
  const canEdit = capability.match && match.club.is_active && !match.is_archived
  const [saved, setSaved] = useState(initial)
  const [pairs, setPairs] = useState(() => pairsFrom(initial))
  const [pending, setPending] = useState<Point | null>(null)
  const [origin, setOrigin] = useState(initial)
  const [dirty, setDirty] = useState(false)
  const [success, setSuccess] = useState('')
  const [needsUpdate, setNeedsUpdate] = useState(false)
  const [timestampInput, setTimestampInput] = useState(String(initial?.source_timestamp_seconds ?? 0))
  const [selection, setSelection] = useState({ timestamp: initial?.source_timestamp_seconds ?? 0, request: 0 })
  const [timestampError, setTimestampError] = useState<Error | null>(null)
  const [displayError, setDisplayError] = useState<Error | null>(null)
  const [frameReady, setFrameReady] = useState(false)
  const frame = useQuery({
    queryKey: [...calibrationKey(match.id), 'frame', video.id, selection],
    queryFn: ({ signal }) => loadCalibrationFrame(match.id, video.id, selection.timestamp, signal),
    // Keep the chosen image stable while placing landmarks. Release its bytes on departure.
    staleTime: Infinity, gcTime: 0, retry: false,
  })
  const save = useMutation({
    mutationFn: ({ body, replace }: { body: CalibrationWrite; replace: boolean }) => saveCalibration(match.id, body, replace),
    onSuccess: (result, { replace }) => {
      setSaved(result)
      setPairs(pairsFrom(result))
      setPending(null)
      setOrigin(result)
      setDirty(false)
      setNeedsUpdate(false)
      setSuccess(replace ? 'Calibration updated.' : 'Calibration saved.')
      client.setQueryData([...calibrationKey(match.id), video.id], result)
    },
    onError: (error) => {
      // GET hides calibrations with stale pitch dimensions. A create conflict must
      // offer an explicit update, never silently retry POST as an overwrite.
      if (error instanceof ApiError && error.status === 409 && error.message === 'A calibration already exists for this video. Use PUT to replace it.') setNeedsUpdate(true)
    },
  })
  const sourceMismatch = Boolean(origin && frame.data && (origin.source_frame_number !== frame.data.frameNumber
    || origin.image_width !== frame.data.width || origin.image_height !== frame.data.height))
  const ready = frameReady && !frame.isFetching && !frame.error && !displayError && !sourceMismatch
  const editable = canEdit && !save.isPending
  const selectable = Boolean(editable && ready)

  function changed() {
    setDirty(true)
    setSuccess('')
    save.reset()
  }
  function resetPoints() {
    if (!editable) return
    setPairs([])
    setPending(null)
    setOrigin(null)
    changed()
  }
  function selectImage(point: Point) {
    if (!selectable || pending || pairs.length >= 64) return
    setPending(point)
    changed()
  }
  function selectPitch(point: Point) {
    if (!selectable || !pending) return
    setPairs([...pairs, { image: pending, pitch: point }])
    setPending(null)
    changed()
  }
  function loadFrame(event: FormEvent) {
    event.preventDefault()
    if (!editable) return
    const timestamp = timestampInput.trim() ? Number(timestampInput) : NaN
    if (!Number.isFinite(timestamp) || timestamp < 0 || timestamp >= video.duration_seconds) {
      setTimestampError(new Error(`Enter a timestamp from 0 up to, but less than, ${video.duration_seconds} seconds.`))
      return
    }
    resetPoints()
    setTimestampError(null)
    setDisplayError(null)
    setFrameReady(false)
    setSelection({ timestamp, request: selection.request + 1 })
  }
  function submit() {
    if (!selectable || pending || pairs.length < 4 || !frame.data) return
    setSuccess('')
    save.mutate({ replace: Boolean(saved) || needsUpdate, body: {
      video_id: frame.data.videoId,
      // Reuse the request that decoded this image, even if a timestamp input has changed.
      source_timestamp_seconds: selection.timestamp,
      image_points: pairs.map((pair) => pair.image),
      pitch_points: pairs.map((pair) => pair.pitch),
    } })
  }

  return <>
    {!canEdit && <p className="mb-6 rounded-lg border border-slate-700 p-4 text-sm text-slate-300">Read-only calibration. Editing requires Admin, Coach or Analyst access to an active club and an unarchived match.</p>}
    {canEdit && <form className="panel mb-6" aria-label="Load calibration frame" onSubmit={loadFrame}>
      <div className="flex flex-wrap items-end gap-4">
        <div className="w-full sm:w-56"><Field label="Timestamp (seconds)"><input type="number" min="0" step="any" required className="field-input" value={timestampInput} disabled={save.isPending} onChange={(event) => { setTimestampInput(event.target.value); setTimestampError(null) }} /></Field></div>
        <button type="submit" className="button-secondary" disabled={save.isPending || frame.isFetching}>Load Frame</button>
      </div>
      <p className="mt-3 text-sm text-slate-400">Choose a clear frame before {video.duration_seconds.toFixed(3)} s. Loading a frame clears selected points. The saved calibration stays unchanged until you update it.</p>
      <ErrorMessage error={timestampError} />
    </form>}
    {canEdit && <p role="status" className="mb-4 text-sm text-emerald-300">{pending ? `Select pitch point ${pairs.length + 1} to complete the pair.` : pairs.length >= 64 ? 'Maximum 64 pairs selected.' : `Select image point ${pairs.length + 1}, then its matching pitch location.`}</p>}
    <div className="grid items-start gap-6 xl:grid-cols-2">
      <section className="panel min-w-0" aria-labelledby="frame-heading">
        <h2 id="frame-heading" className="mb-4 text-xl font-semibold">Video frame</h2>
        {frame.isFetching && <p role="status" className="py-4 text-slate-400">Loading calibration frame...</p>}
        <ErrorMessage error={frame.error || displayError} />
        {(frame.error || displayError) && !canEdit && <button className="button-secondary" onClick={() => { setDisplayError(null); setFrameReady(false); setSelection({ ...selection, request: selection.request + 1 }) }}>Retry frame</button>}
        {sourceMismatch && <p role="alert" className="mb-4 text-sm text-amber-200">Saved landmarks do not match the decoded frame. {canEdit ? 'Reset points and select new landmarks to recalibrate.' : 'Ask a Coach or Analyst to recalibrate.'}</p>}
        {frame.data && <CalibrationFrame key={selection.request} frame={frame.data} points={sourceMismatch ? [] : pairs.map((pair) => pair.image)} pending={pending}
          canSelect={selectable && !pending && pairs.length < 64} onSelect={selectImage} onReady={() => { setFrameReady(true); setDisplayError(null) }} onError={(error) => { setFrameReady(false); setDisplayError(error) }} />}
      </section>
      <section className="panel min-w-0" aria-labelledby="pitch-heading">
        <h2 id="pitch-heading" className="mb-4 text-xl font-semibold">Pitch coordinates</h2>
        <PitchDiagram length={match.pitch_length_metres} width={match.pitch_width_metres} points={pairs.map((pair) => pair.pitch)} canSelect={selectable && Boolean(pending)} onSelect={selectPitch} />
      </section>
    </div>
    <CalibrationPointList pairs={pairs} pending={pending} canEdit={editable} onReset={resetPoints} onRemove={() => {
      if (!editable) return
      if (pending) setPending(null)
      else setPairs(pairs.slice(0, -1))
      changed()
    }} />
    {canEdit && <div className="mt-6">
      <ErrorMessage error={save.error} />
      {needsUpdate && <p className="mb-4 text-sm text-amber-200">Review your points, then choose Update Calibration to replace the existing calibration for this video.</p>}
      <button type="button" className="button-primary" disabled={!selectable || pairs.length < 4 || Boolean(pending)} onClick={submit}>{save.isPending ? 'Saving calibration...' : saved || needsUpdate ? 'Update Calibration' : 'Save Calibration'}</button>
      {save.isPending && <p role="status" className="mt-3 text-sm text-slate-300">Saving calibration...</p>}
      {success && <p role="status" className="mt-3 text-sm text-emerald-300">{success}</p>}
    </div>}
    <CalibrationQuality calibration={saved} dirty={dirty} />
  </>
}

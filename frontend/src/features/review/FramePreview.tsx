import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ErrorMessage, Field, QueryState } from '../football/ui'
import { loadReviewFrame, reviewKey } from './api'
import type { ReviewFrame, ReviewKind, ReviewSummary } from './types'

function PreviewImage({ frame, kind }: { frame: ReviewFrame; kind: ReviewKind }) {
  const image = useRef<HTMLImageElement>(null)
  const [error, setError] = useState<Error | null>(null)
  useEffect(() => {
    const url = URL.createObjectURL(frame.blob)
    if (image.current) image.current.src = url
    return () => URL.revokeObjectURL(url)
  }, [frame.blob])
  return <>
    <ErrorMessage error={error} />
    <img ref={image} alt={kind === 'detections' ? 'Player detection preview' : 'Player tracking preview'}
      width={frame.width} height={frame.height} className={`mt-4 h-auto w-full rounded-lg border border-slate-800 ${error ? 'hidden' : ''}`}
      onError={() => setError(new Error('The preview image could not be displayed. Load the frame again.'))}
      onLoad={(event) => {
        if (event.currentTarget.naturalWidth !== frame.width || event.currentTarget.naturalHeight !== frame.height) {
          setError(new Error('The preview image dimensions do not match. Refresh the review.'))
        }
      }} />
    <p className="mt-3 text-sm text-slate-400">Frame {frame.frameNumber} at {frame.timestamp.toFixed(3)} s · {frame.width} × {frame.height} pixels</p>
  </>
}

export function FramePreview({ matchId, kind, summary }: { matchId: number; kind: ReviewKind; summary: ReviewSummary }) {
  const [selected, setSelected] = useState<number | null>(null)
  const [draft, setDraft] = useState<string | undefined>()
  const [validation, setValidation] = useState<Error | null>(null)
  const preview = useQuery({
    queryKey: [...reviewKey(matchId), kind, 'frame', summary.job_id, summary.job_updated_at, selected],
    queryFn: ({ signal }) => loadReviewFrame(matchId, kind, summary, selected, signal),
    retry: false, gcTime: 0,
  })
  const current = selected ?? preview.data?.frameNumber ?? summary.first_frame
  const value = draft ?? String(current)

  function choose(number: number) {
    setValidation(null)
    setDraft(undefined)
    if (number === selected) void preview.refetch()
    else setSelected(number)
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const number = Number(value)
    if (!value.trim() || !Number.isSafeInteger(number) || number < summary.first_frame || number > summary.last_frame || number % summary.frame_stride !== 0) {
      setValidation(new Error(`Choose a processed frame from ${summary.first_frame} to ${summary.last_frame}, in steps of ${summary.frame_stride}.`))
      return
    }
    choose(number)
  }

  return <div className="mt-6">
    <form aria-label={`Load ${kind} preview`} onSubmit={submit} className="flex flex-wrap items-end gap-3">
      <Field label="Processed frame"><input className="field-input max-w-48" type="number" required min={summary.first_frame} max={summary.last_frame} step={summary.frame_stride} value={value} onChange={(event) => setDraft(event.target.value)} /></Field>
      <button className="button-primary" disabled={preview.isFetching}>Load frame</button>
      <button className="button-secondary" type="button" disabled={preview.isFetching || current <= summary.first_frame} onClick={() => choose(current - summary.frame_stride)}>Previous frame</button>
      <button className="button-secondary" type="button" disabled={preview.isFetching || current >= summary.last_frame} onClick={() => choose(current + summary.frame_stride)}>Next frame</button>
    </form>
    <ErrorMessage error={validation} />
    <QueryState query={preview} />
    {preview.isFetching && !preview.isPending && <p role="status" className="mt-4 text-slate-400">Loading preview…</p>}
    {preview.data && !preview.error && !preview.isFetching && <PreviewImage key={preview.dataUpdatedAt} frame={preview.data} kind={kind} />}
    <p className="mt-3 text-xs leading-5 text-slate-500">Processed frames {summary.first_frame}–{summary.last_frame}, step {summary.frame_stride}. Frames without saved observations have no boxes.</p>
  </div>
}

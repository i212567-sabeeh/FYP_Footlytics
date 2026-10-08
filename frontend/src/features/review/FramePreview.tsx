import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronFirst, ChevronLast, ChevronLeft, ChevronRight, ImageOff, Keyboard, LoaderCircle, Maximize2, Minimize2 } from 'lucide-react'
import { ErrorMessage, Field, QueryState } from '../football/ui'
import { loadReviewFrame, reviewKey } from './api'
import { frameAt, frameRange, isProcessedFrame, positionOf } from './frames'
import type { ReviewFrame, ReviewKind, ReviewSummary } from './types'

// Steps settle briefly so a scrub or key burst requests only its final frame:
// every backend preview scans the saved observations and decodes the video.
const SETTLE_MS = 200
const KEY_STEPS: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, PageUp: -10, PageDown: 10 }

function PreviewImage({ frame, kind, actualSize }: { frame: ReviewFrame; kind: ReviewKind; actualSize: boolean }) {
  const image = useRef<HTMLImageElement>(null)
  const [error, setError] = useState<Error | null>(null)
  useEffect(() => {
    const url = URL.createObjectURL(frame.blob)
    if (image.current) image.current.src = url
    return () => URL.revokeObjectURL(url)
  }, [frame.blob])
  return <>
    <img ref={image} alt={kind === 'detections' ? 'Player detection preview' : 'Player tracking preview'} hidden={error !== null}
      width={frame.width} height={frame.height} className={actualSize ? 'block max-w-none' : 'absolute inset-0 size-full object-contain'}
      onError={() => setError(new Error('The preview image could not be displayed. Load the frame again.'))}
      onLoad={(event) => {
        if (event.currentTarget.naturalWidth !== frame.width || event.currentTarget.naturalHeight !== frame.height) {
          setError(new Error('The preview image dimensions do not match. Refresh the review.'))
        }
      }} />
    {error && <div className="absolute inset-0 grid place-items-center p-4"><ErrorMessage error={error} /></div>}
  </>
}

/**
 * Saved-frame viewer for one result. Only a validated image for the frame the
 * user chose is shown; while another frame loads the stage shows its state.
 */
export function FramePreview({ matchId, kind, summary }: { matchId: number; kind: ReviewKind; summary: ReviewSummary }) {
  const label = kind === 'detections' ? 'Player detection' : 'Player tracking'
  const range = frameRange(summary)
  const [selected, setSelected] = useState<number | null>(null)
  const [pending, setPending] = useState<number | null>(null)
  const [draft, setDraft] = useState<string | undefined>()
  const [validation, setValidation] = useState<Error | null>(null)
  const [actualSize, setActualSize] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  // Without a frame number the backend returns the first frame with saved observations.
  const preview = useQuery({
    queryKey: [...reviewKey(matchId), kind, 'frame', summary.job_id, summary.job_updated_at, selected],
    queryFn: ({ signal }) => loadReviewFrame(matchId, kind, summary, selected, signal),
    retry: false, gcTime: 0,
  })
  const shown = pending === null && preview.data && !preview.error && !preview.isFetching ? preview.data : undefined
  const current = pending ?? selected ?? preview.data?.frameNumber ?? null
  const position = range && current !== null ? positionOf(range, current) : null
  const value = draft ?? (current === null ? '' : String(current))
  const waiting = pending !== null ? `Loading frame ${pending}…` : preview.isFetching
    ? selected === null ? 'Loading the first frame with saved observations…' : `Loading frame ${selected}…` : null

  function request(frame: number, reload = false) {
    if (frame !== selected) setSelected(frame)
    else if (reload) void preview.refetch()
  }
  function go(index: number) {
    if (!range || position === null) return
    const frame = frameAt(range, index)
    if (frame === current) return
    setValidation(null); setDraft(undefined); setPending(frame)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => { setPending(null); request(frame) }, SETTLE_MS)
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const number = Number(value)
    if (!range || !value.trim() || !isProcessedFrame(range, number)) {
      setValidation(new Error(`Choose a processed frame from ${summary.first_frame} to ${summary.last_frame}, in steps of ${summary.frame_stride}.`))
      return
    }
    window.clearTimeout(timer.current); setPending(null); setValidation(null); setDraft(undefined)
    request(number, true)
  }
  // Arrow, Page and Home/End keys step frames while a navigation button has focus.
  // Text and range inputs keep their own keys; modified keys stay with the browser.
  function keyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!range || position === null || event.target instanceof HTMLInputElement || event.altKey || event.ctrlKey || event.metaKey) return
    const target = event.key === 'Home' ? 0 : event.key === 'End' ? range.count - 1
      : event.key in KEY_STEPS ? position + (KEY_STEPS[event.key] ?? 0) : null
    if (target === null) return
    event.preventDefault(); go(target)
  }

  const atStart = position === null || position <= 0
  const atEnd = position === null || !range || position >= range.count - 1
  const fill = range && position !== null && range.count > 1 ? (position / (range.count - 1)) * 100 : 0
  return <div className="mt-5">
    <figure className="min-w-0">
      <div className={`relative rounded-xl border border-line bg-black ${actualSize ? 'max-h-[75vh] overflow-auto' : 'overflow-hidden'}`}
        style={actualSize ? undefined : { aspectRatio: `${summary.frame_width} / ${summary.frame_height}` }}
        {...(actualSize ? { tabIndex: 0, role: 'region', 'aria-label': `${label} frame at full resolution` } : {})}>
        {shown && <PreviewImage key={preview.dataUpdatedAt} frame={shown} kind={kind} actualSize={actualSize} />}
        {!shown && <div className="absolute inset-0 grid place-items-center p-4 text-center text-sm text-slate-400">
          {waiting ? <p role="status" className="flex items-center gap-2"><LoaderCircle aria-hidden="true" className="size-4 animate-spin text-emerald-400 motion-reduce:animate-none" />{waiting}</p>
            : <p className="flex items-center gap-2"><ImageOff aria-hidden="true" className="size-4 text-slate-500" />Preview unavailable</p>}
        </div>}
      </div>
      <figcaption className="mt-2 flex min-h-8 flex-wrap items-center justify-between gap-x-4 gap-y-1 text-sm">
        {shown ? <p className="tabular-nums text-slate-300">Frame {shown.frameNumber} at {shown.timestamp.toFixed(3)} s · {shown.width} × {shown.height} pixels</p> : <span />}
        <button type="button" className="button-secondary min-h-8 px-3 py-1 text-xs" aria-pressed={actualSize} onClick={() => setActualSize(!actualSize)}>
          {actualSize ? <Minimize2 aria-hidden="true" className="size-3.5" /> : <Maximize2 aria-hidden="true" className="size-3.5" />}{actualSize ? 'Fit to view' : 'Full resolution'}</button>
      </figcaption>
      {shown && selected === null && <p className="text-xs text-slate-500">Opened at the first frame with saved observations.</p>}
    </figure>
    {preview.error && <QueryState query={preview} />}
    {range ? <div role="group" aria-label={`${label} frame navigation`} onKeyDown={keyDown} className="mt-3 rounded-xl border border-line bg-canvas/40 p-3">
      <div className="flex items-center gap-2">
        <button type="button" className="icon-button" aria-label="First processed frame" disabled={atStart} onClick={() => go(0)}><ChevronFirst aria-hidden="true" className="size-4" /></button>
        <button type="button" className="button-secondary px-3" disabled={atStart} onClick={() => go((position ?? 0) - 1)}>
          <ChevronLeft aria-hidden="true" className="size-4" /><span className="sr-only lg:not-sr-only">Previous frame</span></button>
        <input type="range" className="frame-scrubber min-w-0 flex-1" min={0} max={range.count - 1} step={1} value={position ?? 0} disabled={position === null || range.count === 1}
          style={{ '--fill': `${fill}%` } as CSSProperties} aria-label={`${label} frame position`}
          aria-valuetext={current === null ? undefined : `Frame ${current}, processed frame ${(position ?? 0) + 1} of ${range.count}`}
          onChange={(event) => go(Number(event.target.value))} />
        <button type="button" className="button-secondary px-3" disabled={atEnd} onClick={() => go((position ?? 0) + 1)}>
          <span className="sr-only lg:not-sr-only">Next frame</span><ChevronRight aria-hidden="true" className="size-4" /></button>
        <button type="button" className="icon-button" aria-label="Last processed frame" disabled={atEnd} onClick={() => go(range.count - 1)}><ChevronLast aria-hidden="true" className="size-4" /></button>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 px-1 text-xs tabular-nums text-slate-500">
        <span>{`Frame ${range.first}`}</span>
        <span className="text-slate-300">{position === null ? 'Locating first frame…' : `Processed frame ${position + 1} of ${range.count}`}</span>
        <span>{`Frame ${range.last}`}</span>
      </div>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-3 border-t border-line pt-3">
        <form aria-label={`Load ${kind} preview`} onSubmit={submit} className="flex flex-wrap items-end gap-2">
          <Field label="Processed frame"><input className="field-input w-32 py-2" type="number" required min={range.first} max={range.last} step={range.stride}
            value={value} onChange={(event) => setDraft(event.target.value)} /></Field>
          <button className="button-primary" disabled={preview.isFetching && pending === null && selected === Number(value)}>Load frame</button>
        </form>
        <p className="hidden items-center gap-2 text-xs text-slate-500 md:flex"><Keyboard aria-hidden="true" className="size-4" />
          {`With a frame button focused: ← → step, PgUp/PgDn ±10, Home/End first/last. Sampled every ${range.stride === 1 ? 'frame' : `${range.stride} frames`}.`}</p>
      </div>
      <ErrorMessage error={validation} />
    </div> : <ErrorMessage error={new Error('The saved frame range is inconsistent. Refresh the review.')} />}
  </div>
}

import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { DateText, ErrorMessage, Field, QueryState } from '../football/ui'
import { jobsKey, uploadVideo, videoKey } from './api'
import type { MatchVideo } from './types'

function formatDuration(seconds: number): string {
  const whole = Math.floor(seconds)
  return [Math.floor(whole / 3600), Math.floor((whole % 3600) / 60), whole % 60]
    .map((value) => String(value).padStart(2, '0')).join(':')
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MiB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GiB`
}

function Metadata({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0"><dt className="text-sm text-slate-400">{label}</dt><dd className="mt-1 break-words">{children}</dd></div>
}

interface VideoPanelProps {
  matchId: number
  query: UseQueryResult<MatchVideo | null>
  canManage: boolean
  hasActiveJob: boolean
}

export function VideoPanel({ matchId, query, canManage, hasActiveJob }: VideoPanelProps) {
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<Error | null>(null)
  const [replacing, setReplacing] = useState(false)
  const [success, setSuccess] = useState('')
  const upload = useMutation({
    mutationFn: ({ selected, replace }: { selected: File; replace: boolean }) => uploadVideo(matchId, selected, replace),
    onSuccess: async (video, { replace }) => {
      client.setQueryData(videoKey(matchId), video)
      setFile(null)
      setReplacing(false)
      setSuccess(replace ? 'Video replaced successfully.' : 'Video uploaded successfully.')
      if (input.current) input.current.value = ''
      await client.invalidateQueries({ queryKey: jobsKey(matchId) })
    },
  })
  const video = query.data
  const blocked = hasActiveJob || upload.isPending

  function chooseFile(selected: File | undefined) {
    upload.reset()
    setSuccess('')
    setFileError(null)
    setFile(selected ?? null)
    if (selected && !/\.(mp4|mov)$/i.test(selected.name)) {
      setFileError(new Error('Choose an MP4 (.mp4) or QuickTime (.mov) video.'))
    } else if (selected?.size === 0) {
      setFileError(new Error('The selected file is empty. Choose a readable video.'))
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!file || fileError || blocked || !canManage) return
    upload.mutate({ selected: file, replace: Boolean(video) })
  }

  return <section className="panel mt-8" aria-labelledby="video-heading">
    <h2 id="video-heading" className="text-xl font-semibold">Video</h2>
    <QueryState query={query} />
    {video && <>
      <dl className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <Metadata label="Original filename">{video.original_filename}</Metadata>
        <Metadata label="Resolution">{video.width} × {video.height}</Metadata>
        <Metadata label="Frame rate">{video.fps.toLocaleString(undefined, { maximumFractionDigits: 3 })} FPS</Metadata>
        <Metadata label="Duration">{formatDuration(video.duration_seconds)}</Metadata>
        <Metadata label="File size">{formatSize(video.file_size_bytes)}</Metadata>
        <Metadata label="Codec">{video.codec || 'Unavailable'}</Metadata>
        <Metadata label="Container">{video.container_format || 'Unavailable'}</Metadata>
        <Metadata label="Frame count">{video.frame_count?.toLocaleString() ?? 'Unavailable'}</Metadata>
        <Metadata label="Uploaded"> <DateText value={video.created_at} /></Metadata>
      </dl>
      {video.warning_message && <p className="mt-4 text-sm text-amber-200">{video.warning_message}</p>}
    </>}
    {video === null && <p className="mt-4 text-slate-400">No match video uploaded.</p>}
    {success && <p role="status" className="mt-4 text-sm text-emerald-300">{success}</p>}
    {canManage && query.isSuccess && <>
      {video && !replacing && <button className="button-secondary mt-6" disabled={blocked} onClick={() => { upload.reset(); setSuccess(''); setReplacing(true) }}>Replace Video</button>}
      {hasActiveJob && <p className="mt-4 text-sm text-slate-400">Wait for the active processing job to finish before changing the video.</p>}
      {(!video || replacing) && <form className="mt-6 max-w-2xl space-y-4" onSubmit={submit} aria-label={video ? 'Replace match video' : 'Upload match video'}>
        {video && <p className="rounded-lg border border-amber-800 bg-amber-950/30 p-4 text-sm text-amber-200">Replacing the source video will require future calibration and analysis to be performed again. The current video remains available if the new upload fails validation.</p>}
        <Field label={video ? 'Replacement video file' : 'Video file'}><input ref={input} className="field-input file:mr-3 file:rounded file:border-0 file:bg-slate-800 file:px-3 file:py-1 file:text-slate-200" type="file" accept=".mp4,.mov,video/mp4,video/quicktime" disabled={blocked} onChange={(event) => chooseFile(event.target.files?.[0])} /></Field>
        <p className="text-sm text-slate-400">MP4 or MOV. The server checks the configured size limit and verifies that the video is readable.</p>
        {file && <p className="break-words text-sm text-slate-300">Selected: {file.name} · {formatSize(file.size)}</p>}
        <ErrorMessage error={fileError || upload.error} />
        {upload.isPending && <p role="status" className="text-sm text-slate-300">Uploading and validating video. Keep this page open.</p>}
        <div className="flex flex-wrap gap-3"><button className="button-primary" disabled={!file || Boolean(fileError) || blocked} type="submit">{upload.isPending ? 'Uploading…' : video ? 'Upload replacement' : 'Upload Video'}</button>
          {video && <button className="button-secondary" disabled={upload.isPending} type="button" onClick={() => { setReplacing(false); setFile(null); setFileError(null); upload.reset() }}>Cancel replacement</button>}
        </div>
      </form>}
    </>}
  </section>
}

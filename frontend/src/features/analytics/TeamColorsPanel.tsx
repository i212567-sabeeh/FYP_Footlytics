import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import { ErrorMessage, Field } from '../football/ui'
import { jobsKey, useMatchJobs } from '../media/api'
import { isActiveJob, type ProcessingJob } from '../media/types'
import { metric } from './format'
import { ResultState } from './ResultState'

export interface ColorSelection { team: 'team_a' | 'team_b'; track_id: number; frame_number: number }
interface ColorSample extends ColorSelection { id: string; quality: number; color: number[] }
interface Colors { tracking_job_id: number; tracking_version: string; current: {
  id: number; classification_mode: 'user_seeded'; samples: ColorSample[]
  prototypes: { team: 'team_a' | 'team_b'; color: number[]; quality: number; sample_ids: string[] }[]
} | null }
interface Preview { track_id: number; frame_number: number; tracking_version: string; crop_data_url: string; quality: number; usable: boolean; rejection_reason: string | null }
const key = (id: number) => ['team-colors', id] as const

export function TeamColorsPanel({ matchId, canManage }: { matchId: number; canManage: boolean }) {
  const query = useQuery({ queryKey: key(matchId), queryFn: ({ signal }) => apiRequest<Colors>(`matches/${matchId}/team-colors`, { signal }), gcTime: 0 })
  return <section className="mt-6 min-w-0 rounded-xl border border-slate-700 p-4 sm:p-6" aria-labelledby="team-colors-heading">
    <h3 id="team-colors-heading" className="text-lg font-semibold">Set Team Colors</h3>
    <p className="mt-2 text-sm leading-6 text-slate-400">Select clear torso examples from tracked frames for both teams. You identify the team colors; the classifier compares other tracks against those examples. Weak evidence remains Unknown. Manual overrides stay in control.</p>
    <ResultState query={query} name="Team colors">{query.data && <ColorEditor key={`${query.data.tracking_version}:${query.data.current?.id ?? 'automatic'}`} matchId={matchId} data={query.data} canManage={canManage} />}</ResultState>
  </section>
}

function ColorEditor({ matchId, data, canManage }: { matchId: number; data: Colors; canManage: boolean }) {
  const client = useQueryClient()
  const [samples, setSamples] = useState<ColorSelection[]>(data.current?.samples.map(({ team, track_id, frame_number }) => ({ team, track_id, frame_number })) ?? [])
  const [team, setTeam] = useState<'team_a' | 'team_b'>('team_a')
  const [track, setTrack] = useState('')
  const [frame, setFrame] = useState('')
  const [message, setMessage] = useState('')
  const [crop, setCrop] = useState<Preview | null>(null)
  const jobs = useMatchJobs(matchId, 0, true)
  const active = jobs.data?.items.some(isActiveJob) ?? false
  const preview = useMutation({ mutationFn: () => apiRequest<Preview>(`matches/${matchId}/team-colors/preview?track_id=${Number(track)}&frame_number=${Number(frame)}&tracking_version=${data.tracking_version}`), onSuccess: setCrop })
  const save = useMutation({ mutationFn: () => apiRequest<Colors>(`matches/${matchId}/team-colors`, { method: 'PUT', body: { tracking_version: data.tracking_version, samples } }),
    onSuccess: (result) => { client.setQueryData(key(matchId), result) } })
  const clear = useMutation({ mutationFn: () => apiRequest<void>(`matches/${matchId}/team-colors`, { method: 'DELETE' }), onSuccess: () => client.invalidateQueries({ queryKey: key(matchId) }) })
  const classify = useMutation({ mutationFn: () => apiRequest<ProcessingJob>(`matches/${matchId}/jobs/team-classification`, { method: 'POST' }), onSuccess: () => client.invalidateQueries({ queryKey: jobsKey(matchId) }), onSettled: () => client.invalidateQueries({ queryKey: jobsKey(matchId) }) })
  const pending = save.isPending || clear.isPending || classify.isPending
  const hasBoth = samples.some(s => s.team === 'team_a') && samples.some(s => s.team === 'team_b')
  const validInput = Number.isSafeInteger(Number(track)) && Number(track) > 0 && frame !== '' && Number.isSafeInteger(Number(frame)) && Number(frame) >= 0
  const duplicate = crop && samples.some(s => s.track_id === crop.track_id && s.frame_number === crop.frame_number)
  function addSample() {
    if (!crop?.usable || duplicate || samples.length >= 10) return
    if (samples.some(s => s.track_id === crop.track_id && s.team !== team)) { setMessage('A representative track cannot seed both teams.'); return }
    setSamples([...samples, { team, track_id: crop.track_id, frame_number: crop.frame_number }]); setMessage('')
  }
  return <>
    <p className="mt-4 text-sm font-medium">Classification mode: {data.current ? 'User-seeded team colors' : 'Automatic clustering'}</p>
    {data.current && <p className="mt-2 text-sm text-slate-400">Saved prototype set #{data.current.id}: {data.current.samples.length} examples. Re-run classification to apply these colors to current tracks.</p>}
    {!canManage && <p className="mt-3 text-sm text-slate-400">Read-only. A coach or analyst can update these examples.</p>}
    {canManage && <form className="mt-5 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); setCrop(null); preview.mutate() }}>
      <Field label="Example team"><select className="field-input" disabled={preview.isPending || pending} value={team} onChange={e => setTeam(e.target.value as 'team_a' | 'team_b')}><option value="team_a">Team A</option><option value="team_b">Team B</option></select></Field>
      <Field label="Example Track ID"><input className="field-input" disabled={preview.isPending || pending} inputMode="numeric" value={track} onChange={e => { setTrack(e.target.value); setCrop(null) }} /></Field>
      <Field label="Example frame number"><input className="field-input" disabled={preview.isPending || pending} inputMode="numeric" value={frame} onChange={e => { setFrame(e.target.value); setCrop(null) }} /></Field>
      <button className="button-secondary" disabled={!validInput || preview.isPending || pending}>{preview.isPending ? 'Loading crop…' : 'Preview crop'}</button>
    </form>}
    <ErrorMessage error={preview.error} />
    {canManage && crop && <div className="mt-4 flex flex-wrap items-center gap-4 rounded-lg bg-slate-950/60 p-4">
      <img className="h-28 max-w-full object-contain" src={crop.crop_data_url} alt={`Torso crop for Track ${crop.track_id}, frame ${crop.frame_number}`} />
      <div className="min-w-0 text-sm"><p>Color evidence quality: {metric(crop.quality * 100, '%')}</p>
        <p className="mt-1 text-xs text-slate-400">Evidence quality is not a probability of correct team assignment.</p>
        {crop.rejection_reason && <p className="mt-2 text-amber-200">{crop.rejection_reason}</p>}
        <button className="button-secondary mt-3" type="button" disabled={!crop.usable || Boolean(duplicate) || samples.length >= 10 || pending} onClick={addSample}>Add to {team === 'team_a' ? 'Team A' : 'Team B'}</button>
      </div>
    </div>}
    {message && <p role="alert" className="mt-3 text-sm text-amber-200">{message}</p>}
    <div className="mt-5 grid gap-4 sm:grid-cols-2">{(['team_a', 'team_b'] as const).map(label => <div className="min-w-0 rounded-lg border border-slate-800 p-4" key={label}>
      <h4 className="font-medium">{label === 'team_a' ? 'Team A' : 'Team B'} examples</h4>
      {!samples.some(s => s.team === label) && <p className="mt-2 text-sm text-slate-400">No examples selected.</p>}
      <ul className="mt-2 space-y-2 text-sm">{samples.filter(s => s.team === label).map(sample => <li key={`${sample.track_id}:${sample.frame_number}`} className="flex flex-wrap items-center justify-between gap-2">
        <span>Track {sample.track_id} · frame {sample.frame_number}</span>
        {canManage && <button className="text-red-300 hover:underline" disabled={pending} onClick={() => setSamples(samples.filter(s => s !== sample))} aria-label={`Remove Track ${sample.track_id} frame ${sample.frame_number}`}>Remove</button>}
      </li>)}</ul>
    </div>)}</div>
    {canManage && <div className="mt-5 flex flex-wrap gap-3">
      <button className="button-primary" disabled={!hasBoth || pending || active} onClick={() => save.mutate()}>{save.isPending ? 'Saving colors…' : 'Save prototypes'}</button>
      <button className="button-secondary" disabled={pending || active || !jobs.isSuccess} onClick={() => classify.mutate()}>{active || classify.isPending ? 'Classification / processing in progress…' : 'Re-run classification'}</button>
      {data.current && <button className="button-secondary" disabled={pending || active} onClick={() => clear.mutate()}>Use automatic clustering</button>}
    </div>}
    <ErrorMessage error={save.error ?? clear.error ?? classify.error} />
    {classify.isSuccess && <p role="status" className="mt-3 text-sm text-emerald-300">Classification queued. Follow progress in Processing; updated assignments appear after completion.</p>}
  </>
}

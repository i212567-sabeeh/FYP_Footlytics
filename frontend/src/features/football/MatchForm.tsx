import { useState, type FormEvent, type ReactNode } from 'react'
import { FootballPitch } from '../../components/FootballPitch'
import { useOptions } from './api'
import { ClubPicker, FormButtons, FormPanel } from './forms'
import { ErrorMessage, Field } from './ui'
import type { FootballMatch, MatchFields, MatchFormat, Team } from './types'

export type MatchValue = MatchFields & { club_id: number }
export const PITCH_DEFAULTS = { '11v11': { length: 105, width: 68 }, '5v5': { length: 40, width: 20 } } as const
function localDateTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
const validPitch = (l: number, w: number) => Number.isFinite(l) && Number.isFinite(w) && l >= 10 && l <= 150 && w >= 5 && w <= 100 && l >= w

function FormSection({ title, children }: { title: string; children: ReactNode }) {
  return <div className="space-y-4 border-t border-line pt-5 first:border-t-0 first:pt-0">
    <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{title}</h3>
    {children}
  </div>
}

export function MatchForm({ initial, saving, error, onSave, onCancel }: {
  initial?: FootballMatch; saving: boolean; error: Error | null; onSave: (data: MatchValue) => void; onCancel: () => void
}) {
  const [club, setClub] = useState(String(initial?.club_id ?? ''))
  const [title, setTitle] = useState(initial?.title ?? '')
  const [teamA, setTeamA] = useState(String(initial?.team_a_id ?? ''))
  const [teamB, setTeamB] = useState(String(initial?.team_b_id ?? ''))
  const [format, setFormat] = useState<MatchFormat>(initial?.match_format ?? '11v11')
  const [length, setLength] = useState(String(initial?.pitch_length_metres ?? 105))
  const [width, setWidth] = useState(String(initial?.pitch_width_metres ?? 68))
  const [date, setDate] = useState(localDateTime(initial?.match_date))
  const [venue, setVenue] = useState(initial?.venue ?? '')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [validation, setValidation] = useState<Error | null>(null)
  const teams = useOptions<Team>('teams', { club_id: club }, !!club)
  const selectable = teams.data?.filter((team) => team.is_active || team.id === initial?.team_a_id || team.id === initial?.team_b_id) ?? []
  const previewLength = Number(length), previewWidth = Number(width)
  function changeFormat(value: MatchFormat) {
    setFormat(value)
    setLength(String(PITCH_DEFAULTS[value].length)); setWidth(String(PITCH_DEFAULTS[value].width))
  }
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim() || !club || !teamA || !teamB || !date) { setValidation(new Error('Complete the title, club, teams and match date.')); return }
    if (teamA === teamB) { setValidation(new Error('Team A and Team B must be different.')); return }
    const l = Number(length), w = Number(width)
    if (!validPitch(l, w)) {
      setValidation(new Error('Use a length of 10–150 m and width of 5–100 m; length must be at least width.')); return
    }
    setValidation(null)
    onSave({ club_id: Number(club), title: title.trim(), team_a_id: Number(teamA), team_b_id: Number(teamB),
      match_format: format, match_date: new Date(date).toISOString(), pitch_length_metres: l, pitch_width_metres: w,
      venue: venue.trim() || null, notes: notes.trim() || null })
  }
  return <FormPanel title={initial ? 'Edit match' : 'Match information'}><form onSubmit={submit}><fieldset disabled={saving} className="space-y-6">
    <FormSection title="Match">
      <Field label="Match title"><input className="field-input" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
      {initial ? <p className="text-sm text-slate-400">Club: {initial.club.name}</p> : <ClubPicker value={club} onChange={(value) => { setClub(value); setTeamA(''); setTeamB('') }} />}
    </FormSection>
    <FormSection title="Teams">
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Team A"><select className="field-input" required value={teamA} disabled={!club || teams.isPending || !!teams.error} onChange={(e) => setTeamA(e.target.value)}>
          <option value="">Select Team A</option>{selectable.map((team) => <option key={team.id} value={team.id} disabled={String(team.id) === teamB}>{team.name}{!team.is_active && ' (inactive)'}</option>)}
        </select></Field>
        <Field label="Team B"><select className="field-input" required value={teamB} disabled={!club || teams.isPending || !!teams.error} onChange={(e) => setTeamB(e.target.value)}>
          <option value="">Select Team B</option>{selectable.map((team) => <option key={team.id} value={team.id} disabled={String(team.id) === teamA}>{team.name}{!team.is_active && ' (inactive)'}</option>)}
        </select></Field>
      </div>
      <ErrorMessage error={teams.error} />
      {club && teams.data && selectable.length < 2 && <p className="text-sm text-amber-300">This club needs at least two active teams before you can create a match.</p>}
    </FormSection>
    <FormSection title="Format and date">
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Match format"><select className="field-input" value={format} onChange={(e) => changeFormat(e.target.value as MatchFormat)}><option value="11v11">11v11</option><option value="5v5">5v5</option></select></Field>
        <Field label="Match date and time (local)"><input className="field-input" type="datetime-local" required value={date} onChange={(e) => setDate(e.target.value)} /></Field>
      </div>
    </FormSection>
    <FormSection title="Pitch">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_13rem] lg:items-center">
        <div className="space-y-4">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Pitch length (X, metres)"><input className="field-input" type="number" required min={10} max={150} step="any" value={length} onChange={(e) => setLength(e.target.value)} /></Field>
            <Field label="Pitch width (Y, metres)"><input className="field-input" type="number" required min={5} max={100} step="any" value={width} onChange={(e) => setWidth(e.target.value)} /></Field>
          </div>
          <p className="text-sm text-slate-400">Changing format fills suggested dimensions. Set the actual pitch measurements for this match; dimensions remain editable. Times are saved in UTC.</p>
        </div>
        {validPitch(previewLength, previewWidth) && <div className="hidden overflow-hidden rounded-lg border border-line lg:block">
          <FootballPitch length={previewLength} width={previewWidth} label={`Pitch preview, ${previewLength} by ${previewWidth} metres`} />
        </div>}
      </div>
    </FormSection>
    <FormSection title="Venue and notes">
      <Field label="Venue (optional)"><input className="field-input" maxLength={200} value={venue} onChange={(e) => setVenue(e.target.value)} /></Field>
      <Field label="Notes (optional)"><textarea className="field-input" rows={3} maxLength={5000} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
    </FormSection>
    <ErrorMessage error={validation || error} /><FormButtons saving={saving} cancel={onCancel} label="Save match" />
  </fieldset></form></FormPanel>
}

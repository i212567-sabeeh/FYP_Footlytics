import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { apiRequest } from '../../api/client'
import { useOptions, useRecords } from './api'
import { playerName, type FootballPlayer, type SquadMembership, type Team } from './types'
import { DateText, ErrorMessage, Field, Pager, QueryState, Status } from './ui'
import { useCapabilities, useSave } from './hooks'

export function SquadPanel({ team }: { team: Team }) {
  const { roster } = useCapabilities()
  const editable = roster && team.is_active && team.club.is_active
  const [offset, setOffset] = useState(0)
  const [active, setActive] = useState('true')
  const [player, setPlayer] = useState('')
  const [shirt, setShirt] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const [editShirt, setEditShirt] = useState('')
  const squad = useRecords<SquadMembership>(`teams/${team.id}/squad`, { offset, limit: 25, active })
  const players = useOptions<FootballPlayer>('players', { club_id: team.club_id, active: true }, editable)
  const add = useSave((data: { player_id: number; shirt_number: number | null }) => apiRequest(`teams/${team.id}/squad`, { method: 'POST', body: data }), () => { setPlayer(''); setShirt('') })
  const change = useSave((data: { id: number; shirt_number: number | null }) => apiRequest(`teams/${team.id}/squad/${data.id}`, { method: 'PATCH', body: { shirt_number: data.shirt_number } }), () => setEditing(null))
  const remove = useSave((id: number) => apiRequest(`teams/${team.id}/squad/${id}`, { method: 'DELETE' }))
  function submit(e: FormEvent) { e.preventDefault(); if (player) add.mutate({ player_id: Number(player), shirt_number: shirt ? Number(shirt) : null }) }
  return <section className="panel mt-8"><h2 className="text-xl font-semibold">Squad</h2><p className="mb-6 mt-2 text-sm text-slate-400">Players belong to this club. Ended memberships remain in squad history.</p>
    {editable && <form onSubmit={submit} className="mb-6"><fieldset disabled={add.isPending} className="flex flex-wrap items-end gap-3"><div className="min-w-60 flex-1"><Field label="Player to add"><select className="field-input" required disabled={players.isPending || !!players.error} value={player} onChange={(e) => setPlayer(e.target.value)}>
      <option value="">Select a football player</option>{players.data?.map((item) => <option value={item.id} key={item.id}>{playerName(item)}</option>)}
    </select></Field></div><div className="w-44"><Field label="Shirt number (optional)"><input className="field-input" type="number" min={1} max={99} step={1} value={shirt} onChange={(e) => setShirt(e.target.value)} /></Field></div>
      <button className="button-primary mb-2" disabled={!player}>Add to squad</button>
    </fieldset><ErrorMessage error={players.error || add.error} /></form>}
    <div className="max-w-xs"><Field label="Membership status"><select className="field-input" value={active} onChange={(e) => { setActive(e.target.value); setOffset(0) }}><option value="true">Current squad</option><option value="">All memberships</option><option value="false">Ended memberships</option></select></Field></div>
    <ErrorMessage error={change.error || remove.error} /><QueryState query={squad} />
    {squad.data && <><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-slate-400"><tr>{['Player', 'Shirt', 'Status', 'Joined / left', ...(editable ? ['Actions'] : [])].map((label) => <th className="py-4 pr-4" key={label}>{label}</th>)}</tr></thead>
      <tbody>{squad.data.items.map((membership) => <tr className="border-t border-slate-800" key={membership.id}>
        <td className="py-4 pr-4"><Link className="record-link" to={`/players/${membership.player_id}`}>{playerName(membership.player)}</Link>{!membership.player.is_active && <span className="block text-slate-500">Inactive player</span>}</td>
        <td className="py-4 pr-4">{membership.shirt_number ?? 'Unassigned'}</td><td className="py-4 pr-4"><Status active={membership.is_active} /></td>
        <td className="py-4 pr-4 text-slate-400"><DateText value={membership.joined_at} />{membership.left_at && <span className="block">Left: <DateText value={membership.left_at} /></span>}</td>
        {editable && <td className="py-4">{membership.is_active && <div className="flex flex-wrap gap-2"><button className="button-secondary" onClick={() => { change.reset(); setEditing(membership.id); setEditShirt(String(membership.shirt_number ?? '')) }}>Edit shirt</button>
          <button className="button-secondary" disabled={remove.isPending} onClick={() => remove.mutate(membership.id)} aria-label={`Remove ${playerName(membership.player)} from squad`}>Remove</button></div>}</td>}
      </tr>)}</tbody></table></div>
      {!squad.data.total && <p className="py-5 text-slate-400">No squad memberships found.</p>}<Pager total={squad.data.total} offset={offset} onChange={setOffset} /></>}
    {editing !== null && <form className="mt-6 border-t border-slate-700 pt-6" onSubmit={(e) => { e.preventDefault(); change.mutate({ id: editing, shirt_number: editShirt ? Number(editShirt) : null }) }}>
      <Field label="New shirt number (optional)"><input type="number" className="field-input max-w-xs" min={1} max={99} step={1} value={editShirt} onChange={(e) => setEditShirt(e.target.value)} /></Field>
      <div className="mt-3 flex gap-3"><button className="button-primary" disabled={change.isPending}>Save shirt</button><button type="button" className="button-secondary" disabled={change.isPending} onClick={() => setEditing(null)}>Cancel</button></div>
    </form>}
  </section>
}

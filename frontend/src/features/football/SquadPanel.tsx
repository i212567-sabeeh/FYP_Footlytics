import { useState, type FormEvent } from 'react'
import { Pencil, Shirt, UserMinus, UserPlus } from 'lucide-react'
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
  return <section className="panel" aria-labelledby="squad-heading">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><h2 id="squad-heading" className="flex items-center gap-2 text-xl font-semibold"><Shirt aria-hidden="true" className="size-5 text-emerald-300" />Squad</h2>
        <p className="mt-1 text-sm text-slate-400">Players belong to this club. Ended memberships remain in squad history.</p></div>
      <div className="w-full sm:w-56"><Field label="Membership status"><select className="field-input" value={active} onChange={(e) => { setActive(e.target.value); setOffset(0) }}><option value="true">Current squad</option><option value="">All memberships</option><option value="false">Ended memberships</option></select></Field></div>
    </div>
    {editable && <form onSubmit={submit} className="mt-5 rounded-xl border border-line bg-canvas/40 p-4"><fieldset disabled={add.isPending} className="flex flex-wrap items-end gap-3"><div className="min-w-60 flex-1"><Field label="Player to add"><select className="field-input" required disabled={players.isPending || !!players.error} value={player} onChange={(e) => setPlayer(e.target.value)}>
      <option value="">Select a football player</option>{players.data?.map((item) => <option value={item.id} key={item.id}>{playerName(item)}</option>)}
    </select></Field></div><div className="w-44"><Field label="Shirt number (optional)"><input className="field-input" type="number" min={1} max={99} step={1} value={shirt} onChange={(e) => setShirt(e.target.value)} /></Field></div>
      <button className="button-primary" disabled={!player}><UserPlus aria-hidden="true" className="size-4" />Add to squad</button>
    </fieldset><ErrorMessage error={players.error || add.error} /></form>}
    <div className="mt-5"><ErrorMessage error={change.error || remove.error} /><QueryState query={squad} /></div>
    {squad.data && <>{squad.data.items.length > 0 && <div className="analytics-scroll" tabIndex={0} role="region" aria-label="Squad table"><table className="analytics-table"><caption className="sr-only">Squad memberships for {team.name}</caption>
      <thead><tr>{['Player', 'Shirt', 'Status', 'Joined / left', ...(editable ? ['Actions'] : [])].map((label) => <th scope="col" key={label}
        className={label === 'Joined / left' ? 'hidden md:table-cell' : label === 'Actions' ? 'sticky right-0 bg-canvas' : undefined}>{label}</th>)}</tr></thead>
      <tbody>{squad.data.items.map((membership) => <tr key={membership.id} className="group">
        <td><Link className="font-medium text-slate-50 hover:text-emerald-200" to={`/players/${membership.player_id}`}>{playerName(membership.player)}</Link>{!membership.player.is_active && <span className="block text-xs text-slate-500">Inactive player</span>}</td>
        <td>{membership.shirt_number === null ? <span className="text-slate-500">Unassigned</span>
          : <span className="inline-grid min-w-8 place-items-center rounded-md bg-emerald-400/10 px-2 py-0.5 font-semibold tabular-nums text-emerald-200 ring-1 ring-emerald-400/30">{membership.shirt_number}</span>}</td>
        <td><Status active={membership.is_active} /></td>
        <td className="hidden text-slate-400 md:table-cell"><DateText value={membership.joined_at} />{membership.left_at && <span className="block">Left: <DateText value={membership.left_at} /></span>}</td>
        {editable && <td className="sticky right-0 bg-surface shadow-[-10px_0_10px_-10px_rgb(0_0_0/0.6)] group-hover:bg-surface-raised">{membership.is_active && <div className="flex flex-wrap gap-2"><button className="button-secondary min-h-8 px-3 py-1 text-xs" onClick={() => { change.reset(); setEditing(membership.id); setEditShirt(String(membership.shirt_number ?? '')) }}><Pencil aria-hidden="true" className="size-3.5" />Edit shirt</button>
          <button className="button-secondary min-h-8 px-3 py-1 text-xs" disabled={remove.isPending} onClick={() => remove.mutate(membership.id)} aria-label={`Remove ${playerName(membership.player)} from squad`}><UserMinus aria-hidden="true" className="size-3.5" />Remove</button></div>}</td>}
      </tr>)}</tbody></table></div>}
      {!squad.data.total && <p className="py-5 text-slate-400">No squad memberships found.</p>}<Pager total={squad.data.total} offset={offset} onChange={setOffset} /></>}
    {editing !== null && <form className="mt-6 rounded-xl border border-line bg-canvas/40 p-4" onSubmit={(e) => { e.preventDefault(); change.mutate({ id: editing, shirt_number: editShirt ? Number(editShirt) : null }) }}>
      <div className="max-w-xs"><Field label="New shirt number (optional)"><input type="number" className="field-input" min={1} max={99} step={1} value={editShirt} onChange={(e) => setEditShirt(e.target.value)} /></Field></div>
      <div className="mt-3 flex gap-3"><button className="button-primary" disabled={change.isPending}>Save shirt</button><button type="button" className="button-secondary" disabled={change.isPending} onClick={() => setEditing(null)}>Cancel</button></div>
    </form>}
  </section>
}

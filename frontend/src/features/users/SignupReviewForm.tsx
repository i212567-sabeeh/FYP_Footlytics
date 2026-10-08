import { useState, type FormEvent } from 'react'
import { CircleAlert, CircleCheck, CircleX, Undo2, X } from 'lucide-react'
import { ROLE_OPTIONS, roleLabel } from '../auth/types'
import { useOptions } from '../football/api'
import type { Club } from '../football/types'
import { Field, Initials, QueryState } from '../football/ui'
import type { SignupApproval, SignupRequest } from './signupApi'

const approvalRoles = ROLE_OPTIONS.filter((option) => option.value !== 'admin')

interface Props {
  request: SignupRequest
  saving: boolean
  error: Error | null
  onApprove: (data: SignupApproval) => void
  onReject: () => void
  onCancel: () => void
}

export function SignupReviewForm({ request, saving, error, onApprove, onReject, onCancel }: Props) {
  const [role, setRole] = useState(request.requested_role ?? '')
  const [club, setClub] = useState('')
  const [validation, setValidation] = useState('')
  const [confirmReject, setConfirmReject] = useState(false)
  const clubs = useOptions<Club>('clubs', { active: true })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const selected = approvalRoles.find((option) => option.value === role)
    if (!selected) { setValidation('Choose a role before approving access.'); return }
    setValidation('')
    onApprove({ roles: [selected.value], club_id: club ? Number(club) : null })
  }

  return <form onSubmit={submit} noValidate className="panel mb-8 border-emerald-400/30" aria-label={`Review ${request.full_name}`}>
    <div className="flex items-center gap-3"><Initials name={request.full_name} />
      <div className="min-w-0"><h2 className="text-xl font-semibold">Review {request.full_name}</h2><p className="break-all text-sm text-slate-400">{request.email}</p></div></div>
    <p className="mt-4 text-sm text-slate-400">Requested role: {request.requested_role ? roleLabel(request.requested_role) : 'Not specified'}</p>
    <fieldset disabled={saving} className="mt-6 space-y-5">
      {confirmReject ? <div className="rounded-xl border border-red-400/30 bg-red-400/5 p-4">
        <h3 className="font-semibold">Reject this signup request?</h3>
        <p className="mt-2 text-sm text-slate-400">No account will be created. The applicant must contact an administrator for further help.</p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" className="button-secondary text-red-300" onClick={onReject}><CircleX aria-hidden="true" className="size-4" />{saving ? 'Rejecting…' : 'Confirm rejection'}</button>
          <button type="button" className="button-secondary" onClick={() => setConfirmReject(false)}><Undo2 aria-hidden="true" className="size-4" />Back to review</button>
        </div>
      </div> : <>
        {request.requested_role ? <p className="text-sm text-slate-300">Approval grants the requested {roleLabel(request.requested_role)} role.</p> :
          <div className="max-w-sm"><Field label="Approved role"><select className="field-input" value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="">Choose a role for this older request</option>
            {approvalRoles.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
          </select></Field></div>}
        <QueryState query={clubs} />
        <div className="max-w-sm"><Field label="Club access (optional)"><select className="field-input" value={club} disabled={clubs.isPending || clubs.isError} onChange={(event) => setClub(event.target.value)}>
          <option value="">Assign a club later</option>
          {clubs.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></Field></div>
        {!club && <p className="text-sm text-slate-400">Without a club assignment, the approved account can sign in but cannot access club records. You can assign memberships under Clubs later.</p>}
        {role === 'player' && <p className="text-sm text-slate-400">Player access also requires a linked active player profile and squad membership, managed under Players and Teams.</p>}
        <div className="flex flex-wrap gap-3">
          <button type="submit" className="button-primary" disabled={clubs.isPending || clubs.isError}><CircleCheck aria-hidden="true" className="size-4" />{saving ? 'Approving…' : 'Approve access'}</button>
          <button type="button" className="button-secondary" onClick={() => { setValidation(''); setConfirmReject(true) }}><CircleX aria-hidden="true" className="size-4" />Reject request</button>
        </div>
      </>}
      {(validation || error) && <p role="alert" className="flex items-start gap-2 rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-2.5 text-sm text-red-200">
        <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{validation || error?.message}</p>}
      <button type="button" className="button-secondary" onClick={onCancel}><X aria-hidden="true" className="size-4" />Cancel review</button>
    </fieldset>
  </form>
}

import { useState, type FormEvent } from 'react'
import { ROLE_OPTIONS, roleLabel } from '../auth/types'
import { useOptions } from '../football/api'
import type { Club } from '../football/types'
import { Field, QueryState } from '../football/ui'
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

  return <form onSubmit={submit} noValidate className="panel mb-8" aria-label={`Review ${request.full_name}`}>
    <h2 className="text-xl font-semibold">Review {request.full_name}</h2>
    <p className="mt-2 break-all text-slate-400">{request.email}</p>
    <p className="mt-2 text-sm text-slate-400">Requested role: {request.requested_role ? roleLabel(request.requested_role) : 'Not specified'}</p>
    <fieldset disabled={saving} className="mt-6 space-y-5">
      {confirmReject ? <div>
        <h3 className="font-semibold">Reject this signup request?</h3>
        <p className="mt-2 text-sm text-slate-400">No account will be created. The applicant must contact an administrator for further help.</p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" className="button-secondary text-red-300" onClick={onReject}>{saving ? 'Rejecting…' : 'Confirm rejection'}</button>
          <button type="button" className="button-secondary" onClick={() => setConfirmReject(false)}>Back to review</button>
        </div>
      </div> : <>
        {request.requested_role ? <p className="text-sm text-slate-300">Approval grants the requested {roleLabel(request.requested_role)} role.</p> :
          <Field label="Approved role"><select className="field-input" value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="">Choose a role for this older request</option>
            {approvalRoles.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
          </select></Field>}
        <QueryState query={clubs} />
        <Field label="Club access (optional)"><select className="field-input" value={club} disabled={clubs.isPending || clubs.isError} onChange={(event) => setClub(event.target.value)}>
          <option value="">Assign a club later</option>
          {clubs.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></Field>
        {!club && <p className="text-sm text-slate-400">Without a club assignment, the approved account can sign in but cannot access club records. You can assign memberships under Clubs later.</p>}
        {role === 'player' && <p className="text-sm text-slate-400">Player access also requires a linked active player profile and squad membership, managed under Players and Teams.</p>}
        <div className="flex flex-wrap gap-3">
          <button type="submit" className="button-primary" disabled={clubs.isPending || clubs.isError}>{saving ? 'Approving…' : 'Approve access'}</button>
          <button type="button" className="button-secondary" onClick={() => { setValidation(''); setConfirmReject(true) }}>Reject request</button>
        </div>
      </>}
      {(validation || error) && <p role="alert" className="text-sm text-red-300">{validation || error?.message}</p>}
      <button type="button" className="button-secondary" onClick={onCancel}>Cancel review</button>
    </fieldset>
  </form>
}

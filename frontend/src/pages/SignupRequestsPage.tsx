import { useState } from 'react'
import { Link } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { approveSignup, fetchSignupRequests, rejectSignup, type SignupApproval, type SignupRequest, type SignupStatus } from '../features/users/signupApi'
import { SignupReviewForm } from '../features/users/SignupReviewForm'
import { roleLabel } from '../features/auth/types'
import { DateText, Empty, Field, Heading, Pager, QueryState } from '../features/football/ui'

type ReviewAction = { id: number; approval: SignupApproval } | { id: number; approval: null }

export function SignupRequestsPage() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<SignupStatus>('pending')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<SignupRequest | null>(null)
  const [notice, setNotice] = useState('')
  const requests = useQuery({
    queryKey: ['signup-requests', status, offset],
    queryFn: ({ signal }) => fetchSignupRequests(status, offset, signal),
  })
  const review = useMutation({
    mutationFn: async (action: ReviewAction) => action.approval
      ? approveSignup(action.id, action.approval) : rejectSignup(action.id),
    onSuccess: async (_result, action) => {
      setSelected(null)
      setOffset(0)
      setNotice(action.approval ? 'Access approved. The applicant can now sign in.' : 'Signup request rejected. No account was created.')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['signup-requests'] }),
        queryClient.invalidateQueries({ queryKey: ['users'] }),
        queryClient.invalidateQueries({ queryKey: ['football'] }),
      ])
    },
    onError: async () => { await queryClient.invalidateQueries({ queryKey: ['signup-requests'] }) },
  })

  return <section>
    <Heading title="Access requests"><Link to="/admin/users" className="button-secondary">User management</Link></Heading>
    <p className="mb-6 max-w-2xl text-slate-400">Review public signup requests. Only approval creates an account; you choose its roles and club access.</p>
    {notice && <p role="status" className="mb-5 text-emerald-300">{notice}</p>}
    {selected && <SignupReviewForm key={selected.id} request={selected} saving={review.isPending} error={review.error}
      onApprove={(approval) => review.mutate({ id: selected.id, approval })}
      onReject={() => review.mutate({ id: selected.id, approval: null })}
      onCancel={() => { setSelected(null); review.reset() }} />}
    <div className="mb-6 max-w-xs"><Field label="Request status"><select className="field-input" value={status} disabled={review.isPending}
      onChange={(event) => { setStatus(event.target.value as SignupStatus); setOffset(0); setSelected(null); setNotice(''); review.reset() }}>
      <option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
    </select></Field></div>
    <QueryState query={requests} />
    {requests.data && <>
      <div className="grid gap-4 sm:grid-cols-2">{requests.data.items.map((request) => <article className="panel min-w-0" key={request.id}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0"><h2 className="break-words text-lg font-semibold">{request.full_name}</h2><p className="mt-1 break-all text-sm text-slate-400">{request.email}</p></div>
          <span className="text-sm capitalize text-emerald-300">{request.status}</span>
        </div>
        <p className="mt-4 text-sm text-slate-400">Requested role: {request.requested_role ? roleLabel(request.requested_role) : 'Not specified'}</p>
        <p className="mt-2 text-sm text-slate-400">Requested <DateText value={request.created_at} /></p>
        {request.reviewed_at && <p className="mt-2 text-sm text-slate-400">Reviewed <DateText value={request.reviewed_at} />{request.reviewed_by_user_id !== null && ` by administrator #${request.reviewed_by_user_id}`}</p>}
        {request.approved_user_id !== null && <p className="mt-2 text-sm text-slate-400">Approved account #{request.approved_user_id}</p>}
        {request.status === 'pending' && <button className="button-secondary mt-5" disabled={review.isPending} aria-label={`Review ${request.full_name}`}
          onClick={() => { review.reset(); setNotice(''); setSelected(request) }}>Review request</button>}
      </article>)}</div>
      {!requests.data.total && <Empty>No {status} signup requests.</Empty>}
      <Pager total={requests.data.total} offset={offset} onChange={(value) => { if (!review.isPending) setOffset(value) }} />
    </>}
  </section>
}

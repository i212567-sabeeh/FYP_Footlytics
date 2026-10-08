import { useState } from 'react'
import { Link } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleCheck, Pencil, UserPlus, UserRoundPlus } from 'lucide-react'
import { createUser, fetchUsers, updateUser } from '../features/users/api'
import { UserForm, type UserFormValue } from '../features/users/UserForm'
import { roleLabel, type User } from '../features/auth/types'
import { Empty, Heading, Initials, Pager, QueryState, Status } from '../features/football/ui'
import { useAuth } from '../hooks/useAuth'

function RoleBadges({ user }: { user: User }) {
  return <div className="flex flex-wrap gap-1.5">{user.roles.map((role) => <span key={role} className={`rounded-full border px-2 py-0.5 text-xs font-medium ${role === 'admin'
    ? 'border-emerald-400/35 bg-emerald-400/10 text-emerald-200' : 'border-line-strong text-slate-300'}`}>{roleLabel(role)}</span>)}</div>
}

export function UsersPage() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const [offset, setOffset] = useState(0)
  const [editor, setEditor] = useState<{ user: User | null } | null>(null)
  const [notice, setNotice] = useState('')
  const users = useQuery({
    queryKey: ['users', offset], queryFn: ({ signal }) => fetchUsers(offset, signal),
  })
  const save = useMutation({
    mutationFn: (values: UserFormValue) => editor?.user
      ? updateUser(editor.user.id, {
        email: values.email, full_name: values.full_name,
        roles: values.roles, is_active: values.is_active,
      })
      : createUser({
        email: values.email, full_name: values.full_name,
        roles: values.roles, password: values.password,
      }),
    onSuccess: async () => {
      setEditor(null)
      setNotice('User saved.')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['users'] }),
        queryClient.invalidateQueries({ queryKey: ['auth', 'me'] }),
      ])
    },
  })

  function openEditor(user: User | null) {
    save.reset()
    setNotice('')
    setEditor({ user })
  }

  return <section>
    <Heading title="User management" description="Login accounts and their global roles. Club access is assigned per club under Clubs; football players are separate records.">
      <Link className="button-secondary" to="/admin/signup-requests"><UserRoundPlus aria-hidden="true" className="size-4" />Review signup requests</Link>
      <button className="button-primary" disabled={save.isPending} onClick={() => openEditor(null)}><UserPlus aria-hidden="true" className="size-4" />Create user</button>
    </Heading>
    {notice && <p role="status" className="mb-5 flex items-center gap-2 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-2.5 text-sm text-emerald-200">
      <CircleCheck aria-hidden="true" className="size-4" />{notice}</p>}
    {editor && currentUser && <div className="mb-8">
      <UserForm key={editor.user?.id ?? 'new'} user={editor.user} currentUserId={currentUser.id}
        saving={save.isPending} error={save.error?.message ?? null}
        onSave={(values) => save.mutate(values)} onCancel={() => setEditor(null)} />
    </div>}
    {users.isPending ? <p role="status" className="py-4 text-sm text-slate-400">Loading users…</p> : <QueryState query={users} />}
    {users.data && <>
      {users.data.items.length === 0 ? <Empty>No users found.</Empty> : <div className="analytics-scroll" tabIndex={0} role="region" aria-label="Users table">
        <table className="analytics-table">
          <caption className="sr-only">Application users and assigned roles</caption>
          {/* Small screens hide Email (shown when editing) and keep Actions pinned in view. */}
          <thead><tr>{['Name', 'Email', 'Roles', 'Status', 'Actions'].map((title) => <th key={title} scope="col"
            className={title === 'Email' ? 'hidden md:table-cell' : title === 'Actions' ? 'sticky right-0 bg-canvas' : undefined}>{title}</th>)}</tr></thead>
          <tbody>{users.data.items.map((user) => <tr key={user.id} className="group">
            <td><span className="flex items-center gap-3"><Initials name={user.full_name} className="size-8 text-xs" /><span className="font-medium text-slate-100">{user.full_name}</span></span></td>
            <td className="hidden text-slate-300 md:table-cell">{user.email}</td>
            <td><RoleBadges user={user} /></td>
            <td><Status active={user.is_active} /></td>
            <td className="sticky right-0 bg-surface shadow-[-10px_0_10px_-10px_rgb(0_0_0/0.6)] group-hover:bg-surface-raised"><button className="button-secondary min-h-8 px-3 py-1 text-xs" disabled={save.isPending}
              aria-label={`Edit ${user.full_name}`} onClick={() => openEditor(user)}><Pencil aria-hidden="true" className="size-3.5" />Edit</button></td>
          </tr>)}</tbody>
        </table>
      </div>}
      <Pager total={users.data.total} offset={offset} onChange={setOffset} />
    </>}
  </section>
}

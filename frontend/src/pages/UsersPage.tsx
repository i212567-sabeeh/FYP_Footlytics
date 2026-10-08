import { useState } from 'react'
import { Link } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createUser, fetchUsers, updateUser } from '../features/users/api'
import { UserForm, type UserFormValue } from '../features/users/UserForm'
import { roleLabel, type User } from '../features/auth/types'
import { useAuth } from '../hooks/useAuth'

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

  return (
    <section>
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">User management</h1>
          <p className="mt-2 text-slate-400">Manage accounts, access and roles.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link className="button-secondary" to="/admin/signup-requests">Review signup requests</Link>
          <button className="button-primary" disabled={save.isPending} onClick={() => openEditor(null)}>Create user</button>
        </div>
      </div>
      {notice && <p role="status" className="mb-4 text-emerald-300">{notice}</p>}
      {editor && currentUser && <div className="mb-8">
        <UserForm key={editor.user?.id ?? 'new'} user={editor.user} currentUserId={currentUser.id}
          saving={save.isPending} error={save.error?.message ?? null}
          onSave={(values) => save.mutate(values)} onCancel={() => setEditor(null)} />
      </div>}
      {users.isPending && <p role="status">Loading users…</p>}
      {users.isError && <div role="alert" className="text-red-300">
        <p>{users.error.message}</p>
        <button className="button-secondary mt-3" onClick={() => { void users.refetch() }}>Try again</button>
      </div>}
      {users.data && <>
        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Application users and assigned roles</caption>
            <thead className="bg-slate-900 text-slate-300">
              <tr>{['Name', 'Email', 'Roles', 'Status', 'Actions'].map((title) =>
                <th key={title} scope="col" className="px-4 py-4 font-medium">{title}</th>)}</tr>
            </thead>
            <tbody>{users.data.items.map((user) => <tr key={user.id} className="border-t border-slate-800">
              <td className="px-4 py-4">{user.full_name}</td>
              <td className="px-4 py-4 text-slate-300">{user.email}</td>
              <td className="px-4 py-4 text-slate-300">{user.roles.map(roleLabel).join(', ')}</td>
              <td className="px-4 py-4">{user.is_active ? 'Active' : 'Inactive'}</td>
              <td className="px-4 py-4"><button className="text-emerald-400 underline" disabled={save.isPending}
                aria-label={`Edit ${user.full_name}`} onClick={() => openEditor(user)}>Edit</button></td>
            </tr>)}</tbody>
          </table>
        </div>
        {users.data.items.length === 0 && <p className="mt-4">No users found.</p>}
        <div className="mt-5 flex items-center justify-between gap-3 text-sm">
          <span>{users.data.total} users</span>
          <div className="flex gap-3">
            <button className="button-secondary" disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button>
            <button className="button-secondary" disabled={offset + 25 >= users.data.total}
              onClick={() => setOffset(offset + 25)}>Next</button>
          </div>
        </div>
      </>}
    </section>
  )
}

import { apiRequest } from '../../api/client'
import type { Role, User } from '../auth/types'

export interface UserFields {
  email: string
  full_name: string
  roles: Role[]
}

export interface UserCreate extends UserFields { password: string }
export interface UserUpdate extends UserFields { is_active: boolean }
export interface UserList {
  items: User[]
  total: number
  offset: number
  limit: number
}

export function fetchUsers(offset: number, signal?: AbortSignal) {
  return apiRequest<UserList>(`users?offset=${offset}&limit=25`, { signal })
}

export function createUser(data: UserCreate) {
  return apiRequest<User>('users', { method: 'POST', body: data })
}

export function updateUser(id: number, data: UserUpdate) {
  return apiRequest<User>(`users/${id}`, { method: 'PATCH', body: data })
}

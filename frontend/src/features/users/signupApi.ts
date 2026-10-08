import { apiRequest } from '../../api/client'
import type { Role, User } from '../auth/types'
import type { Page } from '../football/types'

export type SignupRole = Exclude<Role, 'admin'>
export type SignupStatus = 'pending' | 'approved' | 'rejected'
export interface SignupFields { full_name: string; email: string; password: string; requested_role: SignupRole }
export interface SignupRequest {
  id: number
  email: string
  full_name: string
  requested_role: SignupRole | null
  status: SignupStatus
  created_at: string
  reviewed_at: string | null
  reviewed_by_user_id: number | null
  approved_user_id: number | null
}
export interface SignupApproval { roles: [SignupRole]; club_id: number | null }

export function submitSignup(data: SignupFields) {
  return apiRequest<{ message: string }>('auth/signup', {
    method: 'POST', body: data, authenticated: false,
  })
}
export function fetchSignupRequests(status: SignupStatus, offset: number, signal?: AbortSignal) {
  return apiRequest<Page<SignupRequest>>(`signup-requests?status=${status}&offset=${offset}&limit=25`, { signal })
}
export function approveSignup(id: number, data: SignupApproval) {
  return apiRequest<User>(`signup-requests/${id}/approve`, { method: 'POST', body: data })
}
export function rejectSignup(id: number) {
  return apiRequest<SignupRequest>(`signup-requests/${id}/reject`, { method: 'POST' })
}

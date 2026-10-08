export const ROLE_OPTIONS = [
  { value: 'admin', label: 'Admin' },
  { value: 'coach', label: 'Coach' },
  { value: 'analyst', label: 'Analyst' },
  { value: 'player', label: 'Player' },
  { value: 'club_management', label: 'Club Management' },
] as const

export type Role = (typeof ROLE_OPTIONS)[number]['value']

export interface User {
  id: number
  email: string
  full_name: string
  is_active: boolean
  roles: Role[]
  created_at: string
  updated_at: string
}

export interface Credentials {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
}

export function hasRole(user: User | null, role: Role): boolean {
  return user?.roles.includes(role) ?? false
}

export function hasAnyRole(user: User | null, roles: readonly Role[]): boolean {
  return roles.some((role) => hasRole(user, role))
}

export function roleLabel(role: Role): string {
  return ROLE_OPTIONS.find((option) => option.value === role)?.label ?? role
}

import { createContext } from 'react'
import type { Credentials, User } from './types'

export interface AuthState {
  user: User | null
  accessToken: string | null
  isLoading: boolean
  error: Error | null
  login: (credentials: Credentials) => Promise<void>
  logout: () => void
  retrySession: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

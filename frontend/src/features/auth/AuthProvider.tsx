import { useEffect, useSyncExternalStore, type PropsWithChildren } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import { AuthContext } from './AuthContext'
import { getAccessToken, setAccessToken, subscribeToToken } from './tokenStorage'
import type { Credentials, TokenResponse, User } from './types'

export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient()
  const token = useSyncExternalStore(subscribeToToken, getAccessToken)
  const session = useQuery({
    queryKey: ['auth', 'me', token],
    queryFn: ({ signal }) => apiRequest<User>('auth/me', { signal }),
    enabled: token !== null,
    retry: false,
    staleTime: 30_000,
  })

  useEffect(() => subscribeToToken(() => {
    if (!getAccessToken()) queryClient.clear()
  }), [queryClient])

  async function login(credentials: Credentials) {
    const result = await apiRequest<TokenResponse>('auth/login', {
      method: 'POST', body: credentials, authenticated: false,
    })
    queryClient.clear()
    setAccessToken(result.access_token)
  }

  function logout() {
    setAccessToken(null)
    queryClient.clear()
  }

  return (
    <AuthContext.Provider value={{
      user: token ? session.data ?? null : null,
      accessToken: token,
      isLoading: token !== null && session.isPending,
      error: token ? session.error : null,
      login,
      logout,
      retrySession: () => { void session.refetch() },
    }}>
      {children}
    </AuthContext.Provider>
  )
}

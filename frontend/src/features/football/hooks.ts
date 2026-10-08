import { useMutation, useQueryClient } from '@tanstack/react-query'
import { hasAnyRole } from '../auth/types'
import { useAuth } from '../../hooks/useAuth'

export function useCapabilities() {
  const { user } = useAuth()
  return { admin: hasAnyRole(user, ['admin']), roster: hasAnyRole(user, ['admin', 'coach']),
    match: hasAnyRole(user, ['admin', 'coach', 'analyst']),
    analytics: hasAnyRole(user, ['admin', 'coach', 'analyst', 'club_management']) }
}
export function useSave<T>(mutationFn: (value: T) => Promise<unknown>, onSuccess?: () => void) {
  const client = useQueryClient()
  return useMutation({ mutationFn, onSuccess: async () => {
    await client.invalidateQueries({ queryKey: ['football'] })
    onSuccess?.()
  } })
}

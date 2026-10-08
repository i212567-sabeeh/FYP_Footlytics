import { useCallback, useSyncExternalStore } from 'react'
import { useQueryClient, type QueryKey } from '@tanstack/react-query'

/**
 * Reads data another component has already loaded, without creating a query
 * observer or fetching. The shell uses it for context such as the match title,
 * so navigation chrome never adds API calls or changes access behavior.
 */
export function useCachedQueryData<T>(queryKey: QueryKey | null): T | undefined {
  const client = useQueryClient()
  const subscribe = useCallback((onChange: () => void) => client.getQueryCache().subscribe(onChange), [client])
  return useSyncExternalStore(subscribe, () => (queryKey ? client.getQueryData<T>(queryKey) : undefined))
}

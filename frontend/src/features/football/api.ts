import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import type { Page } from './types'

export type Filters = Record<string, string | number | boolean | undefined>
export function listRecords<T>(path: string, filters: Filters = {}, signal?: AbortSignal) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '') params.set(key, String(value))
  })
  return apiRequest<Page<T>>(`${path}?${params}`, { signal })
}
export function useRecords<T>(path: string, filters: Filters = {}, enabled = true) {
  return useQuery({ queryKey: ['football', path, filters], enabled,
    queryFn: ({ signal }) => listRecords<T>(path, filters, signal) })
}
export const recordKey = (path: string) => ['football', path] as const
export function useRecord<T>(path: string) {
  return useQuery({ queryKey: recordKey(path), queryFn: ({ signal }) => apiRequest<T>(path, { signal }) })
}
// Pickers traverse every page; a club with >100 records must not silently lose options.
export function useOptions<T>(path: string, filters: Filters = {}, enabled = true) {
  return useQuery({ queryKey: ['football', 'options', path, filters], enabled,
    queryFn: async ({ signal }) => {
      const items: T[] = []
      let offset = 0
      while (true) {
        const page = await listRecords<T>(path, { ...filters, offset, limit: 100 }, signal)
        items.push(...page.items)
        offset += page.items.length
        if (offset >= page.total || page.items.length === 0) return items
      }
    } })
}

import { getAccessToken, setAccessToken } from '../features/auth/tokenStorage'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
  authenticated?: boolean
  accept?: string
}

function errorMessage(payload: unknown, status: number): string {
  if (status >= 500) return 'The server could not complete the request. Please try again.'
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    if (typeof payload.detail === 'string') return payload.detail
    if (Array.isArray(payload.detail)) {
      const messages = payload.detail.flatMap((entry: unknown) => {
        if (typeof entry !== 'object' || entry === null || !('msg' in entry)) return []
        return typeof entry.msg === 'string' ? [entry.msg] : []
      })
      if (messages.length) return messages.join('. ')
    }
  }
  return `Request failed (${status}). Please try again.`
}

async function requestResponse(path: string, options: RequestOptions): Promise<Response> {
  const token = options.authenticated === false ? null : getAccessToken()
  const headers: Record<string, string> = { Accept: options.accept ?? 'application/json' }
  const multipart = options.body instanceof FormData
  if (token) headers.Authorization = `Bearer ${token}`
  // The browser supplies the multipart boundary; setting Content-Type loses it.
  if (options.body !== undefined && !multipart) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}/${path.replace(/^\//, '')}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : multipart ? options.body as FormData : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (error) {
    if (options.signal?.aborted) throw error
    throw new ApiError(0, 'Unable to reach the server. Check your connection and try again.')
  }

  if (!response.ok) {
    // An old request must not log out a newly established session.
    if (response.status === 401 && token && token === getAccessToken()) {
      setAccessToken(null)
    }
    let payload: unknown = null
    try { payload = await response.json() } catch { /* Non-JSON errors use a safe fallback. */ }
    throw new ApiError(response.status, errorMessage(payload, response.status))
  }

  return response
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await requestResponse(path, options)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

// Protected images share JSON requests' bearer token, cancellation and error handling.
export async function apiBlobRequest(path: string, options: RequestOptions = {}) {
  const response = await requestResponse(path, { accept: 'application/octet-stream', ...options })
  return { blob: await response.blob(), headers: response.headers }
}

export function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, { signal })
}

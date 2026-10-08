import { afterEach, expect, it, vi } from 'vitest'
import { apiRequest } from './client'
import { getAccessToken, setAccessToken } from '../features/auth/tokenStorage'

afterEach(() => { setAccessToken(null); vi.unstubAllGlobals() })

it('accepts a successful squad removal with no JSON body', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)
  setAccessToken('coach-session')
  await expect(apiRequest<void>('teams/1/squad/2', { method: 'DELETE' })).resolves.toBeUndefined()
  expect(fetchMock).toHaveBeenCalledWith('/api/teams/1/squad/2', expect.objectContaining({ method: 'DELETE', headers: expect.objectContaining({ Authorization: 'Bearer coach-session' }) }))
  expect(getAccessToken()).toBe('coach-session')
})

it('does not let an old 401 clear a newer session', async () => {
  let finish: (value: Response) => void = () => undefined
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { finish = resolve })))
  setAccessToken('old-session')
  const pending = apiRequest('users')
  const rejected = expect(pending).rejects.toMatchObject({ status: 401 })
  setAccessToken('new-session')
  finish(new Response(JSON.stringify({ detail: 'Expired' }), { status: 401 }))
  await rejected
  expect(getAccessToken()).toBe('new-session')
})

it('preserves a valid session on permission failures', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Insufficient permissions' }), { status: 403 })))
  setAccessToken('coach-session')
  await expect(apiRequest('users')).rejects.toMatchObject({ status: 403 })
  expect(getAccessToken()).toBe('coach-session')
})

it('sends multipart replacement without overriding the browser boundary', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 2 })))
  vi.stubGlobal('fetch', fetchMock)
  setAccessToken('coach-session')
  const body = new FormData()
  body.append('file', new File(['fixture'], 'match.mp4', { type: 'video/mp4' }))
  await apiRequest('matches/1/video', { method: 'PUT', body })
  expect(fetchMock).toHaveBeenCalledWith('/api/matches/1/video', expect.objectContaining({ method: 'PUT', body,
    headers: { Accept: 'application/json', Authorization: 'Bearer coach-session' } }))
})

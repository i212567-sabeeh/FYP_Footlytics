import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { AppProviders } from '../../components/AppProviders'
import { setAccessToken } from '../auth/tokenStorage'
import type { User } from '../auth/types'

// Synthetic API fixtures for management UI behaviour only.
const admin: User = { id: 1, email: 'admin@example.com', full_name: 'Test Admin', roles: ['admin'], is_active: true, created_at: '', updated_at: '' }
const analyst: User = { ...admin, id: 5, email: 'ana@example.com', full_name: 'Ana Analyst', roles: ['analyst'] }
const club = { id: 1, name: 'North Club', short_name: 'NC', description: null, is_active: true }
const fetchMock = vi.fn<typeof fetch>()
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const page = (items: unknown[]) => ({ items, total: items.length, offset: 0, limit: 25 })
const calls = (method: string) => fetchMock.mock.calls.filter(([, options]) => options?.method === method).map(([url, options]) => [String(url), options?.body])

function renderApp(path: string, signedIn = true) {
  setAccessToken(signedIn ? 'management-token' : null)
  return render(<AppProviders><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AppProviders>)
}
beforeEach(() => {
  setAccessToken(null)
  fetchMock.mockReset().mockImplementation(async (input, options) => {
    const path = String(input)
    if (path === '/api/auth/me') return json(admin)
    if (path === '/api/auth/login') return json({ access_token: 'issued-token', token_type: 'bearer' })
    if (path === '/api/clubs/1') return json(club)
    if (path.startsWith('/api/clubs/1/members?')) return json(page([{ id: 9, club_id: 1, user_id: 5, user: { id: 5, full_name: 'Ana Analyst' } }]))
    if (options?.method === 'DELETE' && path === '/api/clubs/1/members/5') return new Response(null, { status: 204 })
    if (path.startsWith('/api/users?')) return json(page([admin, analyst]))
    if (path.startsWith('/api/clubs?')) return json(page([club]))
    if (path.startsWith('/api/teams?')) return json(page([{ id: 3, club_id: 1, club, name: 'North First Team', short_name: null, description: null, is_active: true }]))
    return json({ detail: 'Unexpected fixture request' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { vi.unstubAllGlobals(); setAccessToken(null) })

describe('management pages', () => {
  it('asks for confirmation before revoking club access', async () => {
    renderApp('/clubs/1')
    const members = within(await screen.findByRole('region', { name: 'Club members' }))
    fireEvent.click(await members.findByRole('button', { name: 'Remove Ana Analyst from club' }))
    expect(members.getByText('Remove club access?')).toBeVisible()
    fireEvent.click(members.getByRole('button', { name: 'Keep access' }))
    expect(calls('DELETE')).toEqual([])
    fireEvent.click(members.getByRole('button', { name: 'Remove Ana Analyst from club' }))
    fireEvent.click(members.getByRole('button', { name: 'Confirm removal' }))
    await waitFor(() => expect(calls('DELETE')).toEqual([['/api/clubs/1/members/5', undefined]]))
  })
  it('clears list filters in one step and pluralises record counts', async () => {
    renderApp('/teams?club_id=1')
    expect(await screen.findByRole('link', { name: 'North First Team' })).toBeVisible()
    expect(screen.getByText('1 record')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'true' } })
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getByLabelText('Status')).toHaveValue('')
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url) === '/api/teams?offset=0&limit=25')).toBe(true))
  })
  it('reveals the password on request and still submits the same value', async () => {
    renderApp('/login', false)
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'admin@example.com' } })
    const password = screen.getByLabelText('Password')
    fireEvent.change(password, { target: { value: 'correct horse' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(password).toHaveAttribute('type', 'text')
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(password).toHaveAttribute('type', 'password')
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    await waitFor(() => expect(calls('POST')).toEqual([['/api/auth/login', JSON.stringify({ email: 'admin@example.com', password: 'correct horse' })]]))
  })
  it('shows a helpful not-found page', async () => {
    renderApp('/no-such-page', false)
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Return home' })).toHaveAttribute('href', '/')
  })
})

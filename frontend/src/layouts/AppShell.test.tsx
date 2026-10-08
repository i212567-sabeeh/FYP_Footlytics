import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AppProviders } from '../components/AppProviders'
import { setAccessToken } from '../features/auth/tokenStorage'
import type { User } from '../features/auth/types'
import { recordKey } from '../features/football/api'
import { breadcrumbs, isWideRoute, matchIdFromPath } from './navigation'
import { TopBar } from './TopBar'

// Explicit fixtures; the shell always receives users from the backend.
const coach: User = {
  id: 2, email: 'coach@example.com', full_name: 'Test Coach', is_active: true,
  roles: ['coach'], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}
const admin: User = { ...coach, id: 1, email: 'admin@example.com', full_name: 'Test Admin', roles: ['admin'] }
const fetchMock = vi.fn<typeof fetch>()
const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } })

function renderShell(path = '/', user = coach) {
  setAccessToken('shell-token')
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    if (url === '/api/auth/me') return json(user)
    if (/^\/api\/(clubs|teams|players|matches)\?/.test(url)) return json({ items: [], total: 0, offset: 0, limit: 25 })
    throw new Error(`Unexpected test request: ${url}`)
  })
  return render(<AppProviders><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AppProviders>)
}
const mainNavigation = () => screen.findByRole('navigation', { name: 'Main navigation' })

beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock) })
afterEach(() => { vi.unstubAllGlobals(); setAccessToken(null); localStorage.clear() })

describe('route breadcrumbs', () => {
  it.each([
    ['/', ['Home']],
    ['/matches', ['Matches']],
    ['/matches/new', ['Matches', 'New match']],
    ['/matches/4', ['Matches', 'Match details']],
    ['/matches/4/review', ['Matches', 'Match details', 'Detection & tracking review']],
    ['/clubs/2', ['Clubs', 'Club details']],
    ['/admin/signup-requests', ['Administration', 'Access requests']],
    ['/matches/4/unknown', ['Not found']],
    ['/clubs/2/extra', ['Not found']],
  ])('labels %s', (path, labels) => {
    expect(breadcrumbs(path).map((crumb) => crumb.label)).toEqual(labels)
  })

  it('links ancestors, names loaded matches and widens only analysis workspaces', () => {
    expect(breadcrumbs('/matches/9/analytics', 'Derby Day')).toEqual([
      { label: 'Matches', to: '/matches' }, { label: 'Derby Day', to: '/matches/9' }, { label: 'Analytics' },
    ])
    expect([matchIdFromPath('/matches/9/review'), matchIdFromPath('/matches/new')]).toEqual([9, null])
    expect(['/matches/9/analytics', '/matches/9/review', '/matches/9', '/players'].map(isWideRoute)).toEqual([true, true, false, false])
  })
})

describe('application shell', () => {
  it('groups sidebar links and navigates between sections', async () => {
    renderShell('/')
    const nav = await mainNavigation()
    expect(within(nav).getAllByRole('link').map((link) => link.textContent)).toEqual(['Home', 'Matches', 'Clubs', 'Teams', 'Players'])
    expect(within(nav).getByRole('list', { name: 'Squad data' })).toBeVisible()
    fireEvent.click(within(nav).getByRole('link', { name: 'Teams' }))
    expect(await screen.findByRole('heading', { name: 'Teams' })).toBeVisible()
    expect(within(nav).getByRole('link', { name: 'Teams' })).toHaveAttribute('aria-current', 'page')
  })

  it('highlights only the current section and names it in the header', async () => {
    renderShell('/matches')
    const nav = await mainNavigation()
    expect(within(nav).getByRole('link', { name: 'Matches' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current')
    const trail = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(within(trail).getByText('Matches')).toHaveAttribute('aria-current', 'page')
  })

  it.each([[admin, true], [coach, false]])('shows administration links only to admins (%#)', async (user, visible) => {
    renderShell('/', user)
    const nav = await mainNavigation()
    for (const name of ['User management', 'Access requests']) {
      expect(within(nav).queryByRole('link', { name }) !== null).toBe(visible)
    }
  })

  it('opens a modal drawer and closes it with Escape, the backdrop and navigation', async () => {
    renderShell('/')
    const toggle = await screen.findByRole('button', { name: 'Open navigation' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    const drawer = screen.getByRole('dialog', { name: 'Navigation menu' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(within(drawer).getByRole('button', { name: 'Close navigation' })).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(toggle).toHaveFocus()
    fireEvent.click(toggle)
    fireEvent.click(screen.getByTestId('navigation-backdrop'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(toggle)
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('link', { name: 'Teams' }))
    expect(await screen.findByRole('heading', { name: 'Teams' })).toBeVisible()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps keyboard focus inside the open drawer', async () => {
    renderShell('/')
    fireEvent.click(await screen.findByRole('button', { name: 'Open navigation' }))
    const drawer = screen.getByRole('dialog', { name: 'Navigation menu' })
    const first = within(drawer).getByRole('link', { name: 'FOOTLYTICS' })
    const last = within(drawer).getByRole('link', { name: 'Players' })
    last.focus()
    fireEvent.keyDown(last, { key: 'Tab' })
    expect(first).toHaveFocus()
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true })
    expect(last).toHaveFocus()
  })

  it('collapses to accessible icon links and remembers the choice', async () => {
    renderShell('/')
    const collapse = await screen.findByRole('button', { name: 'Collapse navigation' })
    expect(collapse).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(collapse)
    expect(screen.getByRole('button', { name: 'Expand navigation' })).toHaveAttribute('aria-expanded', 'false')
    const matches = within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: 'Matches' })
    expect(matches).toHaveAttribute('title', 'Matches')
    expect(localStorage.getItem('footlytics.sidebar-collapsed')).toBe('true')
  })

  it('shows match context only from data the page already loaded', () => {
    const client = new QueryClient()
    client.setQueryData(recordKey('matches/7'), { title: 'Derby Day', match_format: '11v11', is_archived: false })
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/matches/7/analytics']}>
      <TopBar user={coach} onLogout={vi.fn()} menuOpen={false} onOpenMenu={vi.fn()} menuButton={{ current: null }} />
    </MemoryRouter></QueryClientProvider>)
    const trail = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(within(trail).getByRole('link', { name: 'Matches' })).toHaveAttribute('href', '/matches')
    expect(within(trail).getByRole('link', { name: 'Derby Day' })).toHaveAttribute('href', '/matches/7')
    expect(within(trail).getByText('Analytics')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('11v11')).toBeVisible()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

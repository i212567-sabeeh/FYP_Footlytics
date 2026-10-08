import { Goal, LayoutDashboard, Shield, Shirt, UserCog, UserPlus, Users, type LucideIcon } from 'lucide-react'
import type { Role } from '../features/auth/types'

export interface NavItem { to: string; label: string; icon: LucideIcon; end?: boolean }
export interface NavGroup { label: string; items: readonly NavItem[]; roles?: readonly Role[] }
export interface Crumb { label: string; to?: string }

// Mirrors AppRoutes: signed-in users reach every group; administration also
// needs the admin role. Hiding links is a convenience; routes and API enforce access.
export const NAV_GROUPS: readonly NavGroup[] = [
  { label: 'Workspace', items: [
    { to: '/', label: 'Home', icon: LayoutDashboard, end: true },
    { to: '/matches', label: 'Matches', icon: Goal },
  ] },
  { label: 'Squad data', items: [
    { to: '/clubs', label: 'Clubs', icon: Shield },
    { to: '/teams', label: 'Teams', icon: Users },
    { to: '/players', label: 'Players', icon: Shirt },
  ] },
  { label: 'Administration', roles: ['admin'], items: [
    { to: '/admin/users', label: 'User management', icon: UserCog },
    { to: '/admin/signup-requests', label: 'Access requests', icon: UserPlus },
  ] },
]

const SECTIONS: Partial<Record<string, [string, string]>> = {
  clubs: ['Clubs', 'Club details'], teams: ['Teams', 'Team details'], players: ['Players', 'Player details'],
}
const MATCH_PAGES: Partial<Record<string, string>> = {
  analytics: 'Analytics', review: 'Detection & tracking review', calibration: 'Pitch calibration',
}
const ADMIN_PAGES: Partial<Record<string, string>> = { users: 'User management', 'signup-requests': 'Access requests' }
const NOT_FOUND: Crumb[] = [{ label: 'Not found' }]

/** Numeric match ID of /matches/:id routes ("new" is not an ID). */
export function matchIdFromPath(pathname: string): number | null {
  const id = /^\/matches\/(\d+)(?:\/|$)/.exec(pathname)?.[1]
  return id === undefined ? null : Number(id)
}

/** Analysis workspaces use the full content width; forms and lists stay readable. */
export function isWideRoute(pathname: string): boolean {
  return /^\/matches\/\d+\/(analytics|review|calibration)\/?$/.test(pathname)
}

/** Route-derived trail whose last crumb is the current page. A match title is
 * shown only when the page has already loaded it; otherwise a neutral label. */
export function breadcrumbs(pathname: string, matchTitle?: string): Crumb[] {
  const [section, id, page, ...rest] = pathname.split('/').filter(Boolean)
  if (rest.length) return NOT_FOUND
  if (!section) return [{ label: 'Home' }]
  if (section === 'login' || section === 'signup') return id ? NOT_FOUND : [{ label: section === 'login' ? 'Sign in' : 'Sign up' }]
  if (section === 'matches') {
    if (!id) return [{ label: 'Matches' }]
    const matches = { label: 'Matches', to: '/matches' }
    if (id === 'new') return page ? NOT_FOUND : [matches, { label: 'New match' }]
    if (!/^\d+$/.test(id)) return NOT_FOUND
    const title = matchTitle ?? 'Match details'
    if (!page) return [matches, { label: title }]
    const label = MATCH_PAGES[page]
    return label ? [matches, { label: title, to: `/matches/${id}` }, { label }] : NOT_FOUND
  }
  const names = SECTIONS[section]
  if (names) return page ? NOT_FOUND : id ? [{ label: names[0], to: `/${section}` }, { label: names[1] }] : [{ label: names[0] }]
  const admin = section === 'admin' && id && !page ? ADMIN_PAGES[id] : undefined
  return admin ? [{ label: 'Administration' }, { label: admin }] : NOT_FOUND
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part.charAt(0).toUpperCase()).join('') || '?'
}

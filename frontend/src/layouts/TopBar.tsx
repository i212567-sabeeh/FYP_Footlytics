import type { RefObject } from 'react'
import { ChevronRight, LogOut, Menu } from 'lucide-react'
import { Link, useLocation } from 'react-router'
import { BrandMark } from '../components/BrandMark'
import type { User } from '../features/auth/types'
import { recordKey } from '../features/football/api'
import type { FootballMatch } from '../features/football/types'
import { useCachedQueryData } from '../hooks/useCachedQueryData'
import { Avatar } from './Sidebar'
import { breadcrumbs, matchIdFromPath } from './navigation'

interface Props {
  user: User
  onLogout: () => void
  menuOpen: boolean
  onOpenMenu: () => void
  menuButton: RefObject<HTMLButtonElement | null>
}

export function TopBar({ user, onLogout, menuOpen, onOpenMenu, menuButton }: Props) {
  const { pathname } = useLocation()
  const matchId = matchIdFromPath(pathname)
  // Match context comes only from data the page already loaded: never a new request.
  const match = useCachedQueryData<FootballMatch>(matchId === null ? null : recordKey(`matches/${matchId}`))
  const crumbs = breadcrumbs(pathname, match?.title)
  return <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur-md">
    <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
      <button ref={menuButton} type="button" onClick={onOpenMenu} aria-expanded={menuOpen} aria-controls="mobile-navigation" className="icon-button md:hidden">
        <Menu aria-hidden="true" className="size-5" /><span className="sr-only">Open navigation</span>
      </button>
      <Link to="/" className="shrink-0 rounded-lg md:hidden"><BrandMark compact /></Link>
      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex min-w-0 items-center gap-1.5 text-sm">
          {crumbs.map((crumb, index) => {
            const current = index === crumbs.length - 1
            return <li key={`${index}:${crumb.label}`} className={`items-center gap-1.5 ${current ? 'flex min-w-0' : 'sr-only shrink-0 sm:not-sr-only sm:flex'}`}>
              {current ? <span aria-current="page" className="truncate text-base font-semibold text-slate-50">{crumb.label}</span>
                : crumb.to ? <Link to={crumb.to} className="max-w-56 truncate rounded text-slate-400 transition-colors hover:text-slate-100">{crumb.label}</Link>
                  : <span className="text-slate-400">{crumb.label}</span>}
              {!current && <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-slate-600" />}
            </li>
          })}
        </ol>
      </nav>
      {match && <span className="hidden shrink-0 rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium text-slate-300 lg:inline">
        {match.match_format}{match.is_archived ? ' · Archived' : ''}</span>}
      <div className="flex shrink-0 items-center gap-2">
        <span title={`Signed in as ${user.full_name}`} className="hidden sm:block"><Avatar name={user.full_name} /></span>
        <button type="button" onClick={onLogout} className="button-secondary px-3">
          <LogOut aria-hidden="true" className="size-4" /><span className="sr-only sm:not-sr-only">Logout</span>
        </button>
      </div>
    </div>
  </header>
}

import { useCallback, useRef, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router'
import { BrandMark } from '../components/BrandMark'
import { useAuth } from '../hooks/useAuth'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { MobileNav } from './MobileNav'
import { isWideRoute } from './navigation'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

const COLLAPSED_KEY = 'footlytics.sidebar-collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === 'true'
  } catch {
    return false // Storage can be blocked (private mode); default to expanded.
  }
}

function SkipLink() {
  return <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-emerald-400 focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-slate-950">
    Skip to content
  </a>
}

function PublicLayout() {
  return <div className="min-h-dvh bg-canvas text-slate-100">
    <SkipLink />
    <header className="border-b border-line">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link to="/" className="rounded-lg"><BrandMark /></Link>
        <span className="text-sm text-slate-400">Post-match analysis</span>
      </div>
    </header>
    <main id="main-content" className="mx-auto max-w-6xl px-4 py-12 sm:px-6"><Outlet /></main>
  </div>
}

export function AppLayout() {
  const { user, logout } = useAuth()
  const { pathname } = useLocation()
  const desktop = useMediaQuery('(min-width: 768px)')
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [menuPath, setMenuPath] = useState<string | null>(null)
  const menuButton = useRef<HTMLButtonElement>(null)
  const closeMenu = useCallback(() => setMenuPath(null), [])
  // The drawer belongs to the page it opened on, so navigating closes it; it
  // also closes if the viewport grows into the persistent-sidebar layout.
  const menuOpen = !desktop && menuPath === pathname
  if (!user) return <PublicLayout />

  function toggleCollapsed() {
    const next = !collapsed
    setCollapsed(next)
    try {
      localStorage.setItem(COLLAPSED_KEY, String(next))
    } catch {
      // Storage unavailable: the choice still applies for this visit.
    }
  }

  return <div className="min-h-dvh bg-canvas text-slate-100 md:flex">
    <SkipLink />
    <Sidebar user={user} collapsed={collapsed} onToggle={toggleCollapsed} />
    <div className="flex min-w-0 flex-1 flex-col" inert={menuOpen}>
      <TopBar user={user} onLogout={logout} menuOpen={menuOpen} onOpenMenu={() => setMenuPath(pathname)} menuButton={menuButton} />
      <main id="main-content" className={`mx-auto w-full flex-1 px-4 py-8 sm:px-6 lg:px-8 lg:py-10 ${isWideRoute(pathname) ? 'max-w-[1600px]' : 'max-w-6xl'}`}>
        <Outlet />
      </main>
    </div>
    {menuOpen && <MobileNav user={user} onClose={closeMenu} returnFocus={menuButton} />}
  </div>
}

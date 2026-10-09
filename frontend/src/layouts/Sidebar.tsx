import { useId } from 'react'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { Link, NavLink } from 'react-router'
import { BrandMark } from '../components/BrandMark'
import { hasAnyRole, roleLabel, type User } from '../features/auth/types'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { initials, NAV_GROUPS } from './navigation'

interface NavProps { user: User; compact?: boolean; onNavigate?: () => void }

/** Grouped, role-aware links shared by the sidebar and the mobile drawer. In
 * compact mode labels stay in the accessible name and appear as tooltips. */
export function NavigationLinks({ user, compact = false, onNavigate }: NavProps) {
  const id = useId()
  return <nav aria-label="Main navigation" className="flex flex-col gap-6">
    {NAV_GROUPS.filter((group) => !group.roles || hasAnyRole(user, group.roles)).map((group, index) => <div key={group.label}>
      <p id={`${id}-${index}`} className={compact ? 'sr-only' : 'px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500'}>{group.label}</p>
      {compact && index > 0 && <div aria-hidden="true" className="mx-auto mb-3 h-px w-8 bg-line" />}
      <ul aria-labelledby={`${id}-${index}`} className="space-y-1">
        {group.items.map(({ to, label, icon: Icon, end }) => <li key={to}>
          <NavLink to={to} end={end} title={compact ? label : undefined} onClick={onNavigate}
            className={({ isActive }) => `group relative flex items-center gap-3 rounded-lg text-sm font-medium transition-colors ${compact ? 'mx-auto size-11 justify-center' : 'px-3 py-2.5'} ${isActive
              ? 'bg-emerald-400/10 text-emerald-100' : 'text-slate-400 hover:bg-surface-raised hover:text-slate-100'}`}>
            {({ isActive }) => <>
              {isActive && <span aria-hidden="true" className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-emerald-400" />}
              <Icon aria-hidden="true" className={`size-[18px] shrink-0 transition-colors ${isActive ? 'text-emerald-300' : 'text-slate-500 group-hover:text-slate-300'}`} />
              <span className={compact ? 'sr-only' : 'truncate'}>{label}</span>
            </>}
          </NavLink>
        </li>)}
      </ul>
    </div>)}
  </nav>
}

export function Avatar({ name }: { name: string }) {
  return <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-full bg-emerald-400/15 text-xs font-semibold text-emerald-200 ring-1 ring-inset ring-emerald-400/30">{initials(name)}</span>
}

export function AccountSummary({ user, compact = false }: { user: User; compact?: boolean }) {
  const roles = user.roles.map(roleLabel).join(' · ')
  return <div title={compact ? `${user.full_name} · ${roles}` : undefined}
    className={`flex items-center gap-3 rounded-xl border border-line bg-canvas/50 ${compact ? 'justify-center p-1.5' : 'p-2.5'}`}>
    <Avatar name={user.full_name} />
    <div className={compact ? 'sr-only' : 'min-w-0'}>
      <p className="truncate text-sm font-medium text-slate-100">{user.full_name}</p>
      <p className="truncate text-xs text-slate-400">{roles}</p>
    </div>
  </div>
}

/** Persistent navigation from the md breakpoint: an icon rail on tablets and a
 * user-collapsible sidebar on desktops. Hidden on phones, which use the drawer. */
export function Sidebar({ user, collapsed, onToggle }: { user: User; collapsed: boolean; onToggle: () => void }) {
  const tablet = useMediaQuery('(min-width: 768px) and (max-width: 1023.98px)')
  const compact = collapsed || tablet
  return <div id="app-sidebar" className={`sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-line bg-surface/80 transition-[width] duration-200 ease-out md:flex ${compact ? 'w-[4.5rem]' : 'w-64'}`}>
    <div className={`flex h-16 shrink-0 items-center border-b border-line ${compact ? 'justify-center' : 'px-5'}`}>
      <Link to="/" className="rounded-lg"><BrandMark compact={compact} /></Link>
    </div>
    {/* min-h-0 lets the links scroll on short (landscape) viewports instead of hiding behind the account area. */}
    <div className={`min-h-0 flex-1 overflow-y-auto py-5 ${compact ? 'px-2' : 'px-3'}`}><NavigationLinks user={user} compact={compact} /></div>
    <div className={`space-y-2 border-t border-line ${compact ? 'p-2' : 'p-3'}`}>
      {!tablet && <button type="button" onClick={onToggle} aria-controls="app-sidebar" aria-expanded={!collapsed} title={collapsed ? 'Expand navigation' : undefined}
        className={`flex w-full items-center gap-3 rounded-lg text-sm text-slate-400 transition-colors hover:bg-surface-raised hover:text-slate-100 ${compact ? 'justify-center p-2.5' : 'px-3 py-2'}`}>
        {collapsed ? <PanelLeftOpen aria-hidden="true" className="size-[18px] shrink-0" /> : <PanelLeftClose aria-hidden="true" className="size-[18px] shrink-0" />}
        <span className={compact ? 'sr-only' : ''}>{collapsed ? 'Expand navigation' : 'Collapse navigation'}</span>
      </button>}
      <AccountSummary user={user} compact={compact} />
    </div>
  </div>
}

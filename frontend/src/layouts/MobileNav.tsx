import { useEffect, type KeyboardEvent, type RefObject } from 'react'
import { X } from 'lucide-react'
import { Link } from 'react-router'
import { BrandMark } from '../components/BrandMark'
import type { User } from '../features/auth/types'
import { AccountSummary, NavigationLinks } from './Sidebar'

interface Props { user: User; onClose: () => void; returnFocus: RefObject<HTMLButtonElement | null> }

/** Keeps Tab and Shift+Tab inside the open drawer. */
function trapFocus(event: KeyboardEvent<HTMLDivElement>) {
  if (event.key !== 'Tab') return
  const focusable = event.currentTarget.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')
  const first = focusable[0], last = focusable[focusable.length - 1]
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}

/** Modal navigation drawer for phones, mounted only while open. Escape, the
 * backdrop, the close button and navigation all close it; focus then returns
 * to the menu button. The page behind it is inert and does not scroll. */
export function MobileNav({ user, onClose, returnFocus }: Props) {
  useEffect(() => {
    const trigger = returnFocus.current
    const overflow = document.body.style.overflow
    const closeOnEscape = (event: globalThis.KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = overflow
      document.removeEventListener('keydown', closeOnEscape)
      trigger?.focus()
    }
  }, [onClose, returnFocus])

  return <div className="fixed inset-0 z-50 md:hidden">
    <div data-testid="navigation-backdrop" aria-hidden="true" onClick={onClose} className="absolute inset-0 bg-slate-950/75 backdrop-blur-sm motion-safe:animate-fade-in" />
    <div id="mobile-navigation" role="dialog" aria-modal="true" aria-label="Navigation menu" onKeyDown={trapFocus}
      className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-line bg-surface shadow-2xl shadow-black/60 motion-safe:animate-drawer-in">
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-line px-4">
        <Link to="/" onClick={onClose} className="rounded-lg"><BrandMark /></Link>
        <button type="button" autoFocus onClick={onClose} className="icon-button">
          <X aria-hidden="true" className="size-5" /><span className="sr-only">Close navigation</span>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-5"><NavigationLinks user={user} onNavigate={onClose} /></div>
      <div className="border-t border-line p-3"><AccountSummary user={user} /></div>
    </div>
  </div>
}

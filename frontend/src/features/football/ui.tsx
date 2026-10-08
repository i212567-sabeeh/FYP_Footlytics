import { Children, cloneElement, isValidElement, useId, type ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, CircleAlert, Inbox, ListFilter, LoaderCircle, RotateCw } from 'lucide-react'
import { Link } from 'react-router'
export function ErrorMessage({ error }: { error: Error | null }) {
  return error && <p role="alert" className="my-4 flex items-start gap-2 rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-2.5 text-sm text-red-200">
    <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{error.message}</p>
}
export function QueryState({ query }: { query: Pick<UseQueryResult, 'isPending' | 'error' | 'refetch'> }) {
  if (query.error) return <div><ErrorMessage error={query.error} /><button className="button-secondary" onClick={() => void query.refetch()}><RotateCw aria-hidden="true" className="size-4" />Try again</button></div>
  return query.isPending ? <p role="status" className="flex items-center gap-2 py-4 text-sm text-slate-400">
    <LoaderCircle aria-hidden="true" className="size-4 animate-spin text-emerald-400 motion-reduce:animate-none" />Loading…</p> : null
}
export function Heading({ title, description, children }: { title: string; description?: ReactNode; children?: ReactNode }) {
  return <div className="mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
    <div className="min-w-0 max-w-3xl"><h1 className="text-2xl font-semibold tracking-tight text-balance text-slate-50 sm:text-3xl">{title}</h1>
      {description && <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>}</div>
    {children && <div className="flex flex-wrap gap-2">{children}</div>}
  </div>
}
/** A filter card shared by list pages; "Clear filters" appears only when a filter is set. */
export function FilterPanel({ filtered, onClear, columns = 'sm:grid-cols-2 lg:grid-cols-3', children }: {
  filtered: boolean; onClear: () => void; columns?: string; children: ReactNode
}) {
  return <div className="panel mb-6 p-4 sm:p-5">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <p className="flex items-center gap-2 text-sm font-medium text-slate-300"><ListFilter aria-hidden="true" className="size-4 text-slate-500" />Filters</p>
      {filtered && <button type="button" className="button-secondary min-h-8 px-3 py-1 text-xs" onClick={onClear}>Clear filters</button>}
    </div>
    <div className={`grid gap-4 ${columns}`}>{children}</div>
  </div>
}
export function Initials({ name, className = '' }: { name: string; className?: string }) {
  const letters = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part.charAt(0).toUpperCase()).join('')
  return <span aria-hidden="true" className={`grid size-10 shrink-0 place-items-center rounded-full bg-canvas text-sm font-semibold text-emerald-200 ring-1 ring-emerald-400/30 ${className}`}>{letters || '?'}</span>
}
/** One record in a list page: initials, linked name, context line and status. */
export function RecordRow({ to, name, meta, status }: { to: string; name: string; meta?: ReactNode; status?: ReactNode }) {
  return <li className="flex items-center gap-4 py-4">
    <Initials name={name} />
    <div className="min-w-0 flex-1">
      <Link to={to} className="font-medium text-slate-50 transition-colors hover:text-emerald-200">{name}</Link>
      {meta && <p className="mt-1 truncate text-sm text-slate-400">{meta}</p>}
    </div>
    {status}
  </li>
}
export function Field({ label, children }: { label: string; children: ReactNode }) {
  const id = useId()
  return <div><label className="field-label" htmlFor={id}>{label}</label>
    {Children.map(children, (child) => isValidElement<{ id?: string }>(child)
      && typeof child.type === 'string' && ['input', 'select', 'textarea'].includes(child.type)
      ? cloneElement(child, { id }) : child)}
  </div>
}
export function Pager({ total, offset, onChange }: { total: number; offset: number; onChange: (offset: number) => void }) {
  return <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-400"><span className="tabular-nums">{total} {total === 1 ? 'record' : 'records'}</span><div className="flex gap-2">
    <button className="button-secondary" disabled={!offset} onClick={() => onChange(Math.max(0, offset - 25))}><ChevronLeft aria-hidden="true" className="-ml-1 size-4" />Previous</button>
    <button className="button-secondary" disabled={offset + 25 >= total} onClick={() => onChange(offset + 25)}>Next<ChevronRight aria-hidden="true" className="-mr-1 size-4" /></button>
  </div></div>
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="panel flex items-start gap-3 text-slate-400"><Inbox aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-slate-500" /><div>{children}</div></div>
}
export function Status({ active }: { active: boolean }) {
  return <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${active
    ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' : 'border-slate-500/40 bg-slate-500/10 text-slate-400'}`}>
    <span aria-hidden="true" className={`size-1.5 rounded-full ${active ? 'bg-emerald-400' : 'bg-slate-500'}`} />{active ? 'Active' : 'Inactive'}</span>
}
export function DateText({ value }: { value: string | null }) { return <>{value ? new Date(value).toLocaleString() : 'Not recorded'}</> }

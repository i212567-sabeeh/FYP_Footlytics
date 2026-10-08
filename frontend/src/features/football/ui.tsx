import { Children, cloneElement, isValidElement, useId, type ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, CircleAlert, Inbox, LoaderCircle, RotateCw } from 'lucide-react'
export function ErrorMessage({ error }: { error: Error | null }) {
  return error && <p role="alert" className="my-4 flex items-start gap-2 rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-2.5 text-sm text-red-200">
    <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{error.message}</p>
}
export function QueryState({ query }: { query: Pick<UseQueryResult, 'isPending' | 'error' | 'refetch'> }) {
  if (query.error) return <div><ErrorMessage error={query.error} /><button className="button-secondary" onClick={() => void query.refetch()}><RotateCw aria-hidden="true" className="size-4" />Try again</button></div>
  return query.isPending ? <p role="status" className="flex items-center gap-2 py-4 text-sm text-slate-400">
    <LoaderCircle aria-hidden="true" className="size-4 animate-spin text-emerald-400 motion-reduce:animate-none" />Loading…</p> : null
}
export function Heading({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="mb-8 flex flex-wrap items-center justify-between gap-x-6 gap-y-4"><h1 className="text-2xl font-semibold tracking-tight text-balance text-slate-50 sm:text-3xl">{title}</h1>{children}</div>
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
  return <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-400"><span className="tabular-nums">{total} records</span><div className="flex gap-2">
    <button className="button-secondary" disabled={!offset} onClick={() => onChange(Math.max(0, offset - 25))}><ChevronLeft aria-hidden="true" className="-ml-1 size-4" />Previous</button>
    <button className="button-secondary" disabled={offset + 25 >= total} onClick={() => onChange(offset + 25)}>Next<ChevronRight aria-hidden="true" className="-mr-1 size-4" /></button>
  </div></div>
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="panel flex items-start gap-3 text-slate-400"><Inbox aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-slate-500" /><div>{children}</div></div>
}
export function Status({ active }: { active: boolean }) {
  return <span className={`inline-flex items-center gap-1.5 ${active ? 'text-emerald-300' : 'text-slate-400'}`}>
    <span aria-hidden="true" className={`size-1.5 rounded-full ${active ? 'bg-emerald-400' : 'bg-slate-500'}`} />{active ? 'Active' : 'Inactive'}</span>
}
export function DateText({ value }: { value: string | null }) { return <>{value ? new Date(value).toLocaleString() : 'Not recorded'}</> }

import { Children, cloneElement, isValidElement, useId, type ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
export function ErrorMessage({ error }: { error: Error | null }) {
  return error && <p role="alert" className="my-4 text-sm text-red-300">{error.message}</p>
}
export function QueryState({ query }: { query: Pick<UseQueryResult, 'isPending' | 'error' | 'refetch'> }) {
  if (query.error) return <div><ErrorMessage error={query.error} /><button className="button-secondary" onClick={() => void query.refetch()}>Try again</button></div>
  return query.isPending ? <p role="status" className="py-4 text-slate-400">Loading…</p> : null
}
export function Heading({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="mb-8 flex flex-wrap items-center justify-between gap-4"><h1 className="text-3xl font-semibold tracking-tight">{title}</h1>{children}</div>
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
  return <div className="mt-5 flex items-center justify-between gap-3 text-sm text-slate-400"><span>{total} records</span><div className="flex gap-3">
    <button className="button-secondary" disabled={!offset} onClick={() => onChange(Math.max(0, offset - 25))}>Previous</button>
    <button className="button-secondary" disabled={offset + 25 >= total} onClick={() => onChange(offset + 25)}>Next</button>
  </div></div>
}
export function Empty({ children }: { children: ReactNode }) { return <p className="panel text-slate-400">{children}</p> }
export function Status({ active }: { active: boolean }) { return <span className={active ? 'text-emerald-300' : 'text-slate-400'}>{active ? 'Active' : 'Inactive'}</span> }
export function DateText({ value }: { value: string | null }) { return <>{value ? new Date(value).toLocaleString() : 'Not recorded'}</> }

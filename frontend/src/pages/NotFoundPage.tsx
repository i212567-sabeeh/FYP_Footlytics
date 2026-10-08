import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <section>
      <h1 className="text-3xl font-semibold">Page not found</h1>
      <p className="mt-4 text-slate-300">This page is unavailable.</p>
      <Link to="/" className="mt-6 inline-block text-emerald-400 underline">
        Return home
      </Link>
    </section>
  )
}

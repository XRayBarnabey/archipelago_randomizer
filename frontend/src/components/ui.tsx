import type { ButtonHTMLAttributes } from 'react'

export function Button({ className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
    />
  )
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null
  return <div className="mb-4 rounded border border-red-700 bg-red-950 p-3 text-sm text-red-200">{message}</div>
}

export function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : 'jamais'
}

export function StatusBadge({ status, detail }: { status: string; detail?: string | null }) {
  const color = status === 'official' ? 'bg-emerald-800' : status === 'community' ? 'bg-sky-800' : 'bg-slate-700'
  return <span className={`rounded px-2 py-0.5 text-xs ${color}`}>{detail ? `${status} · ${detail}` : status}</span>
}

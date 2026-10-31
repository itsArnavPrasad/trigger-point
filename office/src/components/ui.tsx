import type { ReactNode } from 'react'
import { safeHref } from '../logic'
import type { Evidence } from '../types'

export const Card = ({ title, hint, children, wide }: { title?: string; hint?: string; children: ReactNode; wide?: boolean }) => (
  <section className={`card${wide ? ' wide' : ''}`}>
    {title && <header><h3>{title}</h3>{hint && <span>{hint}</span>}</header>}
    {children}
  </section>
)

export const Stat = ({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) => (
  <div className={`stat${tone ? ` ${tone}` : ''}`}><b>{value}</b><span>{label}</span></div>
)

export const Tag = ({ tone, children }: { tone?: string; children: ReactNode }) => <span className={`tag ${tone ?? ''}`}>{children}</span>

export const Empty = ({ children }: { children: ReactNode }) => <p className="empty">{children}</p>

export const Source = ({ url, label }: { url?: string | null; label?: string | null }) => {
  const href = safeHref(url)
  return href ? <a href={href} target="_blank" rel="noreferrer noopener">{label ?? 'source'}</a> : <span className="muted">{label ?? 'no link'}</span>
}

const TONES: Record<string, string> = { VERIFIED: 'good', STALE: 'warn', NEEDS_REVIEW: 'warn', CONTRADICTED: 'bad' }

export function EvidenceTable({ rows }: { rows: Evidence[] }) {
  if (!rows.length) return <Empty>No evidence recorded yet.</Empty>
  return (
    <table>
      <thead><tr><th>Claim and excerpt</th><th>Status</th><th>Source</th><th>Event</th><th>Retrieved</th></tr></thead>
      <tbody>{rows.map(e => (
        <tr key={e.id}>
          <td>{e.claim}{e.excerpt && <em>“{e.excerpt}”</em>}</td>
          <td><Tag tone={TONES[e.signal_status]}>{e.signal_status.replace('_', ' ')}</Tag>{e.verification_reasons.length > 0 && <small>{e.verification_reasons.join(', ')}</small>}</td>
          <td><Source url={e.source_url} label={e.publisher ?? e.provider_ref} /></td>
          <td>{e.event_on ?? (e.as_of ? `as of ${e.as_of}` : 'undated')}</td>
          <td>{e.retrieved_at.slice(0, 10)}</td>
        </tr>
      ))}</tbody>
    </table>
  )
}

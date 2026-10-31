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

/** Google Meet's mark, simplified, beside a text label. Only Meet links become join buttons. */
const MeetMark = () => (
  <svg width="18" height="15" viewBox="0 0 87.5 72" aria-hidden="true">
    <path fill="#00832d" d="M49.5 36l8.53 9.75 11.47 7.33 2-17.02-2-16.64-11.69 6.44z" />
    <path fill="#0066da" d="M0 51.5V66c0 3.315 2.685 6 6 6h14.5l3-10.96-3-9.54-9.95-3z" />
    <path fill="#e94235" d="M20.5 0L0 20.5l10.55 3 9.95-3 2.95-9.41z" />
    <path fill="#2684fc" d="M20.5 20.5H0v31h20.5z" />
    <path fill="#00ac47" d="M82.6 8.68L69.5 19.42v33.66l13.16 10.79c1.97 1.54 4.85.135 4.85-2.37V11c0-2.535-2.945-3.925-4.91-2.32zM49.5 36v15.5h-29V72h43c3.315 0 6-2.685 6-6V53.08z" />
    <path fill="#ffba00" d="M63.5 0h-43v20.5h29V36l20-16.57V6c0-3.315-2.685-6-6-6z" />
  </svg>
)

export function MeetButton({ link, compact }: { link?: string | null; compact?: boolean }) {
  const href = link && /^https:\/\/meet\.google\.com\//i.test(link) ? link : undefined
  if (!href) return <span className="meet-btn off" title="No Google Meet link yet"><MeetMark />{compact ? '' : 'No Meet link'}</span>
  return <a className="meet-btn" href={href} target="_blank" rel="noreferrer noopener" title="Join with Google Meet" onClick={e => e.stopPropagation()}><MeetMark />Join</a>
}

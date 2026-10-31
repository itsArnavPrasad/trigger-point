/** What we can do with a person: open their LinkedIn, copy or email an address, call or copy a number.
 *  Every button exists only when Crustdata gave us that value for that person. Nothing is sent from here:
 *  "Email" opens an empty Gmail compose window and the founder writes and sends it. */

import { useEffect, useRef, useState } from 'react'
import { contactStatus, gmailCompose, profileLink, telHref } from '../logic'
import type { ContactPoint, Stakeholder } from '../types'
import Icon from './Icon'
import { Tag } from './ui'

const GmailMark = () => (
  <svg width="18" height="14" viewBox="0 0 24 18" aria-hidden="true">
    <rect x="1" y="1" width="22" height="16" rx="3" fill="#fff" stroke="#dadce0" />
    <path d="M2 4.2v11.3" stroke="#4285f4" strokeWidth="2.6" strokeLinecap="round" />
    <path d="M22 4.2v11.3" stroke="#34a853" strokeWidth="2.6" strokeLinecap="round" />
    <path d="M2.6 3.4 12 10.6l9.4-7.2" fill="none" stroke="#ea4335" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const LinkedInMark = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
    <rect width="24" height="24" rx="5" fill="#0a66c2" />
    <circle cx="6.8" cy="7.2" r="1.7" fill="#fff" />
    <path fill="#fff" d="M5.3 9.8h3v8.9h-3zM10.2 9.8h2.8v1.2c.4-.8 1.4-1.4 2.8-1.4 2.9 0 3.4 1.9 3.4 4.3v4.8h-3v-4.3c0-1.1 0-2.4-1.5-2.4s-1.7 1.1-1.7 2.3v4.4h-2.8z" />
  </svg>
)

function CopyButton({ value, what }: { value: string; what: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const timer = useRef<ReturnType<typeof setTimeout>>()
  useEffect(() => () => clearTimeout(timer.current), [])
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); setState('copied') } catch { setState('failed') }
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setState('idle'), 1600)
  }
  const label = state === 'copied' ? 'Copied' : state === 'failed' ? 'Could not copy' : `Copy ${what}`
  return (
    <button className={`chip-ic copy ${state}`} onClick={() => void copy()} aria-label={label} title={label}>
      <Icon name={state === 'copied' ? 'check' : 'copy'} size={14} />
    </button>
  )
}

function Chip({ c }: { c: ContactPoint }) {
  const status = contactStatus(c.status)
  const email = c.kind === 'email'
  const href = email ? gmailCompose(c.value) : telHref(c.value)
  return (
    <span className="chip-contact">
      <span className="c-icon" aria-hidden="true"><Icon name={email ? 'outreach' : 'phone'} size={14} /></span>
      <span className="c-value">{c.value}</span>
      {c.label === 'personal' && <Tag>Personal</Tag>}
      {status && <Tag tone={status.tone}>{status.text}</Tag>}
      <CopyButton value={c.value} what={email ? 'email address' : 'phone number'} />
      {href && (email
        ? <a className="chip-ic" href={href} target="_blank" rel="noreferrer noopener" aria-label="Email in Gmail" title="Opens an empty Gmail compose window. You write and send it."><GmailMark /></a>
        : <a className="chip-ic" href={href} aria-label="Call" title="Call"><Icon name="phone" size={14} /></a>)}
    </span>
  )
}

/** One wrapping row of buttons. Renders nothing when there is nothing to act on. */
export default function PersonActions({ s }: { s: Stakeholder }) {
  const link = profileLink(s.profile_url)
  const points = s.contact ?? []
  if (!link && !points.length) return null
  return (
    <div className="p-row3">
      {link && (
        <a className="chip-contact link" href={link.href} target="_blank" rel="noreferrer noopener">
          {link.label === 'LinkedIn' ? <LinkedInMark /> : <Icon name="link" size={14} />}{link.label}
        </a>
      )}
      {points.map(c => <Chip key={`${c.kind}:${c.value}`} c={c} />)}
    </div>
  )
}

/** First-open prompt: connect the tools Trigger Point reaches through Claude Code.
 *  Gmail and Google Calendar are needed. Wispr Flow is optional, because transcripts can be pasted by hand.
 *  Connecting happens on claude.ai (one page for all three); this only shows the state and re-checks. */

import { useEffect } from 'react'
import type { connectionRows } from '../logic'
import { GmailMark } from './Contact'
import Icon from './Icon'
import { Tag } from './ui'

const CONNECT_URL = 'https://claude.ai/settings/connectors'
type Row = ReturnType<typeof connectionRows>[number]

const TILE: Record<string, string> = { Gmail: 'gmail', 'Google Calendar': 'meetings', 'Wispr Flow': 'chat' }

function Status({ r }: { r: Row }) {
  if (r.skipped) return <Tag>Skipped</Tag>
  if (r.state === 'connected') return <Tag tone="good">Connected</Tag>
  if (r.state === 'needs_sign_in') return <Tag tone="warn">Needs sign-in</Tag>
  if (r.state === 'failed') return <Tag tone="bad">Could not connect</Tag>
  return <Tag>Not connected</Tag>
}

export default function ConnectPrompt({ rows, ready, checking, onRecheck, onSkip, onUnskip, onClose }: {
  rows: Row[]; ready: boolean; checking: boolean
  onRecheck: () => void; onSkip: () => void; onUnskip: () => void; onClose: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <section className="connect-card" role="dialog" aria-modal="true" aria-labelledby="connect-title">
          <header>
            <h2 id="connect-title">{ready ? 'You are all set' : 'Connect your tools'}</h2>
            <p>{ready ? 'Everything Trigger Point needs is connected.' : 'Trigger Point reaches your email, calendar and meeting notes through Claude Code. Connect them once and it will not ask again.'}</p>
          </header>

          <ul className="connect-list">
            {rows.map(r => {
              const done = r.state === 'connected'
              return (
                <li key={r.id} className={`connect-row${done ? ' done' : ''}`}>
                  <span className="connect-ic" aria-hidden="true">{TILE[r.name] === 'gmail' ? <GmailMark /> : <Icon name={TILE[r.name] ?? 'integrations'} size={18} />}</span>
                  <div className="connect-text">
                    <div className="connect-name"><b>{r.name}</b><Tag tone={r.required ? 'info' : undefined}>{r.required ? 'Needed' : 'Optional'}</Tag></div>
                    <small>{r.why}</small>
                    {!r.required && !done && <small className="connect-alt">{r.skipped ? 'Skipped. Paste transcripts on the Meetings page instead.' : 'No Wispr Flow? Skip it and paste transcripts yourself.'}</small>}
                  </div>
                  <div className="connect-act">
                    <Status r={r} />
                    {!done && !r.skipped && <a className="btn primary small" href={CONNECT_URL} target="_blank" rel="noreferrer noopener">{r.state === 'needs_sign_in' ? 'Sign in' : 'Connect'}</a>}
                    {!r.required && !done && !r.skipped && <button className="btn plain small" onClick={onSkip}>Skip</button>}
                    {r.skipped && <button className="btn plain small" onClick={onUnskip}>Undo</button>}
                  </div>
                </li>
              )
            })}
          </ul>

          {!ready && <p className="connect-hint">Connectors are added in Claude's settings, on one page for all three. After you connect one, come back and press Check again.</p>}
          <footer>
            <button className="btn plain" onClick={onRecheck} disabled={checking}>{checking ? 'Checking…' : 'Check again'}</button>
            <button className="btn primary" onClick={onClose}>{ready ? 'Done' : 'Continue without them'}</button>
          </footer>
        </section>
      </div>
    </div>
  )
}

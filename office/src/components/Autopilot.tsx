/** Autopilot: the switch that lets Trigger Point run the whole path to a booked meeting.
 *  Everything shown here is read from the server. The switch and the sheet only change the policy;
 *  what Autopilot may do is enforced in the backend, never here. */

import { useEffect, useRef, useState } from 'react'
import { post, put } from '../api'
import { autopilotLine, conversationLabel, lastWords, nowDoing } from '../logic'
import type { Autopilot, AutopilotPolicy, Conversation, MissionView } from '../types'
import Icon from './Icon'
import { Tag } from './ui'

export function ModeChip({ a }: { a: Autopilot }) {
  return a.outreach_mode === 'live'
    ? <Tag tone="bad">LIVE: sends reach real people</Tag>
    : <Tag tone="info">DEMO: sends go to {a.demo_inbox ?? 'no inbox set'}</Tag>
}

/** The line under the switch, e.g. "On · up to 50 credits · 5 meetings · Mon–Fri 10:00–17:00 Kolkata". */
export function AutopilotBar({ a, missionId, onChanged, compact }: { a: Autopilot; missionId: string; onChanged: () => void; compact?: boolean }) {
  const [sheet, setSheet] = useState(false)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(() => { try { return localStorage.getItem('tp-autopilot-open') === '1' } catch { return false } })
  const fold = () => { setOpen(!open); try { localStorage.setItem('tp-autopilot-open', open ? '0' : '1') } catch { /* private window: it still works */ } }
  const base = `/missions/${missionId}/autopilot`
  const toggle = async () => {
    setError('')
    try { await put(base, { changes: { enabled: !a.enabled, paused: false } }); onChanged() } catch (e) { setError((e as Error).message) }
  }
  const resume = async () => { try { await put(base, { changes: { paused: false } }); onChanged() } catch (e) { setError((e as Error).message) } }
  const pause = async () => { try { await post(`${base}/pause`); onChanged() } catch (e) { setError((e as Error).message) } }
  return (
    <section className={`autopilot${a.active ? ' on' : ''}${compact ? ' compact' : ''}`} data-testid="autopilot">
      <div className="autopilot-main">
        <button role="switch" aria-checked={a.enabled} aria-label="Autopilot" className={`switch${a.enabled ? ' on' : ''}`} onClick={() => void toggle()}><i /></button>
        <div className="autopilot-text">
          <b>Autopilot {a.paused ? 'is paused' : a.enabled ? 'is on' : 'is off'}</b>
          <small>{a.enabled ? a.summary : 'You decide every step yourself.'}</small>
        </div>
        <div className="autopilot-actions">
          <ModeChip a={a} />
          {a.enabled && !a.paused && <button className="btn plain small" onClick={() => void pause()}>Pause</button>}
          {a.paused && <button className="btn primary small" onClick={() => void resume()}>Resume</button>}
          <button className="btn plain small" onClick={() => setSheet(true)}><Icon name="settings" size={14} /> Settings</button>
        </div>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {!compact && a.log.length > 0 && (
        <button className="autopilot-fold" onClick={fold} aria-expanded={open}>
          <Icon name="chevron" size={14} />{open ? 'Hide what Autopilot did' : `What Autopilot did (${a.log.length})`}
        </button>
      )}
      {!compact && open && a.log.length > 0 && (
        <div className="autopilot-feed">
          <ul>
            {a.log.slice(0, 6).map(e => (
              <li key={e.id} className={e.decision === 'allow' ? 'did' : 'held'}>
                <i aria-hidden="true" />{autopilotLine(e)}
                <time>{new Date(e.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time>
              </li>
            ))}
          </ul>
        </div>
      )}
      {sheet && <Settings a={a} base={base} onClose={() => setSheet(false)} onSaved={() => { setSheet(false); onChanged() }} />}
    </section>
  )
}

function Settings({ a, base, onClose, onSaved }: { a: Autopilot; base: string; onClose: () => void; onSaved: () => void }) {
  const p = a.policy
  const [d, setD] = useState<AutopilotPolicy>(p)
  const [error, setError] = useState('')
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const avail = (patch: Partial<AutopilotPolicy['availability']>) => setD({ ...d, availability: { ...d.availability, ...patch } })
  const save = async () => {
    setError('')
    try {
      await put(base, { changes: { meetings_wanted: d.meetings_wanted, availability: d.availability } })
      onSaved()
    } catch (e) { setError((e as Error).message) }
  }
  const num = (v: string) => (v === '' ? 0 : Number(v))
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <section className="connect-card autopilot-sheet" role="dialog" aria-modal="true" aria-labelledby="ap-title">
          <header>
            <h2 id="ap-title">Autopilot settings</h2>
            <p>Autopilot finds who to meet, writes to them, replies, and books the call. These limits are what it may do without asking you.  Times are India time, Monday to Friday, and Autopilot checks your Google Calendar so it never books over something else.</p>
          </header>
          <div className="form-grid">
            <label>Meetings wanted<input type="number" min={1} value={d.meetings_wanted} onChange={e => setD({ ...d, meetings_wanted: num(e.target.value) })} /></label>
            <label>Meeting length (min)<input type="number" min={15} step={15} value={d.availability.minutes} onChange={e => avail({ minutes: num(e.target.value) })} /></label>
            <label>Meetings from<input type="time" value={d.availability.start} onChange={e => avail({ start: e.target.value })} /></label>
            <label>Meetings until<input type="time" value={d.availability.end} onChange={e => avail({ end: e.target.value })} /></label>
          </div>
          <p className="connect-hint">Decisions that change strategy, such as lessons, experiments and plans, always stay with you.</p>
          {error && <p className="form-error" role="alert">{error}</p>}
          <footer>
            <button className="btn plain" onClick={onClose}>Cancel</button>
            <button className="btn primary" onClick={() => void save()}>Save</button>
          </footer>
        </section>
      </div>
    </div>
  )
}

/** Every conversation Autopilot is having, and what it learned from the ones that ended. */
export function Conversations({ list }: { list: Conversation[] }) {
  if (!list.length) return null
  const declined = list.filter(c => c.state === 'declined')
  return (
    <section className="panel conversations" data-testid="conversations">
      <header><h3>Conversations</h3><span className="hint">Autopilot replies and books for you</span></header>
      <ul className="convo-list">
        {list.map(c => {
          const [label, tone] = conversationLabel(c.state)
          return (
            <li key={c.id}>
              <div className="convo-top"><b>{c.target_name}</b><Tag tone={tone}>{label}</Tag></div>
              {lastWords(c.turns) && <small>“{lastWords(c.turns)}”</small>}
              {c.state === 'needs_you' && c.note && <small className="held-why">{c.note}</small>}
            </li>
          )
        })}
      </ul>
      {declined.length > 0 && (
        <div className="why-no">
          <h4>Why they said no</h4>
          <ul>{declined.map(c => <li key={c.id}><b>{c.target_name}</b>{c.decline_reason ? `: ${c.decline_reason}` : ': gave no reason'}</li>)}</ul>
        </div>
      )}
    </section>
  )
}

/** One line that says what is happening right now. It fades to the next thing when that changes,
 *  and shows nothing when nothing is running. */
export function NowLine({ v }: { v: MissionView }) {
  const text = nowDoing(v)
  const [shown, setShown] = useState<string | null>(text)
  const [leaving, setLeaving] = useState<string | null>(null)
  const last = useRef(text)
  useEffect(() => {
    if (text === last.current) return
    setLeaving(last.current)
    last.current = text
    setShown(text)
    const t = setTimeout(() => setLeaving(null), 350)
    return () => clearTimeout(t)
  }, [text])
  if (!shown && !leaving) return null
  return (
    <p className="now-line" aria-live="polite" data-testid="now-line">
      {leaving && <span key={`o-${leaving}`} className="out"><i />{leaving}</span>}
      {shown && <span key={`i-${shown}`} className="in"><i />{shown}…</span>}
    </p>
  )
}

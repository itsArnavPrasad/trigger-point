/** Agent mode: only the touch points that get a founder into a meeting and through it.
 *  Next meeting and what to prepare, later meetings, what past meetings taught us, decisions that
 *  need you, and a conversation with the Mission Director. Everything else stays in the dashboard. */

import { useEffect, useRef, useState, type FormEvent, type RefObject } from 'react'
import { post } from '../api'
import { meetingStatus, modeLabel, permissionLabel } from '../logic'
import type { MissionView, Permission } from '../types'
import Icon from './Icon'
import { AutopilotBar, Conversations } from './Autopilot'
import { Brief } from './Meetings'
import { MeetButton } from './ui'

type Meeting = MissionView['meetings'][number]
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DAY = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const SUGGEST = ['Prep me for my next meeting', 'Book three more parent calls in Thane', 'What should I ask at my next school meeting?', 'Summarise what we have learned so far']

function when(m: Meeting, today: string) {
  const [y, mo, d] = m.held_on.split('-').map(Number)
  const date = new Date(y, mo - 1, d)
  const t = new Date(today)
  const diff = Math.round((date.getTime() - new Date(t.getFullYear(), t.getMonth(), t.getDate()).getTime()) / 86400000)
  const day = diff === 0 ? 'Today' : diff === 1 ? 'Tomorrow' : diff < 7 && diff > 0 ? DAY[date.getDay()] : `${d} ${MONTH[mo - 1]}`
  return m.time ? `${day} · ${m.time}` : day
}

/** The few things to do before a meeting: the founder's own prep notes first, then open questions. */
function prepPoints(v: MissionView, m: Meeting): string[] {
  const own = (m.prep ?? '').split(/(?<=\.)\s+/).map(s => s.trim()).filter(Boolean)
  const account = v.accounts.find(a => a.name && m.account_name && a.name.toLowerCase() === m.account_name.toLowerCase())
  const signal = account?.signals.find(s => s.status === 'active')?.description
  return [...own, ...(signal && own.length < 3 ? [`Why now: ${signal}`] : [])].slice(0, 3)
}


export function Composer({ inputRef, text, setText, send, sending, error, placeholder, chips, onOpenThread, threadCount }: {
  inputRef: RefObject<HTMLTextAreaElement>; text: string; setText: (t: string) => void; send: (e?: FormEvent) => void
  sending: boolean; error: string; placeholder: string; chips: boolean; onOpenThread?: () => void; threadCount?: number
}) {
  return (
    <form className="dock" onSubmit={send}>
      {!text && (chips || (onOpenThread && !!threadCount)) && (
        <div className="chips">
          {onOpenThread && !!threadCount && <button type="button" className="resume" onClick={onOpenThread}><Icon name="chat" size={13} />Open conversation · {threadCount}</button>}
          {chips && SUGGEST.map(x => <button type="button" key={x} onClick={() => { setText(x); inputRef.current?.focus() }}>{x}</button>)}
        </div>
      )}
      {error && <p className="alert bad">{error}</p>}
      <div className="composer">
        <textarea ref={inputRef} rows={1} value={text} placeholder={placeholder} aria-label="Message the Mission Director"
          onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }} />
        <button className="send" disabled={!text.trim() || sending} aria-label="Send">↑</button>
      </div>
    </form>
  )
}

export default function AgentMode({ v, connected, live, onDashboard, onAnswer, onChanged }: {
  v: MissionView; onChanged: () => void; connected: boolean; live: string; onDashboard: () => void
  onAnswer: (p: Permission, d: 'allow' | 'deny') => void
}) {
  const today = new Date().toISOString().slice(0, 10)
  const company = v.profile?.company ?? v.mission.website_url
  const [open, setOpen] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [pending, setPending] = useState<{ text: string; base: number } | null>(null)
  const feed = useRef<HTMLDivElement>(null)
  const thread = useRef<HTMLDivElement>(null)
  const panel = useRef<HTMLElement>(null)
  const dockInput = useRef<HTMLTextAreaElement>(null)
  const panelInput = useRef<HTMLTextAreaElement>(null)
  const focusInput = () => (chatOpen ? panelInput : dockInput).current?.focus()

  const coming = v.meetings.filter(m => ['today', 'upcoming'].includes(meetingStatus(m, today)))
    .sort((a, b) => (a.held_on + (a.time ?? '')).localeCompare(b.held_on + (b.time ?? '')))
  const next = coming[0]
  const later = coming.slice(1)
  const todayCount = coming.filter(m => m.held_on === today).length
  const held = v.meetings.filter(m => meetingStatus(m, today) === 'held').sort((a, b) => b.held_on.localeCompare(a.held_on))
  const learned = held.flatMap(m => (m.learnings ?? []).map(l => ({ l, from: m.title }))).slice(0, 5)
  const unconfirmed = v.meetings.filter(m => meetingStatus(m, today) === 'needs_update')
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  const showPending = pending && v.messages.length <= pending.base
  const typing = !!showPending || (chatOpen && live === 'working')

  useEffect(() => { thread.current?.scrollTo({ top: thread.current.scrollHeight, behavior: 'smooth' }) }, [v.messages.length, showPending, typing])
  useEffect(() => {
    const el = panel.current as (HTMLElement & { inert: boolean }) | null
    if (el) el.inert = !chatOpen  // closed panel is skipped by Tab and screen readers
    if (!chatOpen) return
    const t = setTimeout(() => panelInput.current?.focus(), 380)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setChatOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => { clearTimeout(t); window.removeEventListener('keydown', onKey) }
  }, [chatOpen])

  const send = async (e?: FormEvent) => {
    e?.preventDefault()
    const msg = text.trim()
    if (!msg || sending) return
    setChatOpen(true); setPending({ text: msg, base: v.messages.length }); setText(''); setSending(true); setError('')
    try { await post(`/missions/${v.mission.id}/messages`, { text: msg }) } catch (err) { setError((err as Error).message); setText(msg); setPending(null) } finally { setSending(false) }
  }

  return (
    <div className="agent-mode">
      <header className="agent-bar">
        <div className="agent-brand">
          <span className="brand-mark"><Icon name="icp" size={15} /></span>
          <b>Trigger Point</b><span className="x">×</span><b className="co">{company}</b>
        </div>
        <div className="mode-switch" role="tablist" aria-label="Mode">
          <button role="tab" aria-selected="true" className="on"><Icon name="sparkle" size={14} />Agent</button>
          <button role="tab" aria-selected="false" onClick={onDashboard}><Icon name="dashboard" size={14} />Dashboard</button>
        </div>
        <div className="agent-status">
          {v.mission.mode !== 'live' && <span className={`mode-chip m-${v.mission.mode}`}>{modeLabel(v.mission.mode)}</span>}
          <span className={`live-chip l-${live}`}><i />{!connected ? 'Connection lost' : live === 'working' ? 'Working' : live === 'needs_you' ? 'Needs you' : 'Idle'}</span>
        </div>
      </header>

      <div className={`agent-body${chatOpen ? ' chatting' : ''}`}>
      <div className="agent-left">
      <div className="agent-feed" ref={feed}>
        <div className="agent-col">
          <section className="agent-hello">
            <h1>{greeting}.</h1>
            <p>
              {todayCount ? `${todayCount} meeting${todayCount === 1 ? '' : 's'} today` : 'No meetings today'}
              {` · ${coming.length} coming up · ${held.length} held`}
              {v.permissions.length ? ` · ${v.permissions.length} waiting on you` : ''}
            </p>
          </section>

          {v.autopilot && <AutopilotBar a={v.autopilot} missionId={v.mission.id} onChanged={onChanged} compact />}

          {v.conversations && <Conversations list={v.conversations} />}

          {v.permissions.map(p => (
            <section key={p.id} className="agent-card needs">
              <span className="pill-icon warn"><Icon name="alert" size={16} /></span>
              <div className="grow"><small>Needs you</small><b>{permissionLabel(p)}</b></div>
              <button className="btn destructive small" onClick={() => onAnswer(p, 'deny')}>Deny</button>
              <button className="btn primary small" onClick={() => onAnswer(p, 'allow')}>Approve</button>
            </section>
          ))}

          {next ? (
            <section className="agent-card next">
              <div className="next-top">
                <span className="eyebrow accent">Next up · {when(next, today)}</span>
                <MeetButton link={next.link} />
              </div>
              <h2>{next.title}</h2>
              <p className="who">{[next.attendee, next.attendee_role, next.account_name !== next.title ? next.account_name : null].filter(Boolean).join(' · ')}</p>
              {prepPoints(v, next).length > 0 && <>
                <h4>Prepare</h4>
                <ul className="prep-list">{prepPoints(v, next).map((x, i) => <li key={i}><span>{i + 1}</span>{x}</li>)}</ul>
              </>}
              <button className="expand" onClick={() => setOpen(open === next.id ? null : next.id)} aria-expanded={open === next.id}>
                {open === next.id ? 'Hide full brief' : 'Full brief'}<Icon name="chevron" size={14} />
              </button>
              {open === next.id && <div className="inline-brief"><Brief v={v} m={next} today={today} bare /></div>}
            </section>
          ) : (
            <section className="agent-card empty-next">
              <Icon name="meetings" size={26} />
              <b>No meetings booked yet</b>
              <p>Ask Trigger Point to find the right people and book them. You approve every message first.</p>
              <button className="btn tinted" onClick={() => { setText('Find the best schools and parents to talk to this week and book the meetings'); focusInput() }}>Book my next meetings</button>
            </section>
          )}

          {later.length > 0 && (
            <section className="agent-sec">
              <h3>Coming up</h3>
              <ul className="agent-list">{later.map(m => (
                <li key={m.id} className={open === m.id ? 'open' : ''}>
                  <div className="agent-row">
                    <span className="when">{when(m, today)}</span>
                    <button className="row-main" onClick={() => setOpen(open === m.id ? null : m.id)} aria-expanded={open === m.id}>
                      <b>{m.title}</b><small>{[m.attendee, m.attendee_role].filter(Boolean).join(' · ') || m.account_name}</small>
                    </button>
                    <MeetButton link={m.link} compact />
                    <button className="icon-btn chev" onClick={() => setOpen(open === m.id ? null : m.id)} aria-label={open === m.id ? 'Hide prep' : 'Show prep'}><Icon name="chevron" size={16} /></button>
                  </div>
                  {open === m.id && <div className="inline-brief"><Brief v={v} m={m} today={today} bare /></div>}
                </li>
              ))}</ul>
            </section>
          )}

          {learned.length > 0 && (
            <section className="agent-sec">
              <h3>What we've learned</h3>
              <ul className="agent-learn">{learned.map((x, i) => <li key={i}><Icon name="learning" size={16} /><div>{x.l}<small>{x.from}</small></div></li>)}</ul>
            </section>
          )}

          {unconfirmed.length > 0 && (
            <section className="agent-sec">
              <h3>Did these happen?</h3>
              <ul className="agent-list">{unconfirmed.map(m => (
                <li key={m.id}><div className="agent-row">
                  <span className="when">{when(m, today)}</span>
                  <div className="row-main"><b>{m.title}</b><small>No notes yet</small></div>
                  <button className="btn plain small" onClick={() => { setText(`Notes for "${m.title}": `); focusInput() }}>Add notes</button>
                </div></li>
              ))}</ul>
            </section>
          )}

        </div>
      </div>

      <div className={`agent-input${chatOpen ? ' gone' : ''}`} aria-hidden={chatOpen}><div className="agent-input-in"><div className="agent-col">
        <Composer inputRef={dockInput} text={text} setText={setText} send={send} sending={sending} error={chatOpen ? '' : error}
          placeholder={`Ask Trigger Point about ${company}'s meetings…`} chips onOpenThread={() => setChatOpen(true)} threadCount={v.messages.length} />
      </div></div></div>
      </div>

      <aside className={`chat-panel${chatOpen ? ' open' : ''}`} ref={panel} aria-label="Conversation with the Mission Director">
        <div className="chat-inner">
          <header className="chat-head">
            <span className="pill-icon accent"><Icon name="sparkle" size={16} /></span>
            <div className="grow"><b>Mission Director</b><small>{typing ? 'Thinking…' : live === 'needs_you' ? 'Waiting on you' : 'Runs on Claude Code'}</small></div>
            <button className="close" onClick={() => setChatOpen(false)} aria-label="Close conversation" title="Close (Esc)">×</button>
          </header>
          <div className="chat-thread" ref={thread} aria-live="polite">
            {v.messages.length === 0 && !showPending && <p className="chat-empty">Ask anything about your meetings. It can research, draft and book once you approve each step.</p>}
            {v.messages.map(x => <p key={x.seq} className={`msg ${x.sender}`}>{x.text}</p>)}
            {showPending && <p className="msg user">{pending.text}</p>}
            {typing && <p className="msg typing" aria-label="Thinking"><i /><i /><i /></p>}
          </div>
          <div className="chat-compose">
            <Composer inputRef={panelInput} text={text} setText={setText} send={send} sending={sending} error={chatOpen ? error : ''}
              placeholder="Message the Mission Director…" chips={v.messages.length === 0 && !showPending} />
          </div>
        </div>
      </aside>
      </div>
    </div>
  )
}

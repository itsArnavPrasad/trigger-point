/** The dashboard: goal, where the mission is, what research found, meetings, and what has been learned.
 *  Every number is read from the mission view. Missing data shows as an empty state with a next step. */

import { useEffect, useRef, useState, type KeyboardEvent as ReactKey, type ReactNode } from "react"
import { DESKS } from "./Room"
import Icon from './Icon'
import { JOURNEY, STAGE_ORDER, agentLabel, journey, meetingStatus, modeLabel, permissionLabel, splitMeetings, stateLabel } from '../logic'
import type { Account, MissionView, Permission } from '../types'
import { MeetButton, Tag } from './ui'
import { AutopilotBar, Conversations } from './Autopilot'

type Go = (page: string) => void

const NEXT: Record<string, string> = {
  understand: 'Review what Trigger Point read on your site, then approve the business profile.',
  target: 'Approve the ideal customer profile and its credit estimate.',
  research: 'Agents are finding accounts, dated buying signals and the right people.',
  engage: 'Review the evidence-backed draft, then send it to your test inbox.',
  learn: 'Log replies and meetings. Trigger Point learns only from real outcomes.',
}
const human = (s: string) => s.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase())
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function Panel({ title, action, onAction, span = 6, children, hint }: { title: string; action?: string; onAction?: () => void; span?: number; hint?: string; children: ReactNode }) {
  return (
    <section className={`panel span-${span}`}>
      <header>
        <h3>{title}</h3>
        {hint && <span className="hint">{hint}</span>}
        {action && <button className="text-btn" onClick={onAction}>{action}<Icon name="chevron" size={14} /></button>}
      </header>
      {children}
    </section>
  )
}

function Kpi({ label, value, sub, icon, onClick, tone }: { label: string; value: ReactNode; sub: string; icon: string; onClick: () => void; tone?: string }) {
  return (
    <button className={`kpi ${tone ?? ''}`} onClick={onClick}>
      <span className="kpi-label"><Icon name={icon} size={15} />{label}</span>
      <b>{value}</b>
      <small>{sub}</small>
    </button>
  )
}

function statusTag(a: Account) {
  const s = a.score.status
  return <Tag tone={s === 'qualified' ? 'good' : s === 'rejected' ? 'bad' : 'warn'}>{s === 'qualified' ? `Qualified${a.score.tier ? ` · Tier ${a.score.tier}` : ''}` : human(s)}</Tag>
}

/** Mission actions live behind a three-dots menu on the first card. Cancelling asks once, because it cannot be undone. */
function HeroMenu({ canCancel, onNew, onCancel }: { canCancel: boolean; onNew: () => void; onCancel: () => void }) {
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const close = () => { setOpen(false); setConfirm(false) }

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) close() }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    document.addEventListener('mousedown', onDown); window.addEventListener('keydown', onKey)
    box.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
    return () => { document.removeEventListener('mousedown', onDown); window.removeEventListener('keydown', onKey) }
  }, [open])

  const arrows = (e: ReactKey) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    const items = [...(box.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])]
    const at = items.indexOf(document.activeElement as HTMLElement)
    items[(at + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus()
    e.preventDefault()
  }

  return (
    <div className="hero-menu" ref={box}>
      <button className={`menu-btn${open ? ' on' : ''}`} aria-haspopup="menu" aria-expanded={open} aria-label="Mission actions" title="Mission actions" onClick={() => (open ? close() : setOpen(true))}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.9" /><circle cx="12" cy="12" r="1.9" /><circle cx="19" cy="12" r="1.9" /></svg>
      </button>
      {open && (
        <div className="menu" role="menu" onKeyDown={arrows}>
          {confirm ? (
            <div className="menu-confirm">
              <b>Cancel this mission?</b>
              <p>Agents stop where they are. A cancelled mission cannot be resumed.</p>
              <div className="row">
                <button className="btn plain small" onClick={close}>Keep running</button>
                <button className="btn solid-bad small" onClick={() => { close(); onCancel() }}>Cancel mission</button>
              </div>
            </div>
          ) : <>
            <button role="menuitem" onClick={() => { close(); onNew() }}><Icon name="plus" size={16} />New mission</button>
            {canCancel && <button role="menuitem" className="danger" onClick={() => setConfirm(true)}><Icon name="alert" size={16} />Cancel mission…</button>}
          </>}
        </div>
      )}
    </div>
  )
}

export function NeedsYou({ v, onAnswer, onReview }: { v: MissionView; onAnswer: (p: Permission, d: 'allow' | 'deny') => void; onReview: (p: Permission) => void }) {
  if (!v.permissions.length) return null
  return (
    <section className="needs-banner" data-testid="needs-you">
      <div className="needs-icon"><Icon name="alert" size={20} /></div>
      <div className="needs-body">
        <h3>{v.permissions.length === 1 ? 'One decision needs you' : `${v.permissions.length} decisions need you`}</h3>
        {v.permissions.map(p => (
          <div className="needs-row" key={p.id}>
            <span>{permissionLabel(p)}{v.autopilot?.held[p.id] && <small className="held-why">Autopilot held this: {v.autopilot.held[p.id]}</small>}</span>
            <button className="btn plain" onClick={() => onReview(p)}>Review</button>
            <button className="btn destructive" onClick={() => onAnswer(p, 'deny')}>Deny</button>
            <button className="btn primary" onClick={() => onAnswer(p, 'allow')}>Approve</button>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function Home({ v, connected, live, go, onAnswer, onReview, onNotes, onAgent, onNewMission, onCancel, onChanged }: {
  v: MissionView; onChanged: () => void; connected: boolean; live: string; go: Go; onNotes: (meetingId: string) => void; onAgent: () => void; onNewMission: () => void; onCancel: () => void
  onAnswer: (p: Permission, d: 'allow' | 'deny') => void; onReview: (p: Permission) => void
}) {
  const m = v.mission
  const f = v.funnel
  const today = new Date().toISOString().slice(0, 10)
  const steps = journey(m)
  const current = steps.find(s => s.phase === 'current')
  const icp = v.icp[v.icp.length - 1]
  const strategy = v.strategy[v.strategy.length - 1]?.body
  const facts = v.profile ? Object.values(v.profile.claims).flat().filter(c => c.kind === 'fact' && c.status !== 'unsupported').length : 0
  const signals = v.accounts.flatMap(a => a.signals)
  const active = signals.filter(s => s.status === 'active')
  const { upcoming, past } = splitMeetings(v.meetings, today)
  const replies = v.outcomes.filter(o => o.kind === 'reply' || o.kind === 'positive_reply')
  const sent = v.outreach.reduce((n, o) => n + (o.test_sends?.length ?? 0), 0)
  const drafts = v.outreach.length + (v.draft ? 1 : 0)
  const credits = v.costs.crustdata_credits

  const sub: Record<string, string> = {
    understand: v.profile ? `${facts} verified fact${facts === 1 ? '' : 's'} · ${human(v.profile.status)}` : 'Reading your site',
    target: icp ? `ICP v${icp.version} · ${human(icp.status)}` : 'Not drafted yet',
    research: f.found !== undefined ? `${f.qualified ?? 0} of ${f.found} qualified` : 'Not started',
    engage: drafts ? `${drafts} draft${drafts === 1 ? '' : 's'} · ${sent} test sent` : 'No drafts yet',
    learn: `${v.meetings.length} meeting${v.meetings.length === 1 ? '' : 's'} · ${v.outcomes.length} outcome${v.outcomes.length === 1 ? '' : 's'}`,
  }
  const now = v.permissions.length ? `Waiting for you: ${permissionLabel(v.permissions[0])}`
    : m.failure ? `Stopped: ${m.failure}`
    : m.wait_reason ? m.wait_reason
    : current ? NEXT[current.id] : stateLabel(m.state)

  const ranked = [...v.accounts].sort((a, b) => b.score.total - a.score.total)
  const reasons = new Map<string, number>()
  for (const a of v.accounts) for (const r of a.score.rejections) reasons.set(r, (reasons.get(r) ?? 0) + 1)
  for (const r of f.removed_accounts ?? []) reasons.set(r.reason, (reasons.get(r.reason) ?? 0) + 1)

  const reached = (k: number) => v.pipeline.accounts.filter(a => STAGE_ORDER.indexOf(a.stage) >= k).length
  const funnel: [string, number | undefined][] = [
    ['Accounts found', f.found], ['Passed checks', f.kept], ['Qualified', f.qualified],
    ['Replied', reached(0)], ['Meeting booked', reached(2)], ['Meeting held', reached(3)],
  ]
  const max = Math.max(1, ...funnel.map(([, n]) => n ?? 0))

  const feedback = [
    ...v.outcomes.filter(o => o.note && !o.note.startsWith('Meeting: ')).map(o => ({ key: o.id, who: o.account_name ?? 'Unknown account', date: o.occurred_on, text: o.note as string, label: human(o.kind), mode: o.mode })),
    ...v.meetings.filter(x => x.notes && meetingStatus(x, today) === 'held').map(x => ({ key: x.id, who: x.account_name ?? x.title, date: x.held_on, text: x.notes as string, label: 'Meeting notes', mode: x.source })),
  ].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 4)

  return (
    <div className="home">
      <section className="hero">
        <HeroMenu canCancel={!['COMPLETE', 'FAILED', 'CANCELLED'].includes(m.state)} onNew={onNewMission} onCancel={onCancel} />
        <div className="hero-top">
          <span className="eyebrow">Mission · {m.website_url}</span>
          <span className={`mode-chip m-${m.mode}`}>{modeLabel(m.mode)}</span>
          <span className={`live-chip l-${live}`}><i />{live === 'needs_you' ? 'Needs you' : live === 'working' ? 'Working' : live === 'lost' ? 'Connection lost' : live === 'ended' ? 'Finished' : 'Idle'}</span>
        </div>
        <h1>{m.goal}</h1>
        <p className={`hero-now${m.failure ? ' bad' : ''}`}>{now}</p>
        <ol className="journey" aria-label="Mission progress">
          {steps.map((s, i) => (
            <li key={s.id} className={s.phase} aria-current={s.phase === 'current' ? 'step' : undefined}>
              <span className="journey-mark">{s.phase === 'done' ? <Icon name="check" size={14} /> : i + 1}</span>
              <span className="journey-text"><b>{s.label}</b><small>{sub[s.id]}</small></span>
            </li>
          ))}
        </ol>
        <button className="agent-cta" onClick={onAgent}>
          <span className="agent-cta-icon"><Icon name="sparkle" size={20} /></span>
          <span><b>Switch to agent mode</b><small>Just your meetings, what to prepare, and a chat. Trigger Point does the rest.</small></span>
          <Icon name="chevron" size={18} />
        </button>
        <p className="sr-only">Step {Math.max(1, steps.findIndex(s => s.phase === 'current') + 1)} of {JOURNEY.length}: {stateLabel(m.state)}</p>
      </section>

      {v.autopilot && <AutopilotBar a={v.autopilot} missionId={v.mission.id} onChanged={onChanged} />}

      <NeedsYou v={v} onAnswer={onAnswer} onReview={onReview} />

      {v.conversations && <Conversations list={v.conversations} />}

      <div className="kpis">
        <Kpi icon="accounts" label="Qualified accounts" value={f.qualified ?? '–'} sub={f.found !== undefined ? `of ${f.found} found` : 'Search not run yet'} onClick={() => go('accounts')} />
        <Kpi icon="signals" label="Active signals" value={active.length} sub={signals.length ? `${signals.length - active.length} expired or undated` : 'None collected yet'} onClick={() => go('signals')} />
        <Kpi icon="meetings" label="Upcoming meetings" value={upcoming.length} sub={`${v.meetings.filter(x => meetingStatus(x, today) === 'held').length} held · ${v.meetings.filter(x => meetingStatus(x, today) === 'missed').length} missed`} onClick={() => go('meetings')} tone={upcoming.length ? 'accent' : ''} />
        <Kpi icon="outreach" label="Replies" value={replies.length} sub={`${replies.filter(r => r.kind === 'positive_reply').length} positive · ${sent} test sent`} onClick={() => go('pipeline')} />
        <Kpi icon="finance" label="Spend" value={`$${v.costs.claude_usd.toFixed(2)}`} sub={`${credits.actual ?? '0'} of ${credits.budget ?? '–'} Crustdata credits`} onClick={() => go('finance')} />
      </div>

      <div className="panels">
        <Panel span={7} title="Top accounts" hint="Ranked by deterministic score" action="All accounts" onAction={() => go('accounts')}>
          {ranked.length ? (
            <ul className="acct-list">
              {ranked.slice(0, 5).map((a, i) => {
                const why = a.score.rejections.length ? `Rejected: ${a.score.rejections.map(human).join(', ')}` : a.signals.find(s => s.status === 'active')?.description ?? 'No active signal'
                return (
                  <li key={a.id} className={a.score.status === 'rejected' ? 'muted-row' : ''}>
                    <span className="rank">{i + 1}</span>
                    <div className="acct-main"><div className="acct-name"><b>{a.name ?? 'Unnamed'}</b>{statusTag(a)}</div><small>{why}</small></div>
                    <div className="score" title={`Score ${a.score.total.toFixed(1)} of 100 (${a.score.version})`}><b>{Math.round(a.score.total)}</b><i><em style={{ width: `${Math.min(100, a.score.total)}%` }} /></i></div>
                  </li>
                )
              })}
            </ul>
          ) : <div className="empty-state"><Icon name="accounts" size={28} /><p>No accounts yet</p><small>Accounts appear once the ICP is approved and discovery runs.</small></div>}
        </Panel>

        <Panel span={5} title="Meetings" action="Open" onAction={() => go('meetings')}>
          {v.meetings.length ? <div className="scroll-area">
            {upcoming.length > 0 && <h4 className="sub-head">Upcoming</h4>}
            <ul className="meet-list">{upcoming.map(x => <MeetingRow key={x.id} x={x} soon onNotes={onNotes} />)}</ul>
            {past.length > 0 && <h4 className="sub-head">Earlier</h4>}
            <ul className="meet-list">{past.map(x => <MeetingRow key={x.id} x={x} status={meetingStatus(x, today)} onNotes={onNotes} />)}</ul>
          </div> : <div className="empty-state"><Icon name="meetings" size={28} /><p>No meetings yet</p><small>Book a test meeting or record one you held.</small><button className="btn tinted" onClick={() => go('meetings')}>Record a meeting</button></div>}
        </Panel>

        <Panel span={7} title="Funnel" hint="Accounts from research, replies and meetings from logged outcomes">
          <ul className="funnel">
            {funnel.map(([label, n]) => (
              <li key={label} title={`${label}: ${n ?? 'not measured yet'}`}>
                <span>{label}</span>
                <i><em style={{ width: `${((n ?? 0) / max) * 100}%` }} /></i>
                <b>{n ?? '–'}</b>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel span={5} title="Learnings so far" action="Details" onAction={() => go('learning')}>
          <div className="learn-meter">
            <div><b>{v.learning.report.counted}</b> of {v.learning.report.min_sample} real outcomes needed before Trigger Point proposes a change</div>
            <i><em style={{ width: `${Math.min(100, (v.learning.report.counted / Math.max(1, v.learning.report.min_sample)) * 100)}%` }} /></i>
            {v.learning.report.excluded > 0 && <small>{v.learning.report.excluded} fixture outcome{v.learning.report.excluded === 1 ? '' : 's'} excluded. Fixtures never teach.</small>}
          </div>
          {v.learning.report.proposals.map(p => <p key={`${p.dimension}:${p.value}`} className="insight"><Icon name="sparkle" size={15} />{p.change} <small>{Math.round(p.rate * 100)}% vs {Math.round(p.baseline * 100)}% baseline, {p.sample} outcomes</small></p>)}
          {reasons.size > 0 && <>
            <h4 className="sub-head">Why we said no</h4>
            <ul className="reason-list">{[...reasons].map(([r, n]) => <li key={r}><span>{human(r)}</span><b>{n}</b></li>)}</ul>
          </>}
          {icp && icp.open_questions.length > 0 && <>
            <h4 className="sub-head">Still open</h4>
            <ul className="bullet-list">{icp.open_questions.slice(0, 2).map((q, i) => <li key={i}>{q}</li>)}</ul>
          </>}
        </Panel>

        <Panel span={7} title="What prospects said" action="Pipeline" onAction={() => go('pipeline')}>
          {feedback.length ? <ul className="quotes">{feedback.map(q => (
            <li key={q.key}>
              <blockquote>{q.text}</blockquote>
              <small><b>{q.who}</b> · {q.label} · {q.date}{q.mode !== 'live' && q.mode !== 'manual' && <> · <Tag tone="warn">{q.mode === 'replay' ? 'Fixture' : human(q.mode)}</Tag></>}</small>
            </li>
          ))}</ul> : <div className="empty-state"><Icon name="chat" size={28} /><p>No feedback yet</p><small>Notes from replies and meetings show up here, in their words.</small></div>}
        </Panel>

        <Panel span={5} title="Our pitch" hint="Hypothesis until outcomes prove it" action="Strategy" onAction={() => go('strategy')}>
          {strategy ? <>
            <p className="pitch">“{strategy.value_proposition?.customer_language}”</p>
            <dl className="mini-facts">
              <div><dt>Who</dt><dd>{strategy.value_proposition?.target_segment}</dd></div>
              <div><dt>Motion</dt><dd>{strategy.gtm_motion?.motion}</dd></div>
              {icp && <div><dt>Ideal customer</dt><dd>{icp.icp_query}</dd></div>}
            </dl>
          </> : <div className="empty-state"><Icon name="strategy" size={28} /><p>No strategy yet</p><small>Drafted after you approve the business profile.</small></div>}
        </Panel>

        <Panel span={7} title="Team" action="Live office" onAction={() => go('office')}>
          <ul className="team-grid">{v.agents.map(a => (
            <li key={a.role} className={`s-${a.status}`}>
              <img src={`/art/characters/${DESKS[a.role]?.sprite}-front-left.png`} alt="" />
              <div><b>{a.name}</b><small><i className="dot" />{a.step && a.status === 'running' ? a.step : agentLabel(a, connected)}</small></div>
            </li>
          ))}</ul>
        </Panel>

        <Panel span={5} title="Recent activity" hint={`${v.events.length} events`}>
          {v.events.length ? <ul className="activity">{[...v.events].reverse().slice(0, 7).map(e => (
            <li key={e.event_id} className={`s-${e.status}`}><time>{e.occurred_at.slice(11, 16)}</time><span>{e.summary}</span></li>
          ))}</ul> : <div className="empty-state"><p>Nothing yet</p></div>}
        </Panel>
      </div>
    </div>
  )
}

function MeetingRow({ x, soon, status, onNotes }: { x: MissionView['meetings'][number]; soon?: boolean; status?: string; onNotes: (id: string) => void }) {
  const [, mm, dd] = x.held_on.split('-')
  return (
    <li className={soon ? 'soon' : ''}>
      <span className="cal"><small>{MONTH[Number(mm) - 1] ?? ''}</small><b>{Number(dd) || '?'}</b></span>
      <div className="meet-body">
        <b>{x.title}</b>
        <small>{x.time ? `${x.time} · ` : ''}{x.attendee ?? x.account_name ?? 'No account'}</small>
        <span className="row-actions">
          {soon && <MeetButton link={x.link} compact />}
          <button className="btn plain small" onClick={() => onNotes(x.id)}><Icon name="profile" size={14} />Notes</button>
          {status && <Tag tone={status === 'held' ? 'good' : status === 'missed' ? 'bad' : 'warn'}>{status === 'needs_update' ? 'Needs update' : human(status)}</Tag>}
        </span>
      </div>
    </li>
  )
}

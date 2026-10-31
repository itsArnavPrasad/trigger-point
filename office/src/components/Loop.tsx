/** The feedback half of the mission: what came back, what it taught, and what changed because of
 *  it. Every decision here is a person's click, and each number says what it is based on. */

import { useState } from 'react'
import { post } from '../api'
import { RESULT_TEXT, percent, signalLabel } from '../logic'
import type { Experiment, Lesson, MissionView, Outreach } from '../types'
import { Card, Empty, Source, Stat, Tag } from './ui'

function useAct() {
  const [error, setError] = useState('')
  const act = async (fn: () => Promise<unknown>) => { try { await fn(); setError('') } catch (e) { setError((e as Error).message) } }
  return { error, act }
}

export function Lifecycle({ reached }: { reached: string[] }) {
  return <ol className="flow-line" aria-label="Message state">{reached.map(s => <li key={s}>{s}</li>)}</ol>
}

export function SendControls({ o, id }: { o: Outreach; id: string }) {
  const { error, act } = useAct()
  const [when, setWhen] = useState('')
  const [tz, setTz] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone)
  const s = o.schedule
  const pending = s?.state === 'scheduled' || s?.state === 'due'
  const sent = Boolean(o.test_sends?.length || o.manual_sends?.length)
  if (o.status === 'rejected') return null
  return (
    <div className="send-controls">
      {s && <p className="muted">Step {s.step} by {s.channel} to {s.recipient}, {new Date(s.send_at).toLocaleString()} ({s.timezone}): <b>{s.state}</b>{s.error ? `. ${s.error}` : ''}</p>}
      {pending
        ? <button className="ghost mini" onClick={() => void act(() => post(`/missions/${id}/outreach/${o.id}/cancel-schedule`))}>Cancel schedule</button>
        : !sent && (
          <div className="row start">
            <input type="datetime-local" aria-label="Send time" value={when} onChange={e => setWhen(e.target.value)} />
            <input aria-label="Timezone" value={tz} onChange={e => setTz(e.target.value)} />
            <button className="ghost mini" disabled={!when} onClick={() => void act(() => post(`/missions/${id}/outreach/${o.id}/schedule`, { send_at: when, timezone: tz }))}>Schedule</button>
          </div>
        )}
      <div className="row start">
        {sent && <button className="ghost mini" onClick={() => void act(() => post(`/missions/${id}/outreach/${o.id}/follow-up`))}>Write follow-up</button>}
        {o.status === 'approved' && !o.manual_sends?.length && <button className="ghost mini" onClick={() => void act(() => post(`/missions/${id}/outreach/${o.id}/mark-sent`, { text: new Date().toISOString().slice(0, 10) }))}>I sent this myself</button>}
      </div>
      {error && <p className="alert bad">{error}</p>}
    </div>
  )
}

export function QualifiedAccounts({ v, audiences }: { v: MissionView; audiences: Record<string, string> }) {
  const id = v.mission.id
  const { error, act } = useAct()
  const [audience, setAudience] = useState(Object.keys(audiences)[0])
  const taken = new Set(v.targets.filter(t => t.account_id !== undefined).map(t => t.account_id))
  const rows = v.accounts.filter(a => a.score.status === 'qualified' && !taken.has(a.id))
  if (!rows.length) return null
  return (
    <Card wide title="Qualified accounts" hint="Make one a target. Why it is worth reaching comes from its research, so the loop can learn which signals work">
      <label className="inline">Writing to <select value={audience} onChange={e => setAudience(e.target.value)}>{Object.entries(audiences).map(([k, label]) => <option key={k} value={k}>{label}</option>)}</select></label>
      {error && <p className="alert bad">{error}</p>}
      <ul className="plain">{rows.map(a => {
        const active = a.signals.filter(s => s.status === 'active')
        return (
          <li key={a.id}><b>{a.name ?? 'Unnamed'}</b> <Tag tone="good">qualified</Tag>{[...new Set(active.map(s => s.type))].map(t => <Tag key={t} tone="info">{signalLabel(t)}</Tag>)}
            {active.map(s => <small key={s.id}>{s.description}</small>)}
            <div className="row start"><button className="allow mini" onClick={() => void act(() => post(`/missions/${id}/accounts/${a.id}/target`, { audience }))}>Make target</button></div>
          </li>
        )
      })}</ul>
    </Card>
  )
}

export function WisprSection({ v, wispr }: { v: MissionView; wispr: string }) {
  const id = v.mission.id
  const { error, act } = useAct()
  const connected = wispr === 'connected'
  const waiting = v.meetings.filter(m => m.source === 'wispr' && !m.progress)
  return (
    <section className="panel" style={{ marginTop: 16 }}>
      <header><h3>Meeting notes from Wispr Flow</h3><span className="hint">{connected ? 'Connected. Each read waits for your click' : 'Not connected: notes are typed by hand'}</span></header>
      <div className="row start"><button className="btn" disabled={!connected} onClick={() => void act(() => post(`/missions/${id}/import-meetings`))}>Import from Wispr Flow</button></div>
      {error && <p className="alert bad">{error}</p>}
      {waiting.length > 0 && <ul className="plain">{waiting.map(m => (
        <li key={m.id}><b>{m.title}</b> <small>Did it move the account forward?</small>
          <div className="row start">{['progressed', 'stalled', 'disqualified'].map(p => <button key={p} className="btn small" onClick={() => void act(() => post(`/missions/${id}/meetings/${m.id}/progress`, { progress: p }))}>{p}</button>)}</div>
        </li>
      ))}</ul>}
    </section>
  )
}

export function Replies({ v }: { v: MissionView }) {
  const id = v.mission.id
  const { error, act } = useAct()
  const { replies, suppressions } = v.learning
  return (
    <Card wide title="Replies" hint="Read from Gmail. Whether someone is interested is your call">
      <div className="row start"><button className="ghost" onClick={() => void act(() => post(`/missions/${id}/check-replies`))}>Check replies</button></div>
      {error && <p className="alert bad">{error}</p>}
      {replies.length ? <ul className="plain">{replies.map(r => (
        <li key={r.id}>
          <b>{r.target_name}</b> <Tag tone={r.kind === 'reply' ? 'info' : 'bad'}>{r.kind.replaceAll('_', ' ')}</Tag>{r.label && <Tag>{r.label.replaceAll('_', ' ')}</Tag>}
          <small>{r.sender} on {r.received_on}</small><p>{r.body}</p>
          {r.kind === 'reply' && !r.label && <div className="row start">
            <button className="allow mini" onClick={() => void act(() => post(`/missions/${id}/replies/${r.id}`, { label: 'positive' }))}>Interested</button>
            <button className="ghost mini" onClick={() => void act(() => post(`/missions/${id}/replies/${r.id}`, { label: 'negative' }))}>Not interested</button>
            <button className="deny mini" onClick={() => void act(() => post(`/missions/${id}/replies/${r.id}`, { label: 'opted_out' }))}>Opt out</button>
          </div>}
        </li>
      ))}</ul> : <Empty>No replies recorded. Check replies reads each thread you sent.</Empty>}
      {suppressions.length > 0 && <><h4>Do not contact</h4><ul className="plain">{suppressions.map(s => <li key={s.id}>{s.target_name} <small>{s.reason.replaceAll('_', ' ')}</small></li>)}</ul></>}
    </Card>
  )
}

export function MeetingReview({ v }: { v: MissionView }) {
  const id = v.mission.id
  const { error, act } = useAct()
  const [names, setNames] = useState<Record<string, string>>({})
  const [edits, setEdits] = useState<Record<string, string>>({})
  const unplaced = v.meetings.filter(m => m.needs_review)
  const review = v.learning.insights.filter(i => i.status === 'needs_review')
  const settled = v.learning.insights.filter(i => i.status === 'verified' || i.status === 'confirmed')
  return (
    <>
      {error && <p className="alert bad">{error}</p>}
      {unplaced.length > 0 && <Card wide title="Which account is this?" hint="Trigger Point could not prove the match">
        <ul className="plain">{unplaced.map(m => (
          <li key={m.id}><b>{m.title}</b> <small>{m.held_on}{m.account_name ? `. Suggested: ${m.account_name}` : ''}</small>
            <div className="row start">
              <input aria-label="Account" value={names[m.id] ?? m.account_name ?? ''} onChange={e => setNames({ ...names, [m.id]: e.target.value })} />
              <button className="allow mini" disabled={!(names[m.id] ?? m.account_name)} onClick={() => void act(() => post(`/missions/${id}/meetings/${m.id}/link`, { text: names[m.id] ?? m.account_name }))}>Link</button>
            </div>
          </li>
        ))}</ul>
      </Card>}
      <Card wide title="Needs your review" hint="Interpretations and unclear points">
        {review.length ? <ul className="plain">{review.map(i => (
          <li key={i.id}><Tag>{i.kind.replaceAll('_', ' ')}</Tag><Tag tone="warn">{i.basis}</Tag> <b>{i.text}</b>
            <textarea rows={2} aria-label="Correction" className="wide-text" placeholder="Correct it, if needed" value={edits[i.id] ?? ''} onChange={e => setEdits({ ...edits, [i.id]: e.target.value })} />
            <div className="row start">
              <button className="allow mini" onClick={() => void act(() => post(`/missions/${id}/insights/${i.id}`, edits[i.id] ? { action: 'correct', text: edits[i.id] } : { action: 'confirm' }))}>{edits[i.id] ? 'Save correction' : 'Confirm'}</button>
              <button className="deny mini" onClick={() => void act(() => post(`/missions/${id}/insights/${i.id}`, { action: 'reject' }))}>Reject</button>
            </div>
          </li>
        ))}</ul> : <Empty>Nothing to review.</Empty>}
      </Card>
      <Card wide title="What customers said" hint="Quotes are checked against the transcript">
        {settled.length ? <ul className="plain">{settled.map(i => (
          <li key={i.id}><Tag>{i.kind.replaceAll('_', ' ')}</Tag>{i.account_name && <Tag tone="info">{i.account_name}</Tag>} <b>{i.text}</b>
            {i.quote && <small>"{i.quote}"{i.speaker ? `, ${i.speaker}` : ''}</small>}
            {i.original_text && <small>Corrected from: {i.original_text}</small>}
            {i.source_link && <small><Source url={i.source_link} label="Source" /></small>}
          </li>
        ))}</ul> : <Empty>No customer statements yet.</Empty>}
      </Card>
    </>
  )
}

function LessonRow({ x, id }: { x: Lesson; id: string }) {
  const { error, act } = useAct()
  const [text, setText] = useState('')
  return (
    <li>
      <b>{x.text}</b> <Tag tone={x.status === 'approved' ? 'good' : x.status === 'rejected' || x.status === 'retired' ? 'bad' : 'info'}>{x.status}</Tag><Tag>{x.target}</Tag>
      <small>{x.sources} source{x.sources === 1 ? '' : 's'}{x.single_source ? '. One source is not a pattern, so this cannot be approved yet' : ''}{x.strategy_version ? `. Strategy version ${x.strategy_version}` : ''}</small>
      {x.history.length > 0 && <small>Earlier wording: {x.history.join(' / ')}</small>}
      {error && <p className="alert bad">{error}</p>}
      <div className="row start">
        {x.status === 'candidate' && <button className="allow mini" disabled={x.single_source} onClick={() => void act(() => post(`/missions/${id}/lessons/${x.id}/decide`, { decision: 'approved' }))}>Approve</button>}
        {x.status === 'candidate' && <button className="deny mini" onClick={() => void act(() => post(`/missions/${id}/lessons/${x.id}/decide`, { decision: 'rejected' }))}>Reject</button>}
        <input aria-label="New wording" placeholder="Correct the wording" value={text} onChange={e => setText(e.target.value)} />
        <button className="ghost mini" disabled={!text} onClick={() => void act(async () => { await post(`/missions/${id}/lessons/${x.id}/edit`, { text }); setText('') })}>Save</button>
        <button className="ghost mini" onClick={() => void act(() => post(`/missions/${id}/lessons/${x.id}/delete`))}>Delete</button>
      </div>
    </li>
  )
}

function ExperimentCard({ e, id }: { e: Experiment; id: string }) {
  const { error, act } = useAct()
  const r = e.result
  const open = e.status === 'running' && r.verdict !== 'insufficient'
  return (
    <Card wide title={e.change} hint={`Strategy version ${e.version}. ${e.metric}`}>
      <div className="tags"><Tag tone={e.status === 'kept' ? 'good' : e.status === 'rolled_back' ? 'bad' : 'info'}>{e.status.replaceAll('_', ' ')}</Tag><Tag tone={r.verdict === 'improved' ? 'good' : r.verdict === 'worse' ? 'bad' : undefined}>{RESULT_TEXT[r.verdict]}</Tag></div>
      <div className="stats"><Stat label={`With the change (${r.after_n})`} value={percent(r.after_rate, r.after_n)} /><Stat label={`Without it (${r.before_n})`} value={percent(r.before_rate, r.before_n)} /></div>
      <small>{e.rule}. One target in five stays on the old approach for comparison.</small>
      {error && <p className="alert bad">{error}</p>}
      {open && <div className="row start">
        <button className={r.action === 'keep' ? 'allow' : 'ghost'} onClick={() => void act(() => post(`/missions/${id}/experiments/${e.id}`, { decision: 'keep' }))}>Keep it</button>
        <button className={r.action === 'roll_back' ? 'deny' : 'ghost'} onClick={() => void act(() => post(`/missions/${id}/experiments/${e.id}`, { decision: 'roll_back' }))}>Roll back</button>
      </div>}
    </Card>
  )
}

export function LearningPage({ v }: { v: MissionView }) {
  const l = v.learning
  const r = l.report
  const id = v.mission.id
  const { error, act } = useAct()
  const open = l.decisions.filter(d => d.status === 'proposed')
  const raised = new Set(l.decisions.map(d => d.change))
  return (
    <div className="grid">
      <Card wide title="The improvement loop" hint="Each step counts real records">
        {l.demo && <p className="alert">DEMO: this is a fixture mission. What it learns stays here and never reaches a real mission.</p>}
        <ol className="loop">{l.steps.map((s, i) => <li key={s.name} className={s.count ? 'on' : ''}><span>{i + 1}</span><b>{s.name}</b><em>{s.count}</em></li>)}</ol>
        <div className="row start">
          <button className="ghost" onClick={() => void act(() => post(`/missions/${id}/review-learning`))}>Review what we learned</button>
          {l.demo && <button className="ghost" onClick={() => void act(() => post(`/missions/${id}/demo-results`))}>Add demo results</button>}
        </div>
        {error && <p className="alert bad">{error}</p>}
      </Card>
      <Card wide title="What the data supports" hint={`Needs ${r.min_sample} sends on each side`}>
        <div className="stats">
          <Stat label="Sends counted" value={r.counted} />
          <Stat label="Too recent" value={r.pending} />
          <Stat label="Test or fixture, excluded" value={r.excluded} tone="warn" />
          <Stat label="Results with no send" value={r.attribution_gaps} tone={r.attribution_gaps ? 'warn' : undefined} />
        </div>
        <small>A send younger than {r.maturity_days} days has had no fair chance, so it waits.</small>
        {r.groups.length ? <table><thead><tr><th>Compared by</th><th>Group</th><th>Sends</th><th>Meetings</th><th>Rate</th></tr></thead><tbody>{r.groups.map(g => <tr key={`${g.dimension}${g.value}`}><td>{g.dimension.replaceAll('_', ' ')}</td><td>{g.value.replaceAll('_', ' ')}</td><td>{g.n}</td><td>{g.wins}</td><td>{g.enough ? percent(g.rate, g.n) : 'Too few'}</td></tr>)}</tbody></table> : <Empty>No real sends yet. Test emails never count. Use "I sent this myself" on an approved message, or import real meetings.</Empty>}
      </Card>
      {r.proposals.filter(p => !raised.has(p.change)).map(p => (
        <Card wide key={`${p.dimension}${p.value}`} title={p.change} hint={`${p.sample} sends. Changes the ${p.target}`}>
          <p>{Math.round(p.rate * 100)}% reached a meeting, against {Math.round(p.baseline * 100)}% for the rest.</p>
          <p className="muted">{p.caveat} {p.checks.alternatives}</p>
          <button className="ghost" onClick={() => void act(() => post(`/missions/${id}/proposals`, { change: p.change, evidence: `${p.sample} sends: ${Math.round(p.rate * 100)}% vs ${Math.round(p.baseline * 100)}%`, outcome_ids: p.outcome_ids, dimension: p.dimension, value: p.value }))}>Put up for decision</button>
        </Card>
      ))}
      {open.length > 0 && <Card wide title="Waiting for your decision" hint="Approving versions the strategy and starts measuring it">
        <ul className="plain">{open.map(d => <li key={d.id}><b>{d.change}</b><small>{d.evidence}</small>
          <div className="row start">
            <button className="allow mini" onClick={() => void act(() => post(`/missions/${id}/proposals/${d.id}`, { decision: 'approved' }))}>Approve</button>
            <button className="deny mini" onClick={() => void act(() => post(`/missions/${id}/proposals/${d.id}`, { decision: 'rejected' }))}>Reject</button>
          </div></li>)}</ul>
      </Card>}
      {l.experiments.map(e => <ExperimentCard key={e.id} e={e} id={id} />)}
      <Card wide title="Lessons" hint="Approved lessons reach new messages, strategy and ICP work for this business">
        {l.lessons.length ? <ul className="plain">{l.lessons.map(x => <LessonRow key={x.id} x={x} id={id} />)}</ul> : <Empty>No lessons yet.</Empty>}
      </Card>
      <Card wide title="Why each version changed">
        {l.timeline.length ? <ol className="timeline">{l.timeline.map(t => (
          <li key={t.version}><b>Version {t.version}</b> <small>{t.author}{t.rolled_back_to ? `. Rolled back to version ${t.rolled_back_to}` : ''}</small>
            {t.changes.map(c => <p key={c}>{c}</p>)}
            {!t.rolled_back_to && t.version < l.timeline.length && <button className="ghost mini" onClick={() => void act(() => post(`/missions/${id}/strategy/${t.version}/rollback`))}>Return to this version</button>}
          </li>
        ))}</ol> : <Empty>No strategy yet.</Empty>}
      </Card>
    </div>
  )
}

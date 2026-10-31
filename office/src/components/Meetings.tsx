/** Meetings: what is coming up, what happened, what was missed, and a pre-meeting brief built from
 *  the research Trigger Point already holds. The brief never invents: every line comes from a record,
 *  and a gap says so. */

import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { post } from '../api'
import { meetingStatus, type MeetingStatus } from '../logic'
import type { MissionView } from '../types'
import Icon from './Icon'
import { MeetButton, Tag } from './ui'

type Meeting = MissionView['meetings'][number]
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const GROUPS: [MeetingStatus, string][] = [['today', 'Today'], ['upcoming', 'Upcoming'], ['needs_update', 'Did these happen?'], ['held', 'Held'], ['missed', 'Missed'], ['cancelled', 'Cancelled']]
const STATUS_TAG: Record<MeetingStatus, [string, string]> = {
  today: ['Today', 'info'], upcoming: ['Upcoming', 'info'], held: ['Held', 'good'], missed: ['Missed', 'bad'], cancelled: ['Cancelled', ''], needs_update: ['Needs update', 'warn'],
}
const AUDIENCE: Record<string, string> = { school_authority: 'School', parent: 'Parent', company_buyer: 'Company', partner: 'Partner' }
const human = (s: string) => s.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase())
const same = (a?: string | null, b?: string | null) => !!a && !!b && a.trim().toLowerCase() === b.trim().toLowerCase()
const longDate = (d: string) => {
  const [y, m, day] = d.split('-').map(Number)
  return Number.isFinite(day) ? `${day} ${MONTH[m - 1]} ${y}` : d
}

export function Brief({ v, m, today, bare }: { v: MissionView; m: Meeting; today: string; bare?: boolean }) {
  const status = meetingStatus(m, today)
  const account = v.accounts.find(a => same(a.name, m.account_name))
  const target = v.targets.find(t => same(t.name, m.account_name) || same(t.name, m.attendee))
  const caseFile = v.case && same(v.case.account_name, account?.name) ? v.case : null
  const history = [
    ...v.outcomes.filter(o => same(o.account_name, m.account_name) && !o.note?.startsWith('Meeting: ')).map(o => ({ date: o.occurred_on, text: `${human(o.kind)}${o.note ? `: “${o.note}”` : ''}` })),
    ...v.meetings.filter(x => x.id !== m.id && same(x.account_name, m.account_name) && x.held_on <= today).map(x => ({ date: x.held_on, text: `${x.title}${x.notes ? `: “${x.notes}”` : ''}` })),
    ...v.outreach.filter(o => same(o.target_name, target?.name)).map(o => ({ date: '', text: `Message “${o.subject}” · ${o.status}${o.test_sends?.length ? ', sent to test inbox' : ', not sent'}` })),
  ].sort((a, b) => b.date.localeCompare(a.date))
  const strategy = v.strategy[v.strategy.length - 1]?.body
  const icp = v.icp[v.icp.length - 1]
  const audience = m.audience ?? target?.audience ?? (account ? 'school_authority' : undefined)
  const angle = strategy?.stakeholder_messages?.find((s: { role: string; message: string }) => m.attendee_role && s.role.toLowerCase().includes(m.attendee_role.toLowerCase().split(' ')[0]))?.message
  const active = account?.signals.filter(s => s.status === 'active') ?? []
  const ask = [...(icp?.open_questions ?? []), ...(v.profile?.questions ?? [])].slice(0, 3)
  const past = status === 'held' || status === 'missed' || status === 'needs_update'

  return (
    <article className="brief">
      {!bare && <header className="brief-head">
        <div className="cal big"><small>{MONTH[Number(m.held_on.split('-')[1]) - 1] ?? ''}</small><b>{Number(m.held_on.split('-')[2]) || '?'}</b></div>
        <div>
          <Tag tone={STATUS_TAG[status][1]}>{STATUS_TAG[status][0]}</Tag>
          <h2>{m.title}</h2>
          <p className="muted">{longDate(m.held_on)}{m.time ? ` · ${m.time}` : ''}{m.attendee ? ` · with ${m.attendee}${m.attendee_role ? `, ${m.attendee_role}` : ''}` : ''}</p>
          <small>{m.source === 'manual' ? 'Logged by hand' : human(m.source)}</small>
        </div>
        {(status === 'upcoming' || status === 'today') && <MeetButton link={m.link} />}
      </header>}

      {past && status === 'held' && (
        <section className="brief-sec">
          <h3><Icon name="profile" size={16} />Summary</h3>
          {m.summary ? <p className="summary">{m.summary}</p> : <p className="muted">No summary yet.</p>}
          <h4>Learnings</h4>
          {m.learnings?.length ? <ul className="learn-list">{m.learnings.map((l, i) => <li key={i}><Icon name="learning" size={15} />{l}</li>)}</ul> : <p className="muted">No learnings recorded. Add what this meeting taught you about the segment.</p>}
        </section>
      )}
      {past && (
        <section className="brief-sec">
          <h3><Icon name="chat" size={16} />{status === 'missed' ? 'What happened' : 'What was said'}</h3>
          {m.notes ? <blockquote className="said">{m.notes}</blockquote> : <p className="muted">No notes yet. Record what was said so Trigger Point can learn from it.</p>}
        </section>
      )}

      <section className="brief-sec">
        <h3><Icon name="sparkle" size={16} />{past ? 'Brief you had going in' : 'Pre-meeting brief'}</h3>
        {m.prep && <div className="prep"><b>Prep notes</b><p>{m.prep}</p></div>}

        <h4>Who you are meeting</h4>
        {account ? (
          <dl className="mini-facts cols">
            <div><dt>{audience ? AUDIENCE[audience] : 'Account'}</dt><dd>{account.name} {account.domain && <small>{account.domain}</small>}</dd></div>
            <div><dt>Size</dt><dd>{account.size ? `${account.size} staff` : 'Unknown'}</dd></div>
            <div><dt>Where</dt><dd>{account.country ?? 'Unknown'}</dd></div>
            <div><dt>Fit score</dt><dd>{Math.round(account.score.total)} · {account.score.tier ? `Tier ${account.score.tier}` : human(account.score.status)}</dd></div>
          </dl>
        ) : target ? (
          <dl className="mini-facts cols">
            <div><dt>{AUDIENCE[target.audience] ?? 'Target'}</dt><dd>{target.name}</dd></div>
            <div><dt>What you told Trigger Point</dt><dd>{target.notes || 'Nothing yet'}</dd></div>
          </dl>
        ) : <p className="muted">Trigger Point has no research on {m.account_name ?? 'this contact'} yet. Add them as a target or run discovery.</p>}

        {(active.length > 0 || caseFile) && <>
          <h4>Why them, why now</h4>
          <ul className="bullet-list good">
            {active.slice(0, 3).map(s => <li key={s.id}>{s.description}</li>)}
            {caseFile && (caseFile.why_now as { text: string }[]).slice(0, 2).map((x, i) => <li key={`n${i}`}>{x.text}</li>)}
          </ul>
        </>}

        {account && account.stakeholders.length > 0 && <>
          <h4>People there</h4>
          <ul className="people-list">{account.stakeholders.map((s, i) => (
            <li key={i}><b>{s.known ? s.name ?? 'Name unknown' : 'Not found yet'}</b><span>{s.title ?? s.role}</span><small>{s.purpose}</small></li>
          ))}</ul>
        </>}

        <h4>History</h4>
        {history.length ? <ul className="history">{history.map((h, i) => <li key={i}>{h.date && <time>{h.date}</time>}<span>{h.text}</span></li>)}</ul> : <p className="muted">First contact. Nothing logged before this meeting.</p>}

        {(strategy || audience) && <>
          <h4>Your angle</h4>
          {strategy?.value_proposition?.customer_language && <p className="pitch small">“{strategy.value_proposition.customer_language}”</p>}
          {angle && <p>{angle}</p>}
          {audience === 'parent' && <p className="muted">Goal: explain what their child gets, and ask for a short conversation about their child.</p>}
          {audience === 'school_authority' && <p className="muted">Goal: propose a small pilot with the school.</p>}
        </>}

        {ask.length > 0 && <>
          <h4>Questions to settle</h4>
          <ul className="bullet-list">{ask.map((q, i) => <li key={i}>{q}</li>)}</ul>
        </>}
        <p className="brief-foot">Built from Trigger Point's records{v.mission.mode !== 'live' ? '. Fixture data, not live research.' : '.'}</p>
      </section>
    </article>
  )
}

export default function MeetingsPage({ v, wispr, focus }: { v: MissionView; wispr: string; focus?: string | null }) {
  const today = new Date().toISOString().slice(0, 10)
  const sorted = useMemo(() => {
    const withStatus = v.meetings.map(m => ({ m, s: meetingStatus(m, today) }))
    return GROUPS.map(([s, label]) => [label, withStatus.filter(x => x.s === s).map(x => x.m).sort((a, b) =>
      s === 'upcoming' || s === 'today' ? a.held_on.localeCompare(b.held_on) : b.held_on.localeCompare(a.held_on))] as const)
  }, [v.meetings, today])
  const first = sorted.find(([, ms]) => ms.length)?.[1][0]
  const [picked, setPicked] = useState<string | null>(focus ?? null)
  useEffect(() => { if (focus) setPicked(focus) }, [focus])
  const selected = v.meetings.find(m => m.id === picked) ?? first
  const held = v.meetings.filter(m => meetingStatus(m, today) === 'held').sort((a, b) => b.held_on.localeCompare(a.held_on))
  const counts = Object.fromEntries(GROUPS.map(([s]) => [s, v.meetings.filter(m => meetingStatus(m, today) === s).length]))

  const [f, setF] = useState({ title: '', held_on: '', time: '', account_name: '', attendee: '', attendee_role: '', status: '', notes: '', summary: '', learnings: '' })
  const [error, setError] = useState('')
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const save = async (e: FormEvent) => {
    e.preventDefault()
    const fields: Record<string, unknown> = Object.fromEntries(Object.entries(f).filter(([, x]) => x))
    if (f.learnings) fields.learnings = f.learnings.split('\n').map(x => x.trim()).filter(Boolean)
    try { await post(`/missions/${v.mission.id}/meetings`, { fields }); setF({ title: '', held_on: '', time: '', account_name: '', attendee: '', attendee_role: '', status: '', notes: '', summary: '', learnings: '' }); setError('') } catch (err) { setError((err as Error).message) }
  }

  return (
    <div className="meetings">
      <div className="kpis">
        {[['today', 'Today'], ['upcoming', 'Upcoming'], ['held', 'Held'], ['missed', 'Missed'], ['needs_update', 'Need an update']].map(([s, label]) => (
          <div key={s} className={`kpi static ${s === 'missed' && counts[s] ? 'bad' : s === 'upcoming' && counts[s] ? 'accent' : ''}`}><span className="kpi-label">{label}</span><b>{counts[s] ?? 0}</b></div>
        ))}
      </div>

      {held.length > 0 && (
        <section className="panel completed">
          <header><h3>Completed meetings</h3><span className="hint">{held.length} held · summaries and what each one taught us</span></header>
          <div className="completed-grid">{held.map(m => (
            <article key={m.id} className="done-card">
              <div className="done-top">
                <span className="cal"><small>{MONTH[Number(m.held_on.split('-')[1]) - 1] ?? ''}</small><b>{Number(m.held_on.split('-')[2]) || '?'}</b></span>
                <div><b>{m.title}</b><small>{m.attendee ?? m.account_name ?? ''}</small></div>
              </div>
              <p className="summary">{m.summary ?? m.notes ?? 'No summary yet.'}</p>
              {m.learnings?.length ? <ul className="learn-list">{m.learnings.map((l, i) => <li key={i}><Icon name="learning" size={15} />{l}</li>)}</ul> : null}
              <button className="text-btn" onClick={() => setPicked(m.id)}>Full notes<Icon name="chevron" size={14} /></button>
            </article>
          ))}</div>
        </section>
      )}

      <div className="meet-split">
        <section className="panel meet-index" aria-label="All meetings">
          {v.meetings.length === 0 && <div className="empty-state"><Icon name="meetings" size={28} /><p>No meetings yet</p><small>Trigger Point books meetings for you once outreach is approved. You can also record one below.</small></div>}
          {sorted.map(([label, ms]) => ms.length > 0 && (
            <div key={label}>
              <h4 className="sub-head">{label}</h4>
              <ul className="meet-list selectable">{ms.map(m => {
                const s = meetingStatus(m, today)
                return (
                  <li key={m.id} className={selected?.id === m.id ? 'on' : ''}>
                    <button className="meet-pick" onClick={() => setPicked(m.id)} aria-pressed={selected?.id === m.id}>
                      <span className={`cal${s === 'upcoming' || s === 'today' ? ' soon' : s === 'missed' ? ' missed' : ''}`}><small>{MONTH[Number(m.held_on.split('-')[1]) - 1] ?? ''}</small><b>{Number(m.held_on.split('-')[2]) || '?'}</b></span>
                      <span className="meet-text"><b>{m.title}</b><small>{m.time ? `${m.time} · ` : ''}{m.attendee ?? m.account_name ?? 'No contact'}</small><Tag tone={STATUS_TAG[s][1]}>{STATUS_TAG[s][0]}</Tag></span>
                    </button>
                    <span className="meet-actions">
                      {(s === 'upcoming' || s === 'today') && <MeetButton link={m.link} compact />}
                      <button className="btn plain small" onClick={() => setPicked(m.id)}><Icon name="profile" size={14} />Notes</button>
                    </span>
                  </li>
                )
              })}</ul>
            </div>
          ))}
          {wispr === 'not_connected' && <p className="brief-foot">Meeting notes are entered by hand until a notetaker is connected.</p>}
        </section>
        <section className="panel meet-detail">{selected ? <Brief v={v} m={selected} today={today} /> : <div className="empty-state"><p>Select a meeting</p></div>}</section>
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <header><h3>Record a meeting</h3></header>
        <form className="form-grid" onSubmit={save}>
          <label>Title<input value={f.title} onChange={set('title')} /></label>
          <label>Date<input type="date" value={f.held_on} onChange={set('held_on')} /></label>
          <label>Time<input type="time" value={f.time} onChange={set('time')} /></label>
          <label>School or parent<input value={f.account_name} onChange={set('account_name')} /></label>
          <label>Who you meet<input value={f.attendee} onChange={set('attendee')} /></label>
          <label>Their role<input value={f.attendee_role} onChange={set('attendee_role')} placeholder="Principal" /></label>
          <label>Status<select value={f.status} onChange={set('status')}><option value="">From the date</option><option value="held">Held</option><option value="missed">Missed</option><option value="cancelled">Cancelled</option></select></label>
          <label className="span">Notes, in their words<textarea rows={3} value={f.notes} onChange={set('notes')} /></label>
          <label className="span">Summary<textarea rows={2} value={f.summary} onChange={set('summary')} /></label>
          <label className="span">Learnings, one per line<textarea rows={3} value={f.learnings} onChange={set('learnings')} /></label>
          {error && <p className="alert bad span">{error}</p>}
          <button className="btn primary" disabled={!f.title || !f.held_on}>Save meeting</button>
        </form>
      </section>
    </div>
  )
}

/** One dashboard per role. Each shows stored records, and says so when something is unknown. */

import { useState } from 'react'
import { post } from '../api'
import { elapsed, statusLabel } from '../logic'
import type { Account, Agent, Claim, Harness, Health, MissionView } from '../types'
import { Card, Empty, EvidenceTable, Source, Stat, Tag } from './ui'

const FIELD_LABEL: Record<string, string> = {
  product_summary: 'Product', value_propositions: 'Value propositions', use_cases: 'Use cases', target_segments: 'Target segments',
  buyer_personas: 'Buyer personas', customer_pains: 'Customer pains', differentiators: 'Differentiators', proof_points: 'Proof points',
  competitors: 'Competitors', exclusions: 'Exclusions',
}
const KIND_TONE: Record<string, string> = { fact: 'good', user_provided: 'info', inference: 'warn' }
const KIND_LABEL: Record<string, string> = { fact: 'Fact', user_provided: 'Your statement', inference: 'Inference', unknown: 'Unknown' }
const DIMENSION = (d: string) => d.replace('_', ' ')

function ClaimRow({ c }: { c: Claim }) {
  return (
    <li className={c.status === 'unsupported' ? 'struck' : ''}>
      <Tag tone={c.status === 'unsupported' ? 'bad' : KIND_TONE[c.kind]}>{c.status === 'unsupported' ? 'Unsupported' : KIND_LABEL[c.kind]}</Tag>
      <div>{c.text}{c.excerpt && <em>“{c.excerpt}” <Source url={c.source_url} label="source" /></em>}{c.status_reason && <small>{c.status_reason}</small>}</div>
    </li>
  )
}

function EditLine({ label, placeholder, onSave }: { label: string; placeholder: string; onSave: (v: string) => Promise<void> }) {
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  return (
    <form className="editline" onSubmit={async e => {
      e.preventDefault()
      try { await onSave(text); setText(''); setError('') } catch (err) { setError((err as Error).message) }
    }}>
      <input value={text} onChange={e => setText(e.target.value)} placeholder={placeholder} aria-label={label} />
      <button disabled={!text.trim()}>{label}</button>
      {error && <small className="err">{error}</small>}
    </form>
  )
}

export function IcpPage({ v }: { v: MissionView }) {
  const versions = [...v.icp].reverse()
  const [picked, setPicked] = useState<number | null>(null)
  const icp = versions.find(i => i.version === picked) ?? versions[0]
  const canEditIcp = v.mission.state === 'ICP_READY'
  const id = v.mission.id
  const groups: [string, string][] = [['must_have', 'Must have'], ['preference', 'Preferred'], ['disqualifier', 'Disqualifiers'], ['context', 'Model context (low confidence)']]
  return (
    <div className="grid">
      {icp ? (
        <Card wide title={`Ideal customer profile · version ${icp.version}`} hint={`${icp.status === 'approved' ? 'Approved' : icp.status === 'hypothesis' ? 'Hypothesis: no customer data yet' : 'Superseded'} · ${icp.author}`}>
          <p className="lead">{icp.icp_query}</p>
          <div className="columns">
            {groups.map(([kind, title]) => {
              const rows = icp.criteria.filter(c => c.kind === kind)
              return rows.length > 0 && (
                <div key={kind}><h4>{title}</h4><ul className="criteria">{rows.map((c, i) => (
                  <li key={i}><span>{c.statement}</span><small>{DIMENSION(c.dimension)} · {c.confidence} confidence</small></li>
                ))}</ul></div>
              )
            })}
          </div>
          {canEditIcp && <EditLine label="Change target" placeholder="Describe the target differently" onSave={async t => { await post(`/missions/${id}/icp`, { changes: { icp_query: t }, rationale: 'Target edited in review' }) }} />}
        </Card>
      ) : <Card wide title="Ideal customer profile"><Empty>The ICP Strategist has not proposed one yet.</Empty></Card>}
      {icp && <>
        <Card title="Personas" hint="Who the account's buyers should be">
          {icp.personas.length ? <ul className="plain">{icp.personas.map(x => <li key={x.title}><b>{x.title}</b><small>{x.why}</small></li>)}</ul> : <Empty>No personas.</Empty>}
        </Card>
        <Card title="Assumptions and open questions">
          <ul className="plain">{icp.assumptions.map((a, i) => <li key={i}>{a}</li>)}{icp.open_questions.map((q, i) => <li key={`q${i}`} className="ask">{q}</li>)}</ul>
          {icp.assumptions.length + icp.open_questions.length === 0 && <Empty>None recorded.</Empty>}
        </Card>
        <Card title="Dimensions with no evidence" hint="Unknown, not assumed">
          <div className="tags">{icp.gaps.map(g => <Tag key={g}>{DIMENSION(g)}</Tag>)}</div>
          {icp.estimated_credits && <p className="muted">Search estimate: up to {icp.estimated_credits} credits</p>}
        </Card>
        <Card title="Version history">
          <ul className="plain">{versions.map(i => (
            <li key={i.version}><button className="link" onClick={() => setPicked(i.version)}>Version {i.version}</button> <Tag tone={i.status === 'approved' ? 'good' : undefined}>{i.status}</Tag><small>{i.rationale}</small>{i.changes.map((c, n) => <small key={n}>{c}</small>)}</li>
          ))}</ul>
        </Card>
      </>}
    </div>
  )
}

export function ProfilePage({ v }: { v: MissionView }) {
  const p = v.profile
  const id = v.mission.id
  const canEditProfile = v.mission.state === 'PROFILE_REVIEW'
  return (
    <div className="grid">
      {p ? (
        <Card wide title={`Business profile · ${p.company ?? p.domain}`} hint={`Version ${p.version} · ${p.status.replace('_', ' ')}`}>
          <div className="stats">
            <Stat label="Pages readable" value={p.readability === 'ok' ? 'Yes' : p.readability === 'thin' ? 'Barely' : 'No'} tone={p.readability === 'ok' ? 'good' : 'bad'} />
            <Stat label="Target geography" value={p.target_geography || 'Not stated'} />
            <Stat label="Time horizon" value={p.time_horizon || 'Not stated'} />
          </div>
          {p.readability !== 'ok' && <p className="alert">Trigger Point got little or nothing from this site. Add what the product does below.</p>}
          {Object.entries(p.claims).map(([f, claims]) => <div key={f}><h4>{FIELD_LABEL[f] ?? f}</h4><ul className="claims">{claims.map((c, i) => <ClaimRow key={i} c={c} />)}</ul></div>)}
          {Object.keys(p.claims).length === 0 && <Empty>No facts yet.</Empty>}
          {canEditProfile && <EditLine label="Add to product" placeholder="Describe the product in your own words" onSave={async t => {
            const current = (p.claims.product_summary ?? []).map(c => c.text)
            await post(`/missions/${id}/profile`, { field: 'product_summary', values: [...current, t] })
          }} />}
          {p.unknowns.length > 0 && <><h4>Unknown</h4><ul className="plain">{p.unknowns.map((u, i) => <li key={i}>{u}</li>)}</ul></>}
          {p.questions.length > 0 && <><h4>Questions for you</h4><ul className="plain">{p.questions.map((q, i) => <li key={i} className="ask">{q}</li>)}</ul></>}
        </Card>
      ) : <Card wide title="Business profile"><Empty>The site has not been read yet.</Empty></Card>}
    </div>
  )
}

export function Accounts({ v }: { v: MissionView }) {
  const f = v.funnel
  if (f.found === undefined) return <Empty>The Account Scout has not searched yet.</Empty>
  return (
    <div className="grid">
      <Card wide title="Account funnel">
        <div className="stats">
          <Stat label="Found" value={f.found} /><Stat label="Removed" value={f.removed} /><Stat label="Kept" value={f.kept} />
          <Stat label="Qualified" value={f.qualified} tone="good" /><Stat label="Need evidence" value={f.insufficient} tone="warn" />
          <Stat label="Rejected" value={f.rejected} tone="bad" /><Stat label="Awaiting research" value={f.awaiting} />
        </div>
      </Card>
      <Card wide title="Accounts" hint="Ranked by deterministic score">
        <table>
          <thead><tr><th>Account</th><th>Score</th><th>Status</th><th>Size</th><th>Where</th><th>Fit</th><th>Timing</th><th>Reach</th><th>Evidence</th></tr></thead>
          <tbody>{v.accounts.map(a => <AccountRow key={a.id} a={a} />)}</tbody>
        </table>
        {v.accounts.length === 0 && <Empty>Accounts are scored once research runs.</Empty>}
      </Card>
      <Card title="Removed before research">
        <ul className="plain">{(f.removed_accounts ?? []).map((r, i) => <li key={i}><b>{r.name ?? 'Unnamed'}</b><small>{r.reason.replaceAll('_', ' ')}</small></li>)}</ul>
        {!f.removed_accounts?.length && <Empty>None.</Empty>}
      </Card>
      <Card title="Provider calls" hint={f.credits?.actual ? `${f.credits.actual} credits used` : undefined}>
        <ul className="plain">{(f.calls ?? []).map((c, i) => <li key={i}>{c.endpoint} <Tag tone={c.ok ? 'good' : 'bad'}>{c.ok ? `${c.result_count ?? 0} results` : 'failed'}</Tag><small>{c.mode === 'replay' ? 'Fixture' : 'Live'}</small></li>)}</ul>
      </Card>
    </div>
  )
}

const comp = (a: Account, k: string) => {
  const c = a.score.components[k]
  return c?.known ? Math.round(c.value ?? 0) : '?'
}
const AccountRow = ({ a }: { a: Account }) => (
  <tr>
    <td><b>{a.name}</b><small>{a.domain}</small>{a.score.rejections.map(r => <small key={r} className="err">{r.replaceAll('_', ' ')}</small>)}</td>
    <td><b>{a.score.total.toFixed(1)}</b>{a.score.tier && <small>Tier {a.score.tier}</small>}</td>
    <td><Tag tone={a.score.status === 'qualified' ? 'good' : a.score.status === 'rejected' ? 'bad' : 'warn'}>{a.score.status.replace('_', ' ')}</Tag></td>
    <td>{a.size ?? 'unknown'}</td><td>{a.country ?? 'unknown'}</td>
    <td>{comp(a, 'fit')}</td><td>{comp(a, 'timing')}</td><td>{comp(a, 'reachability')}</td><td>{comp(a, 'evidence_quality')}</td>
  </tr>
)

export function Signals({ v }: { v: MissionView }) {
  const rows = v.accounts.flatMap(a => a.signals.map(s => ({ ...s, account: a.name })))
  if (!rows.length) return <Empty>The Signal Analyst has not collected signals yet.</Empty>
  const active = rows.filter(s => s.status === 'active').length
  return (
    <div className="grid">
      <Card wide title="Buying signals" hint="Dated events and measured metrics">
        <div className="stats">
          <Stat label="Signals" value={rows.length} /><Stat label="Active" value={active} tone="good" />
          <Stat label="Expired" value={rows.filter(s => s.status === 'expired').length} tone="warn" /><Stat label="Undated, not used" value={rows.filter(s => s.status === 'undated').length} />
        </div>
        <table>
          <thead><tr><th>Account</th><th>Signal</th><th>Type</th><th>Date</th><th>Age</th><th>Strength</th><th>Status</th></tr></thead>
          <tbody>{rows.map(s => (
            <tr key={s.id}><td><b>{s.account}</b></td><td>{s.description}</td><td>{s.type.replaceAll('_', ' ')}</td><td>{s.event_on ?? (s.as_of ? `as of ${s.as_of}` : 'undated')}</td>
              <td>{s.age_days === null ? '-' : `${s.age_days}d of ${s.window_days}d`}</td><td>{Math.round(s.strength * 100)}%</td>
              <td><Tag tone={s.status === 'active' ? 'good' : s.status === 'expired' ? 'warn' : undefined}>{s.status}</Tag></td></tr>
          ))}</tbody>
        </table>
      </Card>
      {v.notes.length > 0 && <Card wide title="Coverage notes"><ul className="plain">{v.notes.map((n, i) => <li key={i}>{n}</li>)}</ul></Card>}
    </div>
  )
}

export function Committee({ v }: { v: MissionView }) {
  const accounts = v.accounts.filter(a => a.people_searched)
  if (!accounts.length) return <Empty>The Buying Committee Mapper has not run yet.</Empty>
  return (
    <div className="grid">
      {accounts.map(a => (
        <Card wide key={a.id} title={a.name ?? 'Account'} hint="Roles and order are suggestions from job titles. Do not contact everyone.">
          {a.stakeholders.length === 0 && <Empty>No verified person found.</Empty>}
          <table>
            <thead><tr><th>Order</th><th>Person</th><th>Role</th><th>Status</th><th>Purpose</th><th>Ask</th><th>Profile</th></tr></thead>
            <tbody>{a.stakeholders.map((s, i) => (
              <tr key={i}>
                <td>{s.sequence}</td>
                <td><b>{s.known ? s.name ?? 'Name unknown' : 'Nobody found yet'}</b><small>{s.title}</small></td>
                <td>{s.role}</td>
                <td><Tag tone={s.known ? (s.employer_verified ? 'good' : 'warn') : undefined}>{s.known ? (s.employer_verified ? 'Employer verified' : 'Unverified') : 'Inferred role'}</Tag></td>
                <td>{s.purpose}</td>
                <td>{s.ask}</td>
                <td>{s.profile_url ? <Source url={s.profile_url} label="profile" /> : '-'}</td>
              </tr>
            ))}</tbody>
          </table>
          {a.people_rejected.length > 0 && <small className="muted">Rejected: {a.people_rejected.map(r => `${r.current_title ?? 'unknown'} (${r.reason.replaceAll('_', ' ')})`).join(', ')}</small>}
        </Card>
      ))}
    </div>
  )
}

export function EvidenceAudit({ v }: { v: MissionView }) {
  const [only, setOnly] = useState('ALL')
  const counts = v.evidence.reduce<Record<string, number>>((n, e) => ({ ...n, [e.signal_status]: (n[e.signal_status] ?? 0) + 1 }), {})
  const shown = only === 'ALL' ? v.evidence : v.evidence.filter(e => e.signal_status === only)
  const c = v.case
  return (
    <div className="grid">
      <Card wide title="Evidence audit" hint="audit-v1 checks source, entity, date and freshness. It does not prove a page says what an excerpt says.">
        <div className="stats"><Stat label="Records" value={v.evidence.length} /><Stat label="Verified" value={counts.VERIFIED ?? 0} tone="good" /><Stat label="Needs review" value={counts.NEEDS_REVIEW ?? 0} tone="warn" /><Stat label="Stale" value={counts.STALE ?? 0} tone="warn" /></div>
        <div className="filters">{['ALL', 'VERIFIED', 'NEEDS_REVIEW', 'STALE'].map(k => <button key={k} className={only === k ? 'on' : ''} onClick={() => setOnly(k)}>{k.replace('_', ' ')}</button>)}</div>
        <EvidenceTable rows={shown} />
      </Card>
      {c && <>
        <Card wide title={`Case file · ${c.account_name}`} hint={`${c.score.total} · ${c.score.tier ? `tier ${c.score.tier}` : c.score.status} · ${c.score.version}`}>
          <div className="columns">{[['why_account', 'Why this account'], ['why_person', 'Why this person'], ['why_now', 'Why now'], ['why_us', 'Why us']].map(([k, t]) => (
            <div key={k}><h4>{t}</h4><ul className="claims">{(c[k] as { text: string; kind: string }[]).map((x, i) => <li key={i}><Tag tone={KIND_TONE[x.kind]}>{KIND_LABEL[x.kind] ?? x.kind}</Tag><div>{x.text}</div></li>)}</ul></div>
          ))}</div>
          <p className="muted">Warm path: {c.warm_path}</p>
        </Card>
        <Card title="Score breakdown">
          <ul className="bars">{Object.entries(c.score.components as Record<string, { value: number | null; known: boolean; detail: string }>).map(([k, x]) => (
            <li key={k}><span>{k.replace('_', ' ')}</span><i><b style={{ width: `${x.value ?? 0}%` }} /></i><em>{x.known ? Math.round(x.value ?? 0) : 'unknown'}</em><small>{x.detail}</small></li>
          ))}</ul>
        </Card>
        <Card title="Coverage gaps"><ul className="plain">{(c.coverage_gaps as string[]).map((g, i) => <li key={i}>{g}</li>)}</ul></Card>
      </>}
    </div>
  )
}

export function Campaign({ v }: { v: MissionView }) {
  const d = v.draft
  if (!d) return <Empty>The Campaign Architect has not written a draft yet.</Empty>
  return (
    <div className="grid">
      <Card wide title={`First touch to ${d.recipient_title} at ${d.account_name}`} hint={`${d.recipient_name ?? ''} · ${d.channel}`}>
        <div className="tags"><Tag tone={d.status === 'approved' ? 'good' : 'info'}>{d.status}</Tag><Tag>Not sent</Tag><Tag>Sending disabled</Tag></div>
        <div className="email"><b>{d.subject}</b><p>{d.body}</p></div>
        <small className="muted">Content hash {d.content_hash.slice(0, 16)}. Approval is bound to this exact text.</small>
      </Card>
      <Card title="Claims and their evidence"><ul className="claims">{d.claims.map((c, i) => <li key={i}><Tag tone={KIND_TONE[c.kind]}>{KIND_LABEL[c.kind]}</Tag><div>{c.text}<small>{c.evidence_ids.length} source{c.evidence_ids.length === 1 ? '' : 's'}</small></div></li>)}</ul></Card>
      <Card title="Verifier log"><ul className="plain">{d.verifier_log.map(a => <li key={a.attempt}>Attempt {a.attempt} <Tag tone={a.outcome === 'pass' ? 'good' : 'bad'}>{a.outcome}</Tag>{a.findings.map((f, i) => <small key={i}>{f.code}: {f.message}</small>)}</li>)}</ul></Card>
      <Card title="Follow-up angles" hint="Plans only, no bodies written"><ul className="plain">{d.follow_ups.map((f, i) => <li key={i}>Day {f.day_offset}: {f.angle}</li>)}</ul>{d.follow_ups.length === 0 && <Empty>None.</Empty>}</Card>
    </div>
  )
}

export function Gate({ v }: { v: MissionView }) {
  if (!v.gate && !v.gate_error) return <Empty>The quality gate has not run yet.</Empty>
  const checks = ['Draft passed the verifier', 'Sending is disabled', 'Account is qualified', 'Route is a cold email', 'Case has not expired', 'Hook evidence passed the audit', 'Every fact is cited and audited', 'No approved draft to this person already']
  return (
    <div className="grid">
      <Card wide title="Quality gate" hint={v.gate?.version}>
        {v.gate_error ? <p className="alert bad">Failed: {v.gate_error}</p> : <ul className="checks">{checks.map(c => <li key={c}>{c}</li>)}</ul>}
      </Card>
    </div>
  )
}

export function Overview({ v }: { v: MissionView }) {
  return (
    <div className="grid">
      <Card wide title="Mission"><p className="lead">{v.mission.goal}</p><p className="muted">{v.mission.website_url}</p></Card>
      <Card wide title="Tasks">
        <table>
          <thead><tr><th>Task</th><th>Agent</th><th>Status</th><th>Attempts</th><th>Took</th></tr></thead>
          <tbody>{v.tasks.map(t => (
            <tr key={t.id}><td>{t.title}{t.error && <small className="err">{t.error.message}</small>}</td><td>{v.agents.find(a => a.role === t.role)?.name}</td>
              <td><Tag tone={t.status === 'succeeded' ? 'good' : t.status === 'failed' ? 'bad' : t.status === 'running' ? 'info' : undefined}>{statusLabel(t.status)}</Tag></td><td>{t.attempt}</td><td>{elapsed(t.started_at, t.finished_at)}</td></tr>
          ))}</tbody>
        </table>
      </Card>
      <Card wide title="Approvals"><ul className="plain">{v.approvals.map(a => <li key={a.id}>{a.summary} <Tag tone={a.status === 'approved' ? 'good' : a.status === 'pending' ? 'info' : undefined}>{a.status}</Tag>{a.reason && <small>{a.reason}</small>}</li>)}</ul>{v.approvals.length === 0 && <Empty>None yet.</Empty>}</Card>
      <Card wide title="Timeline" hint={`${v.events.length} events`}>
        <ul className="timeline">{[...v.events].reverse().slice(0, 60).map(e => <li key={e.event_id} className={`s-${e.status}`}><time>{e.occurred_at.slice(11, 19)}</time><span>{e.summary}</span></li>)}</ul>
      </Card>
    </div>
  )
}

const HEALTH_TONE: Record<string, string> = { test_only: 'info', live: 'good', ready: 'good', connected: 'good', fixture: 'warn', untested: 'warn', no_key: 'warn', needs_auth: 'warn', failed: 'bad', missing: 'bad' }

export function Integrations({ health, harness }: { health: Health[]; harness: Harness[] }) {
  return (
    <div className="grid">
      <Card wide title="Trigger Point connectors" hint="Used by missions today">
        <table>
          <thead><tr><th>Connector</th><th>Purpose</th><th>State</th><th>Access</th><th>Last success</th></tr></thead>
          <tbody>{health.map(h => <tr key={h.id}><td><b>{h.name}</b>{h.note && <small>{h.note}</small>}</td><td>{h.purpose}</td><td><Tag tone={HEALTH_TONE[h.state]}>{h.state.replaceAll('_', ' ')}</Tag></td><td>{h.access}</td><td>{h.last_success?.slice(0, 16).replace('T', ' ') ?? '-'}</td></tr>)}</tbody>
        </table>
      </Card>
      <Card wide title="Available to Claude Code" hint="State reported by Claude Code">
        <table>
          <thead><tr><th>Connector</th><th>What it would do</th><th>Claude Code says</th><th>In Trigger Point</th></tr></thead>
          <tbody>{harness.map(h => <tr key={h.id}><td><b>{h.name}</b></td><td>{h.purpose}</td><td><Tag tone={HEALTH_TONE[h.state]}>{h.state.replaceAll('_', ' ')}</Tag></td><td>{h.wired ? 'Test only' : 'Not wired'}</td></tr>)}</tbody>
        </table>
      </Card>
    </div>
  )
}

export function Costs({ v }: { v: MissionView }) {
  const c = v.costs.crustdata_credits
  return (
    <div className="grid">
      <Card wide title="Costs" hint="Actual and estimated stay separate">
        <div className="stats">
          <Stat label="Claude Code (actual)" value={`$${v.costs.claude_usd.toFixed(3)}`} />
          <Stat label="Crustdata credits (actual)" value={c.actual ?? '0'} />
          <Stat label="Unconfirmed estimate" value={c.unconfirmed_estimate ?? '0'} tone="warn" />
          <Stat label="Credit budget" value={c.budget ?? '-'} />
        </div>
      </Card>
      <Card wide title="Ledger"><ul className="plain">{v.costs.entries.map((e, i) => <li key={i}>{e.source}: {e.amount} {e.unit} <Tag>{e.basis}</Tag></li>)}</ul>{v.costs.entries.length === 0 && <Empty>No charges recorded yet.</Empty>}</Card>
    </div>
  )
}

export function Activity({ a }: { a: Agent }) {
  return (
    <div className="grid">
      <Card wide title="Current work">
        {a.task ? <><p className="lead">{a.task.title}</p><p className="muted">{statusLabel(a.task.status)} · attempt {a.task.attempt} {elapsed(a.task.started_at, a.task.finished_at)}</p>{a.task.error && <p className="alert bad">{a.task.error.kind}: {a.task.error.message}</p>}</> : <Empty>Nothing assigned.</Empty>}
      </Card>
      <Card wide title="Tool calls" hint="From Trigger Point's event log">
        <ul className="timeline">{[...a.tools].reverse().map(t => <li key={t.event_id} className={`s-${t.status}`}><time>{t.occurred_at.slice(11, 19)}</time><span>{t.summary}</span></li>)}</ul>
        {a.tools.length === 0 && <Empty>No tool calls yet.</Empty>}
      </Card>
      <Card wide title="Claude Code activity" hint="From lifecycle hooks">
        <ul className="timeline">{[...a.hook_activity].reverse().map((h, i) => <li key={i}><time>{h.at.slice(11, 19)}</time><span>{h.summary}</span></li>)}</ul>
        {a.hook_activity.length === 0 && <Empty>None recorded.</Empty>}
      </Card>
      <Card wide title="Output"><pre>{a.task?.output && Object.keys(a.task.output).length ? JSON.stringify(a.task.output, null, 2) : 'No output yet.'}</pre></Card>
    </div>
  )
}

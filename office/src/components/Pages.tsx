/** Pages for the rest of the GTM loop. Forms record facts a person knows. Nothing is estimated
 *  to fill a gap, and fixture data is never presented as a real outcome. */

import { useState, type FormEvent } from 'react'
import { post } from '../api'
import { STAGE_ORDER, money, signalLabel } from '../logic'
import type { MissionView, Outreach } from '../types'
import { Lifecycle, QualifiedAccounts, Replies, SendControls } from './Loop'
import { Card, Empty, Stat, Tag } from './ui'

function Field({ label, value, onChange, type = 'text', options }: { label: string; value: string; onChange: (v: string) => void; type?: string; options?: string[] }) {
  return (
    <label>{label}
      {options
        ? <select value={value} onChange={e => onChange(e.target.value)}>{options.map(o => <option key={o} value={o}>{o.replaceAll('_', ' ')}</option>)}</select>
        : <input type={type} value={value} onChange={e => onChange(e.target.value)} />}
    </label>
  )
}

function useForm<T extends Record<string, string>>(initial: T, submit: (f: T) => Promise<unknown>) {
  const [f, setF] = useState(initial)
  const [error, setError] = useState('')
  const set = (k: keyof T) => (v: string) => setF({ ...f, [k]: v })
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    try { await submit(f); setF(initial); setError('') } catch (err) { setError((err as Error).message) }
  }
  return { f, set, onSubmit, error }
}

export function StrategyPage({ v }: { v: MissionView }) {
  const [picked, setPicked] = useState<number | null>(null)
  const versions = [...v.strategy].reverse()
  const current = versions.find(x => x.version === picked) ?? versions[0]
  if (!current) return <Empty>The ICP Strategist has not drafted a strategy yet. It runs after you approve the business profile.</Empty>
  const s = current.body
  const vp = s.value_proposition
  return (
    <div className="grid">
      <Card wide title="Value proposition" hint={`Version ${current.version} · hypothesis until proven`}>
        <p className="lead">{vp.customer_language}</p>
        <dl className="facts">
          {[['Target segment', vp.target_segment], ['Problem', vp.problem], ['Today they use', vp.current_alternative], ['Promised outcome', vp.outcome], ['Differentiation', vp.differentiation], ['Proof', vp.proof || 'None approved yet']].map(([k, x]) => <div key={k}><dt>{k}</dt><dd>{x}</dd></div>)}
        </dl>
      </Card>
      <Card title="Positioning"><p>{s.positioning}</p></Card>
      <Card title="Message pillars"><ul className="plain">{s.message_pillars.map((p: any, i: number) => <li key={i}><b>{p.pillar}</b><small>{p.proof || 'No approved proof yet'}</small></li>)}</ul></Card>
      <Card wide title="From capability to outcome">
        <table><thead><tr><th>Capability</th><th>What the customer gets</th></tr></thead><tbody>{s.capability_outcomes.map((c: any, i: number) => <tr key={i}><td>{c.capability}</td><td>{c.outcome}</td></tr>)}</tbody></table>
      </Card>
      <Card wide title="Market" hint={s.market_category}>
        <table><thead><tr><th>Alternative</th><th>Type</th><th>Basis</th></tr></thead><tbody>{s.competitors.map((c: any, i: number) => <tr key={i}><td>{c.name}</td><td>{c.type.replace('_', ' ')}</td><td><Tag tone={c.basis === 'stated' ? 'good' : 'warn'}>{c.basis === 'stated' ? 'Named in profile' : 'Inferred'}</Tag></td></tr>)}</tbody></table>
        <p className="muted">Web research is not connected, so nothing here comes from competitor sources yet.</p>
      </Card>
      <Card title="Market gaps"><ul className="plain">{s.market_gaps.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>{!s.market_gaps.length && <Empty>None proposed.</Empty>}</Card>
      <Card title="Differentiation hypotheses"><ul className="plain">{s.differentiation_hypotheses.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>{!s.differentiation_hypotheses.length && <Empty>None proposed.</Empty>}</Card>
      <Card wide title={`GTM motion: ${s.gtm_motion.motion}`}>
        <p>{s.gtm_motion.why}</p>
        {s.gtm_motion.alternatives_rejected.map((a: string, i: number) => <small key={i}>Rejected: {a}</small>)}
      </Card>
      <Card wide title="Channel plan" hint="Only email drafts exist. Nothing here sends.">
        <table>
          <thead><tr><th>Channel</th><th>Audience</th><th>Purpose</th><th>Offer</th><th>Timing</th><th>Owner</th><th>Metric</th><th>Available</th></tr></thead>
          <tbody>{s.channels.map((c: any, i: number) => <tr key={i}><td><b>{c.channel}</b></td><td>{c.audience}</td><td>{c.purpose}</td><td>{c.offer}</td><td>{c.timing}</td><td>{c.owner}</td><td>{c.success_metric}</td><td><Tag tone={c.availability === 'draft_only' ? 'info' : undefined}>{c.availability === 'draft_only' ? 'Draft only' : 'Manual'}</Tag></td></tr>)}</tbody>
        </table>
      </Card>
      <Card title="Messaging by stakeholder"><ul className="plain">{s.stakeholder_messages.map((m: any, i: number) => <li key={i}><b>{m.role}</b><small>{m.message}</small></li>)}</ul></Card>
      <Card title="Claims that need proof"><ul className="plain">{s.claims_needing_proof.map((c: string, i: number) => <li key={i} className="ask">{c}</li>)}</ul>{!s.claims_needing_proof.length && <Empty>None flagged.</Empty>}</Card>
      <Card wide title="Experiments"><table><thead><tr><th>Hypothesis</th><th>Varies</th><th>Metric</th><th>Decision rule</th></tr></thead><tbody>{s.experiments.map((x: any, i: number) => <tr key={i}><td>{x.hypothesis}</td><td>{x.variant}</td><td>{x.metric}</td><td>{x.decision_rule}</td></tr>)}</tbody></table></Card>
      <Card wide title="Strategy versions" hint="Approved changes make a new version, and any version can be restored">
        <ul className="plain">{versions.map(x => (
          <li key={x.version}><button className="link" onClick={() => setPicked(x.version)}>Version {x.version}</button> <small>{x.author}{x.changes.length ? `: ${x.changes.join(', ')}` : ''}</small>
            {x.version !== versions[0].version && <button className="ghost mini" onClick={() => void post(`/missions/${v.mission.id}/strategy/${x.version}/rollback`)}>Restore</button>}
          </li>
        ))}</ul>
      </Card>
    </div>
  )
}

const AUDIENCE_LABEL: Record<string, string> = { school_authority: 'School authority', parent: 'Parent', company_buyer: 'Company buyer', partner: 'Partner' }

function OutreachCard({ o, id, reached }: { o: Outreach; id: string; reached: string[] }) {
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState(o.body)
  const [error, setError] = useState('')
  const act = async (fn: () => Promise<unknown>) => { try { await fn(); setError(''); setEditing(false) } catch (e) { setError((e as Error).message) } }
  const last = o.attempts[o.attempts.length - 1]
  return (
    <Card wide title={`${o.target_name}: ${o.subject}`} hint={`${AUDIENCE_LABEL[o.audience]} · ${o.purpose}`}>
      <div className="tags"><Tag tone={o.status === 'approved' ? 'good' : o.status === 'rejected' ? 'bad' : 'info'}>{o.status}</Tag><Tag>{o.test_sends?.length ? `${o.test_sends.length} test sent` : 'Not sent'}</Tag><Tag tone={o.mode === 'live' ? undefined : 'warn'}>{o.mode === 'live' ? 'Written live' : 'Fixture'}</Tag></div>
      {editing ? <textarea className="wide-text" rows={7} value={body} onChange={e => setBody(e.target.value)} aria-label="Message" /> : <div className="email"><b>{o.subject}</b><p>{o.body}</p></div>}
      {last.findings.map((f, i) => <p key={i} className="alert bad">{f.message}</p>)}
      {error && <p className="alert bad">{error}</p>}
      <Lifecycle reached={reached} />
      {o.variant === 'holdout' && <p className="muted">Comparison group: written without the latest lessons.</p>}
      {!!o.lessons_used?.length && <p className="muted">Written with {o.lessons_used.length} approved lesson{o.lessons_used.length === 1 ? '' : 's'}.</p>}
      <div className="row start">
        {editing ? <button className="allow" onClick={() => void act(() => post(`/missions/${id}/outreach/${o.id}`, { subject: o.subject, body }))}>Check and save</button> : <button className="ghost" onClick={() => setEditing(true)}>Edit</button>}
 {!editing && o.status !== 'rejected' && <button className="ghost" onClick={() => void act(() => post(`/missions/${id}/outreach/${o.id}/test-send`))}>Send to test inbox</button>}
        {!editing && o.status === 'verified' && <button className="allow" onClick={() => void act(() => post(`/missions/${id}/outreach/${o.id}/approve`, { content_hash: o.content_hash }))}>Approve this text</button>}
      </div>
      {!editing && <SendControls o={o} id={id} />}
    </Card>
  )
}

export function OutreachPage({ v }: { v: MissionView }) {
  const id = v.mission.id
  const form = useForm({ name: '', audience: 'school_authority', notes: '' }, f => post(`/missions/${id}/targets`, { fields: f }))
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const approved = v.profile?.status === 'approved'
  const write = async (t: string) => {
    setBusy(t); setError('')
    try { await post(`/missions/${id}/targets/${t}/write`) } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  return (
    <div className="grid">
 <QualifiedAccounts v={v} audiences={AUDIENCE_LABEL} />
      <Card wide title="Your targets" hint="People and schools you name. No Crustdata needed.">
        <div className="row start"><button className="ghost" onClick={() => void post(`/missions/${id}/samples`)}>Add sample targets</button><button className="ghost" onClick={() => void post(`/missions/${id}/test-meeting`)}>Book a test meeting</button></div>
        {!approved && <p className="alert">Approve the business profile first. Messages are written only from approved facts.</p>}
        {error && <p className="alert bad">{error}</p>}
        {v.targets.length ? <table><thead><tr><th>Target</th><th>Audience</th><th>Why now, or notes</th><th>Message</th></tr></thead><tbody>{v.targets.map(t => (
          <tr key={t.id}><td><b>{t.name}</b></td><td>{AUDIENCE_LABEL[t.audience]}</td><td>{t.why_now?.length ? <>{(t.signal_types ?? []).map(s => <Tag key={s} tone="info">{signalLabel(s)}</Tag>)}{t.why_now.map((w, i) => <small key={i}>{w}</small>)}</> : (t.notes || '-')}</td><td><button className="ghost mini" disabled={!approved || busy === t.id} onClick={() => void write(t.id)}>{busy === t.id ? 'Writing…' : 'Write message'}</button></td></tr>
        ))}</tbody></table> : <Empty>No targets yet. Add a school or a parent group below.</Empty>}
        <form className="form-grid" onSubmit={form.onSubmit}>
          <Field label="Name" value={form.f.name} onChange={form.set('name')} />
          <Field label="Audience" value={form.f.audience} onChange={form.set('audience')} options={Object.keys(AUDIENCE_LABEL)} />
          <Field label="What you know about them" value={form.f.notes} onChange={form.set('notes')} />
          {form.error && <p className="alert bad span">{form.error}</p>}
          <button className="allow" disabled={!form.f.name}>Add target</button>
        </form>
      </Card>
      <Replies v={v} />
      {[...v.outreach].reverse().map(o => <OutreachCard key={o.id} o={o} id={id} reached={v.learning.lifecycle[o.id]?.reached ?? []} />)}
    </div>
  )
}

export function PipelinePage({ v }: { v: MissionView }) {
  const p = v.pipeline
  const form = useForm({ account_name: '', kind: 'reply', occurred_on: '', value: '', currency: 'USD', note: '' }, f =>
    post(`/missions/${v.mission.id}/outcomes`, { fields: { ...f, value: f.value ? Number(f.value) : null, currency: f.value ? f.currency : null } }))
  return (
    <div className="grid">
      <Card wide title="Pipeline" hint="Open pipeline is not revenue">
        <div className="stats">
          {STAGE_ORDER.map(s => <Stat key={s} label={s.replaceAll('_', ' ')} value={p.counts[s] ?? 0} />)}
        </div>
        <div className="stats"><Stat label="Open pipeline" value={money(p.open_pipeline)} /><Stat label="Won revenue" value={money(p.won_revenue)} tone="good" /></div>
      </Card>
      <Card wide title="Accounts in progress">
        {p.accounts.length ? <table><thead><tr><th>Account</th><th>Stage</th><th>Last activity</th><th>Next action</th><th>Value</th><th>Data</th></tr></thead><tbody>{p.accounts.map((a, i) => <tr key={i}><td><b>{a.account_name ?? 'Unnamed'}</b></td><td>{a.stage.replaceAll('_', ' ')}<small>{p.criteria[a.stage]}</small></td><td>{a.last_activity}</td><td>{a.next_action ?? '-'}</td><td>{a.value ? `${a.value} ${a.currency}` : '-'}</td><td><Tag tone={a.mode === 'live' ? 'good' : 'warn'}>{a.mode === 'live' ? 'Real' : a.mode === 'test' ? 'Test' : 'Fixture'}</Tag></td></tr>)}</tbody></table> : <Empty>No outcomes recorded. Nothing has been sent, so this stays empty until you log what happened.</Empty>}
      </Card>
      <Card wide title="Record what happened">
        <form className="form-grid" onSubmit={form.onSubmit}>
          <Field label="Account" value={form.f.account_name} onChange={form.set('account_name')} />
          <Field label="What happened" value={form.f.kind} onChange={form.set('kind')} options={[...STAGE_ORDER, 'closed_lost', 'disqualified', 'opted_out', 'bounced']} />
          <Field label="Date" type="date" value={form.f.occurred_on} onChange={form.set('occurred_on')} />
          <Field label="Value, if known" type="number" value={form.f.value} onChange={form.set('value')} />
          <Field label="Currency" value={form.f.currency} onChange={form.set('currency')} />
          <Field label="Note" value={form.f.note} onChange={form.set('note')} />
          {form.error && <p className="alert bad span">{form.error}</p>}
          <button className="allow" disabled={!form.f.account_name || !form.f.occurred_on}>Save outcome</button>
        </form>
      </Card>
    </div>
  )
}

export function FinancePage({ v }: { v: MissionView }) {
  const m = v.finance.metrics
  const c = v.costs.crustdata_credits
  const form = useForm({ label: '', amount: '', currency: 'USD', basis: 'actual', on: '' }, f => post(`/missions/${v.mission.id}/costs`, { fields: { ...f, amount: Number(f.amount) } }))
  const unit = (x: number | null | undefined) => (x === null || x === undefined ? 'Unknown' : `$${x.toFixed(3)}`)
  return (
    <div className="grid">
      <Card wide title="Spend" hint="Actual and estimated never mix. No denominator shows as Unknown.">
        <div className="stats"><Stat label="Actual (USD)" value={unit(m.usd_actual)} /><Stat label="Estimated (USD)" value={unit(m.usd_estimated)} tone="warn" /><Stat label="Crustdata credits used" value={c.actual ?? '0'} /><Stat label="Credit budget" value={c.budget ?? '-'} /></div>
        <div className="stats"><Stat label="Per account researched" value={unit(m.cost_per_account)} /><Stat label="Per qualified account" value={unit(m.cost_per_qualified)} /><Stat label="Per meeting held" value={unit(m.cost_per_meeting)} /></div>
        {v.finance.excluded_other_currency > 0 && <p className="muted">{v.finance.excluded_other_currency} entries in other currencies are not in these totals.</p>}
      </Card>
      <Card wide title="Ledger">
        <table><thead><tr><th>Source</th><th>Amount</th><th>Basis</th></tr></thead><tbody>
          {v.costs.entries.map((e, i) => <tr key={i}><td>{e.source}</td><td>{e.amount} {e.unit}</td><td><Tag>{e.basis}</Tag></td></tr>)}
          {v.finance.manual.map(e => <tr key={e.id}><td>{e.label}</td><td>{e.amount} {e.currency}</td><td><Tag tone={e.basis === 'estimated' ? 'warn' : undefined}>{e.basis}</Tag></td></tr>)}
        </tbody></table>
        {v.costs.entries.length + v.finance.manual.length === 0 && <Empty>No charges recorded yet.</Empty>}
      </Card>
      <Card wide title="Add a cost">
        <form className="form-grid" onSubmit={form.onSubmit}>
          <Field label="What" value={form.f.label} onChange={form.set('label')} />
          <Field label="Amount" type="number" value={form.f.amount} onChange={form.set('amount')} />
          <Field label="Currency" value={form.f.currency} onChange={form.set('currency')} />
          <Field label="Basis" value={form.f.basis} onChange={form.set('basis')} options={['actual', 'estimated']} />
          <Field label="Date" type="date" value={form.f.on} onChange={form.set('on')} />
          {form.error && <p className="alert bad span">{form.error}</p>}
          <button className="allow" disabled={!form.f.label || !form.f.amount}>Save cost</button>
        </form>
      </Card>
    </div>
  )
}

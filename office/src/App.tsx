import { useCallback, useEffect, useRef, useState } from 'react'
import { follow, get, post, token } from './api'
import { Accounts, Activity, Campaign, Committee, Costs, EvidenceAudit, Gate, IcpPage, Integrations, Overview, ProfilePage, Signals } from './components/Dashboards'
import { FinancePage, LearningPage, MeetingsPage, OutreachPage, PipelinePage, StrategyPage } from './components/Pages'
import Room, { DESKS } from './components/Room'
import { LIVENESS_LABEL, agentLabel, flowSteps, liveness, modeLabel, permissionLabel, stateLabel } from './logic'
import type { Agent, Bootstrap, MissionView, Permission } from './types'

const PAGES: [string, string][] = [
  ['office', 'Office'], ['profile', 'Business profile'], ['strategy', 'Strategy'], ['icp', 'ICP'], ['accounts', 'Accounts'], ['signals', 'Signals'],
  ['people', 'People'], ['evidence', 'Evidence'], ['campaign', 'Campaign'], ['outreach', 'Outreach'], ['meetings', 'Meetings'], ['pipeline', 'Pipeline'],
  ['learning', 'Learning'], ['finance', 'Finance'], ['integrations', 'Integrations'],
]

function Page({ id, view, boot }: { id: string; view: MissionView; boot: Bootstrap }) {
  switch (id) {
    case 'profile': return <ProfilePage v={view} />
    case 'strategy': return <StrategyPage v={view} />
    case 'icp': return <IcpPage v={view} />
    case 'accounts': return <Accounts v={view} />
    case 'signals': return <Signals v={view} />
    case 'people': return <Committee v={view} />
    case 'evidence': return <EvidenceAudit v={view} />
    case 'campaign': return <Campaign v={view} />
    case 'outreach': return <OutreachPage v={view} />
    case 'meetings': return <MeetingsPage v={view} wispr={boot.health.find(h => h.id === 'wispr')?.state ?? 'not_connected'} />
    case 'pipeline': return <PipelinePage v={view} />
    case 'learning': return <LearningPage v={view} />
    case 'finance': return <FinancePage v={view} />
    default: return <Integrations health={boot.health} harness={boot.harness} />
  }
}

const ROLE_TABS: Record<string, [string, string]> = {
  'icp-strategist': ['work', 'ICP'], 'account-scout': ['work', 'Accounts'], 'signal-analyst': ['work', 'Signals'],
  'buying-committee-mapper': ['work', 'Buying committee'], 'evidence-auditor': ['work', 'Evidence and case'],
  'campaign-architect': ['work', 'Campaign draft'], 'quality-gatekeeper': ['work', 'Quality gate'],
}

function AgentDashboard({ agent, view, boot, tab, setTab, onClose, onAnswer }: {
  agent: Agent; view: MissionView; boot: Bootstrap; tab: string; setTab: (t: string) => void
  onClose: () => void; onAnswer: (p: Permission, d: 'allow' | 'deny') => void
}) {
  const director = agent.role === 'mission-director'
  const tabs: [string, string][] = director
    ? [['overview', 'Overview'], ['integrations', 'Integrations'], ['costs', 'Costs'], ['activity', 'Activity']]
    : agent.role === 'icp-strategist' ? [['strategy', 'Strategy'], ROLE_TABS[agent.role], ['profile', 'Business profile'], ['activity', 'Activity']]
    : agent.role === 'evidence-auditor' ? [ROLE_TABS[agent.role], ['activity', 'Activity']]
    : [ROLE_TABS[agent.role], ['activity', 'Activity']]
  const asks = view.permissions.filter(p => p.dashboard === agent.role)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const d = DESKS[agent.role]
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dashboard" role="dialog" aria-label={agent.name} onClick={e => e.stopPropagation()} data-testid="dashboard">
        <header className="dash-head">
          <img src={`/art/characters/${d.sprite}-front-left.png`} alt="" />
          <div><h2>{agent.name}</h2><p>{agent.purpose}</p></div>
          <span className={`pill s-${agent.status}`}>{agentLabel(agent, true)}</span>
          <button className="close" onClick={onClose} aria-label="Close">×</button>
        </header>
        {asks.map(p => (
          <div className="approval-bar" key={p.id}>
            <span>{permissionLabel(p)}</span>
            <button className="deny" onClick={() => onAnswer(p, 'deny')}>Deny</button>
            <button className="allow" onClick={() => onAnswer(p, 'allow')}>Approve</button>
          </div>
        ))}
        <nav>{tabs.map(([id, label]) => <button key={id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>{label}</button>)}</nav>
        <div className="dash-body">
          {tab === 'activity' ? <Activity a={agent} />
            : tab === 'integrations' ? <Integrations health={boot.health} harness={boot.harness} />
            : tab === 'strategy' ? <StrategyPage v={view} />
            : tab === 'profile' ? <ProfilePage v={view} />
            : tab === 'costs' ? <Costs v={view} />
            : director ? <Overview v={view} />
            : agent.role === 'icp-strategist' ? <IcpPage v={view} />
            : agent.role === 'account-scout' ? <Accounts v={view} />
            : agent.role === 'signal-analyst' ? <Signals v={view} />
            : agent.role === 'buying-committee-mapper' ? <Committee v={view} />
            : agent.role === 'evidence-auditor' ? <EvidenceAudit v={view} />
            : agent.role === 'campaign-architect' ? <Campaign v={view} /> : <Gate v={view} />}
        </div>
      </div>
    </div>
  )
}

function NewMission({ onStart, onClose, mode }: { onStart: (b: Record<string, string>) => Promise<void>; onClose?: () => void; mode: string }) {
  const [f, setF] = useState({ website_url: '', goal: '', product_description: '', target_geography: '', time_horizon: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  return (
    <form className="new-mission" onSubmit={async e => {
      e.preventDefault(); setBusy(true)
      try { await onStart(f) } catch (err) { setError((err as Error).message); setBusy(false) }
    }}>
      <h2>Start a mission</h2>
      {mode === 'replay' && <p className="alert">FIXTURE DATA: only supportpilot.example has fixtures. Results are labelled.</p>}
      {mode === 'mixed' && <p className="alert">PART FIXTURE: real sites can be read, but account search has no live Crustdata key yet.</p>}
      <label>Website<input required value={f.website_url} onChange={set('website_url')} placeholder="yourcompany.com" /></label>
      <label>Goal<input required value={f.goal} onChange={set('goal')} placeholder="Book 10 meetings with…" /></label>
      <label>What does the product do? <small>Recommended. Needed if your site is a JavaScript app.</small><textarea rows={2} value={f.product_description} onChange={set('product_description')} /></label>
      <div className="two">
        <label>Target geography<input value={f.target_geography} onChange={set('target_geography')} /></label>
        <label>Time horizon<input value={f.time_horizon} onChange={set('time_horizon')} placeholder="90 days" /></label>
      </div>
      {error && <p className="alert bad">{error}</p>}
      <div className="row">{onClose && <button type="button" className="ghost" onClick={onClose}>Close</button>}<button className="allow" disabled={busy}>{busy ? 'Starting…' : 'Start mission'}</button></div>
    </form>
  )
}

export default function App() {
  const [boot, setBoot] = useState<Bootstrap | null>(null)
  const [view, setView] = useState<MissionView | null>(null)
  const [missionId, setMissionId] = useState<string | null>(null)
  const [connected, setConnected] = useState(false)
  const [denied, setDenied] = useState(false)
  const [open, setOpen] = useState<{ role: string; tab: string } | null>(null)
  const [creating, setCreating] = useState(false)
  const [page, setPage] = useState('office')
  const [chat, setChat] = useState('')
  const [notice, setNotice] = useState('')
  const missionRef = useRef<string | null>(null)
  missionRef.current = missionId
  const log = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    try {
      const b = await get<Bootstrap>('/bootstrap')
      setBoot(b)
      const id = missionRef.current ?? b.missions[0]?.id ?? null
      if (id && !missionRef.current) setMissionId(id)
      if (id) setView(await get<MissionView>(`/missions/${id}`))
    } catch (e) {
      if (/401/.test(String(e)) || /token/.test(String(e))) setDenied(true)
    }
  }, [])

  useEffect(() => {
    if (!token()) { setDenied(true); return }
    return follow(() => void refresh(), setConnected)
  }, [refresh])
  useEffect(() => { if (missionId) void refresh() }, [missionId, refresh])
  useEffect(() => { log.current?.scrollTo(0, 1e6) }, [view?.messages.length])

  const start = async (body: Record<string, string>) => {
    const out = await post<{ mission_id: string }>('/missions', body)
    setCreating(false); setMissionId(out.mission_id)
  }
  const answer = async (p: Permission, decision: 'allow' | 'deny') => {
    const message = decision === 'deny' ? 'The user denied this in the Trigger Point Office.' : undefined
    await post(`/permissions/${p.id}`, { decision, message })
    void refresh()
  }
  const send = async (e: { preventDefault: () => void }) => {
    e.preventDefault()
    if (!chat.trim() || !view) return
    try { await post(`/missions/${view.mission.id}/messages`, { text: chat }); setChat('') } catch (err) { setNotice((err as Error).message) }
  }

  if (denied) return <main className="gate"><h1>Trigger Point Office</h1><p>Open the link that <code>scripts/office.sh</code> printed. This page needs its access token.</p></main>

  const m = view?.mission
  const live = liveness(view, connected, view?.run?.status === 'working')
  const hour = new Date().getHours()
  const agent = open && view ? view.agents.find(a => a.role === open.role) : undefined
  const blanks: Agent[] = view?.agents ?? Object.keys(DESKS).map(role => ({ role, name: role.split('-').map(w => w[0].toUpperCase() + w.slice(1)).join(' '), purpose: '', status: 'idle', task: null, tasks: [], step: null, tools: [], hook_activity: [] }))
  const stalled = view?.approvals.find(a => a.status === 'pending' && !view.permissions.length)

  return (
    <div className="app">
      <header className="top">
        <strong className="brand">Trigger Point<span>Office</span></strong>
        {boot && boot.missions.length > 0 && (
          <select aria-label="Mission" value={missionId ?? ''} onChange={e => setMissionId(e.target.value)}>
            {boot.missions.map(x => <option key={x.id} value={x.id}>{x.website_url} · {stateLabel(x.state)}</option>)}
          </select>
        )}
        {m && <span className={`mode m-${m.mode}`} title={Object.entries(m.provider_modes).map(([k, v]) => `${k}: ${v}`).join(', ')}>{modeLabel(m.mode)}</span>}
        <span className={`live l-${live}`} data-testid="liveness"><i />{LIVENESS_LABEL[live]}</span>
        <span className="grow" />
        {m && !['COMPLETE', 'FAILED', 'CANCELLED'].includes(m.state) && <button className="ghost" onClick={() => void post(`/missions/${m.id}/cancel`)}>Cancel mission</button>}
        <button className="allow" onClick={() => setCreating(true)}>New mission</button>
      </header>
      <nav className="pages" aria-label="Workspace">
        {PAGES.map(([id, label]) => <button key={id} className={page === id ? 'on' : ''} onClick={() => setPage(id)} data-page={id}>{label}</button>)}
      </nav>
      {page !== 'office' && <main className="page">{view && boot ? <Page id={page} view={view} boot={boot} /> : boot && page === 'integrations' ? <Integrations health={boot.health} harness={boot.harness} /> : <p className="empty">Start a mission first.</p>}</main>}
      <main className="stage" hidden={page !== 'office'}>
        <div className="room-wrap">
          <Room agents={blanks} tasks={view?.tasks ?? []} health={boot?.health ?? []} connected={connected} night={hour < 7 || hour >= 19}
            onAgent={role => view && setOpen({ role, tab: role === 'mission-director' ? 'overview' : 'work' })}
            onObject={(role, tab) => view && setOpen({ role, tab })} />
          {!view && boot && !creating && <div className="center"><NewMission onStart={start} mode={boot.mode} /></div>}
        </div>
        <aside className="rail">
          {view && m ? <>
            {view.permissions.length > 0 && (
              <section className="needs" data-testid="needs-you">
                <h3>Needs you ({view.permissions.length})</h3>
                {view.permissions.map(p => (
                  <div className="ask-card" key={p.id}>
                    <p>{permissionLabel(p)}</p>
                    <div className="row">
                      <button className="ghost" onClick={() => setOpen({ role: p.dashboard, tab: p.dashboard === 'mission-director' ? 'overview' : 'work' })}>Review</button>
                      <button className="deny" onClick={() => void answer(p, 'deny')}>Deny</button>
                      <button className="allow" onClick={() => void answer(p, 'allow')}>Approve</button>
                    </div>
                  </div>
                ))}
              </section>
            )}
            {stalled && <section className="needs quiet"><p>{stalled.summary}</p><small>Waiting for the Director to ask. Message it below if it has stopped.</small></section>}
            <section className="progress">
              <h3>{stateLabel(m.state)}</h3>
              {m.wait_reason && <p className="alert">{m.wait_reason}</p>}
              {m.failure && <p className="alert bad">{m.failure}</p>}
              <ol className="flow">{flowSteps(m).map(s => <li key={s.state} className={s.phase} title={s.label} />)}</ol>
              <ul className="team">{view.agents.map(a => (
                <li key={a.role}><button onClick={() => setOpen({ role: a.role, tab: a.role === 'mission-director' ? 'overview' : 'work' })}><i className={`dot s-${a.status}`} />{a.name}<span>{agentLabel(a, connected)}</span></button></li>
              ))}</ul>
            </section>
            <section className="chat">
              <h3>Mission Director</h3>
              <div className="log" ref={log}>
                {view.messages.map(x => <p key={x.seq} className={x.sender}>{x.text}</p>)}
                {view.messages.length === 0 && <p className="system">No messages. This mission was not started from the Office.</p>}
              </div>
              {notice && <p className="alert bad">{notice}</p>}
              <form onSubmit={send}><input value={chat} onChange={e => setChat(e.target.value)} placeholder="Message the Director" aria-label="Message the Director" /><button disabled={!chat.trim()}>Send</button></form>
            </section>
          </> : <section className="progress"><h3>No mission yet</h3><p className="muted">Eight agents wait at their desks. They only move when real work starts.</p></section>}
        </aside>
      </main>
      <footer className="bottom">
        {boot?.health.filter(h => ['claude', 'web', 'llm', 'crustdata'].includes(h.id)).map(h => <span key={h.id}><i className={`hs-${h.state}`} />{h.id === 'llm' ? 'LLM' : h.name}: {h.state.replace('_', ' ')}</span>)}
        <span className="grow" />
        {view && <span>Claude ${view.costs.claude_usd.toFixed(3)} · {view.costs.crustdata_credits.actual ?? '0'} credits</span>}
      </footer>
      {agent && view && boot && <AgentDashboard agent={agent} view={view} boot={boot} tab={open!.tab} setTab={t => setOpen({ role: agent.role, tab: t })} onClose={() => setOpen(null)} onAnswer={(p, d) => void answer(p, d)} />}
      {creating && boot && <div className="overlay" onClick={() => setCreating(false)}><div className="modal" onClick={e => e.stopPropagation()}><NewMission onStart={start} onClose={() => setCreating(false)} mode={boot.mode} /></div></div>}
    </div>
  )
}

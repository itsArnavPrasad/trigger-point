import { type RefObject, useCallback, useEffect, useRef, useState } from "react"
import { follow, get, post, token } from './api'
import { Accounts, Activity, Campaign, Committee, Costs, EvidenceAudit, Gate, IcpPage, Integrations, Overview, ProfilePage, Signals } from './components/Dashboards'
import AgentMode, { Composer } from './components/Agent'
import Home, { NeedsYou } from './components/Home'
import ConnectPrompt from './components/Connect'
import Icon from './components/Icon'
import { FinancePage, OutreachPage, PipelinePage, StrategyPage } from './components/Pages'
import { LearningPage } from './components/Loop'
import MeetingsPage from './components/Meetings'
import Room, { DESKS } from './components/Room'
import { LIVENESS_LABEL, agentLabel, connectionRows, connectionsReady, flowSteps, liveness, modeLabel, permissionLabel, splitMeetings, stateLabel } from './logic'
import type { Agent, Bootstrap, MissionView, Permission } from './types'

type NavItem = [id: string, label: string, icon: string]
const NAV: [string | null, NavItem[]][] = [
  [null, [['home', 'Dashboard', 'dashboard'], ['office', 'Live office', 'office']]],
  ['Understand', [['profile', 'Business profile', 'profile'], ['strategy', 'Strategy', 'strategy'], ['icp', 'Ideal customer', 'icp']]],
  ['Research', [['accounts', 'Accounts', 'accounts'], ['signals', 'Buying signals', 'signals'], ['people', 'People', 'people'], ['evidence', 'Evidence', 'evidence']]],
  ['Engage', [['campaign', 'Campaign draft', 'campaign'], ['outreach', 'Outreach', 'outreach'], ['meetings', 'Meetings', 'meetings']]],
  ['Learn', [['pipeline', 'Pipeline', 'pipeline'], ['learning', 'Learnings', 'learning'], ['finance', 'Spend', 'finance']]],
]
const SUBTITLE: Record<string, string> = {
  office: 'Eight agents at their desks. Click anyone to see their work.',
  profile: 'What Trigger Point read on your site. Every fact carries its source.',
  strategy: 'Positioning, motion and channels. Hypotheses until outcomes prove them.',
  icp: 'Who to sell to, what disqualifies them, and how sure we are.',
  accounts: 'Every account found, scored by deterministic code, with reasons for each rejection.',
  signals: 'Dated reasons an account may need you now.',
  people: 'The buying committee at each account, verified against the employer.',
  evidence: 'Every claim, its source, and whether it passed the audit.',
  campaign: 'The first touch, every claim mapped to evidence.',
  outreach: 'Name targets and write verified messages for each audience.',
  meetings: 'Calls booked and held, and what was said.',
  pipeline: 'Replies, meetings and opportunities you have logged.',
  learning: 'Changes Trigger Point proposes from real outcomes, for you to approve.',
  finance: 'What the mission has cost. Actual and estimated never mix.',
  integrations: 'What is connected, and what each connector is allowed to do.',
}
const LABEL = Object.fromEntries([...NAV.flatMap(([, items]) => items.map(([id, label]) => [id, label])), ['integrations', 'Integrations']])

function Page({ id, view, boot, focus, onConnect }: { id: string; view: MissionView; boot: Bootstrap; focus?: string | null; onConnect: () => void }) {
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
    case 'meetings': return <MeetingsPage v={view} wispr={boot.health.find(h => h.id === 'wispr')?.state ?? 'not_connected'} focus={focus} />
    case 'pipeline': return <PipelinePage v={view} />
    case 'learning': return <LearningPage v={view} />
    case 'finance': return <FinancePage v={view} />
    default: return <Integrations health={boot.health} harness={boot.harness} onConnect={onConnect} />
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
      <div className="sheet" role="dialog" aria-modal="true" aria-label={agent.name} onClick={e => e.stopPropagation()} data-testid="dashboard">
        <header className="sheet-head">
          <img src={`/art/characters/${d.sprite}-front-left.png`} alt="" />
          <div><h2>{agent.name}</h2><p>{agent.purpose}</p></div>
          <span className={`status-pill s-${agent.status}`}><i className="dot" />{agentLabel(agent, true)}</span>
          <button className="close" onClick={onClose} aria-label="Close">×</button>
        </header>
        {asks.map(p => (
          <div className="approval-bar" key={p.id}>
            <span>{permissionLabel(p)}</span>
            <button className="btn destructive" onClick={() => onAnswer(p, 'deny')}>Deny</button>
            <button className="btn primary" onClick={() => onAnswer(p, 'allow')}>Approve</button>
          </div>
        ))}
        <nav className="segmented" aria-label="Sections">{tabs.map(([id, label]) => <button key={id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>{label}</button>)}</nav>
        <div className="sheet-body">
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
      <p className="muted">Give Trigger Point your website and a goal. It works out who to sell to, why now, and how to reach them.</p>
      {mode === 'replay' && <p className="alert">FIXTURE DATA: only supportpilot.example has fixtures. Results are labelled.</p>}
      {mode === 'mixed' && <p className="alert">PART FIXTURE: real sites can be read, but account search has no live Crustdata key yet.</p>}
      <label>Website<input required value={f.website_url} onChange={set('website_url')} placeholder="yourcompany.com" /></label>
      <label>Goal<input required value={f.goal} onChange={set('goal')} placeholder="Book 10 meetings with…" /></label>
      <label>What does the product do? <small>Recommended. Needed if your site is a JavaScript app.</small><textarea rows={3} value={f.product_description} onChange={set('product_description')} /></label>
      <div className="two">
        <label>Target geography<input value={f.target_geography} onChange={set('target_geography')} placeholder="India" /></label>
        <label>Time horizon<input value={f.time_horizon} onChange={set('time_horizon')} placeholder="90 days" /></label>
      </div>
      {error && <p className="alert bad">{error}</p>}
      <div className="row">{onClose && <button type="button" className="btn plain" onClick={onClose}>Cancel</button>}<button className="btn primary" disabled={busy}>{busy ? 'Starting…' : 'Start mission'}</button></div>
    </form>
  )
}

function ChatButton({ open, busy, needs, onClick }: { open: boolean; busy: boolean; needs: number; onClick: () => void }) {
  return (
    <button className={`chat-btn${open ? ' on' : ''}${busy && !open ? ' busy' : ''}`} onClick={onClick} aria-pressed={open} aria-label={open ? 'Close the Mission Director chat' : 'Open the Mission Director chat'}>
      <span className="chat-btn-icon"><Icon name="sparkle" size={15} /></span>
      <span>{open ? 'Close' : 'Chat'}</span>
      {needs > 0 && !open && <em className="chat-btn-badge">{needs}</em>}
    </button>
  )
}

/** The Mission Director as a floating window anchored to the Chat button. Always mounted, so it can animate both ways. */
function FloatingChat({ open, view, live, page, onClose, onOpen, onAnswer, log, chat, setChat, send, notice }: {
  open: boolean; view: MissionView; live: string; page: string; onClose: () => void; onOpen: (role: string, tab: string) => void
  onAnswer: (p: Permission, d: 'allow' | 'deny') => void; log: RefObject<HTMLDivElement>
  chat: string; setChat: (s: string) => void; send: (e?: { preventDefault: () => void }) => void; notice: string
}) {
  const m = view.mission
  const stalled = view.approvals.find(a => a.status === 'pending' && !view.permissions.length)
  const steps = flowSteps(m)
  const at = steps.findIndex(s => s.phase === 'current')
  const box = useRef<HTMLElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = box.current as (HTMLElement & { inert: boolean }) | null
    if (el) el.inert = !open  // a closed window is skipped by Tab and screen readers
    if (!open) return
    const t = setTimeout(() => input.current?.focus(), 320)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => { clearTimeout(t); window.removeEventListener('keydown', onKey) }
  }, [open, onClose])

  return (
    <aside className={`float-chat${open ? ' open' : ''}`} ref={box} aria-label="Mission Director">
      <header className="chat-head">
        <span className="pill-icon accent"><Icon name="sparkle" size={16} /></span>
        <div className="grow"><b>Mission Director</b><small>{live === 'working' ? 'Thinking…' : `${stateLabel(m.state)}${at >= 0 ? ` · Step ${at + 1} of ${steps.length}` : ''}`}</small></div>
        <button className="close" onClick={onClose} aria-label="Close chat" title="Close (Esc)">×</button>
      </header>
      <ol className="flow">{steps.map(s => <li key={s.state} className={s.phase} title={s.label} />)}</ol>
      {page !== 'home' && view.permissions.length > 0 && (
        <section className="insp-needs" data-testid="needs-you">
          <h3>Needs you</h3>
          {view.permissions.map(p => (
            <div className="ask-card" key={p.id}>
              <p>{permissionLabel(p)}</p>
              <div className="row">
                <button className="btn plain small" onClick={() => onOpen(p.dashboard, p.dashboard === 'mission-director' ? 'overview' : 'work')}>Review</button>
                <button className="btn destructive small" onClick={() => onAnswer(p, 'deny')}>Deny</button>
                <button className="btn primary small" onClick={() => onAnswer(p, 'allow')}>Approve</button>
              </div>
            </div>
          ))}
        </section>
      )}
      {stalled && <p className="chat-note">{stalled.summary} Waiting for the Director to ask. Message it below if it has stopped.</p>}
      {m.wait_reason && <p className="alert chat-note">{m.wait_reason}</p>}
      {m.failure && <p className="alert bad chat-note">{m.failure}</p>}
      <div className="chat-thread" ref={log} aria-live="polite">
        {view.messages.length === 0 && <p className="chat-empty">Ask about your meetings, accounts or next steps. The Director researches, drafts and books once you approve each step.</p>}
        {view.messages.map(x => <p key={x.seq} className={`msg ${x.sender}`}>{x.text}</p>)}
        {live === 'working' && <p className="msg typing" aria-label="Thinking"><i /><i /><i /></p>}
      </div>
      <div className="chat-compose">
        <Composer inputRef={input} text={chat} setText={setChat} send={send} sending={false} error={notice} placeholder="Message the Mission Director…" chips={false} />
      </div>
    </aside>
  )
}

const WISPR_KEY = 'trigger-point-wispr-skipped'
const DISMISS_KEY = 'trigger-point-connect-dismissed'
type Area = 'localStorage' | 'sessionStorage'
const readFlag = (area: Area, key: string) => { try { return window[area].getItem(key) === '1' } catch { return false } }
const writeFlag = (area: Area, key: string, on: boolean) => { try { if (on) window[area].setItem(key, '1'); else window[area].removeItem(key) } catch { /* a per-viewer convenience only */ } }

const MODE_KEY = 'trigger-point-mode'
const savedMode = () => { try { return localStorage.getItem(MODE_KEY) === 'agent' ? 'agent' : 'dashboard' } catch { return 'dashboard' } }

const narrow = () => typeof window !== 'undefined' && window.innerWidth < 900

export default function App() {
  const [boot, setBoot] = useState<Bootstrap | null>(null)
  const [view, setView] = useState<MissionView | null>(null)
  const [missionId, setMissionId] = useState<string | null>(null)
  const [connected, setConnected] = useState(false)
  const [denied, setDenied] = useState(false)
  const [open, setOpen] = useState<{ role: string; tab: string } | null>(null)
  const [creating, setCreating] = useState(false)
  const [page, setPage] = useState('home')
  const [mode, setModeState] = useState<'agent' | 'dashboard'>(savedMode)
  const setMode = (m: 'agent' | 'dashboard') => { setModeState(m); try { localStorage.setItem(MODE_KEY, m) } catch { /* per-viewer convenience only */ } }
  const [meetingFocus, setMeetingFocus] = useState<string | null>(null)
  const [connectOpen, setConnectOpen] = useState(false)
  const [wisprSkipped, setWisprSkipped] = useState(() => readFlag('localStorage', WISPR_KEY))
  const askedToConnect = useRef(false)
  const [sidebar, setSidebar] = useState(!narrow())
  const [inspector, setInspector] = useState(false)
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
  useEffect(() => { const t = setInterval(() => void refresh(), 30000); return () => clearInterval(t) }, [refresh])
  useEffect(() => { log.current?.scrollTo(0, 1e6) }, [view?.messages.length, inspector])
  useEffect(() => {  // the first look at the connectors takes a while: keep looking until it has finished
    if (!boot || (boot.connectors_checked && !boot.connectors_checking)) return
    const t = setInterval(() => void refresh(), 3000)
    return () => clearInterval(t)
  }, [boot, refresh])
  useEffect(() => {  // once they have been checked, ask once per tab if something needed is missing
    if (!boot?.connectors_checked || askedToConnect.current) return
    askedToConnect.current = true
    if (!connectionsReady(connectionRows(boot.harness, wisprSkipped)) && !readFlag('sessionStorage', DISMISS_KEY)) setConnectOpen(true)
  }, [boot, wisprSkipped])

  const start = async (body: Record<string, string>) => {
    const out = await post<{ mission_id: string }>('/missions', body)
    setCreating(false); setMissionId(out.mission_id); setPage('home')
  }
  const answer = async (p: Permission, decision: 'allow' | 'deny') => {
    const message = decision === 'deny' ? 'The user denied this in the Trigger Point Office.' : undefined
    await post(`/permissions/${p.id}`, { decision, message })
    void refresh()
  }
  const send = async (e?: { preventDefault: () => void }) => {
    e?.preventDefault()
    if (!chat.trim() || !view) return
    try { await post(`/missions/${view.mission.id}/messages`, { text: chat }); setChat(''); setNotice('') } catch (err) { setNotice((err as Error).message) }
  }
  const cancelMission = () => { if (view) void post(`/missions/${view.mission.id}/cancel`) }
  const closeConnect = () => { setConnectOpen(false); writeFlag('sessionStorage', DISMISS_KEY, true) }
  const skipWispr = (on: boolean) => { setWisprSkipped(on); writeFlag('localStorage', WISPR_KEY, on) }
  const recheckConnectors = () => { void post('/connectors/refresh').then(() => refresh()) }
  const go = (p: string) => { setPage(p); if (narrow()) setSidebar(false); document.querySelector('.content')?.scrollTo(0, 0) }
  const openAgent = (role: string, tab: string) => view && setOpen({ role, tab })

  if (denied) return <main className="gate"><h1>Trigger Point</h1><p>Open the link that <code>scripts/office.sh</code> printed. This page needs its access token.</p></main>

  const m = view?.mission
  const live = liveness(view, connected, view?.run?.status === 'working')
  const hour = new Date().getHours()
  const agent = open && view ? view.agents.find(a => a.role === open.role) : undefined
  const blanks: Agent[] = view?.agents ?? Object.keys(DESKS).map(role => ({ role, name: role.split('-').map(w => w[0].toUpperCase() + w.slice(1)).join(' '), purpose: '', status: 'idle', task: null, tasks: [], step: null, tools: [], hook_activity: [] }))
  const badge: Record<string, number> = view ? {
    home: view.permissions.length,
    accounts: view.funnel.qualified ?? 0,
    meetings: splitMeetings(view.meetings, new Date().toISOString().slice(0, 10)).upcoming.length,
  } : {}

  const modals = <>
    {agent && view && boot && <AgentDashboard agent={agent} view={view} boot={boot} tab={open!.tab} setTab={t => setOpen({ role: agent.role, tab: t })} onClose={() => setOpen(null)} onAnswer={(p, d) => void answer(p, d)} />}
    {connectOpen && boot && (() => {
      const rows = connectionRows(boot.harness, wisprSkipped)
      return <ConnectPrompt rows={rows} ready={connectionsReady(rows)} checking={!!boot.connectors_checking} onRecheck={recheckConnectors}
        onSkip={() => skipWispr(true)} onUnskip={() => skipWispr(false)} onClose={closeConnect} />
    })()}
    {creating && boot && <div className="overlay" onClick={() => setCreating(false)}><div className="modal" onClick={e => e.stopPropagation()}><NewMission onStart={start} onClose={() => setCreating(false)} mode={boot.mode} /></div></div>}
  </>

  if (mode === 'agent' && view) return <>
    <AgentMode v={view} connected={connected} live={live} onDashboard={() => setMode('dashboard')} onAnswer={(p, d) => void answer(p, d)} />
    {modals}
  </>

  return (
    <div className={`shell${sidebar ? '' : ' no-sidebar'}`}>
      <aside className="sidebar" aria-label="Workspace">
        <div className="brand"><span className="brand-mark"><Icon name="icp" size={16} /></span><div><b>Trigger Point</b><small>GTM operating system</small></div></div>
        <nav>
          {NAV.map(([group, items]) => (
            <div className="nav-group" key={group ?? 'top'}>
              {group && <h4>{group}</h4>}
              {items.map(([id, label, icon]) => (
                <button key={id} className={page === id ? 'on' : ''} onClick={() => go(id)} data-page={id} aria-current={page === id ? 'page' : undefined}>
                  <Icon name={icon} /><span>{label}</span>
                  {badge[id] ? <em className={id === 'home' ? 'warn' : ''}>{badge[id]}</em> : null}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <button className={page === 'integrations' ? 'on' : ''} onClick={() => go('integrations')} data-page="integrations"><Icon name="integrations" /><span>Integrations</span></button>
          <ul className="conn">
            {boot?.health.filter(h => ['claude', 'web', 'llm', 'crustdata'].includes(h.id)).map(h => <li key={h.id}><i className={`hs-${h.state}`} />{h.id === 'llm' ? 'LLM' : h.name}<span>{h.state.replace('_', ' ')}</span></li>)}
          </ul>
        </div>
      </aside>
      {sidebar && narrow() && <div className="scrim" onClick={() => setSidebar(false)} />}

      <div className="main">
        <header className="toolbar">
          <button className="icon-btn" onClick={() => setSidebar(!sidebar)} aria-label={sidebar ? 'Hide sidebar' : 'Show sidebar'} title={sidebar ? 'Hide sidebar' : 'Show sidebar'}><Icon name="sidebar" /></button>
          {boot && boot.missions.length > 0 && (
            <select className="mission-select" aria-label="Mission" value={missionId ?? ''} onChange={e => setMissionId(e.target.value)}>
              {boot.missions.map(x => <option key={x.id} value={x.id}>{x.website_url} · {stateLabel(x.state)}</option>)}
            </select>
          )}
          {m && <span className={`mode-chip m-${m.mode}`} title={Object.entries(m.provider_modes).map(([k, v]) => `${k}: ${v}`).join(', ')}>{modeLabel(m.mode)}</span>}
          <span className={`live-chip l-${live}`} data-testid="liveness"><i />{LIVENESS_LABEL[live]}</span>
          <span className="grow" />
          {view && <div className="mode-switch small" role="tablist" aria-label="Mode"><button role="tab" aria-selected="false" onClick={() => setMode('agent')}><Icon name="sparkle" size={13} />Agent</button><button role="tab" aria-selected="true" className="on"><Icon name="dashboard" size={13} />Dashboard</button></div>}
          {view && <span className="cost">${view.costs.claude_usd.toFixed(3)} · {view.costs.crustdata_credits.actual ?? '0'} credits</span>}
          {view && <ChatButton open={inspector} busy={live === 'working'} needs={view.permissions.length} onClick={() => setInspector(!inspector)} />}
        </header>

        <div className="workspace">
          <main className={`content${page === 'office' ? ' is-office' : ''}`}>
            {page === 'office' ? (
              <div className="office-stage">
                <div className="room-card"><div className="room-fit">
                  <Room agents={blanks} tasks={view?.tasks ?? []} health={boot?.health ?? []} connected={connected} night={hour < 7 || hour >= 19}
                    onAgent={role => openAgent(role, role === 'mission-director' ? 'overview' : 'work')}
                    onObject={(role, tab) => openAgent(role, tab)} />
                </div></div>
                <p className="office-caption">{view ? SUBTITLE.office : 'Eight agents wait at their desks. They only move when real work starts.'}</p>
              </div>
            ) : page === 'home' ? (
              view ? <Home v={view} connected={connected} live={live} go={go} onAnswer={(p, d) => void answer(p, d)} onReview={p => openAgent(p.dashboard, p.dashboard === 'mission-director' ? 'overview' : 'work')} onNotes={id => { setMeetingFocus(id); go('meetings') }} onAgent={() => setMode('agent')} onNewMission={() => setCreating(true)} onCancel={cancelMission} />
                : boot ? <div className="welcome"><div className="welcome-copy"><span className="eyebrow">Trigger Point</span><h1>Find out who needs you, and why now.</h1><p>Give it your website and a goal. Agents read your business, pick the accounts with a real reason to talk, prove it with evidence, and draft outreach you approve.</p></div><NewMission onStart={start} mode={boot.mode} /></div>
                : <p className="loading">Loading…</p>
            ) : (
              <div className="page">
                <header className="page-head"><h1>{LABEL[page]}</h1><p>{SUBTITLE[page]}</p></header>
                {view && <NeedsYou v={view} onAnswer={(p, d) => void answer(p, d)} onReview={p => openAgent(p.dashboard, p.dashboard === 'mission-director' ? 'overview' : 'work')} />}
                {view && boot ? <Page id={page} view={view} boot={boot} focus={meetingFocus} onConnect={() => setConnectOpen(true)} />
                  : boot && page === 'integrations' ? <Integrations health={boot.health} harness={boot.harness} onConnect={() => setConnectOpen(true)} />
                  : <div className="empty-state big"><Icon name="dashboard" size={32} /><p>No mission yet</p><small>Start a mission to fill this page.</small><button className="btn primary" onClick={() => setCreating(true)}>New mission</button></div>}
              </div>
            )}
          </main>
        </div>
      </div>

      {view && <FloatingChat open={inspector} view={view} live={live} page={page} onClose={() => setInspector(false)} onOpen={openAgent} onAnswer={(p, d) => void answer(p, d)} log={log} chat={chat} setChat={setChat} send={send} notice={notice} />}
      {modals}
    </div>
  )
}

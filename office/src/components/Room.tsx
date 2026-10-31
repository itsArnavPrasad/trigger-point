/** The room. Art only, plus eight agents whose every visual state comes from the mission. */

import { agentLabel } from '../logic'
import type { Agent, Health, Task } from '../types'

interface Desk { x: number; y: number; z: number; sprite: string; face: string }

/** Desk positions and facing follow the room art. */
export const DESKS: Record<string, Desk> = {
  'mission-director':        { x: 48.9, y: 52.9, z: 70, sprite: 'Claude-1', face: 'rear-right' },
  'icp-strategist':          { x: 38.5, y: 55.2, z: 58, sprite: 'explore-1', face: 'rear-left' },
  'account-scout':           { x: 25.8, y: 71, z: 85, sprite: 'dev-1', face: 'rear-left' },
  'signal-analyst':          { x: 37.9, y: 68.2, z: 85, sprite: 'employee-2', face: 'rear-right' },
  'buying-committee-mapper': { x: 26.9, y: 59.2, z: 40, sprite: 'employee-1', face: 'front-left' },
  'evidence-auditor':        { x: 55.2, y: 66.8, z: 55, sprite: 'security-audit-1', face: 'front-left' },
  'campaign-architect':      { x: 52.7, y: 78.8, z: 95, sprite: 'Frontend-dev-1', face: 'rear-left' },
  'quality-gatekeeper':      { x: 65.9, y: 75.8, z: 95, sprite: 'employee-3', face: 'rear-right' },
}

const FURNITURE: [string, number, number, number, number?][] = [
  ['standing-desk-left-rear', 42.4, 50.4, 17], ['standing-desk-left-front', 46.7, 53, 17], ['standing-desk-right-front', 39.9, 55.2, 17],
  ['standing-desk-left-rear', 31.4, 64.8, 17], ['standing-desk-left-front', 35.4, 67.5, 17], ['standing-desk-right-front', 27.9, 70, 17],
  ['standing-desk-left-rear', 59, 73.7, 17], ['standing-desk-left-front', 62.6, 76, 17], ['standing-desk-right-front', 55.4, 78.7, 17], ['standing-desk-right-rear', 66.6, 71.1, 17],
  ['monstera-plant', 91.9, 64.7, 12], ['snake-plant', 43.2, 37.9, 10.5], ['money-tree', 32, 71.2, 10.5], ['money-tree', 89.2, 65.7, 10.5], ['monstera-plant', 60.2, 80.4, 12],
]

/** Things in the room that open real data. Nothing else is clickable. */
const OBJECTS: { id: string; label: string; x: number; y: number; w: number; h: number; opens: [string, string] }[] = [
  { id: 'board', label: 'Mission board', x: 80, y: 42, w: 13, h: 15, opens: ['mission-director', 'overview'] },
  { id: 'bell', label: 'Approvals', x: 63, y: 39, w: 5, h: 8, opens: ['mission-director', 'overview'] },
  { id: 'cabinet', label: 'Evidence', x: 45, y: 53, w: 5, h: 9, opens: ['evidence-auditor', 'work'] },
  { id: 'printer', label: 'Drafts', x: 85.4, y: 53, w: 8, h: 11, opens: ['campaign-architect', 'work'] },
  { id: 'tv', label: 'Integrations', x: 90, y: 42, w: 7, h: 10, opens: ['mission-director', 'integrations'] },
  { id: 'poster', label: 'Strategy', x: 8, y: 45, w: 6, h: 12, opens: ['icp-strategist', 'work'] },
  { id: 'coffee', label: 'Costs', x: 78.5, y: 47, w: 5, h: 9, opens: ['mission-director', 'costs'] },
]

export default function Room({ agents, tasks, health, connected, night, onAgent, onObject }: {
  agents: Agent[]; tasks: Task[]; health: Health[]; connected: boolean; night: boolean
  onAgent: (role: string) => void; onObject: (role: string, tab: string) => void
}) {
  return (
    <div className="room" data-testid="room">
      <img className="room-art" src={`/art/rooms/office-${night ? 'night' : 'day'}.png`} alt="" />
      {FURNITURE.map(([src, x, y, h], i) => (
        <img key={i} className="prop" src={`/art/furniture/${src}.png`} alt="" style={{ left: `${x}%`, top: `${y}%`, height: `${h}cqh`, zIndex: Math.round(y) }} />
      ))}
      <img className="prop" src="/art/furniture/coffee-off.png" alt="" style={{ left: '78.5%', top: '50.2%', height: '8.5cqh', zIndex: 50 }} />
      <img className="prop" src="/art/furniture/printer-working.png" alt="" style={{ left: '85.4%', top: '56.8%', height: '11.5cqh', zIndex: 56 }} />
      <img className="prop" src="/art/furniture/filling-closed.png" alt="" style={{ left: '45%', top: '56.5%', height: '9.3cqh', zIndex: 56 }} />
      <div className="wall-board" aria-hidden="true">
        <div><b>{tasks.filter(t => t.status === 'queued').length}</b>To do</div>
        <div><b>{tasks.filter(t => t.status === 'running' || t.status === 'waiting_approval').length}</b>Doing</div>
        <div><b>{tasks.filter(t => t.status === 'succeeded').length}</b>Done</div>
      </div>
      <div className="wall-screen" aria-hidden="true">
        {health.filter(h => ['web', 'llm', 'crustdata'].includes(h.id)).map(h => <i key={h.id} className={`hs-${h.state}`} />)}
      </div>
      {OBJECTS.map(o => (
        <button key={o.id} className="object" title={o.label} aria-label={o.label} data-object={o.id}
          style={{ left: `${o.x}%`, top: `${o.y}%`, width: `${o.w}%`, height: `${o.h}%` }} onClick={() => onObject(...o.opens)}>
          <span>{o.label}</span>
        </button>
      ))}
      {agents.map(a => {
        const d = DESKS[a.role]
        if (!d) return null
        return (
          <button key={a.role} className={`agent s-${a.status}`} style={{ left: `${d.x}%`, top: `${d.y}%`, zIndex: d.z }}
            onClick={() => onAgent(a.role)} aria-label={`${a.name}: ${agentLabel(a, connected)}`} data-role={a.role} data-status={a.status}>
            {a.status === 'running' && a.step && <span className="bubble">{a.step}</span>}
            {a.status === 'waiting_approval' && <span className="bubble ask">Needs you</span>}
            {a.status === 'failed' && <span className="bubble bad">Failed</span>}
            {a.status === 'running' && <img className="typing" src="/art/effects/typing.png" alt="" />}
            <img className="sprite" src={`/art/characters/${d.sprite}-${d.face}.png`} alt="" draggable={false} />
          </button>
        )
      })}
      {agents.map(a => DESKS[a.role] && (
        <span key={a.role} className={`nameplate s-${a.status}`} style={{ left: `${DESKS[a.role].x}%`, top: `${DESKS[a.role].y}%` }}>
          <i />{a.name.replace('Buying Committee Mapper', 'Committee Mapper')}
        </span>
      ))}
    </div>
  )
}

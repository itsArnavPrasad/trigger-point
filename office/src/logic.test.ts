import { describe, expect, it } from 'vitest'
import { agentLabel, elapsed, flowSteps, journey, liveness, meetingStatus, modeLabel, percent, permissionLabel, safeHref, signalLabel, splitMeetings, tokenFromHash } from './logic'
import type { MissionView } from './types'

const view = (over: Partial<MissionView> & { state?: string } = {}) => ({
  mission: { state: over.state ?? 'ICP_READY' }, permissions: [], tasks: [], approvals: [], ...over,
}) as unknown as MissionView

describe('honest status', () => {
  it('says connection lost whatever the mission said last', () => {
    expect(liveness(view(), false, true)).toBe('lost')
    expect(agentLabel({ status: 'running' }, false)).toBe('Connection lost')
  })
  it('is idle when nothing is running, not working', () => expect(liveness(view(), true, false)).toBe('idle'))
  it('is working only with a running Director or task', () => {
    expect(liveness(view(), true, true)).toBe('working')
    expect(liveness(view({ tasks: [{ status: 'running' } as never] }), true, false)).toBe('working')
  })
  it('needs you on an open prompt or missing input', () => {
    expect(liveness(view({ permissions: [{} as never] }), true, true)).toBe('needs_you')
    expect(liveness(view({ state: 'WAITING_FOR_INPUT' }), true, false)).toBe('needs_you')
  })
  it('says needs you, not working, when the Director has finished its turn and waits', () => {
    expect(liveness(view({ run: { status: 'idle', detail: 'success' } }), true, false)).toBe('needs_you')
  })
  it('ends on a terminal state', () => expect(liveness(view({ state: 'COMPLETE' }), true, true)).toBe('ended'))
})

describe('labels', () => {
  it('always marks fixture data', () => {
    expect(modeLabel('replay')).toBe('FIXTURE DATA')
    expect(modeLabel('mixed')).toBe('PART FIXTURE')
    expect(modeLabel('nonsense')).not.toBe('LIVE')
  })
  it('says what each approval does', () => {
    expect(permissionLabel({ tool: 'mcp__trigger_point__approve_campaign_draft' })).toContain('nothing is sent')
    expect(permissionLabel({ tool: 'mcp__trigger_point__discover_accounts' })).toContain('credits')
  })
  it('shows who a test email goes to', () => {
    const p = { tool: 'mcp__claude_ai_Gmail__send_message', input: { to: ['a@b.example'], subject: 'Hi' } }
    expect(permissionLabel(p)).toBe('Send test email to a@b.example: Hi')
  })
  it('places a stopped mission at the step it came from', () => {
    const steps = flowSteps({ state: 'NEEDS_RETRY', resume_state: 'ICP_READY' })
    expect(steps.find(s => s.phase === 'current')?.state).toBe('ICP_READY')
  })
})

describe('dashboard', () => {
  it('maps mission states onto the five-phase journey', () => {
    const phases = (state: string, resume_state?: string) => journey({ state, resume_state }).map(p => p.phase).join(' ')
    expect(phases('PROFILE_REVIEW')).toBe('current todo todo todo todo')
    expect(phases('SIGNALS_RESEARCHED')).toBe('done done current todo todo')
    expect(phases('COMPLETE')).toBe('done done done done current')
    expect(phases('NEEDS_RETRY', 'ICP_READY')).toBe('done current todo todo todo')
    expect(phases('FAILED')).toBe('todo todo todo todo todo')
  })
  it('splits meetings into upcoming (soonest first) and past (latest first)', () => {
    const { upcoming, past } = splitMeetings([{ held_on: '2026-10-01' }, { held_on: '2026-11-09' }, { held_on: '2026-10-31' }, { held_on: '2026-10-20' }], '2026-10-31')
    expect(upcoming.map(m => m.held_on)).toEqual(['2026-10-31', '2026-11-09'])
    expect(past.map(m => m.held_on)).toEqual(['2026-10-20', '2026-10-01'])
  })
})

describe('meeting status', () => {
  const today = '2026-10-31'
  it('never calls a past meeting held without notes or a held mark', () => {
    expect(meetingStatus({ held_on: '2026-10-20' }, today)).toBe('needs_update')
    expect(meetingStatus({ held_on: '2026-10-20', notes: 'Wants a pilot' }, today)).toBe('held')
    expect(meetingStatus({ held_on: '2026-10-20', status: 'held' }, today)).toBe('held')
  })
  it('keeps missed and cancelled whatever the date', () => {
    expect(meetingStatus({ held_on: '2026-10-20', status: 'missed', notes: 'x' }, today)).toBe('missed')
    expect(meetingStatus({ held_on: '2026-11-20', status: 'cancelled' }, today)).toBe('cancelled')
  })
  it('separates today from upcoming', () => {
    expect(meetingStatus({ held_on: today }, today)).toBe('today')
    expect(meetingStatus({ held_on: '2026-11-02' }, today)).toBe('upcoming')
  })
})

describe('safety', () => {
  it('links only http(s)', () => {
    expect(safeHref('https://a.example')).toBe('https://a.example')
    expect(safeHref('javascript:alert(1)')).toBeUndefined()
  })
  it('reads a token only from the expected shape', () => {
    expect(tokenFromHash(`#token=${'a'.repeat(64)}`)).toBe('a'.repeat(64))
    expect(tokenFromHash('#token=<script>')).toBeNull()
  })
  it('formats elapsed time', () => {
    const now = Date.parse('2026-10-31')
    expect(elapsed(new Date(now - 30_000).toISOString(), null, now)).toBe('30s')
    expect(elapsed(null)).toBe('')
  })
})

describe('percent', () => {
  it('never shows a rate with no sends behind it', () => {
    expect(percent(0, 0)).toBe('Unknown')
    expect(percent(0.256, 8)).toBe('26%')
    expect(percent(0, 8)).toBe('0%')
  })
})

describe('signalLabel', () => {
  it('says what a signal means in plain words', () => {
    expect(signalLabel('topic_engagement')).toBe('Staff post about the topic')
    expect(signalLabel('recent_funding')).toBe('Recent funding')
  })
  it('falls back to the type itself, never to a blank', () => {
    expect(signalLabel('some_new_signal')).toBe('some new signal')
  })
})

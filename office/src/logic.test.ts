import { describe, expect, it } from 'vitest'
import { agentLabel, elapsed, flowSteps, journey, liveness, contactStatus, gmailCompose, initials, meetingStatus, modeLabel, profileLink, telHref, rankNote, scoreLine, permissionLabel, safeHref, splitMeetings, tokenFromHash } from './logic'
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

describe('score line', () => {
  const comp = (fit: number | null, timing: number | null, reach: number | null, ev: number | null) => ({
    fit: { value: fit, known: fit !== null, detail: '' }, timing: { value: timing, known: timing !== null, detail: '' },
    reachability: { value: reach, known: reach !== null, detail: '' }, evidence_quality: { value: ev, known: ev !== null, detail: '' },
  })
  const line = (c: ReturnType<typeof comp>, status = 'qualified', rejections: string[] = []) => scoreLine({ status, rejections, components: c })
  it('names the strengths and the one gap', () => {
    expect(line(comp(100, 34, 100, 60))).toBe('A good fit and a verified contact, but no fresh signal.')
  })
  it('says so when everything is strong', () => {
    expect(line(comp(100, 95, 100, 85))).toBe('Strong on every measure: a good fit, fresh signals, a verified contact and solid evidence.')
  })
  it('explains a rejection in plain words, whatever the score', () => {
    expect(line(comp(100, 80, 0, 70), 'rejected', ['no_relevant_buyer'])).toBe('Rejected: no relevant decision-maker found there.')
    expect(line(comp(100, 0, null, 0), 'rejected', ['no_fresh_why_now', 'weird_code'])).toBe('Rejected: no fresh reason to talk now and weird code.')
  })
  it('never calls unknown data weak or strong', () => {
    expect(line(comp(100, null, 60, 60), 'insufficient_evidence')).toBe('Not enough evidence yet: timing unknown.')
  })
  it('does not invent a verdict for middling scores', () => expect(line(comp(60, 60, 60, 60))).toBe('Middling on every measure.'))
})

describe('rank note', () => {
  const acct = (name: string, c: number[], rejections: string[] = []) => ({
    name, score: { status: 'qualified', rejections, components: Object.fromEntries(['fit', 'timing', 'reachability', 'evidence_quality'].map((k, i) => [k, { value: c[i], known: true, detail: '' }])) },
  }) as never
  it('names the measure where it falls furthest behind the account above', () => {
    expect(rankNote(acct('Bayview', [100, 95, 100, 85]), acct('Lakeside', [100, 90, 100, 80]))).toBe('Slightly behind Bayview on timing.')
    expect(rankNote(acct('Sunrise', [100, 95, 100, 85]), acct('Brightlane', [100, 34, 100, 70]))).toBe('Well behind Sunrise on timing.')
  })
  it('says nothing for the first account or when a rejection already explains it', () => {
    expect(rankNote(undefined, acct('A', [100, 100, 100, 100]))).toBeNull()
    expect(rankNote(acct('A', [100, 100, 100, 100]), acct('B', [100, 0, 0, 0], ['no_relevant_buyer']))).toBeNull()
  })
})

describe('contact buttons', () => {
  it('builds a Gmail compose link only from a valid address, encoded', () => {
    expect(gmailCompose('asha@school.example')).toBe('https://mail.google.com/mail/?view=cm&fs=1&to=asha%40school.example')
    expect(gmailCompose('a+b@school.example')).toContain('a%2Bb%40school.example')
    for (const bad of ['', 'nope', 'a@b', 'a b@c.example', 'x@y.example&bcc=boss@z.example', '<x>@y.example', 'a@b.example,c@d.example']) expect(gmailCompose(bad)).toBeUndefined()
  })
  it('builds a tel link only from a plausible number, digits and plus only', () => {
    expect(telHref('+91 22 5550 0101')).toBe('tel:+912255500101')
    for (const bad of ['', 'call me', '12', 'javascript:alert(1)', '+91 22 5550 0101; rm']) expect(telHref(bad)).toBeUndefined()
  })
  it('calls a link LinkedIn only when the host says so, and never links a non-http(s) URL', () => {
    expect(profileLink('https://www.linkedin.com/in/someone')?.label).toBe('LinkedIn')
    expect(profileLink('https://profiles.example/8001')?.label).toBe('Profile')
    expect(profileLink('javascript:alert(1)')).toBeUndefined()
    expect(profileLink(null)).toBeUndefined()
  })
  it('shows the provider status as given, unless it clearly means valid or invalid', () => {
    expect(contactStatus('valid')).toEqual({ text: 'Verified', tone: 'good' })
    expect(contactStatus('Catch_All')).toEqual({ text: 'Catch all', tone: 'warn' })
    expect(contactStatus(null)).toBeUndefined()
  })
  it('makes two-letter initials', () => {
    expect(initials('Asha Kumar Example')).toBe('AE')
    expect(initials(null)).toBe('?')
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

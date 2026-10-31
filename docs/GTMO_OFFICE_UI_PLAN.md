# Trigger Point Office

Trigger Point Office, in `office/`, is the only UI: a purpose-built GTM control room.

**Rule:** everything visible is real state or plain decoration. An object is clickable only if it opens real data.

Art comes from Claude Office under the MIT licence, including the room, 8 character sprite sets and furniture. See `docs/THIRD_PARTY_NOTICES.md`.

## What you see
```text
+------------------------------------------------------------------------------+
| Trigger Point Office | mission picker | FIXTURE DATA | Needs you | Cancel | New mission |
+-----------------------------------------------------+------------------------+
|                                                     | NEEDS YOU              |
|   THE ROOM                                          | Approve the profile    |
|   8 agents at fixed desks. Status label on each.    | [Review][Deny][Approve]|
|   Running: real step in a bubble.                   +------------------------+
|   Waiting: "Needs you". Failed: "Failed".           | Flow bar + 8 agents    |
|   Whiteboard: real To do / Doing / Done counts.     +------------------------+
|   Wall screen: real connector status.               | Mission Director chat  |
+-----------------------------------------------------+------------------------+
| Claude Code: ready | Web: live | LLM: live | Crustdata: fixture | cost so far |
+------------------------------------------------------------------------------+
```
**Workspace pages:** Office, Business profile, Strategy, ICP, Accounts, Signals, People, Evidence, Campaign, Outreach, Meetings, Pipeline, Learning, Finance, Integrations. Each area has its own page, and the room stays one click away.

**Click a character:** its dashboard pops up, using the same views.

| Character | Dashboard |
|---|---|
| Mission Director | Mission, tasks, approvals, timeline; Integrations; Costs |
| ICP Strategist | Strategy (value proposition, positioning, market, motion, channels, experiments); ICP (must-haves, preferences, disqualifiers, confidence, gaps, versions); business profile with sources |
| Account Scout | Funnel, ranked accounts with score parts, rejections, provider calls |
| Signal Analyst | Dated signals: age, strength, status; coverage notes |
| Buying Committee Mapper | People per account: role, employer check, why they matter |
| Evidence Auditor | Evidence table with filters, four-why case file, score breakdown, gaps |
| Campaign Architect | The exact email, claim-to-evidence map, verifier log, follow-up angles |
| Quality Gatekeeper | Gate checks and findings |

Every agent also has an **Activity** tab: current work, tool calls, Claude Code hook activity, output, errors.

**Room objects:** whiteboard and bell open the mission; cabinet opens evidence; printer opens drafts; wall screen opens integrations; poster opens strategy; coffee machine opens costs. Plants, cooler and extinguisher do nothing.

## The path through a mission
1. **New mission:** website, goal, product description, geography, horizon.
2. **Director reads the site** and asks only questions that change a decision, in chat.
3. **Profile approval:** card in Needs you; Review opens the ICP Strategist's dashboard.
4. **ICP approval:** edit, compare versions, approve the credit estimate.
5. **Research:** each credit-spending step is its own approval. Agents work; dashboards fill.
6. **Audit and score,** then **draft** and **gate.**
7. **Draft approval:** you see the exact text. Approval sends nothing.
8. **Outreach:** write messages per audience, schedule them, send to the test inbox and book a test meeting. Each send is held for a click.
9. **Replies and meetings:** check replies, import from Wispr Flow, and review what needs a person.
10. **Learning:** the nine steps with live counts, what the data supports, decisions, experiments, lessons, and why each version changed.

## How the UI drives the harness
```text
Browser --token--> FastAPI /api/office --> Mission Runner --> claude --agent mission-director
   ^                     |                                       | MCP tools    | hooks
   |  stream of ticks    v                                       v              v
   +---------------- SQLite <---- Trigger Point core --------------------+   scripts/office_hook.py
```
- **One process, one database.** No second server. The MCP server, hooks and API share SQLite.
- **Approvals are real Claude Code prompts.** A gated call raises `PermissionRequest`. The hook holds it and waits. Your click answers it, and only then does Claude Code run the tool. Nothing in the API can run a gated tool.
- **Chat** goes to the Director's stdin. If the process died, the next message resumes the same session.
- **Live updates:** the stream sends a tick when anything changes, and the page refetches. Heartbeat every 10 s; 25 s of silence shows Connection lost.

## Gaps in the UI
- Only one account gets a case file and draft in a mission.
- The Quality Gatekeeper lists checks passed, without per-check evidence.
- "Inputs" on the Activity tab are not shown.
- Pipeline outcomes and costs are entered by hand until connectors exist.
- Market research comes from the seller's profile and the model, not outside sources.

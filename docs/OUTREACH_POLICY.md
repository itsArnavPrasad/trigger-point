# Outreach and External Action Policy

> Drafts only for real recipients. The one send path is a test: Gmail and Calendar calls may reach only `TRIGGER_POINT_TEST_RECIPIENTS`, marked `[Trigger Point test]`, and `scripts/office_hook.py` denies anything else. An empty list denies everything. A message is rechecked against the current rules before it is prepared or approved. Approvals happen in Trigger Point Office, and the exact content is one click away on the card.

## Campaign output
Per account, generate:
1. Warm-introduction request only when an actual, evidence-backed connection is known.
2. Cold email only when no credible warm path is available or the user explicitly chooses it.
3. Optional concise LinkedIn note, subject to platform rules and user authorization.
4. A follow-up plan with a distinct angle and recheck/expiry date.
5. A source panel mapping facts in the message to evidence.
6. A recommended next action and reason.

## Writing constraints
- One relevant hook, ideally dated and specific to the person or company.
- One clear bridge from the hook to a problem the seller can plausibly solve.
- One seller-approved proof point, if available.
- One low-friction ask.
- Avoid fake familiarity, false urgency, fake mutual connections, generic flattery, and claims about unverified pain.
- If there is no valid recent hook, say so and use a clearly labeled role-level hypothesis—or recommend not contacting the account.
- Do not use private or sensitive personal information for personalization.
- Never fabricate a source, quote, metric, customer, or product capability.

## Stakeholders and channels
Do not contact every role by default. Recommend a sequence from deal context. Each person gets a distinct purpose and message. Use only channels with a real integration or a clearly labelled manual workflow.

## Human approval gate
Default `dry_run=true`. Before any future send integration is enabled, require:
- exact recipient and channel
- exact rendered message and content hash
- evidence panel visible
- suppression/opt-out and duplicate checks
- user action approving this exact send
- provider permissions and compliance checks
- a durable audit event

Approval for one message is not approval for all future sequence steps. A reply, opt-out, bounce, or explicit stop request must halt follow-ups.

## Deliverability and compliance
Do not hard-code a universal sending-volume recipe. Sending limits vary by provider, domain reputation, geography, law, and recipient consent. Start with drafts and manual review. Before any pilot, consult applicable privacy, marketing, anti-spam, and platform rules; maintain suppression lists and honor opt-outs.

## Outcomes
States are distinct:
`drafted → approved → sent → delivered → replied → meeting_booked → meeting_held → opportunity_created → closed_won`
with branches for `bounced`, `opted_out`, `rejected`, `disqualified`, and `lost`.

Do not infer a later state from an earlier one. Drafted is not sent; sent is not delivered; a reply is not a meeting; a meeting is not revenue.

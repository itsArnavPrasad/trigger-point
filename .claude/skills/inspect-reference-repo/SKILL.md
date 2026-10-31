---
name: inspect-reference-repo
description: Safely inspect an open-source repository for reusable architecture or code patterns before adopting it in Trigger Point. Use when asked to clone, evaluate, port, or reuse code from a reference repo.
---

# Inspect a Reference Repository

1. Read the repository README, LICENSE, NOTICE, contribution terms, and any additional license terms before reading implementation details.
2. Record the URL, commit SHA, date, license, relevant paths, dependencies, maintenance status, and tests in `docs/REPO_NOTES.md`.
3. Identify one specific pattern needed by Trigger Point; do not propose merging entire apps.
4. Trace the pattern through implementation and tests.
5. Check whether it conflicts with Trigger Point's invariants: typed provider adapters, deterministic score, source provenance, human approval, dry-run, and idempotency.
6. Recommend `study only`, `reimplement`, `adapt`, or `reject`, with reasons.
7. If adapting code, preserve required notices and update `docs/THIRD_PARTY_NOTICES.md`.
8. Do not copy secrets, PII, or test data containing real people.
9. Report what was inspected and what was not verified. Never imply a full audit from a README-only review.

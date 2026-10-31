---
name: build-vertical-slice
description: Implement one approved Trigger Point feature end-to-end with tests, validation, and documentation. Use when building or modifying product code.
---

# Build One Vertical Slice

1. Read `CLAUDE.md` and the relevant product/architecture docs.
2. State the user outcome, acceptance criteria, failure modes, and out-of-scope work.
3. Inspect existing code before editing.
4. Write a failing test for the core behavior and at least one edge case.
5. Implement the smallest typed change that passes.
6. Add structured errors and observability; do not swallow provider failures.
7. Run targeted tests, type checks, formatters and linters available in the project.
8. Inspect the diff for secret leakage, unsafe external actions, and changes to policy boundaries.
9. Update documentation if behavior or contracts changed.
10. Report exact commands and actual results. Do not claim checks passed unless executed.

## Trigger Point-specific checks
- Facts have evidence; hypotheses are labeled.
- Score is computed by deterministic code.
- External sends are disabled by default.
- Live/replay mode is explicit.
- Missing data stays unknown.
- Every action has a run ID and audit trail.

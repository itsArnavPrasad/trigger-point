# Claude Code + Superpowers Setup

## 1. Install and open the project
Install Claude Code using the official instructions for your operating system. Open a terminal in the Trigger Point project root and start Claude Code there so project instructions are discoverable.

## 2. Install Superpowers
Inside Claude Code, use the official marketplace command documented by the Superpowers project:

```text
/plugin install superpowers@claude-plugins-official
```

If the official marketplace is unavailable, use the alternate marketplace flow in the current Superpowers README:
```text
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

Restart or open a fresh session if the plugin requires it, and confirm installed plugins/skills using the current Claude Code UI/commands. Installation commands may change; follow the upstream README.

Reference: https://github.com/obra/superpowers

## 3. Install the official Crustdata skills
In Claude Code:
```text
/plugin marketplace add crustdata/skills
/plugin install crustdata@crustdata-plugin
```
Confirm the current upstream README before installing. The skills are a reference and a productivity layer; Trigger Point's backend must still implement its own typed provider adapter, deterministic score, persistence, verifier, and approval gate.

Reference: https://github.com/crustdata/skills

## 4. Optional Anthropic Sales plugin
```text
/plugin marketplace add anthropics/knowledge-work-plugins
/plugin install sales@knowledge-work-plugins
```
Use this for skill design inspiration and supported connected workflows. It is not a substitute for Trigger Point's product runtime.

Reference: https://github.com/anthropics/knowledge-work-plugins/tree/main/sales

## 5. Use Claude Code's mechanisms intentionally
Missions start from Trigger Point Office, which runs `claude --agent mission-director`. Agents are in `.claude/agents/`; project hooks report to the Office and hold approvals. Accept the workspace trust dialog once.
- `CLAUDE.md`: durable project-wide invariants and links to docs.
- `.claude/skills/*/SKILL.md`: repeatable workflows with scoped instructions.
- `.claude/rules/`: optional path-specific rules when a directory needs extra constraints.
- Hooks: automate checks such as formatting/tests or block unsafe actions, but keep hooks small and deterministic.
- Subagents: use for bounded parallel review (e.g., architecture, security, tests); do not delegate the single source of truth for core schema or scoring.
- MCP: typed access to Trigger Point actions and external data; keep critical production paths on validated adapters.
- Hooks are telemetry and controls, never the workflow engine or a database. Check hook names against the installed CLI.

Official guidance: https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more

## 6. Recommended working loop
For each vertical slice:
1. Ask Superpowers to clarify the task and write an implementation plan.
2. Define acceptance criteria and a failing test first.
3. Implement the smallest slice.
4. Run targeted tests, type checks, and lint.
5. Ask for a separate code review of correctness, security, and edge cases.
6. Inspect the diff yourself.
7. Update docs only when behavior actually changed.

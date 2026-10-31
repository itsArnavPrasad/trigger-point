# Trigger Point

An evidence-first GTM operating system. Give it a website and a revenue goal. It works out who to sell to, why they may need the product now, how to reach them, what happened, and what to improve next.

**Core rule:** every account must answer **Why this account? Why this person? Why now? Why us?** with evidence, or be rejected with a reason.

**Trigger Point Office** is the only UI: a live control room where real Claude Code agents do the work. Click a character to open its dashboard. Nothing moves unless real work happened.

## What works
| Works | On fixtures only | Not built |
|---|---|---|
| Live website reading, sourced profile, strategy, versioned ICP | Crustdata accounts, signals and people (needs a key) | Wispr Flow meeting import |
| Human approvals held in the Office | Case files and scores on live accounts | CRM sync |
| Verified outreach per audience | | Reply reading and scheduled sending |
| Gmail and Calendar, **test inbox only** | | Outside market research |

Current status, item by item: [docs/GTMO_AUDIT_REPORT.md](docs/GTMO_AUDIT_REPORT.md).

## Requirements
| Tool | Used for | Install |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python 3.12 and packages | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Node.js](https://nodejs.org/) with npm, 20 or later | Building the Office UI | nodejs.org |
| `python3` on `PATH` | Claude Code hooks (standard library only) | Included on macOS and most Linux |
| [Claude Code](https://code.claude.com/docs) | Running missions | Needed for agents, not for tests |

No API keys are needed for the tests or the fixture demo.

## Quick start: fixture demo
```bash
git clone https://github.com/anmolsureka30/whynoww.git
cd whynoww
uv sync
cp .env.example .env
scripts/office.sh --fixture
```
The script builds the UI, starts the API on `127.0.0.1:8000` and opens the page with its access token. The token is stored at `~/.trigger-point/office-token` with mode `0600`.

To run missions, first start `claude` once in this folder. Accept the workspace trust dialog and approve the `trigger_point` MCP server. Claude Code ignores project permissions, hooks and the server until you do.

1. Click **New mission**, enter `supportpilot.example` and a goal.
2. Answer the Mission Director in chat.
3. Click **Approve** on each card in **Needs you**.
4. Click a character to see its dashboard.

Every screen is labelled as fixture data. `supportpilot.example` is the synthetic site with recorded data.

## Live setup
Edit `.env`. API keys always come from `.env`. Modes can be overridden from the shell.

| Variable | Needed for | Notes |
|---|---|---|
| `WEB_MODE` | Reading real websites | `live` or `replay`. No key needed |
| `LLM_MODE` | Real extraction and drafting | `live` needs `HYDE_INFERENCE_API_KEY` |
| `HYDE_INFERENCE_API_KEY`, `HYDE_BASE_URL`, `LLM_MODEL` | Hyde gateway | Defaults in `.env.example` |
| `CRUSTDATA_MODE` | Real accounts, signals and people | `live` needs `CRUSTDATA_API_KEY` |
| `CRUSTDATA_API_KEY` | Crustdata | From your Crustdata account |
| `CRUSTDATA_API_VERSION` | Crustdata | Keep the value in `.env.example` |
| `CRUSTDATA_RUN_CREDIT_BUDGET` | Spend cap per run | Default 5. Fails closed |
| `DATABASE_URL` | Storage | Default `sqlite:///./trigger_point.db` |
| `TRIGGER_POINT_TEST_RECIPIENTS` | Test email and invites | Comma-separated. Empty blocks everything |
| `ENABLE_EMAIL_SEND`, `ENABLE_LINKEDIN_SEND` | Safety switches | Must stay `false`. `true` stops startup |
| `TRIGGER_POINT_HOME` | Token location | Optional. Default `~/.trigger-point` |

Then run:
```bash
scripts/office.sh
```
Without a Crustdata key, a live mission reads the site and builds the strategy and ICP, then stops at discovery with a clear retryable error. The header shows **PART FIXTURE** whenever modes are mixed.

## Connect Claude Code
Everything is in the repo, and no paths need editing:

| File | What it does |
|---|---|
| `.mcp.json` | Registers the `trigger_point` MCP server (`uv run python -m trigger_point.mcp_server`) |
| `.claude/settings.json` | Tool permissions and hooks |
| `.claude/agents/` | Mission Director and seven specialists |
| `scripts/office_hook.py` | Telemetry, held approvals and the send guard |

Check the connection:
```bash
claude mcp list          # trigger_point should show Connected, not Pending approval
```
The **Integrations** page in the Office shows the same list.

## Test email and calendar
Sending works only through Claude Code's Gmail and Google Calendar connectors, and only to `TRIGGER_POINT_TEST_RECIPIENTS`.

1. Connect Gmail and Google Calendar in your claude.ai connector settings.
2. Set `TRIGGER_POINT_TEST_RECIPIENTS=you@example.com` in `.env`, then restart the Office.
3. On the **Outreach** page, add sample targets and write messages. Samples are named `SAMPLE` and are never contacted.
4. Click **Send to test inbox**, then approve the card.
5. Click **Book test meeting** on the **Meetings** page, then approve the card.

The hook denies any other recipient, and a failure in the guard also denies. Check the spam folder: mail from a personal Gmail account can land there. Real outreach needs an authenticated company domain.

## Commands
```bash
uv run pytest                         # Python tests, offline
uv run ruff check . && uv run mypy    # lint and types
uv run python -m evals.run_evals      # deterministic evals
cd office && npm test                 # UI tests
cd office && npm run build            # type-check and build the UI
```

## Project layout
```text
.claude/        agents, skills, permissions, hooks
docs/           spec, audit, roadmap, architecture, policies
evals/          deterministic evaluation cases
fixtures/       recorded data for replay mode
office/         Trigger Point Office UI (React, Vite)
scripts/        office.sh, office_hook.py, fixture tools
src/trigger_point/     core: web, context, mission, research, scoring, cases,
                drafts, workflow, office API, MCP server
tests/          Python tests
```

## Documentation
| Read | For |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Rules for anyone changing this code |
| [docs/GTM_OS_PRODUCT_SPEC.md](docs/GTM_OS_PRODUCT_SPEC.md) | The target product |
| [docs/GTMO_AUDIT_REPORT.md](docs/GTMO_AUDIT_REPORT.md) | What is true today |
| [docs/GTMO_IMPLEMENTATION_ROADMAP.md](docs/GTMO_IMPLEMENTATION_ROADMAP.md) | Build order |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it fits together |
| [docs/GTMO_OFFICE_UI_PLAN.md](docs/GTMO_OFFICE_UI_PLAN.md) | How the Office works |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | Features, limits and decisions |
| [docs/DEMO_PLAN.md](docs/DEMO_PLAN.md) | Demo script |
| [docs/CLAUDE_CODE_SETUP.md](docs/CLAUDE_CODE_SETUP.md) | Optional plugins and working loop |
| [docs/CLAUDE_HYDE_OPERATOR.md](docs/CLAUDE_HYDE_OPERATOR.md) | The LLM gateway |
| [docs/OUTREACH_POLICY.md](docs/OUTREACH_POLICY.md) | Rules for external action |
| [docs/EVIDENCE_AND_VERIFICATION.md](docs/EVIDENCE_AND_VERIFICATION.md) | Evidence rules |
| [docs/THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md) | Licences |

## Troubleshooting
| Symptom | Fix |
|---|---|
| Page says the token is missing | Open the link printed by `scripts/office.sh` |
| Port 8000 is in use | Stop the other process. The Office uses this port |
| Agents do nothing, or every tool is denied | Run `claude` once here and accept the trust dialog |
| `trigger_point` shows Pending approval | Run `claude` here and approve the server |
| `trigger_point` fails to connect | Run `uv sync`, then `claude mcp list` from this folder |
| A live mission stops at discovery | Add `CRUSTDATA_API_KEY` and set `CRUSTDATA_MODE=live` |
| `replay_missing` | Fixture mode has no recording for this site. Use `supportpilot.example` |
| Startup fails with a send error | Set `ENABLE_EMAIL_SEND` and `ENABLE_LINKEDIN_SEND` to `false` |
| Test email is blocked | Add the address to `TRIGGER_POINT_TEST_RECIPIENTS` and restart |

## Safety rules
- Real recipients cannot be contacted. Outreach stays draft-only outside the test inbox.
- Every approval binds the exact content. Editing the text cancels it.
- Unknown stays unknown. Nothing invents a person, signal, source or proof point.
- Scores are computed by deterministic code, never by a model.
- The API binds to loopback and is not safe to host.
- Never commit `.env`, keys, personal contact data or real prospect exports.

## Licence
Office art comes from [Claude Office](https://github.com/W17ant/Claude-Office) under the MIT licence. See [docs/THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md).

# Trigger Point

<img src="office/public/art/logo.png" alt="Trigger Point logo" width="120" />

An evidence-first GTM operating system. Give it a website and a revenue goal. It works out who to sell to, why they may need the product now, how to reach them, what happened, and what to improve next.

**Core rule:** every account must answer **Why this account? Why this person? Why now? Why us?** with evidence, or be rejected with a reason.

**Trigger Point Office** is the only UI: a live control room where real Claude Code agents do the work. Click a character to open its dashboard. Nothing moves unless real work happened.

## What works
| Works | On fixtures only | Not built |
|---|---|---|
| Live website reading, sourced profile, strategy, versioned ICP | Case files and drafts on live accounts, which need a why-now signal | Client-rendered sites |
| Human approvals held in the Office, live Crustdata discovery and people search | | CRM sync |
| Verified outreach, sequences and schedules | | Sending to real recipients |
| Gmail and Calendar, **test inbox only** | | Outside market research |
| Reply reading and Wispr Flow meeting import | | |
| The improvement loop, shown on the Learnings page | | |

Current status, item by item: [docs/GTMO_AUDIT_REPORT.md](docs/GTMO_AUDIT_REPORT.md).

## How to run

### 1. What you need
| Tool | Used for | Install |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python 3.12 or newer and the packages (uv finds or installs the Python for you) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Node.js](https://nodejs.org/) 20 or later, with npm | Building the Office screen | nodejs.org |
| [Claude Code](https://code.claude.com/docs) | Runs the agents | The `claude` command must be a real program on your `PATH`. A shell alias is not enough, because the Office starts it itself. Check with `which claude` |
| `python3` | Claude Code hooks (standard library only) | Included on macOS and most Linux |

You need no API keys for the tests or the demo. Real data needs the keys in [Run with real data](#run-with-real-data).

### 2. One-time setup
```bash
git clone https://github.com/itsArnavPrasad/trigger-point.git
cd trigger-point
uv sync                  # Python and the packages
cp .env.example .env     # settings. The demo needs no keys
claude                   # run once in this folder, accept the prompts below, then type /exit
```
Claude Code ignores this project's permissions, hooks and tools until you accept two prompts the first time you start it here: the **workspace trust** dialog, and **approve the `trigger_point` server**. Check it worked:
```bash
claude mcp list          # trigger_point should say Connected, not Pending approval
```

### 3. Start the Office
```bash
scripts/office.sh --fixture   # demo: recorded data, no keys, no credits
scripts/office.sh             # real data, as set in .env (see Run with real data)
```
- The first run installs the UI packages and builds the screen, which takes a little while. Later starts are quick.
- Your browser opens at `http://127.0.0.1:8000/#token=...`. If it does not (non-macOS, or `TRIGGER_POINT_NO_OPEN=1`), copy the link the script prints. The token is kept in `~/.trigger-point/office-token`.
- Leave the terminal open. Press **Ctrl+C** to stop.
- **Restart it after you change `.env` or pull new code.** The server does not pick changes up while it runs. The screen is rebuilt for you when its source changed.
- Everything is saved in `trigger_point.db` in this folder. To start completely fresh, stop the Office and delete that file.

### 4. First open: connect your tools
When you open the Office in a new tab, a **Connect your tools** window appears if something is missing:

| Tool | Needed? | What it does |
|---|---|---|
| Gmail | Yes | Sends your approved test emails and reads the replies |
| Google Calendar | Yes | Finds your free times and books test meetings |
| Wispr Flow | **Optional** | Reads meeting transcripts for you. Press **Skip** if you would rather paste transcripts yourself |

**Connect** opens Claude's connector settings (claude.ai, Settings, Connectors). Connect the tool there, come back and press **Check again**. The first check takes about 10 seconds. You can reopen the window any time from **Integrations, Connect tools**. Skipping Wispr is remembered in your browser. The demo's research steps work without any of these; test emails and test meetings need Gmail and Calendar.

### 5. Run a mission
1. On first open you see the start form. Enter a website and a goal. For the demo use `supportpilot.example`, the synthetic site with recorded data. Later missions: the **three dots** on the top card, then **New mission**.
2. Open **Chat** (top right) and answer the Mission Director's questions.
3. When a step needs you, a card appears under **Needs you**. Read it, then **Approve** or **Deny**. Nothing spends credits or goes out without this click.
4. Look around: the sidebar has a page for each stage, **Live office** shows the agents working, and **Switch to agent mode** gives a quiet view of just your meetings, what to prepare, and a chat.

Every screen is labelled as fixture data when it is. A mission started with real data is labelled **LIVE**, or **PART FIXTURE** when modes are mixed.

## Run with real data
1. Get a Hyde key and a Crustdata key. Crustdata contact lookups (email and phone) need a key with contact access.
2. In `.env`, set the three modes to `live` and add the keys, using the table below.
3. Raise `CRUSTDATA_RUN_CREDIT_BUDGET` (default 5) to what you are happy to spend per run. Contact lookups cost about 3 credits per person it can match.
4. Set `TRIGGER_POINT_TEST_RECIPIENTS` to your own address, so test emails have somewhere safe to go.
5. Run `scripts/office.sh` and start a mission with your own website.

API keys always come from `.env`. Modes can be overridden from the shell.

| Variable | Needed for | Notes |
|---|---|---|
| `WEB_MODE` | Reading real websites | `live` or `replay`. No key needed |
| `LLM_MODE` | Real extraction and drafting | `live` needs `HYDE_INFERENCE_API_KEY` |
| `HYDE_INFERENCE_API_KEY`, `HYDE_BASE_URL`, `LLM_MODEL` | Hyde gateway | Defaults in `.env.example` |
| `CRUSTDATA_MODE` | Real accounts, signals and people | `live` needs `CRUSTDATA_API_KEY` |
| `CRUSTDATA_API_KEY` | Crustdata | From your Crustdata account |
| `CRUSTDATA_API_VERSION` | Crustdata | Keep the value in `.env.example` |
| `CRUSTDATA_RUN_CREDIT_BUDGET` | Spend cap per run | Default 5. Fails closed. Raise it to cover contact lookups |
| `CRUSTDATA_FETCH_CONTACTS` | Buy email and phone for the buyers found | Live mode only, default `true`. Needs a key with contact access |
| `DATABASE_URL` | Storage | Default `sqlite:///./trigger_point.db` |
| `TRIGGER_POINT_TEST_RECIPIENTS` | Test email and invites | Comma-separated. Empty blocks everything |
| `ENABLE_EMAIL_SEND`, `ENABLE_LINKEDIN_SEND` | Safety switches | Must stay `false`. `true` stops startup |
| `TRIGGER_POINT_HOME` | Token location | Optional. Default `~/.trigger-point` |

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

## Autopilot

Autopilot is on by default. It answers the approval prompts your policy covers, chooses who to contact, writes and sends the first message, reads replies, and books a Google Meet when someone says yes. If someone says no it records why on the dashboard. Pause it or open **Settings** on the dashboard to change the credit cap, meetings wanted, meeting length and meeting hours (India time, Monday to Friday). It reads your Google Calendar first, so it never offers or books a time that clashes with something else. Strategy and learning decisions always stay with you.

`OUTREACH_MODE=demo` (default) stores the real emails Crustdata finds but sends every message to `TRIGGER_POINT_TEST_RECIPIENTS`. Set your own address there in `.env`. `OUTREACH_MODE=live` with `ENABLE_EMAIL_SEND=true` sends to the real person; it is unverified, so flip it only on purpose.

## Test email and calendar
Sending works only through Claude Code's Gmail and Google Calendar connectors, and only to `TRIGGER_POINT_TEST_RECIPIENTS`.

1. Connect Gmail and Google Calendar (the first-open window, or **Integrations, Connect tools**).
2. Set `TRIGGER_POINT_TEST_RECIPIENTS=you@example.com` in `.env`, then restart the Office.
3. On the **Outreach** page, click **Add sample targets**, then write a message for one. Samples are named `SAMPLE` and are never contacted.
4. Click **Send to test inbox**, then approve the card under **Needs you**.
5. Still on **Outreach**, click **Book a test meeting**, then approve the card.

The hook denies any other recipient, and a failure in the guard also denies. Check the spam folder: mail from a personal Gmail account can land there. Real outreach needs an authenticated company domain.

## Replies, meetings and the improvement loop
Wispr Flow is optional. Connect it the same way as Gmail (first-open window, or **Integrations, Connect tools**), or skip it and type or paste meeting notes yourself on the **Meetings** page.

- **Check replies** (Outreach page) reads each sent thread. Opt-outs and bounces are handled by rule. Whether someone is interested is your click.
- **Import from Wispr Flow** (Meetings page) reads relevant meetings. A customer statement counts only if its quote is found in the transcript. Everything else waits in **Needs your review**.
- **Review what we learned** (Learnings page) finds what repeats across sources.
- **Plan the next campaign** (Learnings page) turns what repeats into one proposal: ICP and messaging changes, each citing its evidence, and the next campaign to run. A change with two or more sources can become a lesson. A change with one source is labelled an experiment and is tested, not taught. Approving the plan makes one strategy version and one experiment; nothing is sent by the plan itself.

Each read is held as a card for your click. To run reads without clicking, add these to `permissions.allow` in `.claude/settings.json`: `mcp__claude_ai_Gmail__get_thread`, `mcp__claude_ai_Wispr_Flow__search_meetings`, `mcp__claude_ai_Wispr_Flow__get_meeting`, `mcp__claude_ai_Wispr_Flow__get_meeting_by_calendar_id`, and the `mcp__trigger_point__` tools `list_open_threads`, `sync_replies`, `import_meeting`, `add_meeting_insights`, `get_learning_inputs`, `propose_lesson`, `write_follow_up`.

**The loop:** capture, link, extract, check, propose, approve, version, measure, then keep or roll back. Approving a change creates a strategy version that new messages, strategy and ICP work receive. One target in five stays out as a comparison group.

**What teaches:** real meetings, and messages you mark **I sent this myself**. Test sends never teach. To see the whole loop, run a fixture mission and use **Add demo results**; those results stay in that mission.

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
| `claude` not found, or agents never start | `which claude` must print a path. A shell alias is invisible to the Office. Put the real program on your `PATH` |
| The connect window says a tool is missing, but it is connected | The first check takes about 10 seconds. Press **Check again**, or run `claude mcp list` in a terminal to see the truth |
| I closed the connect window | **Integrations, Connect tools** opens it again |
| I cannot find a New mission button | It is in the **three dots** menu on the top card of the Dashboard |
| The page looks old after pulling new code | Stop the Office and run `scripts/office.sh` again. It rebuilds the screen when the sources changed
| Port 8000 is in use | Stop the other process. The Office uses this port |
| Agents do nothing, or every tool is denied | Run `claude` once here and accept the trust dialog |
| `trigger_point` shows Pending approval | Run `claude` here and approve the server |
| `trigger_point` fails to connect | Run `uv sync`, then `claude mcp list` from this folder |
| A live mission stops at discovery | Add `CRUSTDATA_API_KEY` and set `CRUSTDATA_MODE=live` |
| Every account is rejected with `no_fresh_why_now` | The market has no signal Crustdata can see. Schools have no job postings. See `docs/CRUSTDATA_INTEGRATION.md` |
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

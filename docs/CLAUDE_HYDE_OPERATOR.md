# LLM Gateway: Hyde and GLM 5.3 Flash

Trigger Point's bounded structured steps run on GLM 5.3 Flash through the Hyde inference gateway. Claude Code runs the workflow itself and does not need Hyde.

- **Trigger Point's code owns the pipeline:** fetching, grounding, budgets, scoring, storage and approval gates.
- **Each judgment step is one bounded GLM call:** extraction, strategy, ICP and drafts, behind `StructuredLlm`.
- **Replay needs no key.** Set `LLM_MODE=replay`.

## Setup
Add to `.env`:
```bash
LLM_MODE=live
HYDE_INFERENCE_API_KEY=your-key
HYDE_BASE_URL=https://inference.hyde.tech/v1
LLM_MODEL=hyde/glm-5.3-flash
```

## Optional: run Claude Code itself on Hyde
Create a separate Claude Code profile, so your normal profile is untouched:

1. In `~/.claude-hyde/settings.json`, set `ANTHROPIC_BASE_URL=https://inference.hyde.tech` and `model: hyde/glm-5.3-flash`, and route the model aliases to GLM.
2. Add an `apiKeyHelper` script that prints your key from a file with mode `600`.
3. Add `alias claude-hyde='CLAUDE_CONFIG_DIR=~/.claude-hyde claude'` to your shell profile.
4. Start `claude-hyde` once in this folder and accept the trust prompt.

Check it:
```bash
claude-hyde -p "Reply with exactly: pong"
```
A `[claude-code:unrecognized_model]` warning is expected for a gateway-only model.

## Modes
Modes come from `.env`, and the shell can override them. API keys always come from `.env`.

| Setup | Settings | Notes |
|---|---|---|
| Live website and GLM, Crustdata replay | `WEB_MODE=live LLM_MODE=live` | Real sites will not match recorded Crustdata data, so discovery reports `replay_missing`. That is honest, not a bug |
| Full replay, no network | `scripts/office.sh --fixture` | Use `supportpilot.example` |
| Fully live | add `CRUSTDATA_API_KEY`, set `CRUSTDATA_MODE=live` | Spend is capped by `CRUSTDATA_RUN_CREDIT_BUDGET` |

To capture live Crustdata responses as fixtures, set `CRUSTDATA_RECORD_DIR=fixtures/replay/crustdata` while running live. Review the files before committing them.

## Measured performance
| Task | Result |
|---|---|
| Context extraction, strict JSON schema, SupportPilot fixture | 19 s, 15/15 facts quote-verified |
| Same, forced tool call | 176 s, 23/23 verified (slower, so Trigger Point uses JSON schema) |
| Context extraction live on plausible.io (8 pages) | 25 s for the LLM step |
| Mission compile live | 7 s, valid plan |
| First-touch drafts on replayed cases | 3 to 5 s each, 3/3 verified on the first attempt |
| Strategy step live | 23 s, valid against the schema |

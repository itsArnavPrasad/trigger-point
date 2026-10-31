# Open-Source Research: What to Clone and What to Learn

Repositories and licenses can change; re-check the current `LICENSE`, dependencies, and recent commits before reusing code. A clone is for inspection, not automatic permission to copy or ship.

## Priority 0 — clone first

### 1. Crustdata Skills
Repo: https://github.com/crustdata/skills
Why first: official workflows for sales prospecting, account research, ICP building, warm-path deal workspace, and sales outreach. Best reference for Crustdata tool usage, source selection, freshness limits, and practical workflow phrasing.
Inspect:
- `skills/sales-outreach/SKILL.md`
- `skills/sales-prospecting/`
- `skills/account-research/`
- `skills/icp-builder/`
- `skills/warm-path-deal-workspace/`
- connector/MCP configuration and provider error handling
Borrow: workflow structure, endpoint selection, freshness rules, source hierarchy, and prompt constraints.
Do not assume the skills provide your database, UI, scoring, claim verifier, or complete campaign runtime.
License: repository currently identifies MIT; verify the checked-out license before copying.

### 2. Outbound Intelligence Engine
Repo: https://github.com/Kazemkhani/outbound-intelligence-engine
Why second: closest architectural reference for deterministic scoring, dated signals, enrichment waterfall, provider adapters, dry-run, human approval, idempotency, suppression, and audit trail.
Inspect:
- normalized domain schemas and provider adapters
- deterministic scoring and signal decay
- send gate and action approval
- recorded fixtures / offline tests
- architecture/security docs and evaluation harness
Borrow: system boundaries and safety invariants; use as a reference implementation, not a dependency.
License: repository currently says Apache-2.0; preserve notices and verify.

## Priority 1 — inspect next

### 3. YALC 1.0
Repo: https://github.com/Othmane-Khadri/YALC-the-GTM-operating-system
Why: website-first onboarding, generated GTM framework, markdown-owned qualification rules, provider abstraction, skills, intelligence store, and Crustdata adapter. Especially relevant to the exact "paste website → understand business" onboarding idea.
Inspect:
- onboarding and framework synthesis
- Crustdata provider and provider contracts
- qualification and outbound validation
- skills architecture
- campaign outcome/intelligence store
Important: YALC's README says it is CLI-first and its codebase includes several provider dependencies. Do not pull the full stack into the MVP without a reason.
License: repository currently says MIT; verify.

### 4. Anthropic Knowledge Work Plugins — Sales
Repo: https://github.com/anthropics/knowledge-work-plugins
Why: official examples of reusable sales skills: account research, lead triage, stakeholder maps, outreach, CRM updates, pipeline review. Excellent reference for Claude skill design and approval-first workflows.
Inspect: `sales/README.md`, `sales/skills/`, plugin instructions and connector docs.
Borrow: skill boundaries, plain-language entry points, asking only for missing context, and presenting proposed actions before writing.
License: repository currently says Apache-2.0; verify.

### 5. OpenGTM
Repo: https://github.com/buildingopen/opengtm
Why: useful end-to-end GTM pipeline decomposition: discover → research → qualify → message → sequence → sync, plus website/AEO context.
Inspect: pipeline modules, ICP scoring, message frameworks, tests, and license.
Borrow: small modular pipeline and CLI workflow. Treat its website/audit heuristics as a source of ideas, not truth.
License: repository currently says MIT; verify.

## Priority 2 — selective inspection

### 6. Superpowers
Repo: https://github.com/obra/superpowers
Why: development workflow, not GTM runtime. Use its brainstorming, planning, test-driven development, debugging, and code-review skills in Claude Code.
Install as a Claude Code plugin rather than copying the plugin's source into the application repo unless developing the plugin itself.
License: check current repo license and plugin terms.

### 7. TREG
Repo: https://github.com/superdesigndev/treg
Why: reference for a tool registry, per-call routing/cost visibility, and lead-signals workflow.
Caution: the repository's current license includes additional terms restricting use to provide hosted/managed/embedded services to third parties without written authorization. **Do not copy it into a commercial SaaS or make it a core dependency without legal review and permission.** For Trigger Point, implement a simple internal tool registry/cost ledger first.

### 8. LangGraph
Repo: https://github.com/langchain-ai/langgraph
Why: durable stateful workflows, checkpoints, human-in-the-loop and resumability.
Use only if the simple pipeline becomes difficult to manage. It is not required for the initial MVP.

### 9. Firecrawl
Repo: https://github.com/firecrawl/firecrawl
Why: reference/option for website crawling and content extraction. Start with bounded HTTP fetch and parsing if that is sufficient; add a crawler when JavaScript-rendered sites, crawling breadth, or extraction quality requires it. Check self-hosting and provider requirements.

## Recommended clone order
1. `crustdata/skills`
2. `Kazemkhani/outbound-intelligence-engine`
3. `Othmane-Khadri/YALC-the-GTM-operating-system`
4. `anthropics/knowledge-work-plugins`
5. `buildingopen/opengtm`
6. `obra/superpowers` only if you need to inspect plugin internals; otherwise install it.
7. TREG only for a license-aware evaluation, not as a default dependency.

## Do not do this
- Do not clone ten repos and ask Claude to "merge them all."
- Do not copy code before reviewing licenses, security, dependencies, tests, and architecture.
- Do not import a full application because one module looks useful.
- Do not let a repository's README override this project's product requirements.
- Do not assume a repo's claimed benchmarks or outcomes are independently validated.

## Other references
- **Hermes Agent memory:** a reference for curated, reviewable memory only. Trigger Point learns from account, campaign, meeting, pipeline and revenue outcomes, not conversation history.
- **Wispr Flow MCP:** read-only meeting source. Search covers titles, summaries and notes, not transcripts. Tool names are not published; read them from a real connection.
- Other spec references are listed at the end of `docs/GTM_OS_PRODUCT_SPEC.md`.


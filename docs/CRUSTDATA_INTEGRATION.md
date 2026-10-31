# Crustdata Integration Plan

## Role in Trigger Point
Crustdata is the canonical identity and B2B signal data layer, not the product's decision engine. Trigger Point owns its normalized domain model, qualification policy, evidence verifier, campaign logic, state, and user experience.

## First checks
Before implementing endpoints, confirm which endpoints the hackathon/API key actually permits. Do not assume all features, datasets, contact fields, or live endpoints are enabled.

- API base URL and exact request/response schemas must come from current official docs.
- Authentication header: `authorization: Bearer <API_KEY>`.
- API version header shown in the brief: `x-api-version: 2025-11-01`.
- Check endpoint access and current credit rules at runtime where the account API supports it.
- Never hard-code a price table without timestamping it and allowing provider pricing to change.

## Recommended call sequence
1. **Company identify** from seller/prospect domain when useful; use identity resolution before costly enrichment.
2. **Company search** using a compiled ICP query and broad enough limits.
3. Normalize and deduplicate results by canonical provider ID/domain.
4. Apply deterministic hard filters and cheap fit rules.
5. **Company enrich** only the shortlist.
6. Collect signal evidence with Job Search, company fields, social posts, or live web search only where enabled and relevant.
7. **Person search** for the pain-owner persona; avoid defaulting to CEO.
8. Enrich only selected contacts; verify current role as supported by the available data.
9. Use Watchers only after the core run works; define baseline, trigger, webhook handling, and test event behavior.
10. Capture usage headers/receipts and persist raw response hashes plus normalized records.

## Provider implementation
Create `CrustdataClient` with typed methods and a `CrustdataProvider` adapter. Do not let LLM-generated URLs, arbitrary endpoint paths, or free-form request bodies reach the HTTP client. Expose only allowlisted methods with schema validation.

Suggested internal methods (match to official schemas during implementation):
- `identify_company(domain_or_url)`
- `search_companies(plan_filters, limit)`
- `enrich_company(provider_company_id, fields)`
- `search_people(company_id, persona_filters, limit)`
- `enrich_person(provider_person_id, fields)`
- `search_jobs(filters, limit)`
- `search_web(query)` / `fetch_web(url)` when supported
- `create_company_watcher(config)` and `create_person_watcher(config)` when supported
- `get_endpoint_access()` if available to the key

## Reliability
- Cache idempotent reads with endpoint-aware TTLs.
- Cap concurrency and implement 429 handling with exponential backoff and jitter.
- Distinguish no results from provider failure and endpoint not enabled.
- Validate response schema and preserve `updated_at`, source fields, and provider IDs.
- Store `X-Credits-Used` or equivalent usage metadata only when actually returned.
- Avoid retrying non-idempotent watcher-creation calls without an idempotency strategy.
- Never fabricate a credit estimate; mark it estimated and reconcile against actual usage.

## Proven live
- **Access:** `GET /account/endpoints` lists 35 endpoints, 12 enabled: company identify, search, enrich and autocomplete; person search, enrich and autocomplete; job search; social post search; web search and fetch; agent query.
- **Field limits:** `/company/identify` omits headcount and locations. `/person/search` omits first and last name, but `basic_profile.name` is returned.
- **Countries:** alpha-3 works (`IND`).
- **Person search:** `current` entries carry the company id, and one person can hold several.
- **Costs:** a 5-result company search with hiring and headcount groups estimated 2.15 and charged 1.15. Identify and empty job or web searches charged 0. Person search charged 0.23 per result, matching the estimate.
- **Identify:** an early-stage seller may have no match. Discovery continues.
- **Funding:** `/company/search` with `fields: ["basic_info", "funding"]` returns a real, dated `funding.last_fundraise_date` for a company that raised one (confirmed live for `crustdata.com`: a seed round of $12,000,000, with its date). It is a normal premium field group (0.2 credits per result received, same tier as `headcount` and `hiring`), not a separate paid enrich step as an earlier note in this file assumed. Trigger Point now requests it whenever a plan's `signal_types` includes `recent_funding`, and `research/signals.py` turns it into a dated `recent_funding` signal, not an "as of" metric. See `docs/PROJECT_STATUS.md` for why the ICP Strategist does not always choose it correctly yet.

**Coverage limit for schools.** Eleven Mumbai schools had 0 job postings at any date and no funding round (expected: schools do not raise venture funding). A `news` web search for one school returned no results. Web and news results have no date field, so a result proves no event date on its own: `start_date` narrows the search, and a date would have to come from fetching the page. This is a real data-coverage limit for this vertical, not a bug: Crustdata's dated signals (hiring, funding) are built for venture-backed and larger organisations. The mission prompt (`mission/prompt.py`) now tells the ICP Strategist to leave `signal_types` empty, rather than guess, when none plausibly applies to the stated buyer type.

**Proven live, 31 October 2026** (through the adapter, `x-api-version: 2025-11-01`):
- **Endpoint probe, identify, company search and post search all work live** on this account.
- **The merged industry+place filters return real schools.** `locations.headquarters (.) Mumbai` AND `basic_info.industries in ["Primary and Secondary Education"]` returned Dhirubhai Ambani International School and JBCN Borivali among 5 results, charged 1.15 credits (estimate 2.15).
- **Post search is billed per post, not per request:** 10 posts cost 5 credits (0.5 each). A people-first run must budget by result count, not calls.
- **Precision gaps found live, to fix in discovery:**
  - The `(.)` fuzzy place filter leaks other countries: a Dubai school appeared in the Mumbai filter results. Filter results need a post-filter country/city check on the returned record, not trust in the filter alone.
  - Post search with `actor.location.city (.) Mumbai` + `text (.) edtech` returns recruiters, sales-hiring posts and UAE founders. Employer type is not filtered by the API on posts, so buyer-vs-seller judgement on the returned records (author title and employer) has to happen in code.
  - `industries` on returned company records came back empty even when the filter matched on `basic_info.industries`; do not rely on it as a returned field — use the filter for matching and basic_info `description`/name for display.

## Social posts (`/social_post/search`)
Used for the `topic_engagement` signal: people at an account publicly posting about a topic.

- **Billing:** 0.5 credits per post returned. An empty result and `limit: 0` cost nothing, and `limit: 0` still returns `total_count`, so a count is free. The topic and date window go in the query, so only matching posts are billed.
- **Contract:** `filters`, `sorts: [{field, order}]`, `fields`, `limit` and `cursor` in; `{posts, next_cursor, total_count}` out. Operators are `=`, `in`, `=>` (not `>=`), `(.)` for all words and `[.]` for an exact phrase.
- **What a post carries:** a real `date_posted`, a public `share_url`, the text, and the author's title and employer **name**. It has no employer id. Author location is coarse (state and country, no city).
- **Reduced on purpose:** the adapter never requests names, headlines, reactors or comments. Evidence stores a role and an employer, not a person.
- **Entity matching:** each campus of a school chain is its own company, and its name carries the place. A name that merely contains the account's is another campus or the group page, so only an exact name counts (case, punctuation and "Pvt Ltd" aside). Two different schools with the identical name in different cities cannot be told apart.
- **Live finding:** a free count showed about 21,000 posts by Mumbai educators since the start of the year, and about 3,000 of them about AI, edtech or ChatGPT. Parents stating they are parents is thin: about 2,000 Mumbai posts, and only 46 about maths or tuition.
- **Company search precision:** a country-only search for schools returned jewellers and hospitality firms. Adding `basic_info.industries` returned schools only, and `locations.headquarters` text narrowed it to the city. Both cost nothing extra.

## REST vs MCP
**Status:** live. Identify, company search, job search and person search are proven through the adapter. Trigger Point does not use the Crustdata plugin MCP: agents have no route around the adapter.

Use direct REST for the demo's critical path because it gives deterministic calls, typed contracts, predictable errors, and explicit budgets. Crustdata's MCP server is useful for exploratory work and developer productivity, but an LLM-selected tool path should not be the only execution route for a judged workflow. MCP may be added as an optional adapter later.

## Official references
- API docs: https://docs.crustdata.com/
- Skills: https://github.com/crustdata/skills
- MCP docs: https://docs.crustdata.com/general/mcp
- Official sales outreach skill: https://github.com/crustdata/skills/tree/main/skills/sales-outreach
- Pricing: https://docs.crustdata.com/general/pricing.md
- Data updates: https://docs.crustdata.com/general/data-updates.md
- Watcher cross-dataset filters: https://docs.crustdata.com/watcher-docs/cross-dataset-filters.md

## Verified API facts (from docs.crustdata.com, API version `2025-11-01`)

These came from the public API reference pages, which embed the OpenAPI spec. The raw `openapi-specs/*.yaml` files redirect to a login page. Live checks below confirm the parts Trigger Point uses.

- **Base URL and headers.** Base URL is `https://api.crustdata.com`. Every request sends `authorization: Bearer <key>`, `x-api-version: 2025-11-01` and `content-type: application/json`. The version header is required; omitting it can float to a newer version.
- **Endpoints in use** (all `POST`):
  - `/company/identify`: free, 30 rpm.
  - `/company/search`: 0.03 credits per result plus premium groups, 30 rpm.
  - `/company/enrich`: 2–4 credits per record.
  - `/person/search`: 0.03 credits per result plus premium groups.
  - `/job/search`: 0.03 credits per result.
  - `/web/search/live` and `/web/enrich/live`: 1 credit each.
  - `GET /account/endpoints` (**free**): per-endpoint `status` (enabled/disabled), enabled and disabled response fields, `effective_rate_limit_rpm` and `base_credits`. This is the capability probe to run before planning a run.
  - `GET /account/credits`: free.
- **Identify.**
  - The body takes exactly one of `names | domains | crustdata_company_ids | professional_network_profile_urls`, with 1–25 values, plus optional `exact_match` and `fields` ⊂ {`crustdata_company_id`, `basic_info`, `social_profiles`}.
  - The response is a top-level array of `{matched_on, match_type, matches:[{confidence_score, company_data:{crustdata_company_id, basic_info{…}}}]}`.
  - No match is a 200 response with `matches: []`. That is distinct from an error.
  - **One exact domain can return several records with `confidence_score: 1`.** The documented example is `cashfree.com`, which returns the parent plus two showcase pages. Identity resolution must therefore treat more than one top-confidence match as *ambiguous*, not pick the first.
- **Search filters.**
  - Filters are `{field, type, value}` or `{op: and|or, conditions:[…]}`.
  - Operators are `=`, `!=`, `<`, `=<`, `>`, `=>`, `in`, `not_in`, `is_null`, `is_not_null`, `(.)` (fuzzy) and `[.]` (exact token). Note `=<` and `=>`, **not** `<=` and `>=`.
  - Optional `search: {query, mode: hybrid|lexical|semantic}` takes the natural-language ICP. When combined with ranked search, filters act as hard constraints.
  - Cursor pagination. Ranked search pages hold at most 100 results, and its cursors expire after 20 minutes.
  - `total_count` is always null for ranked search.
  - A requested group with no data comes back as `null`.
- **Company search signal fields.**
  - `hiring.openings_count` and `hiring.openings_growth_percent`.
  - `headcount.growth_percent.{1m,3m,6m,12m}`.
  - `roles.growth_6m.customer_success_and_support`.
  - `funding.last_fundraise_date` and `funding.last_round_type`.
- **Job search.** `metadata.date_added` is the **job-posted date** (the event date). `metadata.date_updated` is the last refresh. No field says a posting is still open, so "currently hiring" must be phrased with `date_updated` as last-seen evidence.
- **Data freshness.** Indexed records are refreshed every 1–30 days, and each carries `updated_at`. Live endpoints are enterprise-only or an add-on.
- **Errors.**
  - The canonical shape is `{error:{type, message, metadata[]}}`, with `type` one of invalid_request, authentication_error, unauthorized, insufficient_credits, permission_error, rate_limit_error, internal_error.
  - 401 can instead be `{message}`, and the intro page shows `{error, description}`. **The adapter must parse all three shapes.**
  - 402 `insufficient_credits` (which also covers a per-key monthly cap) is terminal: do not retry.
  - 403 `permission_error` is terminal, but a 403 that names `denied_fields` can be retried once with a narrower `fields` list.
  - 429 should be retried after `x-ratelimit-reset` seconds plus jitter.
- **Headers.**
  - `X-Credits-Used` is a decimal string giving exact credits deducted. It is present on successes and errors, and **absent** on 429s generated before the request reaches the API.
  - `x-ratelimit-limit`, `x-ratelimit-remaining` and `x-ratelimit-reset` work on a sliding window.

### Notes
- `GET /account/endpoints` exists and is free.
- The YALC reference adapter uses legacy endpoints and `Token` auth. Do not use it as a schema reference (see `REPO_NOTES.md`).

### Job and Person search
- **`POST /job/search`**
  - Filter fields include `company.basic_info.company_id`, `job_details.title`/`category`, `metadata.date_added`/`date_updated`, `content.description`, and the posting-scoped `technographics.technologies.*` (values case-sensitive; discover with `/job/search/autocomplete`).
  - **Responses name the company id `company.basic_info.crustdata_company_id`.** Trigger Point reads both names.
  - `date_added` is the posting date (the event); `date_updated` is the last refresh. Nothing indicates whether a posting is still open.
  - 0.03 credits per result.
- **`POST /person/search`**
  - Filter on `experience.employment_details.current.company_id` / `.title` / `.seniority_level` / `.function_category`.
  - Responses carry `experience.employment_details.current[].crustdata_company_id`, `social_handles.professional_network_identifier.profile_url` and `metadata.updated_at`.
  - Price: 0.03 base plus 0.1 for filtering on `experience` plus 0.1 for receiving it, so 0.23 per result.
  - Trigger Point's search requests a fixed minimal field list and **never** contact data.
  - **Contact data is a separate paid step, not part of search.** It is `POST /person/contact/enrich` (docs: https://docs.crustdata.com/person-docs/contact/enrich): up to 25 `professional_network_profile_urls` per call and `fields` limited to `contact.*`, answered by a top-level array of `{matched_on, match_type, matches:[{confidence_score, person_data:{crustdata_person_id, contact}}]}`. Emails are `{email, status}` with status deliverable, catch_all, invalid or unknown; phones are strings. Price per matched person: business email 1, phone 2, personal email 2 (not requested), and +0.5 if `verified` is set (not set). People it cannot match are free. The page says enterprise plans only, and a self-serve key gets a 403. The docs give 15 requests per minute here, while the pricing page says 10 for live endpoints.
  - **Implemented, UNVERIFIED (no key has been available):** `CrustdataClient.enrich_contacts`, run inside the committee step for the buyers found, best match per account first, within `CRUSTDATA_RUN_CREDIT_BUDGET` (estimated at 3 credits per person). Live mode only; `CRUSTDATA_FETCH_CONTACTS=false` turns it off. A match is used only if its confidence is at least 0.99 and it does not name a different person than the one we asked about. A 403, an exhausted budget or any provider error is written to the run's notes and the run continues without contact details. The fixture recorder never writes `/person/contact*` responses.
  - If a person response carries a `contact` block (as an enrich response does), `normalise_person` reads it into `PersonRecord.contact`; malformed or duplicate values are dropped. The Office People page shows only the buttons a person has data for. Sources: https://docs.crustdata.com/general/pricing and https://docs.crustdata.com/person-docs/enrichment/introduction.
- **Company search `roles.*` fields are filter-only** (they cannot be selected). `hiring.*` can be returned but not filtered on.

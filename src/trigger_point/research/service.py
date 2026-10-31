"""Account research run: job postings -> signals -> preliminary score -> people for the top
accounts -> final score. Every provider call is budgeted and receipted; stages that cannot
run (budget, permission) are skipped with a visible note instead of guessed.

The two stages can run separately (`run_signals`, then `run_people`), so a workflow can report
each one when it actually happens, or together through `run`."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from trigger_point.mission.models import GTMPlan, Mission
from trigger_point.mission.service import CallRecord, DiscoveryRun
from trigger_point.models.context import Mode
from trigger_point.models.evidence import Evidence, evidence_id
from trigger_point.providers.crustdata.client import (
    CONTACT_CREDITS_PER_PERSON,
    JOB_CREDITS_PER_RESULT,
    PERSON_CREDITS_PER_RESULT,
    POST_CREDITS_PER_RESULT,
    CreditBudget,
    CrustdataClient,
)
from trigger_point.providers.crustdata.errors import CrustdataError
from trigger_point.providers.crustdata.models import (
    MAX_CONTACT_BATCH,
    Company,
    ContactEnrichRequest,
    ContactPoint,
    JobPosting,
    PersonRecord,
)
from trigger_point.research.jobs import compile_job_request
from trigger_point.research.people import (
    PersonaMatch,
    RejectedPerson,
    compile_people_request,
    match_people,
)
from trigger_point.research.posts import compile_post_request
from trigger_point.research.scoring import PeopleOutcome, ScoreBreakdown, rank, score_account
from trigger_point.research.signals import (
    Signal,
    signals_from_company,
    signals_from_postings,
    signals_from_posts,
    wants_postings,
)
from trigger_point.store.db import Store

PEOPLE_TOP_N = 5
JOBS_PER_ACCOUNT = 5
PEOPLE_PER_ACCOUNT = 3
POSTS_PER_ACCOUNT = 3
DEGRADABLE = {"budget_exceeded", "permission", "fields_denied"}


class ResearchFailed(RuntimeError):
    def __init__(self, message: str, research_id: str) -> None:
        super().__init__(message)
        self.research_id = research_id


class ResearchNotFound(LookupError):
    pass


class AccountResearch(BaseModel):
    account: Company
    signals: list[Signal]
    evidence: list[Evidence]
    tech_evidence_ids: list[str] = Field(default_factory=list)
    people_searched: bool
    best_person: PersonaMatch | None
    other_matches: list[PersonaMatch] = Field(default_factory=list)
    people_rejected: list[RejectedPerson] = Field(default_factory=list)
    score: ScoreBreakdown


class ResearchRun(BaseModel):
    id: str
    discovery_id: str
    mission_id: str
    mode: Mode
    initiated_by: str = "ui"
    reference_date: date
    started_at: datetime
    finished_at: datetime | None = None
    outcome: Literal["running", "completed", "failed"] = "running"
    accounts: list[AccountResearch] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    calls: list[CallRecord] = Field(default_factory=list)
    credits: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    stage: Literal["signals", "people"] = "people"
    signals_collected: bool = False


def _affordable(budget: CreditBudget, per_result: Decimal, wanted: int) -> int:
    return max(0, min(wanted, 100, int(budget.remaining / per_result)))


def _person_evidence(m: PersonaMatch, account: Company) -> Evidence:
    p = m.person
    return Evidence(
        id=evidence_id(
            "person", p.provider_person_id, account.provider_company_id, p.current_title
        ),
        entity_type="person",
        entity_id=str(p.provider_person_id),
        claim=f"{p.name or 'This person'} is {p.current_title or 'employed'} at "
        f"{account.name or 'the account'} (current employer verified by Crustdata company "
        f"id {account.provider_company_id}).",
        source_kind="provider_profile",
        source_url=p.profile_url,
        publisher="Crustdata",
        provider_ref=f"crustdata:/person/search:{p.provider_person_id}",
        as_of=date.fromisoformat(p.provider_updated_at[:10]) if p.provider_updated_at else None,
        retrieved_at=p.retrieved_at,
        excerpt=p.current_title,
    )


class ResearchService:
    def __init__(
        self,
        store: Store,
        client_factory: Callable[[CreditBudget], CrustdataClient],
        budget: float,
        reference_date: Callable[[], date],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        fetch_contacts: bool = False,
    ) -> None:
        self._store, self._factory, self._budget = store, client_factory, budget
        self._reference_date, self._clock = reference_date, clock
        self._fetch_contacts = fetch_contacts

    def get(self, research_id: str) -> ResearchRun:
        run = self._store.get_research(research_id)
        if run is None:
            raise ResearchNotFound(research_id)
        return run

    def run(self, discovery_id: str, initiated_by: str = "ui") -> ResearchRun:
        run, mission, discovery = self._start(discovery_id, initiated_by)
        budget = CreditBudget(self._budget)
        client = self._factory(budget)
        run.mode = client.mode

        def both() -> None:
            self._collect_signals(run, client, budget, mission, discovery)
            self._map_people(run, client, budget, mission)

        self._execute(run, client, budget, both, [])
        return run

    def run_signals(self, discovery_id: str, initiated_by: str = "ui") -> ResearchRun:
        """Job postings, signals and a preliminary score. No people search: reachability stays
        unknown until `run_people`."""
        run, mission, discovery = self._start(discovery_id, initiated_by)
        budget = CreditBudget(self._budget)
        client = self._factory(budget)
        run.mode = client.mode
        run.stage = "signals"
        self._execute(
            run,
            client,
            budget,
            lambda: self._collect_signals(run, client, budget, mission, discovery),
            [],
        )
        return run

    def run_people(self, research_id: str) -> ResearchRun:
        """People for the top accounts, then the final score, on a run that has its signals.
        A finished stage is returned as is, so a retry never pays for the same people twice."""
        run = self.get(research_id)
        if run.stage == "people" and run.outcome == "completed":
            return run
        mission = self._store.get_mission(run.mission_id)
        if mission is None:
            raise ResearchNotFound(f"mission {run.mission_id}")
        budget = CreditBudget(self._budget)
        budget.spent = Decimal(run.credits.get("actual", "0"))
        budget.unconfirmed = Decimal(run.credits.get("unconfirmed_estimate", "0"))
        client = self._factory(budget)
        earlier = list(run.calls)
        run.finished_at = None
        run.outcome = "running"

        def people() -> None:
            self._map_people(run, client, budget, mission)
            run.stage = "people"

        self._execute(run, client, budget, people, earlier)
        return run

    def _start(
        self, discovery_id: str, initiated_by: str
    ) -> tuple[ResearchRun, Mission, DiscoveryRun]:
        discovery = self._store.get_discovery(discovery_id)
        if discovery is None:
            raise ResearchNotFound(f"discovery {discovery_id}")
        mission = self._store.get_mission(discovery.mission_id)
        if mission is None:
            raise ResearchNotFound(f"mission {discovery.mission_id}")
        run = ResearchRun(
            id=uuid.uuid4().hex,
            discovery_id=discovery_id,
            mission_id=mission.id,
            mode="live",  # replaced by the client's mode before anything runs
            initiated_by=initiated_by,
            reference_date=self._reference_date(),
            started_at=self._clock(),
        )
        return run, mission, discovery

    def _execute(
        self,
        run: ResearchRun,
        client: CrustdataClient,
        budget: CreditBudget,
        work: Callable[[], None],
        earlier_calls: list[CallRecord],
    ) -> None:
        try:
            work()
            run.outcome = "completed"
        except CrustdataError as exc:
            run.outcome = "failed"
            run.errors.append(str(exc))
        finally:
            run.calls = [*earlier_calls, *(CallRecord.from_receipt(r) for r in client.receipts)]
            run.credits = {
                "actual": str(budget.spent),
                "unconfirmed_estimate": str(budget.unconfirmed),
                "budget": str(budget.limit),
            }
            run.finished_at = self._clock()
            self._store.save_research(run)
        if run.outcome == "failed":
            raise ResearchFailed(run.errors[-1], run.id)

    def _collect_signals(
        self,
        run: ResearchRun,
        client: CrustdataClient,
        budget: CreditBudget,
        mission: Mission,
        discovery: DiscoveryRun,
    ) -> None:
        plan = mission.plan
        accounts = discovery.accounts[: plan.max_accounts]
        if not accounts:
            run.notes.append("discovery returned no accounts to research")
            return
        ids = [a.provider_company_id for a in accounts]
        today = run.reference_date

        postings: list[JobPosting] = []
        jobs_collected = False
        if wants_postings(plan):
            limit = _affordable(budget, JOB_CREDITS_PER_RESULT, JOBS_PER_ACCOUNT * len(ids))
            if limit < 1:
                run.notes.append("job search skipped: credit budget exhausted")
            else:
                try:
                    req = compile_job_request(ids, plan, today, limit)
                    postings = client.search_jobs(req).data.postings
                    jobs_collected = True
                except CrustdataError as exc:
                    if exc.kind not in DEGRADABLE:
                        raise
                    run.notes.append(f"job search unavailable: {exc.kind}")
        posting_signals = signals_from_postings(postings, plan, today)

        per: dict[int, tuple[list[Signal], list[Evidence]]] = {}
        for a in accounts:
            sigs, evs = signals_from_company(a, plan, today)
            sigs = sigs + posting_signals.signals.get(a.provider_company_id, [])
            evs = evs + [
                e for e in posting_signals.evidence if e.entity_id == str(a.provider_company_id)
            ]
            per[a.provider_company_id] = (sigs, evs)
        posts_searched = False
        if "topic_engagement" in plan.signal_types and plan.topic_keywords:
            posts_searched = self._collect_topic_posts(run, client, budget, plan, accounts, per)
        run.signals_collected = jobs_collected or posts_searched or any(per[i][0] for i in ids)

        results: dict[int, AccountResearch] = {}
        for a in accounts:
            cid = a.provider_company_id
            sigs, evs = per[cid]
            tech = [e.id for e in posting_signals.tech_evidence.get(cid, [])]
            results[cid] = AccountResearch(
                account=a,
                signals=sigs,
                evidence=evs,
                tech_evidence_ids=tech,
                people_searched=False,
                best_person=None,
                score=score_account(
                    a,
                    sigs,
                    len(tech),
                    PeopleOutcome(searched=False),
                    plan,
                    run.signals_collected,
                ),
            )
        order = rank([(cid, r.score) for cid, r in results.items()])
        run.accounts = [results[cid] for cid, _ in order]

    def _attach_contacts(
        self,
        run: ResearchRun,
        client: CrustdataClient,
        budget: CreditBudget,
        results: dict[int, AccountResearch],
    ) -> None:
        """Email and phone for the buyers we found, best match per account first, within the credit
        budget. Optional: any failure leaves people without contact details and says why in the notes."""
        asked: list[tuple[int, str]] = []
        seen: set[int] = set()
        for matches in (
            [[ar.best_person] for ar in results.values()],
            [ar.other_matches for ar in results.values()],
        ):
            for group in matches:
                for m in group:
                    pid = m.person.provider_person_id if m else 0
                    if m and m.person.profile_url and pid not in seen:
                        seen.add(pid)
                        asked.append((pid, m.person.profile_url))
        if not asked:
            return
        found: dict[int, list[ContactPoint]] = {}
        done = 0
        try:
            for start in range(0, len(asked), MAX_CONTACT_BATCH):
                batch = asked[start : start + MAX_CONTACT_BATCH]
                can = _affordable(budget, CONTACT_CREDITS_PER_PERSON, len(batch))
                if can < 1:
                    run.notes.append(
                        f"contact lookup stopped: credit budget exhausted, "
                        f"{len(asked) - done} people left without email or phone"
                    )
                    break
                found.update(
                    client.enrich_contacts(ContactEnrichRequest(targets=tuple(batch[:can]))).data
                )
                done += min(can, len(batch))
        except CrustdataError as exc:
            run.notes.append(
                "contact lookup unavailable: your Crustdata key may not include contact access"
                if exc.kind == "permission"
                else f"contact lookup skipped: {exc.kind}"
            )
        if found:
            run.notes.append(f"contact details found for {len(found)} of {len(asked)} people")

        def with_contact(m: PersonaMatch) -> PersonaMatch:
            points = found.get(m.person.provider_person_id)
            if not points:
                return m
            return m.model_copy(update={"person": m.person.model_copy(update={"contact": points})})

        for cid, ar in list(results.items()):
            results[cid] = ar.model_copy(
                update={
                    "best_person": with_contact(ar.best_person) if ar.best_person else None,
                    "other_matches": [with_contact(m) for m in ar.other_matches],
                }
            )

    def _collect_topic_posts(
        self,
        run: ResearchRun,
        client: CrustdataClient,
        budget: CreditBudget,
        plan: GTMPlan,
        accounts: list[Company],
        per: dict[int, tuple[list[Signal], list[Evidence]]],
    ) -> bool:
        """What each account's own staff post in public. Billed per post returned, so each search
        asks for a few, names the topic in the query, and stops when the budget cannot buy one."""
        searched = False
        found = 0
        for a in accounts:
            limit = _affordable(budget, POST_CREDITS_PER_RESULT, POSTS_PER_ACCOUNT)
            if limit < 1:
                run.notes.append("post search skipped: credit budget exhausted")
                break
            req = compile_post_request(a, plan, run.reference_date, limit)
            if req is None:
                continue
            try:
                posts = client.search_posts(req).data.posts
            except CrustdataError as exc:
                if exc.kind not in DEGRADABLE:
                    raise
                run.notes.append(f"post search unavailable: {exc.kind}")
                break
            searched = True
            sigs, evs = signals_from_posts(a, posts, plan, run.reference_date)
            found += len(sigs)
            cid = a.provider_company_id
            per[cid] = ([*per[cid][0], *sigs], [*per[cid][1], *evs])
        if searched:
            run.notes.append(f"topic posts: {found} account(s) with staff posting about the topic")
        return searched

    def _map_people(
        self, run: ResearchRun, client: CrustdataClient, budget: CreditBudget, mission: Mission
    ) -> None:
        plan = mission.plan
        top = [a.account.provider_company_id for a in run.accounts if a.score.status != "rejected"][
            :PEOPLE_TOP_N
        ]

        people: list[PersonRecord] = []
        people_searched = False
        if top:
            limit = _affordable(budget, PERSON_CREDITS_PER_RESULT, PEOPLE_PER_ACCOUNT * len(top))
            if limit < 1:
                run.notes.append(
                    "people search skipped: credit budget exhausted; reachability unknown"
                )
            else:
                try:
                    people = client.search_people(
                        compile_people_request(top, plan, limit)
                    ).data.people
                    people_searched = True
                except CrustdataError as exc:
                    if exc.kind not in DEGRADABLE:
                        raise
                    run.notes.append(f"people search skipped: {exc.kind}; reachability unknown")

        results: dict[int, AccountResearch] = {}
        for ar in run.accounts:
            a = ar.account
            cid = a.provider_company_id
            searched = people_searched and cid in top
            matches = match_people(people, cid, plan) if searched else None
            best = matches.best if matches else None
            outcome = PeopleOutcome(
                searched=searched, best_match_confidence=best.confidence if best else None
            )
            score = score_account(
                a, ar.signals, len(ar.tech_evidence_ids), outcome, plan, run.signals_collected
            )
            results[cid] = ar.model_copy(
                update={
                    "evidence": [*ar.evidence, _person_evidence(best, a)] if best else ar.evidence,
                    "people_searched": searched,
                    "best_person": best,
                    "other_matches": matches.matches[1:3] if matches else [],
                    "people_rejected": matches.rejected if matches else [],
                    "score": score,
                }
            )
        if self._fetch_contacts and people_searched:
            self._attach_contacts(run, client, budget, results)
        order = rank([(cid, r.score) for cid, r in results.items()])
        run.accounts = [results[cid] for cid, _ in order]

"""Topic engagement: do the people at an account publicly talk about what the seller sells?

Dated, sourced posts only. The provider's fuzzy match is never proof: code re-checks the keyword
and the employer, and says plainly when the employer was matched by name."""

from datetime import date, timedelta

import pytest

from tests.research.factories import NOW, TODAY, company, plan
from trigger_point.providers.crustdata.models import (
    PostCondition,
    PostConditionGroup,
    SocialPost,
)
from trigger_point.research.posts import (
    compile_post_request,
    employer_matches,
    topic_hits,
)
from trigger_point.research.signals import signals_from_posts

KEYWORDS = ["AI", "edtech", "artificial intelligence"]
SCHOOL = "Sunrise International School"


def topic_plan(**over: object):  # type: ignore[no-untyped-def]
    base: dict[str, object] = dict(
        signal_types=["topic_engagement"],
        topic_keywords=KEYWORDS,
        personas=[
            {
                "title": "Senior Maths Teacher",
                "function": "education",
                "why": "Owns the maths class",
            }
        ],
    )
    base.update(over)
    return plan(**base)


def post(days_ago: int = 10, **over: object) -> SocialPost:
    base: dict[str, object] = dict(
        post_url=f"https://www.linkedin.example/posts/p{days_ago}",
        text="Our maths teachers are trying AI tutors in Class 8 this term.",
        posted_on=TODAY - timedelta(days=days_ago),
        post_type="original",
        author_id=700 + days_ago,
        author_title="Senior Maths Teacher",
        author_company=SCHOOL,
        retrieved_at=NOW,
    )
    base.update(over)
    return SocialPost(**base)  # type: ignore[arg-type]


def acct():  # type: ignore[no-untyped-def]
    return company(name=SCHOOL, primary_domain="sunrise.example")


# ── employer matching ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("listed", "same"),
    [
        (SCHOOL, True),
        ("sunrise  INTERNATIONAL school", True),
        ("Sunrise International School Pvt. Ltd.", True),
        ("Sunrise International School, Powai", False),  # another campus, or the same? unknown
        ("Sunrise School", False),
        ("Sunrise Public School", False),
        ("Moonrise International School", False),
        ("", False),
        (None, False),
    ],
)
def test_an_employer_matches_only_when_the_name_is_the_same(listed: str | None, same: bool) -> None:
    assert employer_matches(SCHOOL, listed) is same


def test_a_chains_other_campuses_and_group_page_are_not_the_account() -> None:
    # Seen live: each campus is its own company, and its name carries the place.
    campus = "Billabong High International School, Mulund, Mumbai"
    assert employer_matches(campus, "Billabong High International School, Mulund, Mumbai")
    assert not employer_matches(campus, "Billabong High International School Jabalpur")
    assert not employer_matches(campus, "Billabong High International School, Bhopal")
    assert not employer_matches("Podar International School", "Podar International School - India")


def test_a_one_word_name_matches_only_exactly() -> None:
    assert employer_matches("Lernn", "Lernn") is True
    assert employer_matches("Lernn", "Lernn Academy") is False


# ── keyword verification ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "hits"),
    [
        ("We started using AI tutors", ["AI"]),
        ("He said that was fine", []),
        ("ai is lowercase here", []),
        ("The AIR quality was poor", []),
        ("Exploring EdTech in classrooms", ["edtech"]),
        ("Artificial   Intelligence in schools", ["artificial intelligence"]),
        ("AI and edtech are changing teaching", ["AI", "edtech"]),
        ("Nothing relevant here", []),
    ],
)
def test_a_keyword_counts_only_when_the_post_really_says_it(text: str, hits: list[str]) -> None:
    assert topic_hits(text, KEYWORDS) == hits


# ── the search request ──────────────────────────────────────────────────────────────────────


def test_the_request_names_the_employer_topic_and_window() -> None:
    req = compile_post_request(acct(), topic_plan(), TODAY, limit=3)
    assert req is not None and req.limit == 3
    assert isinstance(req.filters, PostConditionGroup)
    fields = {c.field for c in req.filters.conditions if isinstance(c, PostCondition)}
    assert {"actor.actor_type", "post_type", "date_posted", "actor.company_name"} <= fields
    employer = next(
        c for c in req.filters.conditions if getattr(c, "field", "") == "actor.company_name"
    )
    assert employer.type == "[.]" and employer.value == SCHOOL  # type: ignore[union-attr]
    topic = next(c for c in req.filters.conditions if isinstance(c, PostConditionGroup))
    assert topic.op == "or" and len(topic.conditions) == len(KEYWORDS)
    since = next(c for c in req.filters.conditions if getattr(c, "field", "") == "date_posted")
    assert since.value == (TODAY - timedelta(days=120)).isoformat()  # type: ignore[union-attr]


def test_no_request_without_keywords_or_a_name() -> None:
    assert compile_post_request(acct(), topic_plan(topic_keywords=[]), TODAY, 3) is None
    assert compile_post_request(company(name=None), topic_plan(), TODAY, 3) is None


# ── the signal ──────────────────────────────────────────────────────────────────────────────


def test_a_dated_post_becomes_a_sourced_signal_and_evidence() -> None:
    sigs, evidence = signals_from_posts(acct(), [post(10)], topic_plan(), TODAY)
    [s] = sigs
    assert s.type == "topic_engagement" and s.status == "active" and s.age_days == 10
    assert s.event_on == TODAY - timedelta(days=10) and s.as_of is None
    [ev] = evidence
    assert ev.source_kind == "social_post" and ev.source_url == post(10).post_url
    assert ev.event_on == s.event_on and ev.entity_id == str(acct().provider_company_id)
    assert "AI" in (ev.excerpt or "") and ev.id in s.evidence_ids
    assert "Senior Maths Teacher" in ev.claim and SCHOOL in ev.claim


def test_the_employer_match_is_said_to_be_by_name_because_posts_carry_no_company_id() -> None:
    _, [ev] = signals_from_posts(acct(), [post(10)], topic_plan(), TODAY)
    assert "employer matched by name" in ev.claim


def test_another_campus_of_the_same_chain_is_dropped() -> None:
    p = post(10, author_company="Sunrise International School, Powai")
    assert signals_from_posts(acct(), [p], topic_plan(), TODAY) == ([], [])


def test_the_excerpt_is_one_clean_line() -> None:
    p = post(10, text="Big news\n\n\nWe now use AI\nin Class 8   maths. #edtech")
    _, [ev] = signals_from_posts(acct(), [p], topic_plan(), TODAY)
    assert "\n" not in (ev.excerpt or "") and "  " not in (ev.excerpt or "")
    assert "AI" in (ev.excerpt or "")


def test_a_post_that_does_not_really_say_the_keyword_is_dropped() -> None:
    sigs, evidence = signals_from_posts(
        acct(), [post(5, text="He said it was fine")], topic_plan(), TODAY
    )
    assert sigs == [] and evidence == []


def test_a_different_employer_is_dropped() -> None:
    sigs, _ = signals_from_posts(
        acct(), [post(5, author_company="Moonrise International School")], topic_plan(), TODAY
    )
    assert sigs == []


def test_a_post_without_a_date_or_a_public_url_is_dropped() -> None:
    posts = [post(5, posted_on=None), post(6, post_url=None)]
    assert signals_from_posts(acct(), posts, topic_plan(), TODAY) == ([], [])


def test_a_repost_is_not_the_persons_own_words() -> None:
    sigs, _ = signals_from_posts(
        acct(), [post(5, post_type="repost_without_thoughts")], topic_plan(), TODAY
    )
    assert sigs == []


def test_an_old_post_is_expired_not_used_as_why_now() -> None:
    [s], _ = signals_from_posts(acct(), [post(200)], topic_plan(), TODAY)
    assert s.status == "expired"


def test_more_posts_from_more_people_make_a_stronger_signal() -> None:
    [one], _ = signals_from_posts(acct(), [post(10)], topic_plan(), TODAY)
    [three], _ = signals_from_posts(acct(), [post(10), post(20), post(30)], topic_plan(), TODAY)
    assert three.strength > one.strength
    assert "3 post" in three.description and "3 staff" in three.description


def test_the_same_post_twice_counts_once() -> None:
    [s], evidence = signals_from_posts(acct(), [post(10), post(10)], topic_plan(), TODAY)
    assert len(evidence) == 1 and "1 post" in s.description


def test_a_relevant_role_adds_weight() -> None:
    [teacher], _ = signals_from_posts(acct(), [post(10)], topic_plan(), TODAY)
    [other], _ = signals_from_posts(
        acct(), [post(10, author_title="Office Assistant")], topic_plan(), TODAY
    )
    assert teacher.strength > other.strength


def test_no_personal_name_ever_reaches_the_evidence() -> None:
    _, evidence = signals_from_posts(acct(), [post(10)], topic_plan(), TODAY)
    assert all(
        "Asha" not in e.claim and e.publisher == "Professional network post" for e in evidence
    )


def test_the_newest_post_sets_the_event_date_and_evidence_is_capped() -> None:
    posts = [post(d) for d in (40, 5, 15, 25, 35)]
    [s], evidence = signals_from_posts(acct(), posts, topic_plan(), TODAY)
    assert s.event_on == date.fromordinal(TODAY.toordinal() - 5)
    assert len(evidence) == 3 and len(s.evidence_ids) == 3

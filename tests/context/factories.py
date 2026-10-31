from datetime import UTC, datetime

from trigger_point.models.context import BusinessContext, ContextClaim, ContextDraft, PageRef

HOME = "https://acme.com/"
PRICING = "https://acme.com/pricing"
PAGES = {
    HOME: "Acme resolves 60% of support tickets automatically for B2B SaaS teams.",
    PRICING: "Plans start at $99 per agent per month.",
}


def fact(text: str, url: str = HOME, excerpt: str | None = None) -> ContextClaim:
    return ContextClaim(text=text, kind="fact", source_url=url, excerpt=excerpt, confidence="high")


def inference(text: str) -> ContextClaim:
    return ContextClaim(text=text, kind="inference", confidence="medium")


def page_refs() -> list[PageRef]:
    t = datetime(2026, 10, 31, tzinfo=UTC)
    return [
        PageRef(
            url=u, final_url=u, title=None, fetch_status="ok", retrieved_at=t, text_sha256="0" * 64
        )
        for u in PAGES
    ]


def context(**claims: list[ContextClaim]) -> BusinessContext:
    draft = ContextDraft(**claims)  # type: ignore[arg-type]
    return BusinessContext.from_draft(
        draft,
        website_url=HOME,
        domain="acme.com",
        user_goal="find SaaS buyers",
        pages=page_refs(),
        mode="replay",
        run_id="run-test",
    )

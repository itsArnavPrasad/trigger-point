"""HTML → title, visible text, and absolute links. Output is untrusted data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment
from bs4.element import PageElement

INVISIBLE_TAGS = ("script", "style", "noscript", "svg", "template", "iframe", "head")
_WS = re.compile(r"\s+")
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)
_STREAM_SWAP = re.compile(r'\$RC\("(B:\w+)","(S:\w+)"\)')


@dataclass(frozen=True)
class ExtractedPage:
    title: str | None
    text: str
    links: list[str] = field(default_factory=list)


def _resolve_streamed(soup: BeautifulSoup) -> set[str]:
    """React streams a page as a fallback, a hidden `div#S:n`, and a script that swaps them. A
    browser always shows the block, so it is content, and the fallback is not. Only that exact
    trio counts: a real script naming a real placeholder and a hidden div. Returns those ids."""
    blocks: set[str] = set()
    for script in soup.find_all("script"):
        for placeholder_id, block_id in _STREAM_SWAP.findall(script.string or ""):
            placeholder = soup.find("template", id=placeholder_id)
            if placeholder is None or soup.find("div", id=block_id) is None:
                continue
            blocks.add(block_id)
            fallback: list[PageElement] = []
            for node in placeholder.next_siblings:
                if isinstance(node, Comment) and node.strip() == "/$":
                    for item in fallback:
                        item.extract()
                    break
                fallback.append(node)
    return blocks


def extract_page(html: str, base_url: str, max_chars: int = 40_000) -> ExtractedPage:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = _WS.sub(" ", title_tag.get_text()).strip() if title_tag else None
    links = [urljoin(base_url, str(a["href"]).strip()) for a in soup.find_all("a", href=True)]
    streamed = _resolve_streamed(soup)
    for tag in soup(INVISIBLE_TAGS):
        tag.decompose()
    # Text a visitor cannot see is a common prompt-injection carrier; drop it.
    for tag in soup.find_all(True):
        if tag.decomposed:
            continue
        attrs = tag.attrs or {}
        if tag.name == "div" and attrs.get("id") in streamed:
            attrs = {k: v for k, v in attrs.items() if k != "hidden"}
        if (
            "hidden" in attrs
            or str(attrs.get("aria-hidden", "")).lower() == "true"
            or _HIDDEN_STYLE.search(str(attrs.get("style", "")))
        ):
            tag.decompose()
    text = _WS.sub(" ", soup.get_text(" ")).strip()
    # Collapse spaces introduced before punctuation by tag joins ("text ." -> "text.").
    text = re.sub(r" ([.,;:!?])", r"\1", text)
    return ExtractedPage(title=title or None, text=text[:max_chars], links=links)

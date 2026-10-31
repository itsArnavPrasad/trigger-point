from trigger_point.web.extract import extract_page


def test_extracts_title_and_visible_text_only() -> None:
    page = extract_page(
        "<html><head><title> Acme | Support AI </title><style>.x{}</style></head>"
        "<body><script>var secret=1</script><h1>Resolve tickets</h1>"
        "<p>Faster   support\n\n for SaaS.</p><noscript>enable js</noscript></body></html>",
        "https://acme.com/",
    )
    assert page.title == "Acme | Support AI"
    assert "Resolve tickets" in page.text
    assert "Faster support for SaaS." in page.text
    assert "secret" not in page.text
    assert "enable js" not in page.text


def test_malformed_html_still_yields_text() -> None:
    page = extract_page("<div><p>Unclosed <b>bold <i>text</div></p>", "https://acme.com/")
    assert "Unclosed bold text" in page.text


def test_empty_document() -> None:
    page = extract_page("", "https://acme.com/")
    assert page.title is None
    assert page.text == ""
    assert page.links == []


def test_links_are_absolute() -> None:
    page = extract_page(
        '<a href="/pricing">P</a><a href="https://x.org/a">X</a>', "https://acme.com/about"
    )
    assert page.links == ["https://acme.com/pricing", "https://x.org/a"]


def test_text_is_capped() -> None:
    page = extract_page("<p>" + "word " * 20000 + "</p>", "https://acme.com/", max_chars=1000)
    assert len(page.text) <= 1000

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from rustic_ai.serpapi.local_engines import (
    BingEngine,
    BlockReason,
    DuckDuckGoEngine,
    GoogleEngine,
    parse_result_count,
    split_snippet_date,
)

FIXTURES = Path(__file__).parent / "fixtures" / "local_serp"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestGoogleEngine:
    def test_results(self):
        parsed = GoogleEngine().parse(fixture("google_page1.html"), "https://www.google.com/search?q=x")

        assert not parsed.blocked
        assert parsed.total_results == 1234000
        # 10 direct results + 2 /goto results; the maps.google.com link and the duplicate are dropped
        assert len(parsed.results) == 12
        assert [r.url for r in parsed.results[:3]] == [
            "https://example.com/g/1",
            "https://example.com/g/2",
            "https://example.com/g/3",  # unwrapped from /url?q=
        ]
        first = parsed.results[0]
        assert (first.title, first.snippet, first.date, first.needs_resolve) == (
            "Google Result 1",
            "Snippet for google result 1.",
            "",
            False,
        )

    def test_goto_links_are_marked_for_resolution(self):
        parsed = GoogleEngine().parse(fixture("google_page1.html"), "https://www.google.com/search?q=x")

        goto = parsed.results[10]
        assert goto.needs_resolve
        assert goto.url == "https://www.google.com/goto?url=CAESbgHrOzAVTOKENONE"
        assert goto.title == "Goto Result A"
        assert goto.snippet == "Snippet for goto result A."
        assert goto.date == "Apr 1, 2026"

    def test_captcha(self):
        parsed = GoogleEngine().parse(fixture("google_captcha.html"), "https://www.google.com/sorry/index?continue=x")
        assert parsed.block_reason == BlockReason.CAPTCHA
        assert parsed.results == []

    def test_consent_wall(self):
        parsed = GoogleEngine().parse("<html></html>", "https://consent.google.com/ml?continue=x")
        assert parsed.block_reason == BlockReason.CONSENT

    def test_empty_page(self):
        parsed = GoogleEngine().parse(fixture("google_empty.html"), "https://www.google.com/search?q=x")
        assert not parsed.blocked
        assert parsed.results == []

    def test_search_url(self):
        engine = GoogleEngine()
        assert "start" not in engine.search_url("a b", 0, "en", "us")
        url = engine.search_url("a b", 20, "en", "us")
        assert parse_qs(urlparse(url).query) == {"q": ["a b"], "hl": ["en"], "gl": ["us"], "start": ["20"]}


class TestBingEngine:
    def test_results(self):
        parsed = BingEngine().parse(fixture("bing_page1.html"), "https://www.bing.com/search?q=x")

        assert not parsed.blocked
        assert parsed.total_results == 56700
        assert len(parsed.results) == 10
        assert parsed.results[0].url == "https://example.org/b/1"
        assert parsed.results[1].url == "https://example.org/b/2"  # decoded from a bing.com/ck/a redirect
        assert parsed.results[0].snippet == "Snippet for bing result 1."

    def test_captcha(self):
        parsed = BingEngine().parse(fixture("bing_captcha.html"), "https://www.bing.com/search?q=x")
        assert parsed.block_reason == BlockReason.CAPTCHA


class TestDuckDuckGoEngine:
    def test_results(self):
        parsed = DuckDuckGoEngine().parse(fixture("ddg_page1.html"), "https://html.duckduckgo.com/html/?q=x")

        assert not parsed.blocked
        assert len(parsed.results) == 10  # the ad is skipped
        assert parsed.results[0].url == "https://example.net/d/1"  # unwrapped from a /l/?uddg= redirect
        assert parsed.results[0].title == "DDG Result 1"
        assert parsed.results[0].snippet == "Snippet for ddg result 1."

    def test_anomaly_page(self):
        parsed = DuckDuckGoEngine().parse(fixture("ddg_anomaly.html"), "https://html.duckduckgo.com/html/")
        assert parsed.block_reason == BlockReason.CAPTCHA


@pytest.mark.parametrize(
    "text,expected",
    [
        ("About 1,234,000 results (0.32s)", 1234000),
        ("About 118 results (0.21s)", 118),
        ("56,700 results", 56700),
        ("(0.21 seconds)", None),
        ("", None),
    ],
)
def test_parse_result_count(text, expected):
    assert parse_result_count(text) == expected


@pytest.mark.parametrize(
    "snippet,date,rest",
    [
        ("Apr 1, 2026 — 1. Blue Lakes", "Apr 1, 2026", "1. Blue Lakes"),
        ("Aug 3, 2026 · Compare 20 vector databases", "Aug 3, 2026", "Compare 20 vector databases"),
        ("3 days ago — Fresh news", "3 days ago", "Fresh news"),
        ("Rust is a general-purpose language", "", "Rust is a general-purpose language"),
    ],
)
def test_split_snippet_date(snippet, date, rest):
    assert split_snippet_date(snippet) == (date, rest)

"""
HTML parsers for the search engines supported by `LocalSERPAgent`.

Parsers work on raw HTML (as rendered by the browser), so they can be tested against fixture pages without a browser.
All engine-specific URLs and selectors live here: when an engine changes its markup, this is the file to update.
"""

from abc import ABC, abstractmethod
import base64
import binascii
from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup, Tag


class BlockReason(StrEnum):
    CAPTCHA = "captcha"  # a bot check such as a CAPTCHA or "unusual traffic" page
    CONSENT = "consent"  # a cookie / consent wall that could not be dismissed


@dataclass(frozen=True)
class RawResult:
    url: str
    title: str
    snippet: str = ""
    date: str = ""
    # True when `url` is an engine redirect (e.g. Google's opaque /goto link) the agent must resolve.
    needs_resolve: bool = False


@dataclass
class ParsedPage:
    results: List[RawResult] = field(default_factory=list)
    total_results: Optional[int] = None
    block_reason: Optional[BlockReason] = None

    @property
    def blocked(self) -> bool:
        return self.block_reason is not None


def _text(node: Optional[Tag]) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def parse_result_count(text: str) -> Optional[int]:
    """Extract the result count from e.g. "About 1,234 results (0.21s)"; None when no count is shown."""
    match = re.search(r"(\d[\d,.   ]*)\s*results?\b", text, re.IGNORECASE)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


# Leading date on a snippet, e.g. "Apr 1, 2026 — ..." (Google, em dash) or "3 days ago · ..." (Bing, middle dot).
_SNIPPET_DATE = re.compile(
    r"^((?:[A-Z][a-z]{2,8}\.? \d{1,2}, \d{4})|(?:\d{1,2} [A-Z][a-z]{2,8} \d{4})"
    r"|(?:\d+ (?:second|minute|hour|day|week|month|year)s? ago))\s*[—·-]\s*"
)


def split_snippet_date(snippet: str) -> Tuple[str, str]:
    """Split a leading publication date off a snippet; returns (date, snippet)."""
    match = _SNIPPET_DATE.match(snippet)
    if not match:
        return "", snippet
    return match.group(1), snippet[match.end() :]


def _is_http(url: str) -> bool:
    return urlparse(url).scheme in ("http", "https")


class LocalSearchEngine(ABC):
    """A search engine the agent can drive: how to build its URLs, paginate, and parse its result pages."""

    name: str
    page_size: int
    # Playwright selectors for buttons that dismiss a cookie/consent wall.
    consent_selectors: Tuple[str, ...] = ()
    # Set for engines whose later pages are reached by clicking "Next" rather than by an offset in the URL.
    next_page_selector: Optional[str] = None
    # The first "Next" click may land on the same page again; click once more before concluding there are no more.
    next_may_repeat_page: bool = False

    @property
    def paginate_by_click(self) -> bool:
        return self.next_page_selector is not None

    @abstractmethod
    def search_url(self, query: str, offset: int, hl: str, gl: str) -> str:
        """URL for the results page starting at the zero-based `offset`."""

    @abstractmethod
    def parse(self, html: str, final_url: str) -> ParsedPage:
        """Parse a results page."""

    @staticmethod
    def _dedupe(results: List[RawResult]) -> List[RawResult]:
        seen: Set[str] = set()
        unique = []
        for result in results:
            if result.url not in seen:
                seen.add(result.url)
                unique.append(result)
        return unique


class GoogleEngine(LocalSearchEngine):
    name = "google"
    page_size = 10
    consent_selectors = (
        'button:has-text("Reject all")',
        'button:has-text("Accept all")',
        'form[action*="consent"] button',
    )

    _BLOCK_MARKERS = ("unusual traffic from your computer network", "our systems have detected unusual traffic")

    def search_url(self, query: str, offset: int, hl: str, gl: str) -> str:
        url = f"https://www.google.com/search?q={quote_plus(query)}&hl={hl}&gl={gl}"
        if offset:
            url += f"&start={offset}"
        return url

    @staticmethod
    def _unwrap(href: str) -> str:
        if href.startswith("/url?") or href.startswith("https://www.google.com/url?"):
            params = parse_qs(urlparse(href).query)
            target = params.get("q") or params.get("url")
            if target:
                return target[0]
        return urljoin("https://www.google.com", href)

    @staticmethod
    def _is_google_host(url: str) -> bool:
        return re.fullmatch(r"(.+\.)?google\.[a-z.]+", urlparse(url).hostname or "") is not None

    def parse(self, html: str, final_url: str) -> ParsedPage:
        soup = BeautifulSoup(html, "html.parser")
        lowered = html.lower()

        if (
            "/sorry/" in final_url
            or soup.select_one("form#captcha-form")
            or soup.select_one(".g-recaptcha, #recaptcha")
            or any(marker in lowered for marker in self._BLOCK_MARKERS)
        ):
            return ParsedPage(block_reason=BlockReason.CAPTCHA)

        if "consent.google." in final_url:
            return ParsedPage(block_reason=BlockReason.CONSENT)

        container = soup.select_one("#search") or soup.select_one("#rso") or soup
        results: List[RawResult] = []
        for h3 in container.select("a h3"):
            anchor = h3.find_parent("a")
            if anchor is None or not anchor.get("href"):
                continue
            href = str(anchor["href"])
            url = self._unwrap(href)
            # Google now links results through /goto?url=<encrypted token>; only a request to it reveals the target.
            needs_resolve = urlparse(url).path == "/goto" and self._is_google_host(url)
            if not _is_http(url) or (self._is_google_host(url) and not needs_resolve):
                continue

            block = anchor.find_parent("div", class_=["MjjYud", "g"]) or anchor.find_parent(
                "div", attrs={"data-hveid": True}
            )
            snippet_node = None
            if block is not None:
                snippet_node = (
                    block.select_one(".VwiC3b")
                    or block.select_one("[data-sncf]")
                    or block.select_one('[style*="-webkit-line-clamp"]')
                )
            date, snippet = split_snippet_date(_text(snippet_node))
            results.append(RawResult(url=url, title=_text(h3), snippet=snippet, date=date, needs_resolve=needs_resolve))

        stats = soup.select_one("#result-stats")
        total = parse_result_count(_text(stats)) if stats else None
        return ParsedPage(results=self._dedupe(results), total_results=total)


class BingEngine(LocalSearchEngine):
    name = "bing"
    page_size = 10
    consent_selectors = ("#bnp_btn_accept", "button#bnp_btn_reject")
    # Bing ignores `first=` on a fresh request and serves page 1 again; its own "Next" link paginates reliably.
    next_page_selector = "a.sb_pagN"
    # In a fresh session the first "Next" click goes through a cookie-setting redirect that serves page 1 again.
    next_may_repeat_page = True

    def search_url(self, query: str, offset: int, hl: str, gl: str) -> str:
        # Always the first page: later pages are reached by clicking "Next".
        return f"https://www.bing.com/search?q={quote_plus(query)}&setlang={hl}&cc={gl}"

    @staticmethod
    def _unwrap(href: str) -> str:
        parsed = urlparse(href)
        if (parsed.hostname or "").endswith("bing.com") and parsed.path.startswith("/ck/"):
            encoded = parse_qs(parsed.query).get("u", [""])[0]
            if encoded.startswith("a1"):
                payload = encoded[2:]
                try:
                    return base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8")
                except (binascii.Error, UnicodeDecodeError):
                    return href
        return href

    def parse(self, html: str, final_url: str) -> ParsedPage:
        soup = BeautifulSoup(html, "html.parser")

        if soup.select_one("#b_captcha, .captcha, iframe[src*='challenge']") or "/challenge" in final_url:
            return ParsedPage(block_reason=BlockReason.CAPTCHA)

        results: List[RawResult] = []
        for item in soup.select("li.b_algo"):
            anchor = item.select_one("h2 a")
            if anchor is None or not anchor.get("href"):
                continue
            url = self._unwrap(str(anchor["href"]))
            if not _is_http(url):
                continue
            snippet_node = item.select_one(".b_caption p") or item.select_one("[class*='b_lineclamp']")
            date, snippet = split_snippet_date(_text(snippet_node))
            results.append(RawResult(url=url, title=_text(anchor), snippet=snippet, date=date))

        count = soup.select_one(".sb_count")
        total = parse_result_count(_text(count)) if count else None
        return ParsedPage(results=self._dedupe(results), total_results=total)


class DuckDuckGoEngine(LocalSearchEngine):
    name = "duckduckgo"
    page_size = 10
    next_page_selector = "input[type='submit'][value='Next']"

    def search_url(self, query: str, offset: int, hl: str, gl: str) -> str:
        # Always the first page: the html endpoint has no offset parameter; later pages are reached by clicking "Next".
        return f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&kl={gl}-{hl}"

    @staticmethod
    def _unwrap(href: str) -> str:
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if (parsed.hostname or "").endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg")
            if target:
                return target[0]
        return href

    def parse(self, html: str, final_url: str) -> ParsedPage:
        soup = BeautifulSoup(html, "html.parser")

        if soup.select_one(".anomaly-modal__modal, #challenge-form") or "bots use duckduckgo too" in html.lower():
            return ParsedPage(block_reason=BlockReason.CAPTCHA)

        results: List[RawResult] = []
        for item in soup.select(".result"):
            if "result--ad" in (item.get("class") or []):
                continue
            anchor = item.select_one("a.result__a")
            if anchor is None or not anchor.get("href"):
                continue
            url = self._unwrap(str(anchor["href"]))
            if not _is_http(url):
                continue
            results.append(RawResult(url=url, title=_text(anchor), snippet=_text(item.select_one(".result__snippet"))))

        return ParsedPage(results=self._dedupe(results))


ENGINES: Dict[str, LocalSearchEngine] = {
    engine.name: engine for engine in (GoogleEngine(), BingEngine(), DuckDuckGoEngine())
}

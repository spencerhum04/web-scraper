"""
DOM-based fallback extraction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

from playwright.async_api import Page

from scrapers.types import JobCandidate
from utils.urls import canonicalize_url

EXTRACT_CANDIDATES_SCRIPT = """
() => {
    const candidateResults = [];
    const seen = new Set();

    function cleanText(value, maxLength = 800) {
        const collapsed = (value || "").replace(/\\s+/g, " ").trim();
        return collapsed.slice(0, maxLength);
    }

    function isVisible(element) {
        if (!element) {
            return false;
        }

        const style = window.getComputedStyle(element);
        if (!style || style.visibility === "hidden" || style.display === "none") {
            return false;
        }

        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function markerScore(element) {
        const attributes = [
            element.className || "",
            element.id || "",
            element.getAttribute("data-job-id") || "",
            element.getAttribute("data-posting-id") || "",
            element.getAttribute("data-job-posting-id") || "",
            element.getAttribute("data-testid") || "",
            element.getAttribute("data-qa") || "",
        ].join(" ").toLowerCase();

        let score = 0;
        if (/(job|opening|posting|position|opportunit|career|requisition|role)/.test(attributes)) {
            score += 2;
        }
        if (element.querySelector("h1,h2,h3,h4,[role='heading']")) {
            score += 1;
        }
        if (element.parentElement && element.parentElement.children.length > 1) {
            score += 1;
        }
        if (["ARTICLE", "LI", "TR"].includes(element.tagName || "")) {
            score += 1;
        }
        return score;
    }

    function looksLikeListingContainer(element) {
        const text = cleanText(element.innerText || element.textContent || "", 900);
        if (!text || text.length < 8 || text.length > 900) {
            return false;
        }

        const hasHeading = Boolean(
            element.querySelector("h1,h2,h3,h4,[role='heading'],a,button")
        );
        return hasHeading && markerScore(element) >= 1;
    }

    function chooseContainer(element) {
        let current = element;
        let fallback = element.parentElement || element;

        while (current && current !== document.body) {
            const textLength = cleanText(current.innerText || current.textContent || "", 900).length;
            if (textLength > 0 && textLength <= 900) {
                fallback = current;
            }

            if (looksLikeListingContainer(current)) {
                return current;
            }
            current = current.parentElement;
        }

        return fallback;
    }

    function isMeaningfulTitle(text) {
        const cleaned = cleanText(text, 180);
        if (!cleaned || cleaned.length < 4 || cleaned.length > 180) {
            return false;
        }

        const lower = cleaned.toLowerCase();
        const blockedTitles = new Set([
            "apply",
            "learn more",
            "read more",
            "view all",
            "see all",
            "next",
            "previous",
            "back",
        ]);
        return !blockedTitles.has(lower);
    }

    function chooseTitle(sourceElement, container) {
        const heading = container.querySelector("h1,h2,h3,h4,[role='heading']");
        const titleCandidates = [
            sourceElement.getAttribute("aria-label"),
            sourceElement.getAttribute("title"),
            sourceElement.innerText,
            heading ? heading.innerText : "",
            container.getAttribute("aria-label"),
            container.getAttribute("title"),
        ];

        for (const candidate of titleCandidates) {
            if (isMeaningfulTitle(candidate)) {
                return cleanText(candidate, 180);
            }
        }

        return "";
    }

    function normalizeHref(rawHref) {
        if (!rawHref) {
            return "";
        }

        const lower = rawHref.toLowerCase();
        if (
            lower.startsWith("javascript:") ||
            lower.startsWith("mailto:") ||
            lower.startsWith("tel:") ||
            rawHref === "#"
        ) {
            return "";
        }

        try {
            return new URL(rawHref, window.location.href).href;
        } catch (error) {
            return "";
        }
    }

    function pushCandidate(sourceElement, explicitUrl = "") {
        const container = chooseContainer(sourceElement);
        if (!isVisible(sourceElement) && !isVisible(container)) {
            return;
        }

        const titleText = chooseTitle(sourceElement, container);
        const contextText = cleanText(container.innerText || container.textContent || "", 800);
        const score = markerScore(container) + (explicitUrl ? 1 : 0);
        if ((!titleText && !contextText) || score < 1) {
            return;
        }

        const dedupKey = [titleText, contextText.slice(0, 160), explicitUrl].join("|");
        if (seen.has(dedupKey)) {
            return;
        }

        seen.add(dedupKey);
        candidateResults.push({
            title_text: titleText,
            context_text: contextText,
            url: explicitUrl,
            score,
        });
    }

    for (const anchor of document.querySelectorAll("a[href]")) {
        if (!isVisible(anchor)) {
            continue;
        }

        const normalizedHref = normalizeHref(anchor.getAttribute("href"));
        if (!normalizedHref) {
            continue;
        }

        pushCandidate(anchor, normalizedHref);
    }

    const standaloneContainers = document.querySelectorAll(
        "[data-job-id], [data-posting-id], [data-job-posting-id], [data-testid*='job'], [data-qa*='job'], article, li, tr"
    );
    for (const element of standaloneContainers) {
        if (!isVisible(element) || element.querySelector("a[href]")) {
            continue;
        }

        if (!looksLikeListingContainer(element)) {
            continue;
        }

        pushCandidate(element, "");
    }

    return candidateResults;
}
"""


async def extract_from_page(page: Page) -> list[JobCandidate]:
    raw_candidates = await page.evaluate(EXTRACT_CANDIDATES_SCRIPT)
    return _coerce_candidates(raw_candidates)


def _coerce_candidates(raw_candidates: list[dict]) -> list[JobCandidate]:
    candidates: list[JobCandidate] = []
    for raw_candidate in raw_candidates:
        title_text = (raw_candidate.get("title_text") or "").strip()
        context_text = (raw_candidate.get("context_text") or "").strip()
        url = canonicalize_url(raw_candidate.get("url") or "")
        if not title_text and not context_text:
            continue

        candidates.append(
            JobCandidate(
                title_text=title_text,
                context_text=context_text,
                url=url or None,
            )
        )
    return candidates


@dataclass
class _HtmlNode:
    tag: str
    attrs: dict[str, str]
    parent: "_HtmlNode | None" = None
    children: list["_HtmlNode"] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def text_content(self) -> str:
        child_text = "".join(child.text_content() for child in self.children)
        return "".join(self.text_parts) + child_text

    def iter_descendants(self):
        for child in self.children:
            yield child
            yield from child.iter_descendants()


class _FixtureHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = _HtmlNode(tag="document", attrs={})
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attr_map = {key: value or "" for key, value in attrs}
        node = _HtmlNode(tag=tag, attrs=attr_map, parent=self._stack[-1])
        self._stack[-1].children.append(node)
        self._stack.append(node)

    def handle_endtag(self, tag: str):
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                break

    def handle_data(self, data: str):
        if self._stack:
            self._stack[-1].text_parts.append(data)


def extract_candidates_from_html(html: str, base_url: str) -> list[JobCandidate]:
    """Extract job candidates from a local HTML snippet for deterministic tests."""
    parser = _FixtureHtmlParser()
    parser.feed(html)

    candidates: list[JobCandidate] = []
    seen: set[str] = set()

    for node in parser.root.iter_descendants():
        if node.tag != "a":
            continue

        href = node.attrs.get("href", "")
        if not href:
            continue

        container = _find_fixture_container(node)
        title_text = _choose_fixture_title(node, container)
        context_text = _clean_fixture_text(container.text_content(), 800)
        candidate_url = canonicalize_url(urljoin(base_url, href))
        dedup_key = f"{title_text}|{context_text[:160]}|{candidate_url}"
        if dedup_key in seen:
            continue

        seen.add(dedup_key)
        candidates.append(
            JobCandidate(
                title_text=title_text,
                context_text=context_text,
                url=candidate_url or None,
            )
        )

    return candidates


def _find_fixture_container(node: _HtmlNode) -> _HtmlNode:
    current = node.parent or node
    fallback = current
    while current.parent is not None:
        if _looks_like_fixture_container(current):
            return current
        fallback = current
        current = current.parent
    return fallback


def _looks_like_fixture_container(node: _HtmlNode) -> bool:
    text = _clean_fixture_text(node.text_content(), 900)
    if len(text) < 8 or len(text) > 900:
        return False

    marker_text = " ".join(
        [
            node.tag,
            node.attrs.get("class", ""),
            node.attrs.get("id", ""),
            node.attrs.get("data-job-id", ""),
            node.attrs.get("data-posting-id", ""),
            node.attrs.get("data-job-posting-id", ""),
            node.attrs.get("data-testid", ""),
            node.attrs.get("data-qa", ""),
        ]
    ).casefold()
    has_marker = any(
        marker in marker_text
        for marker in ("job", "opening", "posting", "position", "opportunity", "career", "role")
    )
    return has_marker or node.tag in {"article", "li", "tr", "section", "div"}


def _choose_fixture_title(node: _HtmlNode, container: _HtmlNode) -> str:
    for value in (
        node.attrs.get("aria-label", ""),
        node.attrs.get("title", ""),
        node.text_content(),
    ):
        cleaned_value = _clean_fixture_text(value, 180)
        if _is_meaningful_fixture_title(cleaned_value):
            return cleaned_value

    for descendant in container.iter_descendants():
        if descendant.tag not in {"h1", "h2", "h3", "h4"}:
            continue
        cleaned_value = _clean_fixture_text(descendant.text_content(), 180)
        if _is_meaningful_fixture_title(cleaned_value):
            return cleaned_value

    return _clean_fixture_text(node.text_content(), 180)


def _clean_fixture_text(value: str, max_length: int) -> str:
    return " ".join(value.split())[:max_length]


def _is_meaningful_fixture_title(value: str) -> bool:
    if not value or len(value) < 4 or len(value) > 180:
        return False
    return value.casefold() not in {"apply", "learn more", "read more", "view all"}

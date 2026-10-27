"""Step 5 evidence helpers (pure, no I/O): mechanical result selection, publication dates, text, window rules.

Publication dates come only from metadata that clearly denotes publication (schema.org datePublished,
article:published_time). Modified/updated dates and <time> elements are never used. Conflicting dates
give None, which is unusable under rules.is_usable.
"""

import hashlib
import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlparse

from deal_radar.rules import add_months

WINDOW_MONTHS = 24
LATE_MONTHS = 3


def tokens(text: str | None) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()


def names_company(text: str | None, aliases: list[str]) -> bool:
    """True if any alias appears as a whole-token sequence in text (case-insensitive)."""
    words = tokens(text)
    for alias in aliases:
        target = tokens(alias)
        n = len(target)
        if n and any(words[i:i + n] == target for i in range(len(words) - n + 1)):
            return True
    return False


def host(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def on_domain(url: str, domains: list[str]) -> bool:
    h = host(url)
    return any(h == d or h.endswith("." + d) for d in domains)


def canonical_url(url: str) -> str:
    """Host + path (+ query), lower-case, without locale segments such as /uk/ or /en/, so regional copies collapse."""
    parsed = urlparse(url.strip())
    segments = [s for s in parsed.path.lower().split("/") if s and not re.fullmatch(r"[a-z]{2}", s)]
    query = f"?{parsed.query.lower()}" if parsed.query else ""
    return f"{host(url)}/{'/'.join(segments)}{query}"


def evidence_id(company_id: str, url: str) -> str:
    return f"ev-{company_id}-{hashlib.sha1(canonical_url(url).encode()).hexdigest()[:10]}"


def select_results(
    results: list[dict], aliases: list[str], limit: int, disallowed: list[str], opened: set[str],
    skip_domains: list[str] = (),
) -> list[tuple[dict, str]]:
    """Mechanical selection for one template: returns (result, decision) where decision is 'open' or a reason.

    `opened` holds canonical URLs already opened for this company and is updated in place.
    `skip_domains` are undated aggregator profile sites (pass 2 only).
    """
    decisions = []
    taken = 0
    for r in results:
        key = canonical_url(r["url"])
        if on_domain(r["url"], disallowed):
            decision = "disallowed_site"
        elif on_domain(r["url"], list(skip_domains)):
            decision = "aggregator_profile_site"
        elif not (names_company(r["title"], aliases) or names_company(r["url"], aliases)):
            decision = "does_not_name_company"
        elif key in opened:
            decision = "already_opened"
        elif taken >= limit:
            decision = "over_template_limit"
        else:
            decision = "open"
            taken += 1
            opened.add(key)
        decisions.append((r, decision))
    return decisions


_JSONLD_PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r'([a-zA-Z:_-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')


def _iso_day(value: str) -> date | None:
    match = re.match(r"\s*(\d{4}-\d{2}-\d{2})", value or "")
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def published_dates(html: str) -> set[date]:
    """Every publication date the page states in metadata (datePublished / article:published_time)."""
    found = {d for d in (_iso_day(v) for v in _JSONLD_PUBLISHED.findall(html)) if d}
    for tag in _META.findall(html):
        attrs = {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4)) for m in _ATTR.finditer(tag)}
        label = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        if label in ("article:published_time", "datepublished"):
            day = _iso_day(attrs.get("content", ""))
            if day:
                found.add(day)
    return found


def published_date(html: str) -> date | None:
    """The single stated publication date, or None if there is none or the stated dates conflict."""
    found = published_dates(html)
    return found.pop() if len(found) == 1 else None


_JSONLD_MODIFIED = re.compile(r'"dateModified"\s*:\s*"([^"]+)"')


def modified_after(html: str, anchor: date) -> bool:
    """True if the page states it was modified on/after the anchor (dateModified, article:modified_time,
    og:updated_time). Such content may post-date the anchor, so it cannot count (leakage guard only;
    a modified date is never used as the publication date)."""
    found = {d for d in (_iso_day(v) for v in _JSONLD_MODIFIED.findall(html)) if d}
    for tag in _META.findall(html):
        attrs = {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4)) for m in _ATTR.finditer(tag)}
        label = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        if label in ("article:modified_time", "og:updated_time", "datemodified"):
            day = _iso_day(attrs.get("content", ""))
            if day:
                found.add(day)
    return any(d >= anchor for d in found)


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "svg", "form", "iframe", "template"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag == "title":
            self.in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1
        elif tag == "title":
            self.in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        elif not self.skipping:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """Visible text with scripts, styles and page chrome removed; one paragraph per line."""
    parser = _TextExtractor()
    parser.feed(html)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).split("\n"))
    return "\n".join(line for line in lines if line)


def page_title(html: str) -> str | None:
    for tag in _META.findall(html):
        attrs = {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4)) for m in _ATTR.finditer(tag)}
        if (attrs.get("property") or "").lower() == "og:title" and attrs.get("content"):
            return " ".join(attrs["content"].split())
    parser = _TextExtractor()
    parser.feed(html)
    title = " ".join("".join(parser.title_parts).split())
    return title or None


def window_status(pub: date | None, anchor: date, ownership_history: bool) -> tuple[str, list[str]]:
    """('keep' | 'after_anchor' | 'before_window', tags) for the window [anchor - 24 months, anchor).

    Undated items are kept so the gap stays visible (they are unusable downstream).
    ownership_history items may predate the window but must still be before the anchor.
    """
    tags = ["ownership_history"] if ownership_history else []
    if pub is None:
        return "keep", tags
    if pub >= anchor:
        return "after_anchor", tags
    if pub < add_months(anchor, -WINDOW_MONTHS) and not ownership_history:
        return "before_window", tags
    if pub >= add_months(anchor, -LATE_MONTHS):
        tags = ["late", *tags]
    return "keep", tags


def content_leak(text: str, aliases: list[str], buyers: list[str], phrases: list[str]) -> str | None:
    """The first buyer name or target-outcome phrase found in the text (whole tokens, case-insensitive), else None.

    A hit means the stored page reveals the pair's outcome (e.g. a sidebar added after the anchor), so the page is
    excluded as a whole: once it carries post-anchor content we cannot know what else changed.
    """
    patterns = list(buyers) + [p.format(alias=a) for p in phrases for a in aliases]
    return next((p for p in patterns if names_company(text, [p])), None)

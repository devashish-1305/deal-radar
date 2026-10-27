import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest

from deal_radar.cases import load_cases
from deal_radar.evidence import (
    canonical_url,
    evidence_id,
    html_to_text,
    modified_after,
    names_company,
    page_title,
    published_date,
    select_results,
    window_status,
)
from deal_radar.rules import add_months, is_usable
from deal_radar.schemas import Evidence

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data" / "processed" / "evidence.json"
QUERIES = ROOT / "data" / "cases" / "evidence_queries.json"
ARTICLES = ROOT / "data" / "raw" / "articles"
ANCHOR = date(2025, 6, 9)


# --- names and selection ----------------------------------------------------------------------

def test_alias_matching_is_whole_token():
    assert names_company("UiPath acquires Peak AI Limited", ["Peak AI"])
    assert names_company("https://peak.ai/hub/blog/x", ["Peak AI"])
    assert not names_company("Peak International appoints CFO", ["Peak AI"])
    assert not names_company("kaab holdings news", ["AAB"])
    assert names_company("https://aab.uk/news/x", ["AAB"])


def test_canonical_url_collapses_locale_copies_and_keeps_query_ids():
    a = "https://www.macquarie.com/ch/en/about/news/2019/macquarie-completes-x.html"
    b = "https://www.macquarie.com/au/en/about/news/2019/macquarie-completes-x.html"
    assert canonical_url(a) == canonical_url(b)
    assert evidence_id("c", a) == evidence_id("c", b)
    assert canonical_url("https://ldc.co.uk/?p=1499") != canonical_url("https://ldc.co.uk/?p=12896")


def test_mechanical_selection_follows_result_order_and_limit():
    results = [
        {"rank": 1, "title": "Unrelated", "url": "https://example.com/a"},
        {"rank": 2, "title": "Fakeco raises money", "url": "https://news.example/1"},
        {"rank": 3, "title": "x", "url": "https://www.linkedin.com/in/fakeco"},
        {"rank": 4, "title": "Fakeco hires CFO", "url": "https://news.example/2"},
        {"rank": 5, "title": "Fakeco again", "url": "https://news.example/1"},
        {"rank": 6, "title": "Fakeco third", "url": "https://news.example/3"},
    ]
    opened = set()
    decisions = [d for _, d in select_results(results, ["Fakeco"], 2, ["linkedin.com"], opened)]
    assert decisions == ["does_not_name_company", "open", "disallowed_site", "open", "already_opened", "over_template_limit"]
    assert len(opened) == 2


# --- publication dates: leakage-critical -----------------------------------------------------

def page(meta="", body="<p>Fakeco text</p>"):
    return f"<html><head><title>T</title>{meta}</head><body>{body}</body></html>"


def test_published_date_from_json_ld_and_meta():
    assert published_date(page('<script type="application/ld+json">{"datePublished":"2024-03-01T09:00:00+00:00"}</script>')) == date(2024, 3, 1)
    assert published_date(page('<meta property="article:published_time" content="2024-03-02T10:00:00Z">')) == date(2024, 3, 2)
    assert published_date(page('<meta content="2024-03-03" itemprop="datePublished">')) == date(2024, 3, 3)


def test_modified_dates_and_time_elements_are_never_publication_dates():
    html = page(
        '<script type="application/ld+json">{"dateModified":"2026-01-01"}</script>'
        '<meta property="article:modified_time" content="2026-01-02">',
        body='<time datetime="2024-01-01">1 Jan 2024</time><p>Fakeco</p>',
    )
    assert published_date(html) is None


def test_conflicting_or_missing_publication_dates_give_none():
    conflict = page('<script>{"datePublished":"2024-03-01"}</script><meta property="article:published_time" content="2024-04-01">')
    assert published_date(conflict) is None
    assert published_date(page()) is None


def test_page_modified_after_anchor_is_flagged_but_published_date_unchanged():
    html = page('<script>{"datePublished":"2025-01-08","dateModified":"2025-11-18"}</script>')
    assert published_date(html) == date(2025, 1, 8)
    assert modified_after(html, date(2025, 2, 4))
    assert not modified_after(html, date(2026, 1, 1))
    assert modified_after(page('<meta property="og:updated_time" content="2025-02-04">'), date(2025, 2, 4))


def test_undated_evidence_is_never_usable():
    e = Evidence(evidence_id="e", company_id="c", url="https://x", source_type="news",
                 publication_date=None, retrieved_at=datetime(2026, 10, 27))
    assert not is_usable(e, date(2030, 1, 1))


# --- text ---------------------------------------------------------------------------------------

def test_text_extraction_drops_scripts_styles_and_chrome():
    html = ("<html><head><style>.x{}</style><script>var key='x'</script></head><body><nav>Menu</nav>"
            "<header>Top</header><p>Fakeco raised money.</p><footer>Cookies</footer></body></html>")
    assert html_to_text(html) == "Fakeco raised money."


def test_title_prefers_og_title():
    assert page_title(page('<meta property="og:title" content="Fakeco  news">')) == "Fakeco news"
    assert page_title(page()) == "T"


# --- window and tags -----------------------------------------------------------------------------

def test_late_boundaries():
    late_start = add_months(ANCHOR, -3)
    assert window_status(late_start, ANCHOR, False) == ("keep", ["late"])
    assert window_status(date.fromordinal(late_start.toordinal() - 1), ANCHOR, False) == ("keep", [])
    assert window_status(date.fromordinal(ANCHOR.toordinal() - 1), ANCHOR, False) == ("keep", ["late"])
    assert window_status(ANCHOR, ANCHOR, False)[0] == "after_anchor"


def test_window_start_boundary():
    start = add_months(ANCHOR, -24)
    assert window_status(start, ANCHOR, False) == ("keep", [])
    assert window_status(date.fromordinal(start.toordinal() - 1), ANCHOR, False)[0] == "before_window"


def test_ownership_history_may_be_old_but_never_on_or_after_anchor():
    assert window_status(date(2019, 7, 31), ANCHOR, True) == ("keep", ["ownership_history"])
    assert window_status(ANCHOR, ANCHOR, True)[0] == "after_anchor"


def test_undated_items_are_kept_so_the_gap_is_visible():
    assert window_status(None, ANCHOR, False) == ("keep", [])


# --- real data (skipped until generated) ------------------------------------------------------------

def real_evidence():
    if not EVIDENCE.exists():
        pytest.skip("evidence.json not generated yet")
    return json.loads(EVIDENCE.read_text())


def anchors():
    _, _, pairs = load_cases(ROOT / "data" / "cases")
    out = {}
    for p in pairs:
        out[p.deal_company_id] = out[p.control_company_id] = p.anchor_date
    return out


def test_real_evidence_validates_and_has_no_text_field():
    for item in real_evidence():
        Evidence.model_validate(item)
        assert set(item) <= set(Evidence.model_fields)
        assert "text" not in item


def test_real_evidence_is_before_its_pair_anchor_and_late_tag_is_exact():
    anchor_of = anchors()
    for item in real_evidence():
        e = Evidence.model_validate(item)
        anchor = anchor_of[e.company_id]
        if e.publication_date is None:
            assert "late" not in e.tags
            continue
        assert e.publication_date < anchor
        assert ("late" in e.tags) == (add_months(anchor, -3) <= e.publication_date < anchor)
        if "ownership_history" not in e.tags:
            assert e.publication_date >= add_months(anchor, -24)


def test_real_evidence_has_raw_text_files():
    items = real_evidence()
    if not ARTICLES.exists():
        pytest.skip("data/raw/articles absent (e.g. CI)")
    for item in items:
        assert (ARTICLES / f"{item['evidence_id']}.txt").exists()


def test_both_companies_in_each_pair_ran_the_same_templates():
    spec = json.loads(QUERIES.read_text())
    templates = {}
    for q in spec["queries"]:
        templates.setdefault(q["company_id"], set()).add(q["template"])
        assert q["result_count"] == len(q["results"])
    _, _, pairs = load_cases(ROOT / "data" / "cases")
    for p in pairs:
        assert templates[p.deal_company_id] == templates[p.control_company_id] == set(spec["protocol"]["templates"])


# --- Step 5.1: pass 2 and logged exceptions ------------------------------------------------------

EXCEPTIONS = ROOT / "data" / "cases" / "evidence_exceptions.json"
GUARD_EXCLUDED = [  # removed by the modified_after_anchor guard in Step 5; must never come back
    "https://www.ldc.co.uk/portfolio/hsl-compliance-investment-in-expansion/",
    "https://mooreks.co.uk/insights/moore-kingston-smith-advises-cytora-on-sale-to-applied-systems-inc/",
    "https://startupintros.com/news/2024-02-01-artificial-labs-series-a-2",
    "https://www.mwe.com/?p=329471",
]


def test_pass2_skips_aggregator_profiles_and_urls_opened_in_pass1():
    results = [
        {"rank": 1, "title": "Fakeco funding", "url": "https://www.cbinsights.com/company/fakeco"},
        {"rank": 2, "title": "Fakeco news", "url": "https://news.example/old"},
        {"rank": 3, "title": "Fakeco more", "url": "https://news.example/new"},
    ]
    opened = {canonical_url("https://news.example/old")}
    decisions = [d for _, d in select_results(results, ["Fakeco"], 6, [], opened, ["cbinsights.com"])]
    assert decisions == ["aggregator_profile_site", "already_opened", "open"]


def test_pass2_rules_are_logged_in_the_protocol():
    p2 = json.loads(QUERIES.read_text())["protocol"]["pass2"]
    assert p2["per_template_open_limit"] == 6
    assert {"cbinsights.com", "pitchbook.com", "glassdoor.com", "owler.com", "crunchbase.com",
            "dealroom.co", "tracxn.com"} <= set(p2["skip_domains"])


def test_only_the_two_authorised_exceptions_exist():
    rows = json.loads(EXCEPTIONS.read_text())
    assert {(r["company_id"], r["kind"].split(" ")[0]) for r in rows} <= {
        ("xeinadin", "intent_signal"), ("hsl_compliance", "ownership_history")}
    for r in rows:
        assert "selection-rule quirk" in r["justification"] or "Not applied" in r["justification"]
        assert "harmless" not in r["justification"].lower()
    xein = next(r for r in rows if r["company_id"] == "xeinadin")
    assert "harder" in xein["justification"]


def test_applied_exceptions_are_dated_and_pre_anchor():
    items = {e["url"]: e for e in real_evidence()}
    anchor_of = anchors()
    for r in json.loads(EXCEPTIONS.read_text()):
        if r.get("url") and r["url"] in items:
            e = items[r["url"]]
            assert e["publication_date"] is not None
            assert date.fromisoformat(e["publication_date"]) < anchor_of[r["company_id"]]


def test_guard_excluded_pages_never_return():
    urls = {e["url"] for e in real_evidence()}
    assert not urls & set(GUARD_EXCLUDED)


OVERRIDES = ROOT / "data" / "cases" / "evidence_overrides.json"
PROXY_PREFIX = "VC funding-age proxy (last priced round before anchor), not a holding-period start: "


def quoted_part(field: str, value: str) -> str:
    """The verbatim quote inside an override field: ownership_basis may carry our own label prefix and a trailing
    parenthetical note; date_evidence is all quote."""
    if field == "ownership_basis":
        value = value.removeprefix(PROXY_PREFIX)
        value = re.sub(r"\s*\([^()]*\)\s*$", "", value) if value.rstrip().endswith(".)") else value
    return value


def test_override_quotes_are_at_most_25_words_and_verbatim():
    for eid, o in json.loads(OVERRIDES.read_text()).items():
        for field in ("ownership_basis", "date_evidence"):
            if field not in o:
                continue
            quote = quoted_part(field, o[field])
            assert len(quote.split()) <= 25, (eid, field, len(quote.split()))
            if field == "ownership_basis" and (ARTICLES / f"{eid}.txt").exists():
                assert " ".join(quote.split()) in " ".join((ARTICLES / f"{eid}.txt").read_text().split()), eid

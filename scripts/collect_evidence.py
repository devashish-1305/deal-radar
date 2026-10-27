"""Step 5: fetch the mechanically selected search results, record dated Evidence, write the evidence log.

Run from the repo root:  PYTHONPATH=src .venv/bin/python scripts/collect_evidence.py
Inputs:  data/cases/evidence_queries.json (query log + protocol), data/cases/evidence_overrides.json (manual
         datelines / ownership-history judgements, each with a quote from the fetched page).
Outputs: data/processed/evidence.json, data/raw/articles/<evidence_id>.txt (git-ignored), docs/evidence_log.md.
Pages are fetched with requests after a robots.txt check; anything blocked is logged, never worked around.
"""

import hashlib
import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from deal_radar.cases import load_cases
from deal_radar.evidence import (
    canonical_url,
    evidence_id,
    html_to_text,
    modified_after,
    names_company,
    on_domain,
    page_title,
    published_dates,
    select_results,
    tokens,
    window_status,
)
from deal_radar.schemas import Evidence

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "cases"
ARTICLES = ROOT / "data" / "raw" / "articles"
HTML_CACHE = ARTICLES / "html"
OUT = ROOT / "data" / "processed" / "evidence.json"
LOG = ROOT / "docs" / "evidence_log.md"
UA = "deal-radar-research/0.1 (public-data research prototype)"
TIMEOUT = (5, 15)
DOMAIN_DELAY = 1.0
MIN_TEXT_CHARS = 400


def robots_allows(url: str, cache: dict) -> bool:
    parsed = urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    if root not in cache:
        parser = RobotFileParser()
        try:
            r = requests.get(root + "/robots.txt", headers={"User-Agent": UA}, timeout=TIMEOUT)
            if r.status_code in (401, 403):
                parser.disallow_all = True
            elif r.status_code == 200:
                parser.parse(r.text.splitlines())
            else:
                parser.allow_all = True
        except requests.RequestException:
            parser.allow_all = True  # robots.txt unreachable: the page fetch itself decides
        cache[root] = parser
    return cache[root].can_fetch(UA, url)


def fetch(url: str, robots: dict, last_hit: dict) -> dict:
    """Fetch once and cache: {'ok': bool, 'reason', 'html', 'fetched_at'}."""
    key = hashlib.sha1(canonical_url(url).encode()).hexdigest()[:16]
    meta_path, html_path = HTML_CACHE / f"{key}.json", HTML_CACHE / f"{key}.html"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        meta["html"] = html_path.read_text() if meta["ok"] else None
        return meta
    meta = {"ok": False, "reason": None, "fetched_at": datetime.now(timezone.utc).isoformat()}
    html = None
    if not robots_allows(url, robots):
        meta["reason"] = "robots_disallowed"
    else:
        netloc = urlparse(url).netloc
        wait = DOMAIN_DELAY - (time.monotonic() - last_hit.get(netloc, 0.0))
        if wait > 0:
            time.sleep(wait)
        last_hit[netloc] = time.monotonic()
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
            if r.status_code != 200:
                meta["reason"] = f"http_{r.status_code}"
            elif "html" not in r.headers.get("content-type", "").lower():
                meta["reason"] = "unsupported_content_type"
            else:
                meta["ok"], html = True, r.text
        except requests.RequestException as exc:
            meta["reason"] = type(exc).__name__
    HTML_CACHE.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta))
    if html is not None:
        html_path.write_text(html)
    meta["html"] = html
    return meta


def source_type(url: str, own_domains: list[str], press: dict) -> str:
    domains = own_domains + press["pr_wires"] + press["investor_sites"]
    return "press_release" if on_domain(url, domains) else "news"


def main() -> None:
    spec = json.loads((CASES / "evidence_queries.json").read_text())
    protocol, cfg = spec["protocol"], spec["companies"]
    overrides_path = CASES / "evidence_overrides.json"
    overrides = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
    _, _, pairs = load_cases(CASES)
    order, context = [], {}
    for p in pairs:
        for cid, role in ((p.deal_company_id, "deal"), (p.control_company_id, "control")):
            order.append(cid)
            context[cid] = {"pair": p.pair_id, "role": role, "anchor": p.anchor_date}

    queries_by = defaultdict(list)
    for q in spec["queries"]:
        queries_by[q["company_id"]].append(q)

    log = {cid: {"queries": [], "excluded": [], "opened": []} for cid in order}
    candidates = []
    for cid in order:
        opened: set[str] = set()
        for q in sorted(queries_by[cid], key=lambda q: q["template"]):
            decisions = select_results(q["results"], cfg[cid]["aliases"], protocol["per_template_open_limit"],
                                       protocol["disallowed_domains"], opened)
            n_open = sum(d == "open" for _, d in decisions)
            log[cid]["queries"].append((q["template"], q["query"], q["result_count"], n_open))
            for r, d in decisions:
                if d == "open":
                    candidates.append({"company_id": cid, "template": q["template"], "rank": r["rank"], "url": r["url"]})
                else:
                    log[cid]["excluded"].append((q["template"], r["rank"], d, r["url"]))

    robots, last_hit = {}, {}
    kept = []
    for c in candidates:
        cid, url = c["company_id"], c["url"]
        c["evidence_id"] = eid = evidence_id(cid, url)
        page = fetch(url, robots, last_hit)
        c["fetched_at"] = page["fetched_at"]
        if not page["ok"]:
            c["outcome"] = f"blocked: {page['reason']}"
            continue
        html = page["html"]
        text, title = html_to_text(html), page_title(html)
        c["title"] = title
        if len(text) < MIN_TEXT_CHARS:
            c["outcome"] = "blocked: thin_or_paywalled_text"
            continue
        if not names_company(f"{title}\n{text}", cfg[cid]["aliases"]):
            c["outcome"] = "discarded: page_does_not_name_company"
            continue
        if modified_after(html, context[cid]["anchor"]):
            c["outcome"] = "discarded: modified_after_anchor"
            continue
        stated = published_dates(html)
        override = overrides.get(eid, {})
        pub, c["date_source"] = (stated.pop(), "metadata") if len(stated) == 1 else (None, "metadata_conflict" if stated else "none")
        if pub is None and override.get("manual_publication_date"):
            pub, c["date_source"] = date.fromisoformat(override["manual_publication_date"]), "manual_dateline"
            c["date_evidence"] = override["date_evidence"]
        ownership = bool(override.get("ownership_history"))
        if ownership:
            c["ownership_basis"] = override["ownership_basis"]
        status, tags = window_status(pub, context[cid]["anchor"], ownership)
        c.update(publication_date=pub, tags=tags, text=text,
                 source_type=source_type(url, cfg[cid]["own_domains"], protocol["press_release_domains"]))
        if status != "keep":
            c["outcome"] = f"discarded: {status}"
            continue
        kept.append(c)

    # Syndicated copies: same company and same normalised title -> keep the earliest publication.
    groups = defaultdict(list)
    for c in kept:
        groups[(c["company_id"], " ".join(tokens(c["title"])))].append(c)
    survivors = []
    for group in groups.values():
        group.sort(key=lambda c: (c["publication_date"] is None, c["publication_date"] or date.max, c["template"], c["rank"]))
        survivors.append(group[0])
        for dup in group[1:]:
            dup["outcome"] = f"discarded: duplicate_of {group[0]['evidence_id']}"

    # Per-company cap: press releases first, then template order, then result rank.
    final = []
    by_company = defaultdict(list)
    for c in survivors:
        by_company[c["company_id"]].append(c)
    for cid, items in by_company.items():
        items.sort(key=lambda c: (c["source_type"] != "press_release", c["template"], c["rank"]))
        for i, c in enumerate(items):
            if i < protocol["per_company_keep_cap"]:
                c["outcome"] = "kept"
                final.append(c)
            else:
                c["outcome"] = "discarded: over_company_cap"

    ARTICLES.mkdir(parents=True, exist_ok=True)
    keep_ids = {c["evidence_id"] for c in final}
    for stale in ARTICLES.glob("*.txt"):
        if stale.stem not in keep_ids:
            stale.unlink()
    records = []
    for c in sorted(final, key=lambda c: (order.index(c["company_id"]), c["template"], c["rank"])):
        (ARTICLES / f"{c['evidence_id']}.txt").write_text(c["text"])
        records.append(Evidence(
            evidence_id=c["evidence_id"], company_id=c["company_id"], url=c["url"], source_type=c["source_type"],
            publication_date=c["publication_date"], retrieved_at=c["fetched_at"], title=c["title"], tags=c["tags"],
        ).model_dump(mode="json"))
    OUT.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n")

    for c in candidates:
        log[c["company_id"]]["opened"].append(c)
    LOG.write_text(render_log(protocol, cfg, order, context, log, candidates))
    print(f"queries {len(spec['queries'])}, opened {len(candidates)}, kept {len(records)}")
    print("outcomes:", dict(Counter(c["outcome"].split(":")[0] if ":" in c["outcome"] else c["outcome"] for c in candidates)))


def render_log(protocol, cfg, order, context, log, candidates) -> str:
    L = ["# Evidence log (Step 5)", "",
         "Generated by `scripts/collect_evidence.py` from `data/cases/evidence_queries.json` and "
         "`data/cases/evidence_overrides.json`. Do not edit by hand.", "",
         "## Protocol",
         f"- **{protocol['note']}**",
         f"- Search tool: {protocol['search_tool']}; searched on {protocol['searched_on']}.",
         "- Templates (identical for every company):"]
    L += [f"  - {k}: `{v}`" for k, v in protocol["templates"].items()]
    L += [f"- Selection: {protocol['selection_rule']} Per-template limit L = {protocol['per_template_open_limit']}; "
          f"per-company cap = {protocol['per_company_keep_cap']} (press releases first, then template order, then rank).",
          f"- Source type: {protocol['source_type_rule']}",
          "- Window: publication date in [anchor − 24 months, anchor), using the pair's anchor for both companies. "
          "`late` = [anchor − 3 months, anchor). Anything on/after the anchor is discarded.",
          "- Publication dates: only schema.org `datePublished` or `article:published_time` from the fetched page "
          "(never modified/updated dates, `<time>` elements, search snippets or URL patterns). Conflicting or missing "
          "→ None (kept, unusable). A manual date is used only from a visible dateline/byline quoted below.",
          "- Leakage guard: a page whose metadata says it was modified on/after the anchor (`dateModified`, "
          "`article:modified_time`, `og:updated_time`) is discarded as `modified_after_anchor`, because its current text "
          "may post-date the anchor (CLAUDE.md: content published later never counts). Modified dates are never used "
          "as publication dates.",
          "- Ownership history: PE-backed → the current sponsor's investment announcement. VC-backed → the last priced "
          "round before the anchor, tagged only if the opened page documents it. **For VC-backed companies this is a "
          "funding-age proxy, not a holding-period start**; Step 7 decides whether to use it (exploratory only, not in PRD §8).",
          "- Fetching: `requests` with robots.txt respected, 1 s per-domain delay. Blocked, paywalled, non-HTML or "
          f"thin pages (< {MIN_TEXT_CHARS} chars of text) are logged and skipped, never worked around.", ""]

    L += ["## Summary", "",
          "| Company | Pair | Role | Anchor | Kept | Late | Undated (unusable) | Ownership history found |",
          "|---|---|---|---|---|---|---|---|"]
    for cid in order:
        kept = [c for c in log[cid]["opened"] if c.get("outcome") == "kept"]
        L.append(f"| {cid} | {context[cid]['pair']} | {context[cid]['role']} | {context[cid]['anchor']} | {len(kept)} | "
                 f"{sum('late' in c['tags'] for c in kept)} | {sum(c['publication_date'] is None for c in kept)} | "
                 f"{'y' if any('ownership_history' in c['tags'] for c in kept) else 'n'} |")

    blocked = [c for c in candidates if c["outcome"].startswith("blocked")]
    L += ["", "## Blocked or paywalled pages (not fetched or unusable, not worked around)", ""]
    L += [f"- {c['company_id']} · {c['template']} #{c['rank']} · {c['outcome'].split(': ', 1)[1]} · {c['url']}" for c in blocked] or ["- none"]

    undated = [c for c in candidates if c.get("outcome") == "kept" and c["publication_date"] is None]
    L += ["", "## Kept items with publication_date None (unusable)", ""]
    L += [f"- {c['evidence_id']} · {c['date_source']} · {c['url']}" for c in undated] or ["- none"]

    manual = [c for c in candidates if c.get("date_source") == "manual_dateline"]
    L += ["", "## Manual datelines (quoted from the fetched page)", ""]
    L += [f"- {c['evidence_id']} · {c['publication_date']} · \"{c['date_evidence']}\"" for c in manual] or ["- none"]

    owned = [c for c in candidates if c.get("ownership_basis")]
    L += ["", "## Ownership-history judgements (quoted from the fetched page)", ""]
    L += [f"- {c['evidence_id']} · {c.get('publication_date')} · {c['outcome']} · \"{c['ownership_basis']}\"" for c in owned] or ["- none"]

    for cid in order:
        entry = log[cid]
        opened = entry["opened"]
        outcomes = Counter(c["outcome"].split(" ")[0].rstrip(":") for c in opened)
        L += ["", f"## {cid} ({context[cid]['pair']}, {context[cid]['role']}, anchor {context[cid]['anchor']})", "",
              f"Search name `{cfg[cid]['search_name']}`; aliases {cfg[cid]['aliases']}. "
              f"Results found {sum(q[2] for q in entry['queries'])}, opened {len(opened)}, "
              f"kept {outcomes.get('kept', 0)}, discarded {outcomes.get('discarded', 0)}, blocked {outcomes.get('blocked', 0)}.", "",
              "| Template | Query | Results | Opened |", "|---|---|---|---|"]
        L += [f"| {t} | `{q}` | {n} | {o} |" for t, q, n, o in entry["queries"]]
        L += ["", "Opened:", ""]
        for c in opened:
            date_part = f" · published {c['publication_date']} ({c.get('date_source')})" if "publication_date" in c else ""
            tag_part = f" · tags {c['tags']}" if c.get("tags") else ""
            L.append(f"- {c['template']} #{c['rank']} · **{c['outcome']}**{date_part}{tag_part} · {c['url']}")
        L += ["", "Not opened:", ""]
        L += [f"- {t} #{rank} · {reason} · {url}" for t, rank, reason, url in entry["excluded"]]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()

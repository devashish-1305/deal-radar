"""Companies House API client (I/O only). Official API only; the key is read from .env and never logged.

Raw responses are cached under data/raw/companies_house/<number>/ (git-ignored) and fetched only if missing.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = "https://api.company-information.service.gov.uk"
MIN_INTERVAL = 0.6  # seconds between calls: ~500 requests / 5 min, under the 600 limit
MAX_RETRIES = 5
PAGE_SIZE = 100
# resource name -> (path suffix, response field holding the total number of items)
RESOURCES = {
    "officers": ("/officers", "total_results"),
    "filing_history": ("/filing-history", "total_count"),
    "charges": ("/charges", "total_count"),
    "psc": ("/persons-with-significant-control", "total_results"),  # all PSC kinds, individual and corporate
}

_last_call = 0.0


class CompaniesHouseError(RuntimeError):
    """Raised with a path and status only, so the API key can never appear in the message."""


def api_key() -> str:
    load_dotenv()
    key = os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip()
    if not key:
        raise CompaniesHouseError("COMPANIES_HOUSE_API_KEY is not set (add it to .env)")
    return key


def get_json(path: str, params: dict | None = None, *, key: str, allow_404: bool = False) -> dict | None:
    """GET one API path. Throttled; 429 is retried with exponential backoff. 404 returns None if allowed."""
    global _last_call
    for attempt in range(MAX_RETRIES + 1):
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        try:
            response = requests.get(BASE + path, params=params, auth=(key, ""), timeout=30)
        except requests.RequestException as exc:
            raise CompaniesHouseError(f"request failed for {path}: {type(exc).__name__}") from None
        if response.status_code == 429 and attempt < MAX_RETRIES:
            time.sleep(2 ** (attempt + 1))
            continue
        if response.status_code == 404 and allow_404:
            return None
        if response.status_code != 200:
            raise CompaniesHouseError(f"{path} returned HTTP {response.status_code}")
        return response.json()
    raise CompaniesHouseError(f"{path}: gave up after {MAX_RETRIES} retries")  # pragma: no cover


def fetch_all(path: str, total_key: str, *, key: str, page_size: int = PAGE_SIZE) -> dict:
    """Fetch every page of a list endpoint and merge the items. A 404 means an empty list."""
    items: list[dict] = []
    while True:
        page = get_json(path, {"items_per_page": page_size, "start_index": len(items)}, key=key, allow_404=True)
        if page is None:
            return {"items": [], "total": 0}
        got = page.get("items") or []
        items += got
        total = page.get(total_key, len(items))
        if not got or len(items) >= total:
            return {"items": items, "total": total}


def fetch_company(number: str, cache_dir: Path, *, key: str) -> dict[str, dict]:
    """Return profile, officers, filing_history, charges and psc for one CH number, from cache where present."""
    folder = Path(cache_dir) / number
    result = {}
    for name in ("profile", *RESOURCES):
        cached = folder / f"{name}.json"
        if not cached.exists():
            if name == "profile":
                data = get_json(f"/company/{number}", key=key)
            else:
                suffix, total_key = RESOURCES[name]
                data = fetch_all(f"/company/{number}{suffix}", total_key, key=key)
            data["fetched_at"] = datetime.now(timezone.utc).isoformat()
            folder.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(data))
        result[name] = json.loads(cached.read_text())
    return result

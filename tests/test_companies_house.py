import traceback

import pytest
import requests

from deal_radar import companies_house as ch

KEY = "test-key-SECRET-123"


class Response:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr(ch.time, "sleep", recorded.append)
    monkeypatch.setattr(ch, "_last_call", 0.0)
    return recorded


def fake_requests(monkeypatch, responses):
    calls = []

    def fake_get(url, params=None, auth=None, timeout=None):
        calls.append({"url": url, "params": params, "auth": auth})
        item = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(ch.requests, "get", fake_get)
    return calls


def test_pagination_merges_every_page(monkeypatch):
    all_items = [{"n": i} for i in range(5)]
    starts = []

    def fake_get_json(path, params=None, *, key, allow_404=False):
        starts.append(params["start_index"])
        # the server returns at most 2 items per page, whatever page size was asked for
        return {"items": all_items[params["start_index"]:params["start_index"] + 2], "total_results": 5}

    monkeypatch.setattr(ch, "get_json", fake_get_json)
    result = ch.fetch_all("/company/1/officers", "total_results", key=KEY, page_size=100)
    assert result == {"items": all_items, "total": 5}
    assert starts == [0, 2, 4]


def test_missing_list_endpoint_is_an_empty_list(monkeypatch):
    monkeypatch.setattr(ch, "get_json", lambda *a, **k: None)
    assert ch.fetch_all("/company/1/charges", "total_count", key=KEY) == {"items": [], "total": 0}


def test_fetch_company_caches_raw_json_and_refetches_only_when_missing(monkeypatch, tmp_path):
    calls = []

    def fake_get_json(path, params=None, *, key, allow_404=False):
        calls.append(path)
        return {"items": [{"x": 1}], "total_results": 1, "total_count": 1, "company_name": "FAKECO LTD"}

    monkeypatch.setattr(ch, "get_json", fake_get_json)
    first = ch.fetch_company("99999999", tmp_path, key=KEY)
    assert set(first) == {"profile", "officers", "filing_history", "charges", "psc"}
    assert len(calls) == 5
    assert {p.name for p in (tmp_path / "99999999").iterdir()} == {f"{n}.json" for n in first}
    assert "fetched_at" in first["profile"]

    ch.fetch_company("99999999", tmp_path, key=KEY)
    assert len(calls) == 5  # everything came from the cache

    (tmp_path / "99999999" / "charges.json").unlink()
    ch.fetch_company("99999999", tmp_path, key=KEY)
    assert len(calls) == 6  # only the missing resource was fetched


def test_429_is_retried_with_backoff(monkeypatch, sleeps):
    calls = fake_requests(monkeypatch, [Response(429), Response(429), Response(200, {"ok": True})])
    assert ch.get_json("/company/1", key=KEY) == {"ok": True}
    assert len(calls) == 3
    assert [s for s in sleeps if s >= 1] == [2, 4]


def test_persistent_429_gives_up(monkeypatch):
    calls = fake_requests(monkeypatch, [Response(429)])
    with pytest.raises(ch.CompaniesHouseError, match="HTTP 429"):
        ch.get_json("/company/1", key=KEY)
    assert len(calls) == ch.MAX_RETRIES + 1


def test_calls_are_throttled(monkeypatch, sleeps):
    fake_requests(monkeypatch, [Response(200, {})])
    monkeypatch.setattr(ch.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(ch, "_last_call", 99.8)
    ch.get_json("/company/1", key=KEY)
    assert sleeps and sleeps[0] == pytest.approx(ch.MIN_INTERVAL - 0.2)


def test_basic_auth_uses_key_as_username(monkeypatch):
    calls = fake_requests(monkeypatch, [Response(200, {})])
    ch.get_json("/company/1", key=KEY)
    assert calls[0]["auth"] == (KEY, "")


def test_404_returns_none_only_when_allowed(monkeypatch):
    fake_requests(monkeypatch, [Response(404)])
    assert ch.get_json("/company/1/charges", key=KEY, allow_404=True) is None
    with pytest.raises(ch.CompaniesHouseError, match="HTTP 404"):
        ch.get_json("/company/1", key=KEY)


def test_api_key_never_appears_in_errors_or_output(monkeypatch, capsys, caplog):
    leaky = requests.ConnectionError(f"could not connect using {KEY}")
    fake_requests(monkeypatch, [leaky])
    with pytest.raises(ch.CompaniesHouseError) as raised:
        ch.get_json("/company/1", key=KEY)
    rendered = "".join(traceback.format_exception(raised.value))
    assert KEY not in str(raised.value) and KEY not in repr(raised.value) and KEY not in rendered

    fake_requests(monkeypatch, [Response(401)])
    with pytest.raises(ch.CompaniesHouseError) as raised:
        ch.get_json("/company/1", key=KEY)
    assert KEY not in str(raised.value)

    out = capsys.readouterr()
    assert KEY not in out.out + out.err + caplog.text


def test_api_key_is_read_from_the_environment(monkeypatch):
    monkeypatch.setattr(ch, "load_dotenv", lambda: None)
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", f"  {KEY}  ")
    assert ch.api_key() == KEY


def test_missing_api_key_message_does_not_contain_a_key(monkeypatch):
    monkeypatch.setattr(ch, "load_dotenv", lambda: None)
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    with pytest.raises(ch.CompaniesHouseError, match="not set"):
        ch.api_key()

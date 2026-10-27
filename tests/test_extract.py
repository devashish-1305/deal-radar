"""Step 6b: extractor, post-checks and evaluation (no network; the API client is mocked)."""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from deal_radar.extract import ModelUnavailable, check_models, extract_document, match, parse_output
from deal_radar.schemas import Evidence, Signal

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = date(2025, 6, 9)
TEXT = "Fakeco has appointed Jane Doe as chief financial officer. Fakeco raised £10m in a Series A round."
FAKE_KEY = "fake-test-key-0123456789abcdef"


def ev(pub=date(2024, 1, 10), eid="ev-fakeco-1"):
    return Evidence(evidence_id=eid, company_id="fakeco", url="https://news.example/fakeco",
                    source_type="news", publication_date=pub, retrieved_at=datetime(2026, 10, 27))


def item(**overrides):
    fields = dict(signal_type="new_cfo_or_chair", signal_class="readiness",
                  evidence_quote="Fakeco has appointed Jane Doe as chief financial officer.",
                  event_date="2023-12-01", status="confirmed", subject_company="Fakeco")
    fields.update(overrides)
    return fields


class FakeClient:
    """Returns the queued raw texts in order and records every request."""

    def __init__(self, *raws, error=None):
        self.raws, self.error, self.calls = list(raws), error, []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.raws.pop(0))],
                               usage=SimpleNamespace(input_tokens=100, output_tokens=20), stop_reason="end_turn")


def run(client, evidence=None, **kw):
    return extract_document(client, "model-x", "system prompt", evidence or ev(), ANCHOR, TEXT, "Fakeco", ["Fakeco"], **kw)


def test_valid_signal_is_kept_with_dates_and_url_from_evidence():
    out = run(FakeClient(json.dumps([item(event_date="2025-12-31")])))
    [s] = out["signals"]
    assert s.publication_date == date(2024, 1, 10)  # from Evidence, never from the LLM
    assert s.source_url == "https://news.example/fakeco"
    assert s.extraction_method == "llm"
    assert s.event_date == date(2025, 12, 31)  # the LLM's event_date never overrides publication_date


def test_llm_publication_date_or_url_fields_make_output_invalid():
    out = run(FakeClient(json.dumps([item(publication_date="2026-01-01")]), json.dumps([item(source_url="https://x")])))
    assert out["failure"] == "invalid_output_after_retry" and out["signals"] == []


def test_quote_not_in_text_is_rejected():
    out = run(FakeClient(json.dumps([item(evidence_quote="Fakeco named a new finance chief.")])))
    assert out["signals"] == [] and out["rejections"][0]["reason"] == "quote_not_in_text"


def test_quote_match_is_whitespace_normalised():
    out = run(FakeClient(json.dumps([item(evidence_quote="Fakeco  has appointed\nJane Doe as chief financial officer.")])))
    assert len(out["signals"]) == 1


def test_wrong_subject_company_is_rejected():
    out = run(FakeClient(json.dumps([item(subject_company="Otherco")])))
    assert out["signals"] == [] and out["rejections"][0]["reason"] == "wrong_subject_company"


def test_class_mismatch_is_rejected():
    out = run(FakeClient(json.dumps([item(signal_class="direct_intent")])))
    assert out["signals"] == [] and out["rejections"][0]["reason"] == "class_mismatch"


@pytest.mark.parametrize("pub", [None, ANCHOR, date(2025, 7, 1)])
def test_undated_or_post_anchor_evidence_is_never_sent(pub):
    client = FakeClient(json.dumps([item()]))
    with pytest.raises(ValueError):
        run(client, evidence=ev(pub=pub))
    assert client.calls == []


def test_invalid_json_is_retried_once_then_succeeds():
    client = FakeClient("not json", json.dumps([item()]))
    out = run(client)
    assert len(client.calls) == 2 and len(out["signals"]) == 1 and out["failure"] is None


def test_invalid_json_twice_is_a_failure():
    client = FakeClient("not json", "[{broken")
    out = run(client)
    assert len(client.calls) == 2 and out["failure"] == "invalid_output_after_retry" and out["signals"] == []


def test_fenced_json_and_empty_list_are_valid():
    assert parse_output("```json\n[]\n```") == []
    assert run(FakeClient("[]"))["signals"] == []


def test_probability_or_score_field_is_never_accepted():
    for extra in ({"probability": 0.7}, {"score": 3}, {"likelihood": "high"}):
        with pytest.raises(ValueError):
            parse_output(json.dumps([item(**extra)]))
    assert not {"probability", "score", "likelihood", "prediction"} & set(Signal.model_fields)


def test_cache_is_reused_without_calling_the_model(tmp_path):
    run(FakeClient(json.dumps([item()])), cache_dir=tmp_path)
    client = FakeClient(error=AssertionError("must not be called"))
    assert len(run(client, cache_dir=tmp_path)["signals"]) == 1


def http_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(f"model not found (key {FAKE_KEY})", response=httpx2.Response(status, request=request), body=None)


def test_unavailable_model_stops_and_never_substitutes():
    client = FakeClient(error=http_error(anthropic.NotFoundError, 404))
    with pytest.raises(ModelUnavailable) as exc:
        check_models(client, ["claude-haiku-5-5", "claude-sonnet-5-5"], FAKE_KEY)
    assert [c["model"] for c in client.calls] == ["claude-haiku-5-5"]  # stopped at the first, no other model tried
    assert "claude-haiku-5-5" in str(exc.value)


def test_key_never_appears_in_errors_or_logs(caplog):
    client = FakeClient(error=http_error(anthropic.NotFoundError, 404))
    with caplog.at_level(logging.DEBUG), pytest.raises(ModelUnavailable) as exc:
        check_models(client, ["claude-haiku-5-5"], FAKE_KEY)
    assert FAKE_KEY not in str(exc.value) and "[REDACTED]" in str(exc.value)
    assert FAKE_KEY not in caplog.text


def sig(eid, stype, status="confirmed", i=0):
    from deal_radar.schemas import SIGNAL_CLASS_OF
    return Signal(signal_id=f"s{eid}{stype}{i}", company_id="c", evidence_id=eid, signal_class=SIGNAL_CLASS_OF[stype],
                  signal_type=stype, event_date=None, publication_date=date(2024, 1, 1), evidence_quote="q",
                  status=status, source_url="u", extraction_method="llm")


def test_duplicates_are_not_counted_as_true_positives():
    gold = {"d1": [{"signal_type": "new_cfo_or_chair", "status": "confirmed"}], "d2": []}
    preds = [sig("d1", "new_cfo_or_chair", i=0), sig("d1", "new_cfo_or_chair", i=1), sig("d1", "new_cfo_or_chair", i=2),
             sig("d2", "governance_change", i=0), sig("d2", "governance_change", i=1)]
    m = match(gold, preds)
    assert m["tp"] == 1 and len(m["duplicates"]) == 3 and len(m["fp"]) == 1 and m["fn"] == []
    assert m["precision"] == 0.5 and m["recall"] == 1.0


def test_matching_is_one_to_one_and_counts_misses():
    gold = {"d1": [{"signal_type": "pe_holding_period", "status": "confirmed"}] * 2}
    m = match(gold, [sig("d1", "pe_holding_period", status="attributed")])
    assert m["tp"] == 1 and len(m["fn"]) == 1 and m["status_agreement"] == 0.0


# --- real data (skipped until the extraction has run) -----------------------------------------------

@pytest.mark.parametrize("model", ["haiku", "sonnet"])
def test_real_llm_signals_validate_and_quotes_are_in_source_text(model):
    path = ROOT / "data" / "processed" / f"llm_signals_{model}.json"
    if not path.exists():
        pytest.skip("extraction not run yet")
    articles = ROOT / "data" / "raw" / "articles"
    evidence = {e["evidence_id"]: e for e in json.loads((ROOT / "data" / "processed" / "evidence.json").read_text())}
    for raw in json.loads(path.read_text()):
        s = Signal.model_validate(raw)
        e = evidence[s.evidence_id]
        assert s.extraction_method == "llm" and s.source_url == e["url"]
        assert str(s.publication_date) == e["publication_date"]
        if articles.exists():
            text = " ".join((articles / f"{s.evidence_id}.txt").read_text().split())
            assert " ".join(s.evidence_quote.split()) in text

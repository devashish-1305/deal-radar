"""Step 6: LLM extraction of PRD §8 signals from in-scope evidence, deterministic post-checks, and evaluation.

The LLM only extracts. publication_date and source_url are always copied from the Evidence record.
Only Evidence usable at its pair's anchor (rules.is_usable) may be sent; anything else raises before any call.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from deal_radar.evidence import names_company
from deal_radar.rules import is_usable
from deal_radar.schemas import MAX_QUOTE_WORDS, SIGNAL_CLASS_OF, Evidence, Signal, SignalClass, SignalType

PROMPT_VERSION = "extract_v1"
MAX_TOKENS = 4000


class ModelUnavailable(RuntimeError):
    """A requested model cannot be used with this key. Never substitute another model."""


class LLMSignal(BaseModel):
    """One item of the model's JSON output. Extra fields (e.g. a probability or score) make the output invalid."""

    model_config = ConfigDict(extra="forbid")
    signal_type: SignalType
    signal_class: SignalClass
    evidence_quote: str
    event_date: date | None
    status: Literal["confirmed", "attributed", "speculative"]
    subject_company: str


LLM_OUTPUT = TypeAdapter(list[LLMSignal])


def norm(text: str) -> str:
    return " ".join(text.split())


def redact(message: str, secret: str | None) -> str:
    return message.replace(secret, "[REDACTED]") if secret else message


def check_models(client, models: list[str], secret: str | None = None, temperature: float | None = None) -> None:
    """One minimal call per model, with the same sampling settings as extraction.
    Raises ModelUnavailable (key redacted) instead of falling back to another model."""
    kwargs = {"temperature": temperature} if temperature is not None else {}
    for model in models:
        try:
            client.messages.create(model=model, max_tokens=16, messages=[{"role": "user", "content": "Reply OK"}], **kwargs)
        except (anthropic.NotFoundError, anthropic.PermissionDeniedError, anthropic.BadRequestError) as exc:
            raise ModelUnavailable(redact(f"{model}: {type(exc).__name__}: {exc}", secret)) from None


def parse_output(raw: str) -> list[LLMSignal]:
    """Parse the model's text as a JSON list of LLMSignal (a ```json fence is tolerated). Raises ValueError."""
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        return LLM_OUTPUT.validate_python(json.loads(body))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid output: {type(exc).__name__}") from None


def post_check(item: LLMSignal, text: str, company_name: str, aliases: list[str]) -> str | None:
    """Deterministic checks; returns the rejection reason or None."""
    if norm(item.evidence_quote) not in norm(text):
        return "quote_not_in_text"
    if not (names_company(item.subject_company, aliases + [company_name])
            or norm(item.subject_company).lower() == norm(company_name).lower()):
        return "wrong_subject_company"
    if SIGNAL_CLASS_OF[item.signal_type] != item.signal_class:
        return "class_mismatch"
    if len(item.evidence_quote.split()) > MAX_QUOTE_WORDS:
        return "quote_over_25_words"
    return None


def call_model(client, model: str, system: str, company_name: str, text: str, temperature: float | None) -> dict:
    kwargs = {"temperature": temperature} if temperature is not None else {}
    response = client.messages.create(
        model=model, max_tokens=MAX_TOKENS, system=system,
        messages=[{"role": "user", "content": f"TARGET COMPANY: {company_name}\n\nARTICLE:\n{text}"}],
        **kwargs,
    )
    raw = "".join(block.text for block in response.content if block.type == "text")
    return {"raw": raw, "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
            "stop_reason": response.stop_reason}


def extract_document(client, model: str, system: str, evidence: Evidence, anchor: date, text: str,
                     company_name: str, aliases: list[str], cache_dir: Path | None = None,
                     temperature: float | None = None) -> dict:
    """Extract signals from one document. Returns {'signals', 'rejections', 'failure', 'attempts'}.

    Invalid output is retried once, then recorded as a failure. Raw responses are cached per attempt.
    """
    if not is_usable(evidence, anchor):
        raise ValueError(f"{evidence.evidence_id} is not usable at {anchor}; it must never be sent to the LLM")
    attempts, items = [], None
    for attempt in range(2):
        path = cache_dir / f"{evidence.evidence_id}.{attempt}.json" if cache_dir else None
        if path and path.exists():
            result = json.loads(path.read_text())
        else:
            result = call_model(client, model, system, company_name, text, temperature)
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(result, ensure_ascii=False))
        attempts.append(result)
        try:
            items = parse_output(result["raw"])
            break
        except ValueError:
            continue
    if items is None:
        return {"signals": [], "rejections": [], "failure": "invalid_output_after_retry", "attempts": attempts}
    signals, rejections = [], []
    for i, item in enumerate(items):
        reason = post_check(item, text, company_name, aliases)
        if reason:
            rejections.append({"evidence_id": evidence.evidence_id, "reason": reason, "item": item.model_dump(mode="json")})
            continue
        signals.append(Signal(
            signal_id=f"{model}-{evidence.evidence_id}-{i}", company_id=evidence.company_id,
            evidence_id=evidence.evidence_id, signal_class=item.signal_class, signal_type=item.signal_type,
            event_date=item.event_date, publication_date=evidence.publication_date,
            evidence_quote=item.evidence_quote, status=item.status, source_url=evidence.url, extraction_method="llm",
        ))
    return {"signals": signals, "rejections": rejections, "failure": None, "attempts": attempts}


def match(gold: dict[str, list[dict]], predicted: list[Signal]) -> dict:
    """One-to-one matching on (evidence_id, signal_type).

    Per (document, type): the first k predictions match the k gold signals (TP); if gold has none, the first
    prediction is a FP. Any further prediction of the same type in the same document is a duplicate, reported
    separately and counted as neither TP nor FP.
    """
    by_key: dict[tuple[str, str], list[Signal]] = {}
    for s in predicted:
        by_key.setdefault((s.evidence_id, s.signal_type), []).append(s)
    gold_count: dict[tuple[str, str], list[dict]] = {}
    for eid, items in gold.items():
        for g in items:
            gold_count.setdefault((eid, g["signal_type"]), []).append(g)
    tp, fp, dup, fn, pairs = 0, [], [], [], []
    for key in set(by_key) | set(gold_count):
        preds, golds = by_key.get(key, []), gold_count.get(key, [])
        n = min(len(preds), len(golds))
        tp += n
        pairs += list(zip(golds[:n], preds[:n]))
        if golds:
            dup.extend(preds[n:])
        elif preds:
            fp.append(preds[0])
            dup.extend(preds[1:])
        fn += [(key[0], g) for g in golds[n:]]
    n_pred = tp + len(fp)
    return {"tp": tp, "fp": fp, "fn": fn, "duplicates": dup, "pairs": pairs,
            "precision": tp / n_pred if n_pred else None,
            "recall": tp / (tp + len(fn)) if tp + len(fn) else None,
            "status_agreement": sum(g["status"] == p.status for g, p in pairs) / len(pairs) if pairs else None}

"""Core rules as pure functions: month arithmetic, point-in-time usability, window labels."""

from __future__ import annotations

import calendar
from datetime import date
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from deal_radar.schemas import Evidence, MatchedPair, Signal, Transaction

Label = Literal[
    "positive",
    "excluded_competing_ipo",
    "out_of_scope_public",
    "no_publicly_observed_transaction",
]


def add_months(d: date, n: int) -> date:
    """Shift d by n calendar months, keeping the day number.

    If that day does not exist in the target month, clamp to the month's last day
    (e.g. 2025-03-31 - 1 month -> 2025-02-28). This is the only month arithmetic
    used in the project.
    """
    month_index = d.year * 12 + (d.month - 1) + n
    year, month = divmod(month_index, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def is_usable(item: Evidence | Signal, prediction_date: date) -> bool:
    """Point-in-time rule: usable only if published strictly before the prediction date.

    Uses publication_date only (never event_date). Unknown publication date is not usable.
    """
    return item.publication_date is not None and item.publication_date < prediction_date


def snapshot_dates(anchor_date: date) -> list[date]:
    """Prediction dates 12, 6 and 3 months before the anchor (the deal's announcement date).

    Used for both companies in a matched pair.
    """
    return [add_months(anchor_date, -m) for m in (12, 6, 3)]


def label_window(transactions: list[Transaction], prediction_date: date) -> Label:
    """Label the 12-month window after prediction_date for one company's transactions.

    Window: prediction_date < announcement_date <= add_months(prediction_date, 12).
    Precedence:
      a. IPO announced on or before prediction_date -> out_of_scope_public.
      b. Earliest in-window event decides: change_of_control -> positive,
         ipo -> excluded_competing_ipo. A same-day tie counts as IPO-first (excluded),
         because a change of control is positive only if announced before any IPO.
      c. Nothing in the window -> no_publicly_observed_transaction.
    """
    if any(t.transaction_type == "ipo" and t.announcement_date <= prediction_date for t in transactions):
        return "out_of_scope_public"

    window_end = add_months(prediction_date, 12)
    in_window = [t for t in transactions if prediction_date < t.announcement_date <= window_end]
    if not in_window:
        return "no_publicly_observed_transaction"

    first_date = min(t.announcement_date for t in in_window)
    first_types = {t.transaction_type for t in in_window if t.announcement_date == first_date}
    if "ipo" in first_types:
        return "excluded_competing_ipo"
    return "positive"


def usable_pairs(pairs: list[MatchedPair]) -> list[MatchedPair]:
    """Keep only pairs whose control is verified; unresolved controls are never used."""
    return [p for p in pairs if p.control_status == "verified"]

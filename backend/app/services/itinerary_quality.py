"""Deterministic itinerary quality analysis.

Pure functions — no LLM, no DB writes. This is the single source of objective
truth about how good a plan is. It powers two consumers that must never
disagree:

  1. the `review_itinerary` tool — the mirror the agent reasons against, and
  2. the `finalize_itinerary` gate — the hard stop that refuses to ship a plan
     with any *blocking* issue.

The agent owns every creative decision (what to search, what goes where, the
times). This module does NOT plan or reorder anything; it only reports facts
and flags problems so the agent is forced to keep iterating until the plan is
genuinely good.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as dt_date, time as dt_time
from typing import Any, Literal

# --- Classification ----------------------------------------------------------

Bucket = Literal["food", "shopping", "culture", "outdoor", "other"]

# Ordered most-specific-first; first matching bucket wins. Keywords are matched
# against the lowercased item_type + title, accent-insensitively enough for the
# Portuguese/English mix the providers return (restaurante, café, museu, etc.).
_BUCKET_KEYWORDS: list[tuple[Bucket, tuple[str, ...]]] = [
    ("food", (
        "restaur", "restaurante", "cafe", "café", "bar", "bakery", "padaria",
        "eatery", "bistro", "lanchonete", "comida", "food", "dining", "pub",
        "cafeteria", "doceria", "sorveteria", "gastronom", "churrascaria",
        "pizzaria", "cervejaria",
    )),
    ("shopping", (
        "shopping", "mall", "shop", "store", "loja", "market", "mercado",
        "feira", "outlet", "boutique", "galeria comercial",
    )),
    ("culture", (
        "museu", "museum", "gallery", "galeria", "church", "igreja", "historic",
        "histor", "landmark", "monument", "monumento", "theater", "theatre",
        "teatro", "cathedral", "catedral", "palace", "palacio", "palácio",
        "fort", "forte", "memorial", "cultural", "centro cultural", "exhibition",
        "exposic", "patrimonio", "patrimônio",
    )),
    ("outdoor", (
        "park", "parque", "beach", "praia", "garden", "jardim", "viewpoint",
        "mirante", "square", "praca", "praça", "plaza", "trail", "trilha",
        "lake", "lago", "river", "rio", "waterfall", "cachoeira", "zoo",
        "botanical", "botanico", "botânico", "boardwalk", "orla", "pier",
    )),
]


def classify_item(item: Any) -> Bucket:
    """Map an itinerary item to a coarse activity bucket from its type/title."""
    haystack = f"{getattr(item, 'item_type', '') or ''} {getattr(item, 'title', '') or ''}".lower()
    for bucket, keywords in _BUCKET_KEYWORDS:
        if any(kw in haystack for kw in keywords):
            return bucket
    return "other"


# --- Pace --------------------------------------------------------------------

def pace_minimum(pace: str | None) -> int:
    """Minimum item count per day for a given travel pace.

    Mirrors the pace buckets the prompt uses in central_mind._get_mode_instructions.
    """
    normalized = (pace or "balanced").strip().lower()
    if normalized in ("leve", "relaxed", "relaxado", "tranquilo"):
        return 4
    if normalized in ("intenso", "intensive", "fast", "rapido", "rápido"):
        return 6
    return 5


# --- Reports -----------------------------------------------------------------

@dataclass
class Issue:
    severity: Literal["blocking", "warning"]
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "message": self.message}


@dataclass
class DayReport:
    date: str
    item_count: int
    bucket_counts: dict[str, int]
    timeline: list[dict[str, Any]]
    longest_gap_min: int
    longest_hop_min: int
    issues: list[Issue] = field(default_factory=list)

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "blocking"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "item_count": self.item_count,
            "bucket_counts": self.bucket_counts,
            "timeline": self.timeline,
            "longest_gap_min": self.longest_gap_min,
            "longest_hop_min": self.longest_hop_min,
            "issues": [i.as_dict() for i in self.issues],
            "blocking_count": len(self.blocking),
            "warning_count": len(self.warnings),
        }


# Thresholds (minutes)
_LUNCH_START, _LUNCH_END = dt_time(11, 30), dt_time(14, 30)
_DINNER_START, _DINNER_END = dt_time(18, 30), dt_time(22, 0)
_MAX_GAP_MIN = 90
_MAX_HOP_MIN = 25
_MAX_CONSECUTIVE_FOOD = 2  # 3+ in a row is blocking


def _minutes(t: dt_time) -> int:
    return t.hour * 60 + t.minute


def _is_food_in_window(bucket: Bucket, start: dt_time, win_start: dt_time, win_end: dt_time) -> bool:
    return bucket == "food" and win_start <= start <= win_end


def analyze_day(
    items: list[Any],
    pace: str | None = None,
    *,
    repeated_titles: set[str] | None = None,
) -> DayReport:
    """Analyze a single day's items and flag blocking/warning issues.

    `repeated_titles` is the set of (lowercased) titles that appear on more than
    one day across the whole itinerary; any such title on this day is flagged as
    a repeat. Passed in by analyze_itinerary so this stays a pure function.
    """
    repeated_titles = repeated_titles or set()
    ordered = sorted(items, key=lambda x: x.start_time)
    buckets = [classify_item(it) for it in ordered]

    bucket_counts: dict[str, int] = defaultdict(int)
    for b in buckets:
        bucket_counts[b] += 1

    timeline = [
        {
            "title": it.title,
            "start": it.start_time.strftime("%H:%M"),
            "end": it.end_time.strftime("%H:%M"),
            "bucket": b,
            "travel_min": getattr(it, "travel_time_min", 0) or 0,
        }
        for it, b in zip(ordered, buckets)
    ]

    # Gaps between consecutive items, and the worst travel hop.
    longest_gap = 0
    for a, b in zip(ordered, ordered[1:]):
        gap = _minutes(b.start_time) - _minutes(a.end_time)
        longest_gap = max(longest_gap, gap)
    longest_hop = max((getattr(it, "travel_time_min", 0) or 0 for it in ordered), default=0)

    issues: list[Issue] = []
    day_str = ordered[0].date.isoformat() if ordered else "?"

    # --- Blocking issues ---
    has_lunch = any(_is_food_in_window(b, it.start_time, _LUNCH_START, _LUNCH_END) for it, b in zip(ordered, buckets))
    has_dinner = any(_is_food_in_window(b, it.start_time, _DINNER_START, _DINNER_END) for it, b in zip(ordered, buckets))
    has_anchor = bucket_counts["culture"] > 0 or bucket_counts["outdoor"] > 0

    if not has_lunch:
        issues.append(Issue("blocking", "no_lunch", "Dia sem almoço (nenhum restaurante entre 11:30 e 14:30)."))
    if not has_dinner:
        issues.append(Issue("blocking", "no_dinner", "Dia sem jantar (nenhum restaurante entre 18:30 e 22:00)."))
    if not has_anchor:
        issues.append(Issue(
            "blocking", "no_anchor",
            "Dia sem âncora cultural ou ao ar livre (nenhum museu, marco histórico, parque ou praia). "
            "Busque e adicione um ponto de interesse principal.",
        ))

    # 3+ consecutive food items.
    run = 0
    food_cluster = False
    for b in buckets:
        run = run + 1 if b == "food" else 0
        if run > _MAX_CONSECUTIVE_FOOD:
            food_cluster = True
            break
    if food_cluster:
        issues.append(Issue(
            "blocking", "consecutive_food",
            "Três ou mais paradas de comida em sequência. Intercale com atrações, passeios ou cultura.",
        ))

    minimum = pace_minimum(pace)
    if len(ordered) < minimum:
        issues.append(Issue(
            "blocking", "too_few_items",
            f"Apenas {len(ordered)} atividade(s); o ritmo pede ao menos {minimum}.",
        ))

    repeats = sorted({it.title for it in ordered if it.title.strip().lower() in repeated_titles})
    if repeats:
        issues.append(Issue(
            "blocking", "repeated_place",
            f"Lugar(es) repetido(s) de outro dia: {', '.join(repeats)}.",
        ))

    # --- Warning issues ---
    if longest_gap > _MAX_GAP_MIN:
        issues.append(Issue("warning", "large_gap", f"Intervalo de {longest_gap} min entre paradas (> {_MAX_GAP_MIN} min)."))
    if longest_hop > _MAX_HOP_MIN:
        issues.append(Issue("warning", "zigzag", f"Deslocamento de {longest_hop} min entre paradas (> {_MAX_HOP_MIN} min); evite ziguezague."))
    for a, b in zip(buckets, buckets[1:]):
        if a == b and a in ("shopping", "culture"):
            label = "compras" if a == "shopping" else "atividades culturais"
            issues.append(Issue("warning", f"consecutive_{a}", f"Duas {label} em sequência; varie o tipo de parada."))
            break

    return DayReport(
        date=day_str,
        item_count=len(ordered),
        bucket_counts=dict(bucket_counts),
        timeline=timeline,
        longest_gap_min=longest_gap,
        longest_hop_min=longest_hop,
        issues=issues,
    )


def analyze_itinerary(trip: Any, active: Any, pace: str | None = None) -> dict[str, Any]:
    """Analyze a full itinerary across every trip day (start_date..end_date).

    A trip day with no items is itself a blocking issue. Returns a dict that is
    safe to hand straight back to the agent as a tool result.
    """
    items_by_day: dict[dt_date, list[Any]] = defaultdict(list)
    if active and active.items:
        for item in active.items:
            items_by_day[item.date].append(item)

    # Titles that appear on more than one day → repeats.
    title_days: dict[str, set[dt_date]] = defaultdict(set)
    for day, items in items_by_day.items():
        for it in items:
            title_days[it.title.strip().lower()].add(day)
    repeated_titles = {title for title, days in title_days.items() if len(days) > 1 and title}

    day_reports: list[dict[str, Any]] = []
    blocking_count = 0
    warning_count = 0

    current = trip.start_date
    while current <= trip.end_date:
        items = items_by_day.get(current, [])
        if not items:
            report = {
                "date": current.isoformat(),
                "item_count": 0,
                "bucket_counts": {},
                "timeline": [],
                "longest_gap_min": 0,
                "longest_hop_min": 0,
                "issues": [Issue("blocking", "empty_day", "Dia sem nenhuma atividade planejada.").as_dict()],
                "blocking_count": 1,
                "warning_count": 0,
            }
            blocking_count += 1
        else:
            day_report = analyze_day(items, pace, repeated_titles=repeated_titles)
            report = day_report.as_dict()
            blocking_count += report["blocking_count"]
            warning_count += report["warning_count"]
        day_reports.append(report)
        current = current.fromordinal(current.toordinal() + 1)

    return {
        "days": day_reports,
        "blocking_count": blocking_count,
        "warning_count": warning_count,
        "is_finalizable": blocking_count == 0,
    }

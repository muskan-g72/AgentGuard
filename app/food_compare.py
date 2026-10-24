"""Three parallel, read-only comparison sources; no staging or order capability."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError

from guard.food.models import FoodCriteria, FoodMessage, FoodOption, PLATFORMS, Platform, RankedOption, RejectedOption
from guard.food.ranking import rank_options

Reader = Callable[[FoodCriteria], list[FoodOption | dict]]


class ComparisonFailure(FoodMessage):
    platform: Platform
    reason: str


class ComparisonReport(FoodMessage):
    complete: bool
    ranked: list[RankedOption]
    rejected: list[RejectedOption]
    failures: list[ComparisonFailure]
    winner: RankedOption | None


def compare_platforms(criteria: FoodCriteria | dict, readers: Mapping[Platform, Reader]) -> ComparisonReport:
    """Compare all three sources, selecting no winner if any source fails.

    Each injected reader must be read-only and set a deadline on its own I/O.
    This starter contains no live platform adapters or browser action tools.
    """
    criteria = FoodCriteria.model_validate(criteria)
    if set(readers) != set(PLATFORMS):
        raise ValueError("Comparison requires exactly FoodHub, QuickBite, and DineDash readers")
    options, failures = [], []
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="food-compare") as pool:
        pending = {platform: pool.submit(readers[platform], criteria.model_copy(deep=True)) for platform in PLATFORMS}
        for platform in PLATFORMS:
            try:
                rows = pending[platform].result()
                if not isinstance(rows, list):
                    raise ValueError("Comparison must return a list")
                validated = [FoodOption.model_validate(row) for row in rows]
                if any(row.platform != platform for row in validated):
                    raise ValueError("Comparison source disagrees with option platform")
                options.extend(validated)
            except Exception as error:
                # Never put vendor bodies, credentials, or untrusted exception
                # messages into an audit-friendly comparison report.
                kind = "invalid data" if isinstance(error, (ValidationError, ValueError)) else "reader failure"
                failures.append(ComparisonFailure(platform=platform, reason=f"Comparison stopped: {kind} ({type(error).__name__})."))
    ranking = rank_options(criteria, options)
    complete = not failures
    return ComparisonReport(complete=complete, ranked=ranking.ranked, rejected=ranking.rejected, failures=failures,
                            winner=ranking.ranked[0] if complete and ranking.ranked else None)

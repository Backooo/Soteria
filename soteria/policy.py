"""The assessor as a rule engine. Sees only projections.

This file knows no case ID and no stored ground truth -- it receives traffic
lights (ampel), thresholds (schwelle) and flags and decides from them.
`tests/test_policy.py` checks this by searching the source for case names. If
there were an `if case_id == "s3"` anywhere here, the hit rate would be a number
about itself.

**Honesty:** the order of the rules was written against the known cases. Their
hit rate is therefore a consistency check, not a claim. The rate over the
holdout cases, which the data track does not reveal, is the only number that
claims anything.

The order of the rules is the order of irreversibility:
safety before feasibility before liability before cost.
"""

from __future__ import annotations

from typing import Any, Mapping

# The order in which the assessor asks: (field, reason).
# `market_sensitive` is deliberately second: the quarantine must take effect
# before anything else happens.
ASK_PLAN: tuple[tuple[str, str], ...] = (
    ("temperature_curve", "safety"),
    ("market_sensitive", "confidentiality"),
    ("cargo_class", "safety"),
    ("route_weakness", "feasibility"),
    ("alt_route_status", "feasibility"),
    ("road_access", "feasibility"),
    ("locality_class", "safety"),
    ("replacement_available", "feasibility"),
    ("cooling_required", "safety"),
    ("customer_stock", "time"),
    ("customer_urgency", "time"),
    ("contract_penalty", "liability"),
    ("contract_deadline_h", "liability"),
)


def _is(sheets: Mapping[str, Any], field: str, *values: Any) -> bool:
    return sheets.get(field) in values


def decide(
    sheets: Mapping[str, Any],
    flags: tuple[str, ...],
    missing: tuple[str, ...],
    situation: Mapping[str, Any] | None = None,
) -> tuple[tuple[str, ...], str]:
    """Choose measures from traffic lights, thresholds, flags and the shared report.

    `sheets`    field name -> projected value, as it came from the node.
    `flags`     situation markers, derived from the data.
    `missing`   parties that did not answer.
    `situation` the report everyone may see: `track_blocked`,
                `train_operational`, `severity`. Not a secret -- the driver
                reported it.
    """
    sit = dict(situation or {})
    blocked = bool(sit.get("track_blocked"))
    operational = str(sit.get("train_operational", "normal"))
    immobilized = operational == "immobilized"
    inhabited = _is(sheets, "locality_class", "village", "town_edge", "dense_urban")

    # 1 Hazmat damaged and the train cannot move. Not knowing about a possible
    #   leak is itself the reason to stop and report -- all the more so next to
    #   residential buildings.
    if "hazmat" in flags and (immobilized or inhabited):
        return ("stop_train", "notify_authority"), "safety"

    # 2 Line impassable. No measure on the train helps, it has to go around --
    #   and only if there is a diversion.
    if blocked or _is(sheets, "route_weakness", "rot"):
        if _is(sheets, "alt_route_status", "available", "available_short", "long_detour"):
            return ("alt_transport",), "feasibility"
        # No diversion. Transshipment needs a road.
        if _is(sheets, "road_access", "gruen", "gelb") and not _is(
            sheets, "replacement_available", "rot"
        ):
            return ("reload",), "feasibility"
        return ("hold", "contact"), "feasibility"

    # 3 Cargo outside its window. Transship only if a replacement exists.
    if _is(sheets, "temperature_curve", "rot"):
        if _is(sheets, "replacement_available", "gruen", "gelb"):
            return ("cool", "reload"), "safety"
        return ("cool", "hold"), "safety"

    # 4 A party is missing and the cargo is perishable: act conservatively and
    #   name the gap. Not deciding is not an option.
    if missing and "perishable" in flags:
        return ("cool", "hold"), "missing_data"

    # 5 Danger to life or critical urgency at the customer, and the deadline is
    #   getting tight. The assessor does not know which customer -- only how urgent.
    if _is(sheets, "customer_urgency", "rot") and _is(sheets, "contract_deadline_h", "below"):
        if _is(sheets, "replacement_available", "gruen"):
            return ("reload",), "time"
        return ("contact",), "time"

    # 6 Contract penalty above the threshold, and transshipment is feasible. The
    #   assessor never learns how high it is -- only that it is above.
    if _is(sheets, "contract_penalty", "above") and not _is(
        sheets, "replacement_available", "rot"
    ):
        return ("reload",), "liability"

    # 7 Cooling degraded, but the goods are still in their window and the
    #   customer has stock. Cooling is cheap and keeps every option open; an
    #   expensive measure would be waste here. This is the rule the traffic
    #   light on stock was invented for.
    if _is(sheets, "temperature_curve", "gelb") and _is(sheets, "cooling_required", True):
        if _is(sheets, "customer_stock", "gruen"):
            return ("cool",), "safety"
        return ("cool", "hold"), "safety"

    # 8 Everything green and the train is running. `sheets and not missing` is
    #   essential: without answers `temperature_curve` is also None, and "nothing
    #   known" must not look like "no refrigerated cargo".
    if (
        sheets
        and not missing
        and operational == "normal"
        and not blocked
        and _is(sheets, "temperature_curve", "gruen", None)
    ):
        return ("proceed",), "cost"

    # 9 Nothing reliable. Holding is the most reversible measure.
    return ("hold",), ("missing_data" if (missing or not sheets) else "time")

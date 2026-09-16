"""The rule engine sees only projections -- never a number, never a case ID.

That is the integrity condition of this file. Otherwise the hit rate would be a
number about itself.
"""

import inspect

from soteria import policy
from soteria.envelope import MEASURE, REASON


def _code_strings_and_names(module) -> set[str]:
    """All identifiers and literals of the module -- without docstrings and comments.

    A raw-text scan would report the warning in the docstring itself as a hit.
    The code is checked, not the prose about it.
    """
    import ast

    tree = ast.parse(inspect.getsource(module))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                out.add(node.value)
        elif isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            out.update(a.name for a in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                out.add(node.module)
    return out


def test_decide_cannot_see_the_case_id_or_the_truth():
    params = set(inspect.signature(policy.decide).parameters)
    assert params == {"sheets", "flags", "missing", "situation"}
    tokens = _code_strings_and_names(policy)
    for forbidden in ("case_id", "truth", "s1", "s2", "s3", "h1", "load_case",
                      "load_scenario", "cases", "party_id", "display_name"):
        assert forbidden not in tokens, (
            f"policy.py uses {forbidden!r} in code -- a rule could then recognise "
            "a single case, and the hit rate would be worthless"
        )


def test_damaged_hazmat_on_an_immobilized_train_stops_and_notifies():
    measures, reason = policy.decide(
        {"locality_class": "town_edge"}, ("hazmat",), (),
        {"train_operational": "immobilized", "track_blocked": True},
    )
    assert set(measures) == {"stop_train", "notify_authority"}
    assert reason == "safety"


def test_hazmat_next_to_housing_stops_even_if_the_train_could_move():
    measures, _ = policy.decide(
        {"locality_class": "dense_urban"}, ("hazmat",), (),
        {"train_operational": "restricted", "track_blocked": False},
    )
    assert "stop_train" in measures


def test_hazmat_in_open_country_on_a_rolling_train_does_not_escalate():
    """Hazmat alone is no reason for tier 3. The situation makes the difference."""
    measures, _ = policy.decide(
        {"locality_class": "open_country", "temperature_curve": "gruen"}, ("hazmat",), (),
        {"train_operational": "normal", "track_blocked": False},
    )
    assert "stop_train" not in measures


def test_a_blocked_track_with_a_detour_goes_around():
    measures, reason = policy.decide(
        {"route_weakness": "gelb", "alt_route_status": "long_detour", "temperature_curve": "gelb"},
        ("perishable",), (), {"track_blocked": True, "train_operational": "restricted"},
    )
    assert measures == ("alt_transport",)
    assert reason == "feasibility"


def test_a_blocked_track_without_a_detour_reloads_if_there_is_a_road():
    measures, _ = policy.decide(
        {"alt_route_status": "none", "road_access": "gruen", "replacement_available": "gruen"},
        (), (), {"track_blocked": True, "train_operational": "restricted"},
    )
    assert measures == ("reload",)


def test_a_blocked_track_with_neither_detour_nor_road_holds_and_contacts():
    measures, _ = policy.decide(
        {"alt_route_status": "none", "road_access": "rot"},
        (), (), {"track_blocked": True, "train_operational": "immobilized"},
    )
    assert set(measures) == {"hold", "contact"}


def test_a_red_temperature_with_replacement_nearby_cools_and_reloads():
    measures, reason = policy.decide(
        {"temperature_curve": "rot", "replacement_available": "gruen", "customer_stock": "rot"},
        ("perishable",), (), {"train_operational": "normal"},
    )
    assert set(measures) == {"cool", "reload"}
    assert reason == "safety"


def test_a_red_temperature_without_replacement_cools_and_holds():
    measures, _ = policy.decide(
        {"temperature_curve": "rot", "replacement_available": "rot"}, ("perishable",), (),
        {"train_operational": "normal"},
    )
    assert set(measures) == {"cool", "hold"}


def test_a_missing_party_with_perishable_cargo_falls_back_conservatively():
    measures, reason = policy.decide(
        {"temperature_curve": "gelb", "replacement_available": "gruen"},
        ("perishable",), ("customer_c1_frischemarkt",), {"train_operational": "normal"},
    )
    assert set(measures) == {"cool", "hold"}
    assert reason == "missing_data"


def test_a_critical_customer_against_a_tight_deadline_reloads():
    measures, reason = policy.decide(
        {"temperature_curve": "gruen", "customer_urgency": "rot",
         "contract_deadline_h": "below", "replacement_available": "gruen"},
        (), (), {"train_operational": "normal"},
    )
    assert measures == ("reload",)
    assert reason == "time"


def test_a_penalty_above_the_threshold_reloads():
    measures, reason = policy.decide(
        {"temperature_curve": "gruen", "contract_penalty": "above",
         "replacement_available": "gruen", "customer_stock": "gelb"},
        (), (), {"train_operational": "normal"},
    )
    assert measures == ("reload",)
    assert reason == "liability"


def test_an_amber_temperature_with_full_stock_only_cools():
    """The traffic light on stock prevents the expensive measure."""
    measures, reason = policy.decide(
        {"temperature_curve": "gelb", "cooling_required": True, "customer_stock": "gruen",
         "contract_penalty": "below"},
        ("perishable",), (), {"train_operational": "normal", "track_blocked": False},
    )
    assert measures == ("cool",)
    assert reason == "safety"


def test_an_amber_temperature_with_thin_stock_also_holds():
    measures, _ = policy.decide(
        {"temperature_curve": "gelb", "cooling_required": True, "customer_stock": "rot",
         "contract_penalty": "below"},
        ("perishable",), (), {"train_operational": "normal"},
    )
    assert set(measures) == {"cool", "hold"}


def test_everything_green_on_a_rolling_train_proceeds():
    measures, reason = policy.decide(
        {"temperature_curve": "gruen", "customer_stock": "gruen", "contract_penalty": "below"},
        (), (), {"train_operational": "normal", "track_blocked": False},
    )
    assert measures == ("proceed",)
    assert reason == "cost"


def test_knowing_nothing_holds():
    measures, reason = policy.decide({}, (), ("a", "b"), {})
    assert measures == ("hold",)
    assert reason == "missing_data"


def test_every_returned_measure_and_reason_is_from_the_value_list():
    cases = [
        ({"locality_class": "town_edge"}, ("hazmat",), (), {"train_operational": "immobilized"}),
        ({"alt_route_status": "none", "road_access": "rot"}, (), (), {"track_blocked": True}),
        ({}, (), ("x",), {}),
        ({"temperature_curve": "gruen"}, (), (), {"train_operational": "normal"}),
        ({"temperature_curve": "rot", "replacement_available": "rot"}, (), (), {}),
    ]
    for sheets, flags, missing, sit in cases:
        measures, reason = policy.decide(sheets, flags, missing, sit)
        assert set(measures) <= set(MEASURE), measures
        assert reason in REASON, reason
        assert len(set(measures)) == len(measures)

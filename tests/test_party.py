"""The party node hands out only projections -- and cannot do more.

Three independent bolts are checked here:
  1. the node does not have the others' data,
  2. the matrix projects,
  3. the transport carries only scalars.
"""

import dataclasses

import pytest

from soteria.cases import Case, _worst, load_case, raw_records_for_party
from soteria.envelope import EnvelopeError
from soteria.party_app import answer_ask
from soteria.wire import SCALARS, fact_record, read_reply


def s(cid: str = "s3") -> Case:
    return load_case(cid)


# --- bolt 1: the node does not have it ----------------------------------


def test_a_customer_node_never_loads_another_customers_contract():
    """Row-level protection by the federation, not field-level protection by the matrix."""
    case = dataclasses.replace(
        s("s3"),
        sources={
            **s("s3").sources,
            "customers": [
                "data/parties/customer_c2_stadtklinik.json",
                "data/parties/customer_c3_chemiewerk.json",
            ],
            "contracts": ["data/contracts/contract_k2.json", "data/contracts/contract_k3.json"],
        },
        federations=s("s3").federations
        + ({"party_id": "customer_c2_stadtklinik", "party_type": "customer",
            "speaks_as": ["customer"]},),
    )
    c2 = raw_records_for_party(case, "customer_c2_stadtklinik")
    c3 = raw_records_for_party(case, "customer_c3_chemiewerk")
    # Each sees exactly one penalty -- its own, and they differ.
    assert c2["contract"]["contract_penalty"] == 140_000
    assert c3["contract"]["contract_penalty"] == 9_000
    assert c2["contract"]["contract_penalty"] != c3["contract"]["contract_penalty"]


def test_a_customer_node_holds_no_network_and_no_market_flag():
    records = raw_records_for_party(s(), "customer_c3_chemiewerk")
    assert "network" not in records
    assert "carrier" not in records
    flat = {f for block in records.values() for f in block}
    assert "route_weakness" not in flat
    assert "market_sensitive" not in flat


def test_a_supplier_node_holds_no_customer_record():
    records = raw_records_for_party(s(), "supplier_nordfrost")
    assert "customer" not in records
    reply = answer_ask(s(), "supplier_nordfrost", "assessor", "customer_stock", "time")
    assert reply["code"] == "unknown_field"


def test_the_carrier_node_holds_only_the_affected_wagons_cargo():
    """The consignment note of the whole train does not belong in the incident."""
    records = raw_records_for_party(s(), "carrier_rheinrail")
    affected = set(s().report["affected_wagons"])
    assert set(records["train"]["cargo_class"]) == affected
    assert len(affected) < s().report["wagon_count"]


# --- bolt 2: the matrix projects ----------------------------------------


def test_the_assessor_gets_a_traffic_light_not_a_number():
    reply = answer_ask(s(), "customer_c3_chemiewerk", "assessor", "customer_stock", "time")
    assert reply["value"] in {"gruen", "gelb", "rot"}
    assert reply["visibility"] == "ampel"
    for number in ("1.0", "6.0", "5.0"):
        assert number not in str(reply["value"])


def test_the_assessor_gets_a_threshold_not_a_sum():
    reply = answer_ask(s(), "carrier_rheinrail", "assessor", "contract_penalty", "liability")
    assert reply["value"] in {"above", "below"}
    assert "9000" not in str(reply["value"])


def test_a_held_field_the_asker_may_not_see_is_not_in_matrix_not_unknown():
    """The difference is half the demo.

    `unknown_field`  -- the node does not hold it at all.
    `not_in_matrix`  -- it holds it, but may not show it to this asker.
    """
    held_but_hidden = answer_ask(
        s(), "customer_c3_chemiewerk", "assessor", "contact_person", "time"
    )
    assert held_but_hidden["code"] == "not_in_matrix"
    not_held = answer_ask(s(), "supplier_nordfrost", "assessor", "contact_person", "time")
    assert not_held["code"] == "unknown_field"


def test_the_intake_may_have_the_contact_the_assessor_may_not():
    for_intake = answer_ask(s(), "customer_c3_chemiewerk", "intake", "contact_person", "time")
    assert for_intake["code"] == ""
    for_assessor = answer_ask(s(), "customer_c3_chemiewerk", "assessor", "contact_person", "time")
    assert for_assessor["code"] == "not_in_matrix"


def test_the_supplier_asking_the_customer_for_stock_is_refused_by_the_matrix():
    reply = answer_ask(s(), "customer_c3_chemiewerk", "supplier", "customer_stock", "feasibility")
    assert reply["code"] == "not_in_matrix"
    assert reply["value"] == ""


# --- bolt 3: the transport carries only scalars -------------------------


def test_every_answer_on_the_wire_is_a_scalar():
    case = s()
    for party_id in case.party_ids:
        for field in ("temperature_curve", "cargo_class", "customer_stock",
                      "replacement_available", "contract_penalty", "market_sensitive"):
            reply = answer_ask(case, party_id, "assessor", field, "safety")
            assert isinstance(reply["value"], SCALARS), f"{party_id}/{field}"


def test_the_transport_refuses_a_non_scalar_even_if_the_matrix_allowed_it():
    with pytest.raises(EnvelopeError) as exc:
        fact_record("intake", "temperature_curve", "raw", {"current_c": 12.4})
    assert exc.value.code == "bad_value"
    assert "scalar" in exc.value.detail


def test_an_object_valued_field_crosses_only_as_a_scalar_rendering():
    """A raw object cannot cross the wire -- never, for anyone.

    `ConfigRecord` only carries scalars. A field whose raw form is an object
    therefore travels as a line (`curve_line`, `contact_line`). That weakens
    nothing: the matrix still decides WHO gets it -- the supplier the curve, the
    assessor only the traffic light.
    """
    for_supplier = answer_ask(s(), "carrier_rheinrail", "supplier", "temperature_curve", "safety")
    assert for_supplier["code"] == ""
    assert isinstance(for_supplier["value"], str)
    assert "11.8" in for_supplier["value"]          # the supplier may see the number

    for_assessor = answer_ask(s(), "carrier_rheinrail", "assessor", "temperature_curve", "safety")
    assert for_assessor["value"] == "rot"
    assert "11.8" not in str(for_assessor["value"])  # the assessor may not

    for_legal = answer_ask(s(), "carrier_rheinrail", "legal", "temperature_curve", "safety")
    assert for_legal["code"] == "not_in_matrix"      # and the contract agent not at all


# --- multi-valued fields ------------------------------------------------


def test_the_worst_scope_wins_and_is_named():
    reply = answer_ask(s(), "carrier_rheinrail", "assessor", "temperature_curve", "safety")
    assert reply["value"] == "rot"
    assert reply["scope"] == "W02"      # the pharma wagon, 55 min outside


def test_worst_ranks_traffic_lights_thresholds_and_flags():
    assert _worst({"a": "gruen", "b": "rot", "c": "gelb"}) == ("b", "rot")
    assert _worst({"a": "below", "b": "above"}) == ("b", "above")
    assert _worst({"a": False, "b": True}) == ("b", True)
    # Not rankable: the first reference unit, so the meaning does not flip.
    assert _worst({"a": "regulated", "b": "general"}) == ("a", "regulated")
    with pytest.raises(EnvelopeError):
        _worst({})


def test_a_missing_replacement_is_the_worst_case_and_its_scope_is_coarsened():
    """The reference unit names the most critical cargo class -- but only as
    coarsely as the matrix grants the asker. `hazmat` becomes `hazardous`."""
    for_assessor = answer_ask(
        s(), "supplier_nordfrost", "assessor", "replacement_available", "feasibility"
    )
    assert for_assessor["value"] == "rot"
    assert for_assessor["scope"] == "hazardous"
    assert for_assessor["scope"] != "hazmat"

    # The supplier knows its own goods at fine resolution.
    for_supplier = answer_ask(
        s(), "supplier_nordfrost", "supplier", "replacement_available", "feasibility"
    )
    assert for_supplier["scope"] == "hazmat"


# --- outages and misconfiguration ---------------------------------------


def test_an_offline_party_refuses_with_quota_not_with_silence():
    case = dataclasses.replace(s(), offline_parties=("customer_c3_chemiewerk",))
    reply = answer_ask(case, "customer_c3_chemiewerk", "assessor", "customer_stock", "time")
    assert reply["code"] == "quota"


def test_an_undeclared_field_is_a_typed_refusal():
    reply = answer_ask(s(), "carrier_rheinrail", "assessor", "salary", "cost")
    assert reply["code"] == "unknown_field"


def test_a_party_that_is_not_in_the_case_is_refused():
    with pytest.raises(EnvelopeError) as exc:
        s().party_type("customer_c1_frischemarkt")   # belongs to s1, not s3
    assert exc.value.code == "unknown_role"


def test_the_case_report_carries_no_raw_cargo_and_no_person():
    report = s().report
    assert report["cargo_classes_coarse"] == ["cooled", "general", "hazardous", "regulated"]
    blob = str(report)
    for secret in ("hazmat", "pharmaceutical", "Varga", "TF-1108"):
        assert secret not in blob, f"{secret!r} is in the shared report"


def test_flags_are_derived_from_the_data_not_hand_maintained():
    assert "hazmat" in s("s3").flags          # because there is a hazmat wagon in the train
    assert "market_sensitive" in s("s3").flags
    assert "hazmat" not in s("s1").flags
    assert "market_sensitive" not in s("s1").flags


def test_an_unconfirmed_truth_is_reported_as_unconfirmed():
    """REGRESSION: `_public` dropped `truth._status`, so every ground truth counted
    as confirmed -- including the ones the engine track had only proposed."""
    case = s("s1")
    assert case.truth_status.startswith("PROPOSAL")
    assert case.truth_confirmed is False
    confirmed = dataclasses.replace(case, truth_status="confirmed 16.09.")
    assert confirmed.truth_confirmed is True

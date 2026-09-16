"""Der Parteiknoten gibt nur Projektionen heraus -- und kann nicht mehr.

Drei unabhaengige Riegel werden hier geprueft:
  1. der Knoten hat die Daten der anderen nicht,
  2. die Matrix projiziert,
  3. der Transport traegt nur Skalare.
"""

import dataclasses

import pytest

from soteria.cases import Case, _worst, load_case, raw_records_for_party
from soteria.envelope import EnvelopeError
from soteria.party_app import answer_ask
from soteria.wire import SCALARS, fact_record, read_reply


def s(cid: str = "s3") -> Case:
    return load_case(cid)


# --- Riegel 1: der Knoten hat es nicht ----------------------------------


def test_a_customer_node_never_loads_another_customers_contract():
    """Zeilenschutz durch die Foederation, nicht Feldschutz durch die Matrix."""
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
    # Jeder sieht genau eine Strafe -- seine eigene, und sie unterscheiden sich.
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
    """Der Frachtbrief des ganzen Zuges gehoert nicht in den Vorfall."""
    records = raw_records_for_party(s(), "carrier_rheinrail")
    affected = set(s().report["affected_wagons"])
    assert set(records["train"]["cargo_class"]) == affected
    assert len(affected) < s().report["wagon_count"]


# --- Riegel 2: die Matrix projiziert ------------------------------------


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
    """Der Unterschied ist die halbe Demo.

    `unknown_field`  -- der Knoten fuehrt es gar nicht.
    `not_in_matrix`  -- er fuehrt es, darf es diesem Frager aber nicht zeigen.
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


# --- Riegel 3: der Transport traegt nur Skalare -------------------------


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
    """Ein Rohobjekt kann den Draht nicht ueberqueren -- nie, fuer niemanden.

    `ConfigRecord` traegt nur Skalare. Ein Feld, dessen Rohform ein Objekt ist,
    reist daher als Zeile (`curve_line`, `contact_line`). Das schwaecht nichts
    ab: die Matrix entscheidet weiter, WER sie bekommt -- der Zulieferer die
    Kurve, der Bewerter nur die Ampel.
    """
    for_supplier = answer_ask(s(), "carrier_rheinrail", "supplier", "temperature_curve", "safety")
    assert for_supplier["code"] == ""
    assert isinstance(for_supplier["value"], str)
    assert "11.8" in for_supplier["value"]          # der Zulieferer darf die Zahl sehen

    for_assessor = answer_ask(s(), "carrier_rheinrail", "assessor", "temperature_curve", "safety")
    assert for_assessor["value"] == "rot"
    assert "11.8" not in str(for_assessor["value"])  # der Bewerter nicht

    for_legal = answer_ask(s(), "carrier_rheinrail", "legal", "temperature_curve", "safety")
    assert for_legal["code"] == "not_in_matrix"      # und der Vertragsagent gar nicht


# --- mehrwertige Felder -------------------------------------------------


def test_the_worst_scope_wins_and_is_named():
    reply = answer_ask(s(), "carrier_rheinrail", "assessor", "temperature_curve", "safety")
    assert reply["value"] == "rot"
    assert reply["scope"] == "W02"      # der Pharmawagen, 55 min ausserhalb


def test_worst_ranks_traffic_lights_thresholds_and_flags():
    assert _worst({"a": "gruen", "b": "rot", "c": "gelb"}) == ("b", "rot")
    assert _worst({"a": "below", "b": "above"}) == ("b", "above")
    assert _worst({"a": False, "b": True}) == ("b", True)
    # Nicht rangbar: die erste Bezugsgroesse, damit die Bedeutung nicht kippt.
    assert _worst({"a": "regulated", "b": "general"}) == ("a", "regulated")
    with pytest.raises(EnvelopeError):
        _worst({})


def test_a_missing_replacement_is_the_worst_case_for_hazmat():
    reply = answer_ask(s(), "supplier_nordfrost", "assessor", "replacement_available", "feasibility")
    assert reply["value"] == "rot"
    assert reply["scope"] == "hazmat"


# --- Ausfaelle und Fehlkonfiguration ------------------------------------


def test_an_offline_party_refuses_with_quota_not_with_silence():
    case = dataclasses.replace(s(), offline_parties=("customer_c3_chemiewerk",))
    reply = answer_ask(case, "customer_c3_chemiewerk", "assessor", "customer_stock", "time")
    assert reply["code"] == "quota"


def test_an_undeclared_field_is_a_typed_refusal():
    reply = answer_ask(s(), "carrier_rheinrail", "assessor", "salary", "cost")
    assert reply["code"] == "unknown_field"


def test_a_party_that_is_not_in_the_case_is_refused():
    with pytest.raises(EnvelopeError) as exc:
        s().party_type("customer_c1_frischemarkt")   # gehoert zu s1, nicht s3
    assert exc.value.code == "unknown_role"


def test_the_case_report_carries_no_raw_cargo_and_no_person():
    report = s().report
    assert report["cargo_classes_coarse"] == ["general", "hazardous", "perishable", "regulated"]
    blob = str(report)
    for secret in ("hazmat", "pharmaceutical", "Varga", "TF-1108"):
        assert secret not in blob, f"{secret!r} steht in der gemeinsamen Meldung"


def test_flags_are_derived_from_the_data_not_hand_maintained():
    assert "hazmat" in s("s3").flags          # weil ein Gefahrgutwagen im Zug ist
    assert "market_sensitive" in s("s3").flags
    assert "hazmat" not in s("s1").flags
    assert "market_sensitive" not in s("s1").flags

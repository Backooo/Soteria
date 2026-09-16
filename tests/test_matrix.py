"""Die Matrix haelt -- auch ueber Rollenketten hinweg."""

import pytest

from soteria.envelope import AMPEL, ROLES, EnvelopeError
from soteria.matrix import (
    DEFAULT_THRESHOLDS,
    FIELDS,
    RECORD_TYPES,
    fields_for,
    fields_held_by,
    holders,
    matrix_table,
    owners,
    project,
    visibility,
)


def test_every_field_declares_a_visibility_for_every_role():
    for name, fld in FIELDS.items():
        for role in ROLES:
            assert role in fld.visibility, f"{name} sagt nichts ueber {role}"


def test_supplier_never_sees_the_customers_stock():
    assert visibility("customer_stock", "supplier") == "none"
    with pytest.raises(EnvelopeError) as exc:
        project("customer_stock", 0.5, "supplier", DEFAULT_THRESHOLDS)
    assert exc.value.code == "not_in_matrix"


def test_assessor_sees_the_stock_only_as_a_traffic_light():
    assert visibility("customer_stock", "assessor") == "ampel"
    assert project("customer_stock", 0.5, "assessor", DEFAULT_THRESHOLDS) == "rot"
    assert project("customer_stock", 2.0, "assessor", DEFAULT_THRESHOLDS) == "gelb"
    assert project("customer_stock", 9.0, "assessor", DEFAULT_THRESHOLDS) == "gruen"


def test_the_customer_keeps_the_number_itself():
    assert project("customer_stock", 2.0, "customer", DEFAULT_THRESHOLDS) == 2.0


def test_assessor_sees_the_penalty_only_as_above_or_below():
    assert visibility("contract_penalty", "assessor") == "schwelle"
    assert project("contract_penalty", 80_000, "assessor", DEFAULT_THRESHOLDS) == "above"
    assert project("contract_penalty", 1_000, "assessor", DEFAULT_THRESHOLDS) == "below"
    assert "80" not in str(project("contract_penalty", 80_000, "assessor", DEFAULT_THRESHOLDS))


def test_legal_keeps_the_penalty_and_never_sees_the_stock():
    assert project("contract_penalty", 80_000, "legal", DEFAULT_THRESHOLDS) == 80_000
    assert visibility("customer_stock", "legal") == "none"


def test_route_weakness_reaches_the_assessor_and_nobody_else():
    assert visibility("route_weakness", "assessor") == "ampel"
    for role in ("intake", "legal", "supplier", "customer"):
        assert visibility("route_weakness", role) == "none"


def test_temperature_curve_becomes_a_traffic_light_for_the_assessor():
    hot = {"setpoint_c": 5.0, "current_c": 12.0, "limit_c": 8.0, "minutes_out": 45}
    warm = {"setpoint_c": 5.0, "current_c": 7.0, "limit_c": 8.0, "minutes_out": 10}
    cold = {"setpoint_c": 5.0, "current_c": 5.1, "limit_c": 8.0, "minutes_out": 0}
    assert project("temperature_curve", hot, "assessor", DEFAULT_THRESHOLDS) == "rot"
    assert project("temperature_curve", warm, "assessor", DEFAULT_THRESHOLDS) == "gelb"
    assert project("temperature_curve", cold, "assessor", DEFAULT_THRESHOLDS) == "gruen"
    assert project("temperature_curve", hot, "supplier", DEFAULT_THRESHOLDS) == hot


def test_cargo_class_reaches_the_assessor_only_coarsely():
    """Das Vokabular kommt vom Datenstrang: pharmaceutical, perishable, hazmat, general_goods."""
    assert project("cargo_class", "pharmaceutical", "assessor", DEFAULT_THRESHOLDS) == "regulated"
    assert project("cargo_class", "hazmat", "assessor", DEFAULT_THRESHOLDS) == "hazardous"
    assert project("cargo_class", "perishable", "assessor", DEFAULT_THRESHOLDS) == "perishable"
    assert project("cargo_class", "general_goods", "assessor", DEFAULT_THRESHOLDS) == "general"
    # Der Zulieferer behaelt die Ware selbst, nicht die Regulierungslage.
    assert project("cargo_class", "pharmaceutical", "supplier", DEFAULT_THRESHOLDS) == "pharmaceutical"
    assert visibility("cargo_class", "legal") == "none"


def test_replacement_availability_is_a_traffic_light_for_two_roles():
    near = {"available": True, "eta_min": 30}
    far = {"available": True, "eta_min": 600}
    none_ = {"available": False, "eta_min": 0}
    assert project("replacement_available", near, "assessor", DEFAULT_THRESHOLDS) == "gruen"
    assert project("replacement_available", far, "assessor", DEFAULT_THRESHOLDS) == "gelb"
    assert project("replacement_available", none_, "assessor", DEFAULT_THRESHOLDS) == "rot"
    assert project("replacement_available", near, "supplier", DEFAULT_THRESHOLDS) == near


def test_contact_person_never_reaches_the_assessor():
    assert visibility("contact_person", "assessor") == "none"
    assert project("contact_person", "Frau Weber, +49...", "intake", DEFAULT_THRESHOLDS)


def test_market_sensitive_arrives_as_a_boolean_flag_not_a_value():
    assert project("market_sensitive", True, "assessor", DEFAULT_THRESHOLDS) is True
    assert project("market_sensitive", "ja, Boerse", "assessor", DEFAULT_THRESHOLDS) is True
    assert visibility("market_sensitive", "supplier") == "none"


def test_an_unknown_field_is_a_typed_refusal_not_a_keyerror():
    with pytest.raises(EnvelopeError) as exc:
        project("salary", 1, "assessor", DEFAULT_THRESHOLDS)
    assert exc.value.code == "unknown_field"
    with pytest.raises(EnvelopeError) as exc:
        visibility("salary", "assessor")
    assert exc.value.code == "unknown_field"


def test_an_unknown_role_is_a_typed_refusal():
    with pytest.raises(EnvelopeError) as exc:
        visibility("customer_stock", "journalist")
    assert exc.value.code == "unknown_role"


def test_no_role_chain_widens_a_visibility():
    """Der Kern: was eine Rolle weitergeben koennte, ist nie mehr als sie sah."""
    rank = {"none": 0, "flag": 1, "schwelle": 1, "ampel": 2, "coarse": 2, "raw": 3}
    for name, fld in FIELDS.items():
        raw_holders = {r for r in ROLES if fld.visibility[r] == "raw"}
        for role in ROLES:
            if role in raw_holders:
                continue
            assert rank[fld.visibility[role]] < 3, f"{name}/{role} haelt raw ohne Eigentuemer zu sein"


def test_fields_for_lists_only_what_a_role_can_ever_receive():
    assert "customer_stock" not in fields_for("supplier")
    assert "customer_stock" in fields_for("assessor")
    assert "contract_penalty" in fields_for("legal")
    assert "route_weakness" in fields_for("assessor")


def test_every_field_is_owned_by_a_declared_record_type_on_a_real_party():
    """Der Eigentuemer ist ein Datensatztyp, und jeder liegt auf einem Parteityp."""
    party_types = {"carrier", "customer", "supplier", "shared"}
    for name, owner in owners().items():
        assert owner in RECORD_TYPES, f"{name}: Eigentuemer {owner} ist kein Datensatztyp"
        assert holders()[name] in party_types, f"{name}: liegt auf {holders()[name]!r}"


def test_the_assessor_holds_no_raw_field_of_another_party():
    """Die eigentliche Aussage. Praezise: der Bewerter sieht Rohwerte nur aus
    der eigenen Organisation (dem Betreiber), nie aus Kunden-, Zulieferer- oder
    Vertragsdaten."""
    for name, fld in FIELDS.items():
        if fld.visibility["assessor"] != "raw":
            continue
        assert fld.held_by == "carrier", (
            f"{name} gehoert {fld.held_by!r} und erreicht den Bewerter als raw"
        )


def test_a_node_only_holds_the_fields_of_its_own_party_type():
    """Der Knoten des Kunden haelt keine Vertragsstrafe... ausser seiner eigenen.

    `contract` ist `shared`: beide Vertragsparteien laden ihn. Das ist Feldschutz
    plus Zeilenschutz -- Kunde 2 laedt Vertrag 1 nie, weil sein Knoten ihn nicht
    kennt.
    """
    customer_side = set(fields_held_by("customer"))
    assert "customer_stock" in customer_side
    assert "contract_penalty" in customer_side  # shared, aber nur die eigene Zeile
    assert "route_weakness" not in customer_side
    assert "market_sensitive" not in customer_side
    supplier_side = set(fields_held_by("supplier"))
    assert "customer_stock" not in supplier_side
    assert "replacement_available" in supplier_side


def test_matrix_table_renders_every_field_and_role():
    table = matrix_table()
    for name in FIELDS:
        assert name in table
    for role in ROLES:
        assert role in table


def test_ampel_values_come_from_the_value_list():
    for value in ("gruen", "gelb", "rot"):
        assert value in AMPEL

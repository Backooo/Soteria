"""Die Umschlaege sind der Vertrag zwischen allen vier Straengen."""

import pytest

from soteria.envelope import (
    AMPEL,
    MEASURE,
    REASON,
    REFUSAL,
    ROLES,
    Advice,
    Ask,
    Coverage,
    Decision,
    EnvelopeError,
    FactSheet,
    Report,
    Review,
    canonical,
    digest,
)


def test_refusal_codes_are_closed():
    for code in ("not_in_matrix", "no_grant", "grant_mismatch", "quarantine"):
        assert code in REFUSAL


def test_envelope_error_rejects_untyped_code():
    with pytest.raises(ValueError, match="not a typed refusal"):
        EnvelopeError("weil es mir nicht passt")


def test_envelope_error_carries_its_code():
    err = EnvelopeError("not_in_matrix", "customer_stock ist fuer supplier nicht sichtbar")
    assert err.code == "not_in_matrix"
    assert "customer_stock" in str(err)


def test_digest_is_stable_under_key_order():
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})
    assert digest({"a": 1}) != digest({"a": 2})
    assert len(digest({"a": 1})) == 16


def test_canonical_has_no_whitespace():
    assert canonical({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_report_requires_a_known_reporter_role():
    with pytest.raises(EnvelopeError) as exc:
        Report(
            incident_id="i1",
            location="Terminal Nord",
            ts=1_758_000_000.0,
            cargo_class="pharma_cooled",
            symptom="cooling_failure",
            reporter_role="stranger",
        )
    assert exc.value.code == "unknown_role"


def test_ask_requires_a_typed_reason():
    with pytest.raises(EnvelopeError) as exc:
        Ask(from_role="assessor", to_role="customer", field="customer_stock", reason_code="neugier")
    assert exc.value.code == "bad_value"


def test_factsheet_counts_answered_fields():
    sheet = FactSheet(
        role="customer",
        fields={"customer_stock": "gelb", "contact_person": "Frau Weber"},
        flags=("perishable",),
    )
    assert sheet.answered == 2
    assert sheet.as_dict()["role"] == "customer"


def test_advice_rejects_an_unknown_measure():
    with pytest.raises(EnvelopeError) as exc:
        Advice(role="legal", measures=("teleport",), reason_code="liability", deadline_min=30)
    assert exc.value.code == "bad_value"


def test_decision_takes_several_measures_and_reports_its_tier():
    decision = Decision(
        measures=("cool", "reload"),
        params={"terminal": "Nord"},
        tier=2,
        grants=("ops-1",),
        coverage=Coverage(answered=4, asked=5, roles_missing=("legal",)),
        reason_code="safety",
        receipt_hash="0" * 16,
    )
    assert decision.measures == ("cool", "reload")
    assert decision.coverage.roles_missing == ("legal",)
    assert set(decision.measures) <= set(MEASURE)


def test_coverage_rejects_more_answers_than_questions():
    with pytest.raises(EnvelopeError) as exc:
        Coverage(answered=6, asked=5, roles_missing=())
    assert exc.value.code == "bad_value"


def test_review_quality_is_bounded():
    with pytest.raises(EnvelopeError):
        Review(incident_id="i1", human_verdict="proceed", quality_1_5=6, attribution={})
    ok = Review(incident_id="i1", human_verdict="proceed", quality_1_5=4, attribution={"legal": 0.5})
    assert ok.quality_1_5 == 4


def test_roles_and_reasons_are_the_documented_five_and_seven():
    assert ROLES == ("intake", "assessor", "legal", "supplier", "customer")
    assert len(REASON) == 7
    assert AMPEL == ("gruen", "gelb", "rot")

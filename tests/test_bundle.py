"""Die gebuendelte Nachfrage: eine Nachricht je Knoten statt eine je Feld.

Gebuendelt wird der Transport, nicht die Pruefung. Diese Tests halten fest, dass
jedes Feld weiter einzeln durch Matrix und Skalar-Riegel geht und dass die
Ansichten denselben Ereignisstrom bekommen wie vorher.
"""

import pytest

from soteria.cases import load_case
from soteria.envelope import EnvelopeError
from soteria.party_app import answer_ask, answer_bundle
from soteria.policy import ASK_PLAN
from soteria.wire import (
    SCALARS,
    bundle_ask_record,
    bundle_reply,
    fact_record,
    read_bundle_ask,
    read_bundle_reply,
    refusal_record,
)


def test_a_bundle_survives_the_round_trip_in_order():
    plan = [("temperature_curve", "safety"), ("market_sensitive", "confidentiality")]
    asker, case_id, back = read_bundle_ask(bundle_ask_record("assessor", plan, "s3"))
    assert (asker, case_id, back) == ("assessor", "s3", plan)


def test_a_bundle_rejects_an_untyped_reason():
    with pytest.raises(EnvelopeError) as exc:
        bundle_ask_record("assessor", [("customer_stock", "neugier")], "s1")
    assert exc.value.code == "bad_value"


def test_a_bundle_rejects_an_agent_that_does_not_exist():
    with pytest.raises(EnvelopeError) as exc:
        bundle_ask_record("journalist", [("customer_stock", "time")], "s1")
    assert exc.value.code == "unknown_role"


def test_an_empty_bundle_is_refused():
    with pytest.raises(EnvelopeError):
        bundle_ask_record("assessor", [], "s1")


def test_the_reply_keeps_one_record_per_field_in_order():
    records = [
        fact_record("intake", "temperature_curve", "ampel", "rot", (), "W02"),
        refusal_record("customer", "contact_person", "not_in_matrix"),
        fact_record("legal", "contract_penalty", "schwelle", "below"),
    ]
    back = read_bundle_reply(bundle_reply(records))
    assert [r["field"] for r in back] == ["temperature_curve", "contact_person", "contract_penalty"]
    assert back[1]["code"] == "not_in_matrix" and back[1]["value"] == ""


def test_the_reply_keeps_order_beyond_ten_records():
    """Die Schluessel sind nullgepolstert -- sonst sortiert 'answer.10' vor 'answer.2'."""
    records = [fact_record("intake", f"f{i}", "flag", True) for i in range(13)]
    assert [r["field"] for r in read_bundle_reply(bundle_reply(records))] == [f"f{i}" for i in range(13)]


@pytest.mark.parametrize("case_id", ["s1", "s2", "s3"])
def test_a_bundled_answer_equals_the_single_field_answers(case_id):
    """Buendeln darf am Ergebnis nichts aendern, Feld fuer Feld."""
    case = load_case(case_id)
    plan = list(ASK_PLAN)
    for party_id in case.party_ids:
        bundled = answer_bundle(case, party_id, "assessor", plan)
        single = [answer_ask(case, party_id, "assessor", f, r) for f, r in plan]
        assert bundled == single


def test_one_refused_field_does_not_sink_the_rest_of_the_bundle():
    """Ein Feld darf abgelehnt werden, ohne die anderen zu kippen."""
    case = load_case("s3")
    customer = next(f["party_id"] for f in case.federations if f["party_type"] == "customer")
    replies = answer_bundle(case, customer, "assessor",
                            [("contact_person", "time"), ("customer_stock", "time")])
    assert replies[0]["code"] == "not_in_matrix"
    assert replies[1]["code"] == "" and replies[1]["value"] in {"gruen", "gelb", "rot"}


def test_every_bundled_value_is_still_a_scalar():
    case = load_case("s3")
    for party_id in case.party_ids:
        for reply in answer_bundle(case, party_id, "assessor", list(ASK_PLAN)):
            assert isinstance(reply["value"], SCALARS)


def test_the_event_stream_keeps_ask_before_fact_per_field():
    """Der Ereignisvertrag der Ansichten: je Feld erst die Frage, dann die Antworten."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from record_run import record

    events = record("s3")["events"]
    last_ask: str | None = None
    for event in events:
        if event["type"] == "soteria.ask":
            last_ask = event["field"]
        elif event["type"] == "soteria.fact":
            assert event["field"] == last_ask, f"Antwort auf {event['field']} ohne vorherige Frage"
    fields = [e["field"] for e in events if e["type"] == "soteria.ask"]
    assert fields.index("market_sensitive") < fields.index("customer_stock")
    assert any(e["type"] == "soteria.quarantine" for e in events)

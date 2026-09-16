"""The frontend export must not show anything that was not already in the event stream."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from export_frontend import FIXTURES, export_case  # noqa: E402
from wire_proof import _raw_needles_by_field  # noqa: E402

from soteria.cases import load_case

CASES = ["s1", "s2", "s3"]


def _fixture(case_id):
    return json.loads((FIXTURES / f"{case_id}.json").read_text())


@pytest.mark.parametrize("case_id", CASES)
def test_export_leaks_no_raw_value_the_stream_did_not_carry(case_id):
    fixture = _fixture(case_id)
    stream_text = json.dumps(fixture["events"], ensure_ascii=False)
    _, entry = export_case(fixture)
    export_text = json.dumps(entry, ensure_ascii=False)
    for field, needles in _raw_needles_by_field(load_case(case_id)).items():
        for needle in needles:
            if needle in stream_text:
                continue  # already allowed in the stream
            assert needle not in export_text, (field, needle)


@pytest.mark.parametrize("case_id", CASES)
def test_export_matches_the_decision(case_id):
    fixture = _fixture(case_id)
    incident_id, entry = export_case(fixture)
    decision = fixture["outcome"]["decision"]
    assert incident_id == fixture["case"]["report"]["incident_id"]
    assert entry["soteriaTier"] == decision["tier"]
    assert entry["receiptHead"] == decision["receipt_hash"]
    assert {c["role"] for c in entry["consensus"]} == {"intake", "assessor", "legal", "supplier", "customer"}


def test_only_s3_is_market_sensitive_and_quarantines_legal():
    entries = {c: export_case(_fixture(c))[1] for c in CASES}
    assert [c for c, e in entries.items() if e["marketSensitive"]] == ["s3"]
    legal = next(i for i in entries["s3"]["consensus"] if i["role"] == "legal")
    assert legal["status"] == "quarantined"


@pytest.mark.parametrize("case_id", CASES)
def test_structured_decision_mirrors_the_decision_event(case_id):
    fixture = _fixture(case_id)
    _, entry = export_case(fixture)
    decision = fixture["outcome"]["decision"]
    assert [m["code"] for m in entry["decision"]["measures"]] == decision["measures"]
    assert entry["decision"]["grants"] == decision["grants"]
    assert entry["decision"]["keysNeeded"] == len(decision["grants"])
    assert entry["events"] == fixture["events"]


@pytest.mark.parametrize("case_id", CASES)
def test_export_names_who_decided(case_id):
    fixture = _fixture(case_id)
    _, entry = export_case(fixture)
    event = next(e for e in fixture["events"] if e["type"] == "soteria.decision")
    assert entry["decision"]["decidedBy"] == event.get("decided_by", "policy")
    assert entry["decision"]["model"] == event.get("model", "")

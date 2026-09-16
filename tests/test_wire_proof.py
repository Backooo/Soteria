"""The boundary proof as a test -- so it cannot regress.

`scripts/wire_proof.py` attempts every role/field/node crossing and checks that
no raw value reaches a role that may not have it. The version without a
denominator reported authorised disclosure as a violation; these tests pin the
distinction down so it does not get lost again.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wire_proof import prove  # noqa: E402

from soteria.cases import available_cases
from soteria.matrix import FIELDS, coarse_of, vocabulary
from soteria.party_app import answer_ask
from soteria.cases import load_case


@pytest.mark.parametrize("case_id", available_cases())
def test_no_raw_value_reaches_a_role_that_may_not_have_it(case_id, capsys):
    result = prove(case_id, verbose=False)
    capsys.readouterr()
    assert result["violations"] == [], result["violations"]


@pytest.mark.parametrize("case_id", available_cases())
def test_the_proof_has_a_denominator(case_id, capsys):
    """A zero result without a denominator would be worthless.

    The test must show that boundaries were touched at all: typed refusals AND
    authorised disclosures, both in meaningful numbers.
    """
    result = prove(case_id, verbose=False)
    capsys.readouterr()
    assert result["attempts"] > 50, "too few crossings attempted"
    assert result["refused"] > 20, "the test barely triggers refusals"
    assert result["authorised_raw"] > 10, "the test barely sees authorised disclosure"
    assert result["needles"] > 15, "too few raw values to search for"


def test_a_coarse_class_is_never_spelled_like_a_fine_one():
    """Otherwise it cannot be checked whether coarsening happened.

    Exactly this mistake made the first boundary proof blind: `perishable` was
    a fine value AND a coarse class, so coarsening could not be demonstrated
    for that class.
    """
    fine = set(vocabulary("cargo_class"))
    coarse = {coarse_of("cargo_class", v) for v in fine}
    assert not (fine & coarse), f"collision: {sorted(fine & coarse)}"
    fine_trades = set(vocabulary("trade"))
    coarse_trades = {coarse_of("trade", v) for v in fine_trades}
    assert not (fine_trades & coarse_trades), f"collision: {sorted(fine_trades & coarse_trades)}"


def test_the_scope_of_an_answer_goes_through_the_matrix_too():
    """The reference unit is a value. Without projection it would be a side channel.

    Found by wire_proof.py: `customer_stock = gelb @pharmaceutical` revealed to
    the assessor the fine cargo class it may only see coarsely.
    """
    case = load_case("s3")
    customer = next(
        f["party_id"] for f in case.federations if f["party_type"] == "customer"
    )
    for_assessor = answer_ask(case, customer, "assessor", "customer_stock", "time")
    assert for_assessor["scope"] not in vocabulary("cargo_class")
    assert for_assessor["scope"] == coarse_of("cargo_class", "pharmaceutical")

    # The customer itself may see the fine class.
    for_customer = answer_ask(case, customer, "customer", "customer_stock", "time")
    assert for_customer["scope"] == "pharmaceutical"


def test_a_wagon_number_is_not_a_secret_and_stays_readable():
    """A wagon number is in the shared report. It may stay."""
    case = load_case("s3")
    carrier = next(f["party_id"] for f in case.federations if f["party_type"] == "carrier")
    reply = answer_ask(case, carrier, "assessor", "temperature_curve", "safety")
    assert reply["scope"] in case.report["affected_wagons"]

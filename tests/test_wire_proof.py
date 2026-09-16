"""Der Grenzbeweis als Test -- damit er nicht zurueckfallen kann.

`scripts/wire_proof.py` versucht jeden Rolle/Feld/Knoten-Uebertritt und prueft,
dass kein Rohwert eine Rolle erreicht, die ihn nicht haben darf. Die Fassung
ohne Nennwert meldete erlaubte Offenlegung als Verstoss; diese Tests halten die
Unterscheidung fest, damit sie nicht wieder verloren geht.
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
    """Ein Nullergebnis ohne Nennwert waere wertlos.

    Der Test muss zeigen, dass ueberhaupt Grenzen beruehrt wurden: getippte
    Ablehnungen UND erlaubte Offenlegungen, beide in nennenswerter Zahl.
    """
    result = prove(case_id, verbose=False)
    capsys.readouterr()
    assert result["attempts"] > 50, "zu wenige Uebertritte versucht"
    assert result["refused"] > 20, "der Test loest kaum Ablehnungen aus"
    assert result["authorised_raw"] > 10, "der Test sieht kaum erlaubte Offenlegung"
    assert result["needles"] > 15, "zu wenige Rohwerte zum Suchen"


def test_a_coarse_class_is_never_spelled_like_a_fine_one():
    """Sonst laesst sich nicht pruefen, ob vergroebert wurde.

    Genau dieser Fehler machte den ersten Grenzbeweis blind: `perishable` war
    Feinwert UND Grobklasse, also war die Vergroeberung fuer diese Klasse
    nicht nachweisbar.
    """
    fine = set(vocabulary("cargo_class"))
    coarse = {coarse_of("cargo_class", v) for v in fine}
    assert not (fine & coarse), f"Kollision: {sorted(fine & coarse)}"
    fine_trades = set(vocabulary("trade"))
    coarse_trades = {coarse_of("trade", v) for v in fine_trades}
    assert not (fine_trades & coarse_trades), f"Kollision: {sorted(fine_trades & coarse_trades)}"


def test_the_scope_of_an_answer_goes_through_the_matrix_too():
    """Der Bezug ist ein Wert. Ohne Projektion waere er ein Seitenkanal.

    Gefunden von wire_proof.py: `customer_stock = gelb @pharmaceutical` verriet
    dem Bewerter die feine Ladungsklasse, die er nur grob sehen darf.
    """
    case = load_case("s3")
    customer = next(
        f["party_id"] for f in case.federations if f["party_type"] == "customer"
    )
    for_assessor = answer_ask(case, customer, "assessor", "customer_stock", "time")
    assert for_assessor["scope"] not in vocabulary("cargo_class")
    assert for_assessor["scope"] == coarse_of("cargo_class", "pharmaceutical")

    # Der Kunde selbst darf die feine Klasse sehen.
    for_customer = answer_ask(case, customer, "customer", "customer_stock", "time")
    assert for_customer["scope"] == "pharmaceutical"


def test_a_wagon_number_is_not_a_secret_and_stays_readable():
    """Eine Wagennummer steht in der gemeinsamen Meldung. Sie darf bleiben."""
    case = load_case("s3")
    carrier = next(f["party_id"] for f in case.federations if f["party_type"] == "carrier")
    reply = answer_ask(case, carrier, "assessor", "temperature_curve", "safety")
    assert reply["scope"] in case.report["affected_wagons"]

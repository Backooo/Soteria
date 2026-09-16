"""Der Beweis: kein Rohwert erreicht eine Rolle, die ihn nicht haben darf.

    uv run python scripts/wire_proof.py          # alle Faelle
    uv run python scripts/wire_proof.py s3

**Was hier gemessen wird, und warum die naive Fassung falsch war.** Der erste
Versuch fragte "steht irgendein Rohwert auf dem Draht?" und meldete 17 Lecks --
darunter `contract_penalty = 9000` an den Vertragsagenten und die Kuehlkurve an
den Zulieferer. Beides stellt die Matrix diesen Rollen ausdruecklich zu. Ein
Detektor ohne Nennwert meldet erlaubte Offenlegung als Verstoss und ist damit
wertlos, und "0 Lecks" waere eine Behauptung ueber etwas, das nie gemessen wurde.

Die richtige Frage hat einen Nennwert: fuer jedes Paar (Rolle, Feld), bei dem
die Matrix **nicht** `raw` sagt, darf in der Antwort kein Rohwert dieses Feldes
vorkommen. Erlaubte Offenlegung wird getrennt gezaehlt und ausgewiesen, damit
sichtbar bleibt, wie gross der Nennwert ueberhaupt ist.

Geprueft werden ALLE Rolle/Feld/Knoten-Kombinationen, nicht nur die des
Frageplans -- eine boeswillige Partei fragt genau das, was sie nicht fragen soll.
Benutzt wird `soteria.party_app.answer_ask`, derselbe Code, den die Foederation
faehrt; nur der Transport ist ein Aufruf statt eines Sockets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from soteria.cases import available_cases, load_case, raw_records_for_party
from soteria.envelope import ROLES
from soteria.matrix import FIELDS, visibility
from soteria.party_app import answer_ask

# Kuerzere Zeichenketten beweisen nichts: "0", "1", "no" stehen zufaellig ueberall.
_MIN_NEEDLE = 3


def _needles(value: Any, out: set[str]) -> None:
    """Die Zeichenketten, die ein Mitschnitt als Rohwert dieses Feldes zeigen wuerde."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if not str(key).startswith("_"):
                _needles(inner, out)
        return
    if isinstance(value, (list, tuple)):
        for inner in value:
            _needles(inner, out)
        return
    if isinstance(value, bool) or value is None:
        return
    text = str(value)
    if len(text) >= _MIN_NEEDLE:
        out.add(text)


def _raw_needles_by_field(case: Any) -> dict[str, set[str]]:
    """Feld -> die Rohzeichenketten, die irgendein Knoten dazu haelt."""
    out: dict[str, set[str]] = {}
    for party_id in case.party_ids:
        for _record_type, block in raw_records_for_party(case, party_id).items():
            for field_name, value in block.items():
                if field_name in FIELDS:
                    out.setdefault(field_name, set())
                    _needles(value, out[field_name])
    return out


def prove(case_id: str, verbose: bool = True) -> dict[str, Any]:
    case = load_case(case_id)
    needles = _raw_needles_by_field(case)

    print(f"\n{'=' * 78}\n{case_id}: {case.title}\n{'=' * 78}")
    if verbose:
        print(f"{'Frager':<10} {'Knoten':<10} {'Feld':<22} {'darf':<9} Antwort")
        print("-" * 78)

    attempts = refused = authorised_raw = 0
    rows: list[dict[str, Any]] = []
    violations: list[str] = []
    cross_field: list[str] = []

    for asker in ROLES:
        for party_id in case.party_ids:
            if asker in case.roles_of(party_id):
                continue  # eine Rolle fragt nicht ihren eigenen Knoten
            for field in FIELDS:
                reply = answer_ask(case, party_id, asker, field, "confidentiality")
                if reply["code"] == "unknown_field":
                    continue  # der Knoten fuehrt es nicht -- keine Grenze beruehrt
                attempts += 1
                level = visibility(field, asker)
                blob = json.dumps(reply, sort_keys=True, default=str)
                rows.append({
                    "asker": asker,
                    "party_id": party_id,
                    "party_type": case.party_type(party_id),
                    "field": field,
                    "allowed": level,
                    "outcome": ("refused" if reply["code"]
                                else "raw" if level == "raw" else "projected"),
                    "code": reply["code"],
                    # Der Wert steht nur drin, wo er den Frager auch erreicht hat.
                    "value": "" if reply["code"] else reply["value"],
                    "scope": reply["scope"],
                })

                if reply["code"]:
                    refused += 1
                    if verbose:
                        print(f"{asker:<10} {party_id.split('_')[0]:<10} {field:<22} "
                              f"{level:<9} ABGELEHNT {reply['code']}")
                    continue

                shown = str(reply["value"])[:28]
                scope = f" @{reply['scope']}" if reply["scope"] else ""
                if verbose:
                    print(f"{asker:<10} {party_id.split('_')[0]:<10} {field:<22} "
                          f"{level:<9} {shown}{scope}")

                if level == "raw":
                    # Erlaubte Offenlegung. Sie ist der Nennwert, nicht der Fehler.
                    authorised_raw += 1
                    continue

                # Die eigentliche Pruefung: eine nicht-rohe Aufloesung darf keinen
                # Rohwert dieses Feldes enthalten.
                for needle in sorted(needles.get(field, set())):
                    if needle in blob:
                        violations.append(
                            f"{asker} bekam {field!r} als {level!r}, aber {needle!r} "
                            f"steht in der Antwort von {party_id}"
                        )
                # Und keine Antwort ueber X darf einen Rohwert von Y mitschleppen.
                for other, other_needles in needles.items():
                    if other == field:
                        continue
                    if visibility(other, asker) == "raw":
                        continue
                    for needle in sorted(other_needles):
                        if len(needle) >= 6 and needle in blob:
                            cross_field.append(
                                f"Antwort auf {field!r} an {asker} enthielt {needle!r} "
                                f"aus {other!r}"
                            )

    print("-" * 78)
    print(f"{attempts} Grenzuebertritte versucht  |  {refused} abgelehnt  |  "
          f"{authorised_raw} erlaubte Rohoffenlegungen  |  "
          f"{attempts - refused - authorised_raw} projizierte Antworten")
    checked = sum(len(v) for v in needles.values())
    print(f"{checked} Rohzeichenketten gegen jede Antwort geprueft, in der die Matrix "
          "nicht 'raw' sagt.")
    for line in violations + cross_field:
        print(f"  VERSTOSS  {line}")
    if not violations and not cross_field:
        print("  kein Verstoss.")
    return {
        "case_id": case_id,
        "attempts": attempts,
        "refused": refused,
        "authorised_raw": authorised_raw,
        "needles": checked,
        "violations": violations + cross_field,
        "rows": rows,
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    quiet = "--quiet" in sys.argv
    ids = args or list(available_cases())
    results = [prove(case_id, verbose=not quiet) for case_id in ids]

    attempts = sum(r["attempts"] for r in results)
    refused = sum(r["refused"] for r in results)
    authorised = sum(r["authorised_raw"] for r in results)
    needles = sum(r["needles"] for r in results)
    violations = [f"{r['case_id']}: {v}" for r in results for v in r["violations"]]

    if "--json" in sys.argv:
        out = Path(__file__).resolve().parents[1] / "view" / "fixtures" / "boundary.json"
        out.write_text(json.dumps({
            "_comment": "Erzeugt von scripts/wire_proof.py --json. Jeder Grenzuebertritt, "
                        "den eine Partei versuchen koennte, und was daraus wurde.",
            "cases": [{k: v for k, v in r.items()} for r in results],
        }, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        print(f"\ngeschrieben: {out.relative_to(out.parents[2])}")

    print(f"\n{'=' * 78}")
    print(f"{len(ids)} Faelle  |  {attempts} Grenzuebertritte  |  {refused} abgelehnt  |  "
          f"{authorised} erlaubte Rohoffenlegungen  |  {needles} Rohwerte geprueft")
    if violations:
        print(f"\nFEHLGESCHLAGEN -- {len(violations)} Verstoss/Verstoesse:")
        for line in violations:
            print(f"  {line}")
        return 1
    print("\nBESTANDEN. Kein Rohwert hat eine Rolle erreicht, die ihn nicht haben darf.")
    print(f"Der Nennwert steht daneben: {refused} Versuche wurden getippt abgelehnt, und")
    print(f"{authorised} Rohoffenlegungen sind erlaubt und als solche ausgewiesen -- der")
    print("Test unterscheidet also zwischen beidem, statt jede Offenlegung zu melden.")
    print("Nicht weil ein Prompt es verbietet: die Projektion laeuft auf dem Knoten der")
    print("Partei, und ein ConfigRecord traegt nur Skalare.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

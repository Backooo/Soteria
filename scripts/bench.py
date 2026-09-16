"""Die vier Zahlen. Aus Laeufen, nicht aus dem Bauchgefuehl.

    uv run python scripts/bench.py

Faehrt jeden Fall durch dieselbe `Assessor`-Klasse wie die Foederation, prueft
den Grenzbeweis und schreibt `view/fixtures/bench.json` fuer die Fallübersicht.

**Was jede Zahl behauptet -- und was nicht.**

1. Zeit bis zur Entscheidung. Gemessen wird die Logik ohne Transport; die echte
   Foederation braucht 3-7 s (docs/RISKS.md). Beides wird ausgewiesen. Die
   Basislinie der Telefonkette ist eine ANNAHME, keine Messung.
2. Trefferquote. Getrennt nach bekannten Faellen und Holdout. `policy.py` wurde
   gegen die bekannten Faelle geschrieben, deren Quote ist eine
   Konsistenzpruefung. Solange die Wahrheit als VORSCHLAG markiert ist, ist sie
   zusaetzlich unbestaetigt -- und das steht neben der Zahl.
3. Dichtheit. Aus scripts/wire_proof.py, mit Nennwert: versuchte Uebertritte,
   abgelehnte, erlaubte Rohoffenlegungen, Verstoesse.
4. Verhalten mit Luecke. Jeder Fall wird ein zweites Mal gefahren, mit dem
   Kunden offline. Kein Fall hat das von Haus aus -- also wird es erzeugt, und
   so steht es da.
"""

from __future__ import annotations

import dataclasses
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from record_run import Recorder, local_sender  # noqa: E402
from wire_proof import prove  # noqa: E402

from soteria.assessor_app import run_incident  # noqa: E402
from soteria.cases import available_cases, load_case  # noqa: E402
from soteria.charter import Budget  # noqa: E402
from soteria.envelope import EnvelopeError  # noqa: E402
from soteria.ledger import Ledger  # noqa: E402
from soteria.policy import ASK_PLAN  # noqa: E402

OUT = HERE.parent / "view" / "fixtures" / "bench.json"

# ANNAHME, keine Messung. Wir haben keine Telefonkette gestoppt.
BASELINE_MINUTES = 47
BASELINE_SOURCE = (
    "Angenommene Dauer einer Telefonkette aus fuenf Parteien einschliesslich "
    "Rueckrufen. Nicht gemessen -- eine Annahme, die als solche ausgewiesen ist."
)

# Aus docs/RISKS.md, gemessen auf der echten Foederation mit gebuendelter
# Nachfrage (eine Nachricht je Knoten). Vorher, mit 13 Runden: 69,1 / 126,9 / 68,0 s.
FEDERATION_SECONDS = {"s1": 6.4, "s2": 6.2, "s3": 3.2}


def _run(case: Any) -> tuple[dict[str, Any] | None, str | None, float, list[dict]]:
    recorder = Recorder()
    ledger = Ledger(
        Budget(max_delegations=len(ASK_PLAN) + 2, max_depth=2,
               seconds=240.0, max_connector_calls=0),
        recorder,
    )
    started = time.perf_counter()
    try:
        decision = run_incident(case, ledger, local_sender(case)).as_dict()
        refusal = None
    except EnvelopeError as exc:
        decision, refusal = None, exc.code
    return decision, refusal, time.perf_counter() - started, recorder.events


def _hit(decision: dict | None, refusal: str | None, truth: dict) -> bool:
    expected_refusal = truth.get("expect_refusal")
    if expected_refusal:
        return refusal == expected_refusal
    if not decision:
        return False
    if set(decision["measures"]) != set(truth.get("measures") or ()):
        return False
    return not (set(decision["measures"]) & set(truth.get("must_not") or ()))


def main() -> int:
    cases: list[dict[str, Any]] = []
    for case_id in available_cases():
        case = load_case(case_id)
        truth = dict(case.truth)
        decision, refusal, seconds, events = _run(case)

        # Zahl 4: dieselbe Lage, der Kunde antwortet nicht.
        customers = tuple(
            str(f["party_id"]) for f in case.federations if f.get("party_type") == "customer"
        )
        gap_decision, gap_refusal, _, _ = _run(
            dataclasses.replace(case, offline_parties=customers)
        )

        cases.append({
            "id": case_id,
            "title": case.title,
            "holdout": case_id.startswith("h"),
            "truth": sorted(truth.get("measures") or ()),
            "truth_reason": truth.get("reason_code"),
            "truth_confirmed": case.truth_confirmed,
            "decided": sorted(decision["measures"]) if decision else [],
            "decided_reason": decision["reason_code"] if decision else None,
            "refusal": refusal,
            "hit": _hit(decision, refusal, truth),
            "reason_matches": bool(decision) and decision["reason_code"] == truth.get("reason_code"),
            "tier": decision["tier"] if decision else 0,
            "grants": decision["grants"] if decision else [],
            "receipt_hash": decision["receipt_hash"] if decision else "",
            "seconds_logic": round(seconds, 4),
            "seconds_federation": FEDERATION_SECONDS.get(case_id),
            "quarantined": any(e["type"] == "soteria.quarantine" for e in events),
            "gap": {
                "offline": list(customers),
                "decided": sorted(gap_decision["measures"]) if gap_decision else [],
                "reason": gap_decision["reason_code"] if gap_decision else None,
                "refusal": gap_refusal,
            },
        })

    known = [c for c in cases if not c["holdout"]]
    holdout = [c for c in cases if c["holdout"]]
    unconfirmed = [c["id"] for c in cases if not c["truth_confirmed"]]

    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        proofs = [prove(c["id"], verbose=False) for c in cases]
    boundary = {
        "attempts": sum(p["attempts"] for p in proofs),
        "refused": sum(p["refused"] for p in proofs),
        "authorised_raw": sum(p["authorised_raw"] for p in proofs),
        "violations": sum(len(p["violations"]) for p in proofs),
    }

    fed = [v for v in FEDERATION_SECONDS.values() if v]
    numbers = {
        "1_time": {
            "logic_median_ms": round(statistics.median(c["seconds_logic"] for c in cases) * 1000, 1),
            "federation_median_s": round(statistics.median(fed), 1) if fed else None,
            "federation_max_s": max(fed) if fed else None,
            "baseline_minutes": BASELINE_MINUTES,
            "baseline_is_assumption": True,
        },
        "2_hits": {
            "known": f"{sum(c['hit'] for c in known)}/{len(known)}",
            "holdout": f"{sum(c['hit'] for c in holdout)}/{len(holdout)}" if holdout else None,
            "reasons_matching": f"{sum(c['reason_matches'] for c in cases)}/{len(cases)}",
            "truth_unconfirmed": unconfirmed,
        },
        "3_boundary": boundary,
        "4_gap": {
            "cases": len(cases),
            "still_decided": sum(1 for c in cases if c["gap"]["decided"]),
        },
    }

    honesty = [
        {"claim": "Kein Rohwert erreicht eine Rolle, die ihn nicht haben darf",
         "real": f"{boundary['attempts']} Grenzuebertritte versucht, {boundary['refused']} "
                 f"abgelehnt, {boundary['violations']} Verstoesse -- mit Nennwert gemessen",
         "simulated": "nichts. Der Grenzbeweis ruft die Knoten-Handler direkt auf; derselbe "
                      "Code laeuft in der Foederation"},
        {"claim": "Drei Parteien, drei Knoten",
         "real": "drei SuperNodes mit eigener node-config, echte Flower-Nachrichten, alle "
                 "drei Faelle getroffen",
         "simulated": "die drei Knoten laufen auf einem Rechner"},
        {"claim": "Eine Foederation je Partei",
         "real": "eine Foederation mit drei Parteiknoten",
         "simulated": "drei SuperLinks erreicht ein ServerApp in flwr nicht gemeinsam -- das "
                      "ist die Ausbaustufe, nicht der Stand"},
        {"claim": "Entscheidung in Minuten statt Telefonkette",
         "real": f"Logik {numbers['1_time']['logic_median_ms']} ms, Foederation "
                 f"{numbers['1_time']['federation_median_s']} s im Median",
         "simulated": f"die Basislinie von {BASELINE_MINUTES} min ist eine ANNAHME"},
        {"claim": "Trefferquote",
         "real": f"{numbers['2_hits']['known']} auf den bekannten Faellen",
         "simulated": "die Regeln wurden gegen genau diese Faelle geschrieben -- eine "
                      "Konsistenzpruefung, keine Verallgemeinerung. "
                      + ("Die Wahrheit ist zudem unbestaetigt (VORSCHLAG). " if unconfirmed else "")
                      + ("Holdout-Faelle fehlen." if not holdout else "")},
        {"claim": "Agenten",
         "real": "ein Bewerter als ServerApp, Parteiknoten als ClientApps",
         "simulated": "der Bewerter ist eine Regelmaschine, kein Sprachmodell. Die Parteiknoten "
                      "brauchen keins: eine Projektion ist eine Funktion"},
        {"claim": "Daten",
         "real": "Schema, Validierung, Vokabulare",
         "simulated": "alle Daten erfunden -- keine echten Bahndaten, Personen oder Firmen"},
        {"claim": "Quittungen",
         "real": "Kette ueber den ganzen Vorfall, verify() rechnet sie nach",
         "simulated": "16 Hex-Zeichen aus SHA-256 -- eine Pruefsumme, keine Kryptografie "
                      "fuer den Ernstfall"},
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": time.time(),
        "baseline_source": BASELINE_SOURCE,
        "numbers": numbers,
        "cases": cases,
        "honesty": honesty,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    t, h, b, g = (numbers["1_time"], numbers["2_hits"], numbers["3_boundary"], numbers["4_gap"])
    print("Soteria -- die vier Zahlen\n" + "=" * 72)
    print(f"1 Zeit      Logik {t['logic_median_ms']} ms  |  Foederation {t['federation_median_s']} s "
          f"Median, {t['federation_max_s']} s max  |  Basislinie {t['baseline_minutes']} min (ANNAHME)")
    print(f"2 Treffer   bekannt {h['known']}  |  Holdout {h['holdout'] or 'keine Faelle'}  |  "
          f"Begruendung passt {h['reasons_matching']}")
    if h["truth_unconfirmed"]:
        print(f"            ACHTUNG: Wahrheit unbestaetigt fuer {', '.join(h['truth_unconfirmed'])}")
    print(f"3 Dichtheit {b['attempts']} Uebertritte  |  {b['refused']} abgelehnt  |  "
          f"{b['authorised_raw']} erlaubt  |  {b['violations']} Verstoesse")
    print(f"4 Luecke    {g['still_decided']}/{g['cases']} Faelle entschieden, obwohl der Kunde schweigt")
    print("=" * 72)
    for c in cases:
        gap = ", ".join(c["gap"]["decided"]) or f"KEINE ({c['gap']['refusal']})"
        print(f"  {'TREFFER ' if c['hit'] else 'ABWEICH.'} {c['id']:<4} "
              f"{', '.join(c['decided']) or c['refusal']:<30} Grund {c['decided_reason']:<12}"
              f"{'' if c['reason_matches'] else '(soll ' + str(c['truth_reason']) + ')'}")
        print(f"           ohne Kunde: {gap} ({c['gap']['reason']})")
    print(f"\ngeschrieben: {OUT.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

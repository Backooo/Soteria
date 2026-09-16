"""Einen Vorfall fahren und als Ereignisstrom aufzeichnen.

    uv run python scripts/record_run.py s1
    uv run python scripts/record_run.py --all

Schreibt `view/fixtures/<case>.json` in der Form aus `docs/EVENTS.md`.

Laeuft **ohne** SuperLink: `local_sender` ruft die Handler der Parteiknoten
direkt auf, statt Nachrichten zu verschicken. Alles andere ist der
Produktionspfad -- dieselbe `Assessor`-Klasse, dieselbe Matrix, dieselben
Riegel. Der Unterschied ist der Transport, nicht die Logik, und genau so steht
er in der Ehrlichkeitstabelle.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from soteria.assessor_app import run_incident
from soteria.cases import Case, available_cases, load_case
from soteria.charter import Budget
from soteria.envelope import EnvelopeError
from soteria.ledger import Ledger
from soteria.party_app import answer_bundle
from soteria.policy import ASK_PLAN

FIXTURES = Path(__file__).resolve().parents[1] / "view" / "fixtures"


class Recorder:
    """Sammelt die Ereignisse und gibt ihnen `seq` und `t`."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._t0 = time.monotonic()

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(
            {"seq": len(self.events) + 1,
             "t": round(time.monotonic() - self._t0, 3),
             **event}
        )


def local_sender(case: Case) -> Callable[[list[tuple[str, str]]], dict[str, list[dict[str, Any]]]]:
    """Der Grid, ersetzt durch direkte Aufrufe der Knoten-Handler.

    Dieselbe Form wie in der Foederation: ein Frageplan je Knoten, Antworten je
    Feld gesammelt.
    """

    def send(plan: list[tuple[str, str]]) -> dict[str, list[dict[str, Any]]]:
        by_field: dict[str, list[dict[str, Any]]] = {field: [] for field, _ in plan}
        for party_id in case.party_ids:
            for payload in answer_bundle(case, party_id, "assessor", plan):
                by_field[payload["field"]].append(payload)
        return by_field

    return send


def record(case_id: str) -> dict[str, Any]:
    case = load_case(case_id)
    recorder = Recorder()
    ledger = Ledger(
        Budget(max_delegations=len(ASK_PLAN) + 2, max_depth=2,
               seconds=240.0, max_connector_calls=0),
        recorder,
    )
    decision: dict[str, Any] | None = None
    refusal: str | None = None
    try:
        decision = run_incident(case, ledger, local_sender(case)).as_dict()
    except EnvelopeError as exc:
        refusal = exc.code
        recorder.emit({"type": "soteria.no_decision", "code": exc.code,
                       "detail_chars": len(exc.detail)})

    return {
        "case": {
            "id": case.case_id,
            "title": case.title,
            "report": case.report,
            "flags": list(case.flags),
            "parties": [
                {"party_id": str(f.get("party_id")), "party_type": str(f.get("party_type"))}
                for f in case.federations
            ],
            "truth": dict(case.truth),
        },
        "outcome": {"decision": decision, "refusal": refusal},
        "events": recorder.events,
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--all"]
    ids = args or list(available_cases())
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for case_id in ids:
        data = record(case_id)
        out = FIXTURES / f"{case_id}.json"
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        events = data["events"]
        refusals = sum(1 for e in events if e["type"] == "soteria.refusal")
        decision = data["outcome"]["decision"]
        verdict = (
            ", ".join(decision["measures"]) if decision
            else f"KEINE ENTSCHEIDUNG ({data['outcome']['refusal']})"
        )
        truth = data["case"]["truth"].get("measures") or []
        hit = bool(decision) and set(decision["measures"]) == set(truth)
        print(f"{case_id}: {len(events):>3} Ereignisse, {refusals} Ablehnungen  "
              f"-> {verdict:<30} soll {', '.join(truth):<26} "
              f"{'TREFFER' if hit else 'ABWEICHUNG'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

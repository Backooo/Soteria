"""Der Bewerter als ServerApp: fragt die Parteiknoten ueber Grid, entscheidet.

Der einzige Agent mit Entscheidungsgewalt -- und der mit den wenigsten
Rohdaten. Jede Antwort, die hier ankommt, ist eine Ampel, eine Schwelle, ein
Flag oder eine Grobklasse; Rohwerte bekommt er nur aus der eigenen Organisation.

    ./scripts/federation.sh up s1
    uv run flwr run . carrier-fed --stream --run-config 'case="s1"'
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from flwr.app import Context
from flwr.serverapp import Grid, ServerApp

from .cases import Case, load_case
from .charter import Budget
from .envelope import Coverage, Decision, EnvelopeError
from .grants import GrantBook, KEYS_REQUIRED, tier_of
from .ledger import Ledger
from .matrix import visibility
from .policy import ASK_PLAN, decide
from .receipts import ReceiptChain
from .wire import ASK_FIELD, ask_record, read_reply, unwrap, wrap

app = ServerApp()

# Eine Nachfragerunde darf nie laenger dauern als das, was von der Wanduhr
# bleibt; 30 s ist die Obergrenze je Runde, damit ein stummer Knoten den Lauf
# nicht ueber SuperGrids 5-Minuten-Grenze traegt.
ROUND_TIMEOUT = 30.0


class Assessor:
    """Ein Vorfall: fragen, sammeln, entscheiden, quittieren.

    Der Transport ist austauschbar: `send` bekommt (Feld, Grund) und gibt die
    Antworten zurueck. In der Foederation ist das `Grid.send_and_receive`, in
    `scripts/record_run.py` ein direkter Aufruf der Knoten-Handler. Die Logik
    ist in beiden Faellen dieselbe -- das ist der Grund fuer diese Naht.
    """

    def __init__(self, case: Case, ledger: Ledger) -> None:
        self._case = case
        self._ledger = ledger
        self._chain = ReceiptChain()
        self._sheets: dict[str, Any] = {}
        self._scopes: dict[str, str] = {}
        self._answered_by: set[str] = set()
        self._asked = 0

    # -- Quittungen ------------------------------------------------------

    def _receipt(self, kind: str, payload: Mapping[str, Any]) -> None:
        receipt = self._chain.append(kind, payload)
        self._ledger.emit(
            "soteria.receipt",
            {"seq_in_chain": receipt.seq, "kind": receipt.kind,
             "hash": receipt.hash, "prev": receipt.prev},
        )

    # -- Ablauf ----------------------------------------------------------

    def open(self) -> dict[str, Any]:
        report = self._case.report
        self._ledger.emit(
            "soteria.incident.open",
            {
                "case_id": self._case.case_id,
                "incident_id": report["incident_id"],
                "train_id": report["train_id"],
                "location": report["location"],
                "symptom": report["symptom"],
                "severity": report["severity"],
                "train_operational": report["train_operational"],
                "track_blocked": report["track_blocked"],
                "affected_wagons": report["affected_wagons"],
                "cargo_classes_coarse": report["cargo_classes_coarse"],
                "flags": list(self._case.flags),
            },
        )
        for fed in self._case.federations:
            party_id = str(fed.get("party_id"))
            self._ledger.emit(
                "soteria.role.ready",
                {
                    "party_id": party_id,
                    "party_type": str(fed.get("party_type")),
                    "speaks_as": list(fed.get("speaks_as") or ()),
                    "online": party_id not in self._case.offline_parties,
                },
            )
        self._receipt("incident", report)
        return report

    def gather(self, send: Callable[[str, str], list[dict[str, Any]]]) -> None:
        """Den Frageplan abarbeiten. Jede Runde ein Feld an alle Knoten."""
        for field, reason_code in ASK_PLAN:
            self._ledger.require_time(f"asking for {field}", floor=2.0)
            level = visibility(field, "assessor")
            if level == "none":
                # Der Bewerter darf das Feld nicht sehen. Dann fragt er nicht --
                # ein Frageplan, der die Matrix ignoriert, waere ein Fehler.
                continue
            self._asked += 1
            self._ledger.emit(
                "soteria.ask",
                {"from_role": "assessor", "field": field,
                 "reason_code": reason_code, "visibility": level},
            )
            for payload in send(field, reason_code):
                self._absorb(field, payload)

    def _absorb(self, field: str, payload: Mapping[str, Any]) -> None:
        code = str(payload.get("code") or "")
        if code:
            # `unknown_field` heisst nur "nicht mein Feld" und ist keine
            # Blockade. Alles andere ist eine und gehoert auf den Schirm.
            if code != "unknown_field":
                self._ledger.note_refusal(
                    str(payload.get("role") or "node"), f"ask {field}", code
                )
                self._receipt("refusal", {"field": field, "code": code,
                                          "role": payload.get("role")})
            return

        value = payload.get("value")
        if field in self._sheets:
            # Mehrere Knoten fuehren dasselbe Feld -- den Vertrag halten Kunde,
            # Zulieferer und der Vertragsagent. Stimmen sie ueberein, zaehlt es
            # einmal. Stimmen sie nicht ueberein, ist das ein Befund und keine
            # Nebensache: dann widersprechen sich zwei Parteien.
            if self._sheets[field] == value:
                return
            self._ledger.emit(
                "soteria.disagreement",
                {"field": field, "held": self._sheets[field], "offered": value,
                 "role": payload.get("role")},
            )
            self._receipt("disagreement", {"field": field, "held": self._sheets[field],
                                           "offered": value})
            return
        self._sheets[field] = value
        if payload.get("scope"):
            self._scopes[field] = str(payload["scope"])
        self._answered_by.add(str(payload.get("role") or ""))
        self._ledger.emit(
            "soteria.fact",
            {"role": payload.get("role"), "field": field,
             "visibility": payload.get("visibility"), "value": value,
             "scope": payload.get("scope", ""), "flags": payload.get("flags") or []},
        )
        self._receipt("fact", {"role": payload.get("role"), "field": field,
                               "visibility": payload.get("visibility"), "value": value})

        # Die Quarantaene muss greifen, sobald das Flag gelesen ist -- nicht
        # erst bei der Entscheidung. Deshalb steht market_sensitive weit vorn
        # im Frageplan.
        if field == "market_sensitive" and bool(value):
            self._ledger.mark_market_sensitive(str(payload.get("role") or "carrier"), field)

    def conclude(self) -> Decision:
        case = self._case
        report = case.report
        situation = {
            "track_blocked": report["track_blocked"],
            "train_operational": report["train_operational"],
            "severity": report["severity"],
        }
        expected = {p for p in case.party_ids}
        # Wer geschwiegen hat: angekuendigt oder im Lauf ausgeblieben. Die
        # Rollennamen der Antworten auf Parteien zurueckzurechnen ist unnoetig --
        # eine Partei, die nichts beigetragen hat, fehlt.
        contributed = {
            p for p in expected
            if set(case.roles_of(p)) & self._answered_by
        }
        missing = tuple(sorted((expected - contributed) | set(case.offline_parties)))

        measures, reason_code = decide(self._sheets, case.flags, missing, situation)
        tier = tier_of(measures)
        coverage = Coverage(
            answered=len(self._sheets), asked=self._asked,
            roles_missing=(),  # Parteien, nicht Rollen -- siehe parties_missing
        )
        self._ledger.emit(
            "soteria.coverage",
            {"answered": len(self._sheets), "asked": self._asked,
             "parties_expected": sorted(expected), "parties_missing": list(missing)},
        )

        params = {"case_id": case.case_id, "train_id": report["train_id"]}
        keys_needed = KEYS_REQUIRED[tier]
        self._ledger.emit(
            "soteria.grant.required",
            {"measures": list(measures), "tier": tier, "keys_needed": keys_needed},
        )

        book = GrantBook()
        book.load(case.keys)
        try:
            granted = book.require(measures, params)
        except EnvelopeError as exc:
            self._ledger.note_refusal(
                "assessor", f"decide {'+'.join(measures)}", exc.code, exc.detail
            )
            self._receipt("refusal", {"measures": list(measures), "code": exc.code})
            raise
        for human_id in granted:
            self._ledger.emit(
                "soteria.grant.given",
                {"measures": list(measures), "human_id": human_id,
                 "keys_have": len(granted), "keys_needed": keys_needed},
            )

        payload = {
            "measures": list(measures), "params": params, "tier": tier,
            "grants": list(granted), "coverage": coverage.as_dict(),
            "reason_code": reason_code, "parties_missing": list(missing),
        }
        receipt = self._chain.append("decision", payload)
        self._ledger.emit(
            "soteria.receipt",
            {"seq_in_chain": receipt.seq, "kind": "decision",
             "hash": receipt.hash, "prev": receipt.prev},
        )
        decision = Decision(
            measures=measures, params=params, tier=tier, grants=granted,
            coverage=coverage, reason_code=reason_code, receipt_hash=receipt.hash,
        )
        self._ledger.emit("soteria.decision", {**decision.as_dict(),
                                              "parties_missing": list(missing),
                                              "scopes": dict(self._scopes)})
        return decision

    def done(self, started: float) -> None:
        self._ledger.emit(
            "soteria.done",
            {
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "refusals": self._ledger.refusals,
                "refusal_codes": self._ledger.refusal_codes,
                "asks": self._asked,
                "answers": len(self._sheets),
                "quarantined": self._ledger.quarantined,
                "receipt_chain_verified": self._chain.verify(),
                "receipt_head": self._chain.head,
            },
        )

    @property
    def sheets(self) -> dict[str, Any]:
        return dict(self._sheets)

    @property
    def chain(self) -> ReceiptChain:
        return self._chain


def _grid_sender(grid: Grid, case: Case, ledger: Ledger) -> Callable[[str, str], list[dict]]:
    """Eine Nachfrage an alle Knoten dieses Falls, ueber echte Flower-Nachrichten."""
    node_ids = list(grid.get_node_ids())
    if not node_ids:
        raise EnvelopeError("quota", "no SuperNode is connected to this federation")
    round_no = {"n": 0}

    def send(field: str, reason_code: str) -> list[dict[str, Any]]:
        round_no["n"] += 1
        messages = [
            grid.create_message(
                content=wrap(ask_record("assessor", field, reason_code, case.case_id)),
                message_type=ASK_FIELD,
                dst_node_id=node_id,
                group_id=str(round_no["n"]),
            )
            for node_id in node_ids
        ]
        out: list[dict[str, Any]] = []
        timeout = min(ROUND_TIMEOUT, max(2.0, ledger.remaining_seconds()))
        for reply in grid.send_and_receive(messages, timeout=timeout):
            if reply.has_error():
                ledger.note_refusal("node", f"ask {field}", "quota", str(reply.error))
                continue
            out.append(read_reply(unwrap(reply.content)))
        return out

    return send


def run_incident(case: Case, ledger: Ledger, send: Callable[[str, str], list[dict]]) -> Decision:
    started = time.monotonic()
    assessor = Assessor(case, ledger)
    assessor.open()
    assessor.gather(send)
    try:
        return assessor.conclude()
    finally:
        assessor.done(started)


@app.main()
def main(grid: Grid, context: Context) -> None:
    """Fahre einen Vorfall gegen die verbundenen Parteiknoten."""
    case_id = context.run_config.get("case")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("run-config 'case' must name a directory in data/, e.g. case=\"s1\"")
    case = load_case(case_id.strip())

    seconds = context.run_config.get("budget_seconds")
    budget = Budget(
        max_delegations=len(ASK_PLAN) + 2,
        max_depth=2,
        seconds=float(seconds) if isinstance(seconds, (int, float)) and seconds > 0 else 240.0,
        max_connector_calls=0,
    )
    ledger = Ledger(budget, None)

    print(f"\n=== Soteria: {case.title} ===")
    try:
        decision = run_incident(case, ledger, _grid_sender(grid, case, ledger))
    except EnvelopeError as exc:
        print(f"\nKEINE ENTSCHEIDUNG: {exc.code}")
        print(f"  {exc.detail}")
        expected = (case.truth or {}).get("expect_refusal")
        print(f"Hinterlegte Erwartung: {expected!r} -> "
              f"{'TREFFER' if expected == exc.code else 'ABWEICHUNG'}")
        print(f"\n{ledger.headline()}")
        return

    print(f"\nMaßnahmen: {', '.join(decision.measures)} "
          f"(Stufe {decision.tier}, {decision.reason_code})")
    print(f"Freigaben: {', '.join(decision.grants) or 'keine noetig'}")
    print(f"Quittung:  {decision.receipt_hash}")
    if ledger.quarantined:
        print(f"QUARANTAENE: {', '.join(ledger.blocked_channels)} gesperrt")
    print(f"Ablehnungen: {ledger.refusal_codes or 'keine'}")
    truth = case.truth or {}
    if truth.get("measures"):
        hit = set(decision.measures) == set(truth["measures"])
        print(f"Wahrheit:  {', '.join(truth['measures'])} -> "
              f"{'TREFFER' if hit else 'ABWEICHUNG'}")
    print(f"\n{ledger.headline()}")

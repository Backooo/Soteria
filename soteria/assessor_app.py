"""The assessor as a ServerApp: asks the party nodes over Grid, then decides.

The only agent with decision authority -- and the one with the least raw data.
Every answer that arrives here is a traffic light, a threshold, a flag or a
coarse class; raw values only come from its own organisation.

The decision itself is made by the LLM `flower-endeavor-v1.0`, running as the
Flower AgentApp in `agent/` on SuperGrid (see `soteria/llm.py`). The rule policy
in `policy.py` stays as the safety floor and as the fallback when the model is
unreachable; every decision event says which of the two decided.

    ./scripts/federation.sh up s1
    uv run flwr run . carrier-fed --stream --run-config 'case="s1"'
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Mapping

from flwr.app import Context, Message
from flwr.serverapp import Grid, ServerApp

from .cases import Case, load_case
from .charter import Budget
from .envelope import Coverage, Decision, EnvelopeError
from .grants import GrantBook, KEYS_REQUIRED, tier_of
from .ledger import Ledger
from .llm import LLMConfig, propose
from .matrix import visibility
from .policy import ASK_PLAN, decide
from .receipts import ReceiptChain
from .wire import ASK_FIELDS, bundle_ask_record, read_bundle_reply

app = ServerApp()

# Upper bound for waiting on the nodes, halved against the budget's 240 s. The
# bundled round waits twice as long because it carries everything.
ROUND_TIMEOUT = 30.0


class StdoutEvents:
    """Every event as one prefixed JSON line, for `scripts/bridge.py`.

    Same shape as `scripts/record_run.py:Recorder`: `seq` counts from 1, `t` is
    seconds since the run started. `flush=True` so the line leaves the process
    while the run is still going -- a buffered stream would arrive only at the
    end and there would be nothing live about it.
    """

    PREFIX = "SOTERIA_EVENT "

    def __init__(self) -> None:
        self._seq = 0
        self._t0 = time.monotonic()

    def emit(self, event: dict[str, Any]) -> None:
        self._seq += 1
        line = {"seq": self._seq, "t": round(time.monotonic() - self._t0, 3), **event}
        print(self.PREFIX + json.dumps(line, ensure_ascii=False, default=str), flush=True)


class Assessor:
    """One incident: ask, gather, decide, record receipts.

    The transport is interchangeable: `send` takes (field, reason) pairs and
    returns the answers. In the federation that is `Grid.send_and_receive`; in
    `scripts/record_run.py` it is a direct call to the node handlers. The logic
    is the same in both cases -- that is the reason for this seam.
    """

    def __init__(self, case: Case, ledger: Ledger, llm: LLMConfig | None = None) -> None:
        self._case = case
        self._ledger = ledger
        self._llm = llm if llm is not None else LLMConfig.from_env()
        self._chain = ReceiptChain()
        self._sheets: dict[str, Any] = {}
        self._scopes: dict[str, str] = {}
        self._answered_by: set[str] = set()
        self._asked = 0

    # -- receipts --------------------------------------------------------

    def _receipt(self, kind: str, payload: Mapping[str, Any]) -> None:
        receipt = self._chain.append(kind, payload)
        self._ledger.emit(
            "soteria.receipt",
            {"seq_in_chain": receipt.seq, "kind": receipt.kind,
             "hash": receipt.hash, "prev": receipt.prev},
        )

    # -- flow ------------------------------------------------------------

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

    def plan(self) -> list[tuple[str, str]]:
        """The ask plan without the fields the assessor may not see at all.

        An ask plan that ignored the matrix would be a bug -- so the assessor
        only asks for what it can receive in some resolution.
        """
        return [(f, r) for f, r in ASK_PLAN if visibility(f, "assessor") != "none"]

    def gather(self, send: Callable[[list[tuple[str, str]]], dict[str, list[dict[str, Any]]]]) -> None:
        """The whole ask plan in ONE round to all nodes.

        Events stay per field in plan order -- ask, then answers -- so the views'
        event contract still holds and `market_sensitive` is still processed
        before everything else.
        """
        plan = self.plan()
        self._ledger.require_time("asking the plan", floor=2.0)
        answers = send(plan)
        for field, reason_code in plan:
            self._asked += 1
            self._ledger.emit(
                "soteria.ask",
                {"from_role": "assessor", "field": field,
                 "reason_code": reason_code, "visibility": visibility(field, "assessor")},
            )
            for payload in answers.get(field, []):
                self._absorb(field, payload)

    def _absorb(self, field: str, payload: Mapping[str, Any]) -> None:
        code = str(payload.get("code") or "")
        if code:
            # `unknown_field` only means "not my field" and is not a block.
            # Anything else is one and belongs on screen.
            if code != "unknown_field":
                self._ledger.note_refusal(
                    str(payload.get("role") or "node"), f"ask {field}", code
                )
                self._receipt("refusal", {"field": field, "code": code,
                                          "role": payload.get("role")})
            return

        value = payload.get("value")
        if field in self._sheets:
            # Several nodes hold the same field -- the contract is held by the
            # customer, the supplier and the legal agent. If they agree, it
            # counts once. If they disagree, that is a finding, not a detail:
            # two parties contradict each other.
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

        # The quarantine must take effect as soon as the flag is read -- not
        # only at decision time. That is why market_sensitive sits early in the
        # ask plan.
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
        # Who stayed silent: announced offline or absent during the run. Mapping
        # answer roles back to parties is unnecessary -- a party that
        # contributed nothing is missing.
        contributed = {
            p for p in expected
            if set(case.roles_of(p)) & self._answered_by
        }
        missing = tuple(sorted((expected - contributed) | set(case.offline_parties)))

        coverage = Coverage(
            answered=len(self._sheets), asked=self._asked,
            roles_missing=(),  # parties, not roles -- see parties_missing
        )
        self._ledger.emit(
            "soteria.coverage",
            {"answered": len(self._sheets), "asked": self._asked,
             "parties_expected": sorted(expected), "parties_missing": list(missing)},
        )

        # The LLM decides from the same projections; the rule policy is the
        # safety floor and the fallback. Neither ever sees a raw party value.
        policy = decide(self._sheets, case.flags, missing, situation)
        self._ledger.emit("soteria.model.request", {
            "model": self._llm.model if self._llm.enabled else "",
            "federation": self._llm.federation,
            "signals": sorted(self._sheets),
        })
        proposal = propose(
            self._llm, self._sheets, case.flags, missing, situation, policy,
            time_left=self._ledger.remaining_seconds(),
        )
        self._ledger.emit("soteria.model.decision", proposal.as_event())
        measures, reason_code = proposal.measures, proposal.reason_code
        tier = tier_of(measures)

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
            "decided_by": proposal.decided_by, "model": proposal.model,
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
                                              "scopes": dict(self._scopes),
                                              "decided_by": proposal.decided_by,
                                              "model": proposal.model,
                                              "rationale": proposal.rationale})
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


Sender = Callable[[list[tuple[str, str]]], dict[str, list[dict[str, Any]]]]


def _grid_sender(grid: Grid, case: Case, ledger: Ledger) -> Sender:
    """The whole ask plan as ONE Flower message per node.

    Measured: thirteen rounds cost 69-127 s, because every message starts a
    ClientApp process on the node. One round per node now carries everything.
    """
    node_ids = list(grid.get_node_ids())
    if not node_ids:
        raise EnvelopeError("quota", "no SuperNode is connected to this federation")

    def send(plan: list[tuple[str, str]]) -> dict[str, list[dict[str, Any]]]:
        messages = [
            Message(
                content=bundle_ask_record("assessor", plan, case.case_id),
                message_type=ASK_FIELDS,
                dst_node_id=node_id,
                group_id="1",
            )
            for node_id in node_ids
        ]
        by_field: dict[str, list[dict[str, Any]]] = {field: [] for field, _ in plan}
        timeout = min(ROUND_TIMEOUT * 2, max(5.0, ledger.remaining_seconds()))
        replies = list(grid.send_and_receive(messages, timeout=timeout))
        if len(replies) < len(node_ids):
            # A node did not answer in time. That is a gap, not a block --
            # conclude() names it in the coverage.
            ledger.emit("soteria.warning", {
                "detail": f"{len(node_ids) - len(replies)} of {len(node_ids)} nodes "
                          f"did not answer within {timeout:.0f}s"})
        for reply in replies:
            if reply.has_error():
                ledger.note_refusal("node", "ask bundle", "quota", str(reply.error))
                continue
            for payload in read_bundle_reply(reply.content):
                if payload["field"] in by_field:
                    by_field[payload["field"]].append(payload)
        return by_field

    return send


def run_incident(case: Case, ledger: Ledger, send: Sender, llm: LLMConfig | None = None) -> Decision:
    started = time.monotonic()
    assessor = Assessor(case, ledger, llm)
    assessor.open()
    assessor.gather(send)
    try:
        return assessor.conclude()
    finally:
        assessor.done(started)


@app.main()
def main(grid: Grid, context: Context) -> None:
    """Run one incident against the connected party nodes."""
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
    ledger = Ledger(budget, StdoutEvents())
    llm = LLMConfig.from_run_config(context.run_config)

    print(f"\n=== Soteria: {case.title} ===")
    try:
        decision = run_incident(case, ledger, _grid_sender(grid, case, ledger), llm)
    except EnvelopeError as exc:
        print(f"\nNO DECISION: {exc.code}")
        print(f"  {exc.detail}")
        expected = (case.truth or {}).get("expect_refusal")
        print(f"Expected: {expected!r} -> "
              f"{'HIT' if expected == exc.code else 'MISMATCH'}")
        print(f"\n{ledger.headline()}")
        return

    print(f"\nMeasures:  {', '.join(decision.measures)} "
          f"(tier {decision.tier}, {decision.reason_code})")
    print(f"Approvals: {', '.join(decision.grants) or 'none required'}")
    print(f"Receipt:   {decision.receipt_hash}")
    if ledger.quarantined:
        print(f"QUARANTINE: {', '.join(ledger.blocked_channels)} blocked")
    print(f"Refusals:  {ledger.refusal_codes or 'none'}")
    truth = case.truth or {}
    if truth.get("measures"):
        hit = set(decision.measures) == set(truth["measures"])
        print(f"Truth:     {', '.join(truth['measures'])} -> "
              f"{'HIT' if hit else 'MISMATCH'}")
    print(f"\n{ledger.headline()}")

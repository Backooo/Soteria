"""The ClientApp that runs on a party's machine.

Start on the party's computer:

    flower-supernode --insecure --superlink 127.0.0.1:9092 \
        --node-config 'party="customer_c1_frischemarkt" case="s1"'

The node loads **only** its party's records and answers `query.ask_field`.
Every answer is a projected scalar or a typed refusal.

No model runs here: a projection is a function, not inference. So the party
does not have to lend the federation a model -- which is a good part of the
reason it takes part at all.

Three bolts, independent of each other:

1. **The node does not have it.** `raw_records_for_party` opens only its own
   files. Another customer's contract does not exist in memory here.
2. **The matrix projects.** `Field.project` raises `not_in_matrix` if the asker
   is not allowed to see the field.
3. **The transport carries only scalars.** `fact_record` rejects a raw object,
   even if the matrix wrongly allowed it.
"""

from __future__ import annotations

from typing import Any, Mapping

from flwr.app import Context, Message
from flwr.clientapp import ClientApp

from .cases import Case, _worst, load_case, raw_records_for_party
from .envelope import EnvelopeError
from .matrix import FIELDS, visibility, vocabulary
from .wire import (
    bundle_reply,
    fact_record,
    read_ask,
    read_bundle_ask,
    refusal_record,
    unwrap,
    wrap,
)

app = ClientApp()


def _project_scope(scope: str, asker: str, thresholds: Mapping[str, Any]) -> str:
    """Bring an answer's reference unit down to the permitted resolution.

    A wagon number (`W02`) is not a secret -- it is in the shared report. A
    cargo class is one: it falls under `cargo_class` and may only reach the
    asker at the resolution the matrix grants there. Without this line, `scope`
    would be a side channel around the matrix.
    """
    if not scope:
        return ""
    if scope not in vocabulary("cargo_class"):
        return scope
    try:
        return str(FIELDS["cargo_class"].project(scope, asker, thresholds))
    except EnvelopeError:
        # The asker may not know the cargo class at all. Then not as a
        # reference unit either -- the value itself stays valid.
        return ""


def answer_ask(
    case: Case, party_id: str, asker: str, field: str, reason_code: str
) -> dict[str, Any]:
    """This node's answer as a flat dict -- exactly what goes on the wire.

    Separate from the Flower message so it can be tested without a SuperLink.
    Returns a typed refusal on any problem and does not raise: a node that
    crashes looks like silence to the assessor, and silence is not a reason.
    """
    def refuse(code: str) -> dict[str, Any]:
        return {"role": party_id, "field": field, "visibility": "none",
                "value": "", "scope": "", "code": code, "flags": []}

    if field not in FIELDS:
        return refuse("unknown_field")
    if party_id in case.offline_parties:
        return refuse("quota")

    spec = FIELDS[field]
    try:
        records = raw_records_for_party(case, party_id)
    except EnvelopeError as exc:
        return refuse(exc.code)

    block = records.get(spec.owner) or {}
    if field not in block:
        # This node does not hold the field. No forwarding, no searching.
        return refuse("unknown_field")

    raw = block[field]
    scope = ""
    try:
        if isinstance(raw, Mapping):
            # Multi-valued: per wagon, consignment or cargo class.
            candidates = {str(k): v for k, v in raw.items() if not str(k).startswith("_")}
            if not candidates:
                return refuse("unknown_field")
            # First pick the reference unit by a CANONICAL severity -- which
            # consignment is the most critical must not depend on who asks.
            # Then project the value for the asker.
            level = spec.ranking_level
            if level:
                severity = {
                    key: spec.project_at(level, value, case.thresholds)
                    for key, value in candidates.items()
                }
                scope, _ = _worst(severity)
            else:
                scope = next(iter(candidates))
            value = spec.project(candidates[scope], asker, case.thresholds)
            # The reference unit must pass through the same matrix as the value.
            # Otherwise `scope` would be an unaudited side channel:
            # "customer_stock = gelb @pharmaceutical" reveals the cargo class,
            # which the assessor may only see coarsely. Found by
            # scripts/wire_proof.py.
            scope = _project_scope(scope, asker, case.thresholds)
        else:
            value = spec.project(raw, asker, case.thresholds)
    except EnvelopeError as exc:
        return refuse(exc.code)

    level = visibility(field, asker)
    try:
        record = fact_record(spec.speaks_as, field, level, value, spec.flags, scope)
    except EnvelopeError as exc:
        return refuse(exc.code)

    from .wire import read_reply

    return read_reply(record)


@app.query("ask_field")
def ask_field(message: Message, context: Context) -> Message:
    """Answer exactly one ask for exactly one field."""
    party_id = str(context.node_config.get("party", "")).strip()
    try:
        asker, field, reason_code, case_id = read_ask(unwrap(message.content))
    except EnvelopeError as exc:
        return Message(
            content=wrap(refusal_record(party_id or "unknown", "?", exc.code)), reply_to=message
        )

    configured = str(context.node_config.get("case", "")).strip()
    if configured and configured != case_id:
        # This node is set up for a different case. Do not answer, do not
        # reload -- otherwise the node configuration would have no effect.
        return Message(
            content=wrap(refusal_record(party_id or "unknown", field, "quota")), reply_to=message
        )

    try:
        case = load_case(case_id)
        case.party_type(party_id)  # raises if this node is not a party
    except EnvelopeError as exc:
        return Message(
            content=wrap(refusal_record(party_id or "unknown", field, exc.code)), reply_to=message
        )

    reply = answer_ask(case, party_id, asker, field, reason_code)
    record = (
        refusal_record(reply["role"] or party_id, field, reply["code"])
        if reply["code"]
        else fact_record(
            reply["role"], field, reply["visibility"], reply["value"],
            tuple(reply["flags"]), reply["scope"],
        )
    )
    return Message(content=wrap(record), reply_to=message)


def answer_bundle(
    case: Case, party_id: str, asker: str, plan: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    """Answer the whole ask plan, field by field with `answer_ask`.

    Only the transport is bundled. Every field goes through the matrix and the
    scalar bolt individually -- one field can be refused without toppling the
    others.
    """
    return [answer_ask(case, party_id, asker, field, reason) for field, reason in plan]


def _record_of(reply: dict[str, Any], party_id: str, field: str):
    if reply["code"]:
        return refusal_record(reply["role"] or party_id, field, reply["code"])
    return fact_record(
        reply["role"], field, reply["visibility"], reply["value"],
        tuple(reply["flags"]), reply["scope"],
    )


@app.query("ask_fields")
def ask_fields(message: Message, context: Context) -> Message:
    """Answer the whole ask plan in one message.

    One message instead of thirteen: every message starts a ClientApp process
    on the node, and thirteen of them cost 69-127 s.
    """
    party_id = str(context.node_config.get("party", "")).strip()
    try:
        asker, case_id, plan = read_bundle_ask(message.content)
    except EnvelopeError as exc:
        return Message(
            content=bundle_reply([refusal_record(party_id or "unknown", "?", exc.code)]),
            reply_to=message,
        )

    def refuse_all(code: str) -> Message:
        return Message(
            content=bundle_reply(
                [refusal_record(party_id or "unknown", field, code) for field, _ in plan]
            ),
            reply_to=message,
        )

    configured = str(context.node_config.get("case", "")).strip()
    if configured and configured != case_id:
        return refuse_all("quota")
    try:
        case = load_case(case_id)
        case.party_type(party_id)
    except EnvelopeError as exc:
        return refuse_all(exc.code)

    replies = answer_bundle(case, party_id, asker, plan)
    return Message(
        content=bundle_reply(
            [_record_of(r, party_id, field) for r, (field, _) in zip(replies, plan)]
        ),
        reply_to=message,
    )

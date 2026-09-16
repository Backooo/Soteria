"""The wire between the assessor and the party nodes.

A Flower message carries a `RecordDict`. A `ConfigRecord` inside it only holds
scalars and lists of scalars (`flwr/common/typing.py:24-26`). Here that is not an
obstacle but the **second bolt**: a projection is always a scalar (`"rot"`,
`"above"`, a number, a bool), a raw object never is. A `temperature_curve`
therefore cannot be sent at all.

`fact_record()` enforces this instead of hoping for it, and raises `bad_value`
if anyone tries. Matrix and transport thus check the same thing independently
of each other -- a bug in one layer does not take the other down with it.
"""

from __future__ import annotations

from typing import Any

from flwr.app import ConfigRecord, RecordDict

from .envelope import FLAG, REASON, REFUSAL, ROLES, EnvelopeError

ASK_FIELD = "query.ask_field"
RECORD_KEY = "soteria"
SCALARS = (str, int, float, bool)


def ask_record(asker: str, field: str, reason_code: str, case_id: str) -> ConfigRecord:
    """The ask as a record. Four scalars, no free-text field."""
    if asker not in ROLES:
        raise EnvelopeError("unknown_role", f"{asker!r} is not one of {ROLES}")
    if reason_code not in REASON:
        raise EnvelopeError("bad_value", f"reason_code={reason_code!r} is not one of {REASON}")
    return ConfigRecord(
        {"asker": asker, "field": field, "reason_code": reason_code, "case_id": case_id}
    )


def read_ask(record: ConfigRecord) -> tuple[str, str, str, str]:
    """(asker, field, reason_code, case_id) from an ask record."""
    try:
        return (
            str(record["asker"]),
            str(record["field"]),
            str(record["reason_code"]),
            str(record["case_id"]),
        )
    except KeyError as exc:
        raise EnvelopeError("bad_value", f"ask record is missing {exc.args[0]!r}") from None


def fact_record(
    role: str,
    field: str,
    visibility: str,
    value: Any,
    flags: tuple[str, ...] = (),
    scope: str = "",
) -> ConfigRecord:
    """The projected answer as a record.

    `scope` names the reference unit if the field has one -- the wagon number
    or the cargo class. A wagon number is not a secret; it is what makes the
    answer readable in the view.

    Raises `bad_value` if `value` is not a scalar. That is the bolt: a raw
    object cannot leave the party's node.
    """
    if not isinstance(value, SCALARS):
        raise EnvelopeError(
            "bad_value",
            f"{field} projected to {type(value).__name__}, which is not a scalar; "
            "a raw object must never reach the wire",
        )
    unknown = [f for f in flags if f not in FLAG]
    if unknown:
        raise EnvelopeError("bad_value", f"unknown flags {unknown}")
    return ConfigRecord(
        {
            "role": role,
            "field": field,
            "visibility": visibility,
            "value": value,
            "scope": scope,
            "code": "",
            "flags": list(flags),
        }
    )


def refusal_record(actor: str, field: str, code: str) -> ConfigRecord:
    """A typed refusal as a record. Never carries a value."""
    if code not in REFUSAL:
        raise EnvelopeError("bad_value", f"{code!r} is not a typed refusal")
    return ConfigRecord(
        {
            "role": actor,
            "field": field,
            "visibility": "none",
            "value": "",
            "scope": "",
            "code": code,
            "flags": [],
        }
    )


def read_reply(record: ConfigRecord) -> dict[str, Any]:
    return {
        "role": str(record.get("role", "")),
        "field": str(record.get("field", "")),
        "visibility": str(record.get("visibility", "none")),
        "value": record.get("value", ""),
        "scope": str(record.get("scope", "")),
        "code": str(record.get("code", "")),
        "flags": [str(f) for f in (record.get("flags") or [])],
    }


def wrap(record: ConfigRecord) -> RecordDict:
    return RecordDict({RECORD_KEY: record})


def unwrap(records: RecordDict) -> ConfigRecord:
    try:
        return records[RECORD_KEY]
    except KeyError:
        raise EnvelopeError("bad_value", f"message carries no {RECORD_KEY!r} record") from None


# --- bundled ask: one message per node instead of one per field ------------
#
# Measured on the real federation: 13 rounds cost 69-127 s, because every
# message starts a ClientApp process. One message per node now carries the
# whole ask plan; the reply is a RecordDict with ONE ConfigRecord per field.
# The scalar bolt therefore still applies to every field individually -- the
# transport is bundled, not the check.

ASK_FIELDS = "query.ask_fields"
_BUNDLE_KEY = "soteria.ask"


def bundle_ask_record(
    asker: str, plan: list[tuple[str, str]], case_id: str
) -> RecordDict:
    """The whole ask plan as one ask. Two string lists, no free text."""
    if asker not in ROLES:
        raise EnvelopeError("unknown_role", f"{asker!r} is not one of {ROLES}")
    bad = [reason for _, reason in plan if reason not in REASON]
    if bad:
        raise EnvelopeError("bad_value", f"reason_codes {bad} are not in {REASON}")
    if not plan:
        raise EnvelopeError("bad_value", "an ask bundle needs at least one field")
    return RecordDict({
        _BUNDLE_KEY: ConfigRecord({
            "asker": asker,
            "case_id": case_id,
            "fields": [field for field, _ in plan],
            "reasons": [reason for _, reason in plan],
        })
    })


def read_bundle_ask(records: RecordDict) -> tuple[str, str, list[tuple[str, str]]]:
    """(asker, case_id, [(field, reason), ...]) from a bundled ask."""
    try:
        record = records[_BUNDLE_KEY]
        fields = [str(f) for f in record["fields"]]
        reasons = [str(r) for r in record["reasons"]]
        asker, case_id = str(record["asker"]), str(record["case_id"])
    except KeyError as exc:
        raise EnvelopeError("bad_value", f"ask bundle is missing {exc.args[0]!r}") from None
    if len(fields) != len(reasons):
        raise EnvelopeError("bad_value", "fields and reasons differ in length")
    return asker, case_id, list(zip(fields, reasons))


def _answer_key(index: int) -> str:
    return f"soteria.answer.{index:03d}"


def bundle_reply(records: list[ConfigRecord]) -> RecordDict:
    """A node's answers, in ask-plan order."""
    return RecordDict({_answer_key(i): r for i, r in enumerate(records)})


def read_bundle_reply(records: RecordDict) -> list[dict[str, Any]]:
    keys = sorted(k for k in records.config_records if k.startswith("soteria.answer."))
    return [read_reply(records[k]) for k in keys]

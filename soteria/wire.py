"""Der Draht zwischen dem Bewerter und den Parteiknoten.

Eine Flower-Nachricht traegt einen `RecordDict`. Ein `ConfigRecord` darin nimmt
nur Skalare und Skalarlisten auf (`flwr/common/typing.py:24-26`). Das ist hier
kein Hindernis, sondern der **zweite Riegel**: eine Projektion ist immer ein
Skalar (`"rot"`, `"above"`, eine Zahl, ein bool), ein Rohobjekt ist keiner. Eine
`temperature_curve` laesst sich also gar nicht verschicken.

`fact_record()` erzwingt das, statt es zu hoffen, und wirft `bad_value`, wenn
jemand es versucht. Matrix und Transport pruefen damit unabhaengig voneinander
dasselbe -- ein Fehler in der einen Schicht reisst die andere nicht mit.
"""

from __future__ import annotations

from typing import Any

from flwr.app import ConfigRecord, RecordDict

from .envelope import FLAG, REASON, REFUSAL, ROLES, EnvelopeError

ASK_FIELD = "query.ask_field"
RECORD_KEY = "soteria"
SCALARS = (str, int, float, bool)


def ask_record(asker: str, field: str, reason_code: str, case_id: str) -> ConfigRecord:
    """Die Nachfrage als Record. Vier Skalare, kein Freitextfeld."""
    if asker not in ROLES:
        raise EnvelopeError("unknown_role", f"{asker!r} is not one of {ROLES}")
    if reason_code not in REASON:
        raise EnvelopeError("bad_value", f"reason_code={reason_code!r} is not one of {REASON}")
    return ConfigRecord(
        {"asker": asker, "field": field, "reason_code": reason_code, "case_id": case_id}
    )


def read_ask(record: ConfigRecord) -> tuple[str, str, str, str]:
    """(asker, field, reason_code, case_id) aus einem Nachfrage-Record."""
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
    """Die projizierte Antwort als Record.

    `scope` nennt die Bezugsgroesse, wenn das Feld eine hat -- die Wagennummer
    oder die Ladungsklasse. Eine Wagennummer ist kein Geheimnis; sie macht die
    Antwort in der Ansicht erst lesbar.

    Wirft `bad_value`, wenn `value` kein Skalar ist. Das ist der Riegel: ein
    Rohobjekt kann den Knoten der Partei nicht verlassen.
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
    """Eine getippte Ablehnung als Record. Traegt niemals einen Wert."""
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


# --- gebuendelte Nachfrage: eine Nachricht je Knoten statt eine je Feld -----
#
# Gemessen auf der echten Foederation: 13 Runden kosteten 69-127 s, weil jede
# Nachricht einen ClientApp-Prozess startet. Eine Nachricht je Knoten traegt
# jetzt den ganzen Frageplan; die Antwort ist ein RecordDict mit EINEM
# ConfigRecord je Feld. Der Skalar-Riegel gilt damit weiter fuer jedes Feld
# einzeln -- gebuendelt wird der Transport, nicht die Pruefung.

ASK_FIELDS = "query.ask_fields"
_BUNDLE_KEY = "soteria.ask"


def bundle_ask_record(
    asker: str, plan: list[tuple[str, str]], case_id: str
) -> RecordDict:
    """Der ganze Frageplan als eine Nachfrage. Zwei String-Listen, kein Freitext."""
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
    """(asker, case_id, [(field, reason), ...]) aus einer gebuendelten Nachfrage."""
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
    """Die Antworten eines Knotens, in Frageplan-Reihenfolge."""
    return RecordDict({_answer_key(i): r for i, r in enumerate(records)})


def read_bundle_reply(records: RecordDict) -> list[dict[str, Any]]:
    keys = sorted(k for k in records.config_records if k.startswith("soteria.answer."))
    return [read_reply(records[k]) for k in keys]

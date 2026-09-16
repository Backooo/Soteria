"""Der ClientApp, der auf der Maschine einer Partei laeuft.

Start auf dem Rechner der Partei:

    flower-supernode --insecure --superlink 127.0.0.1:9092 \
        --node-config 'party="customer_c1_frischemarkt" case="s1"'

Der Knoten laedt **nur** die Datensaetze seiner Partei und beantwortet
`query.ask_field`. Jede Antwort ist ein projizierter Skalar oder eine getippte
Ablehnung.

Ein Modell laeuft hier nicht: eine Projektion ist eine Funktion, keine Inferenz.
Die Partei muss der Foederation also kein Modell leihen -- was ein guter Teil des
Grundes ist, warum sie ueberhaupt mitmacht.

Drei Riegel, unabhaengig voneinander:

1. **Der Knoten hat es nicht.** `raw_records_for_party` oeffnet nur die eigenen
   Dateien. Der Vertrag eines anderen Kunden existiert hier nicht im Speicher.
2. **Die Matrix projiziert.** `Field.project` wirft `not_in_matrix`, wenn der
   Fragende das Feld nicht sehen darf.
3. **Der Transport traegt nur Skalare.** `fact_record` weist ein Rohobjekt
   zurueck, selbst wenn die Matrix es faelschlich erlaubte.
"""

from __future__ import annotations

from typing import Any, Mapping

from flwr.app import Context, Message
from flwr.clientapp import ClientApp

from .cases import Case, _worst, load_case, raw_records_for_party
from .envelope import EnvelopeError
from .matrix import FIELDS, visibility
from .wire import fact_record, read_ask, refusal_record, unwrap, wrap

app = ClientApp()


def answer_ask(
    case: Case, party_id: str, asker: str, field: str, reason_code: str
) -> dict[str, Any]:
    """Die Antwort dieses Knotens, als flaches dict -- genau das, was auf den Draht geht.

    Getrennt von der Flower-Nachricht, damit sie ohne SuperLink testbar ist.
    Gibt bei jedem Problem eine getippte Ablehnung zurueck und wirft nicht: ein
    Knoten, der abbricht, sieht fuer den Bewerter wie Schweigen aus, und
    Schweigen ist kein Grund.
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
        # Dieser Knoten fuehrt das Feld nicht. Keine Weiterleitung, keine Suche.
        return refuse("unknown_field")

    raw = block[field]
    scope = ""
    try:
        if isinstance(raw, Mapping):
            # Mehrwertig: je Wagen, Konsignation oder Ladungsklasse. Projizieren,
            # dann die schlimmste Bezugsgroesse nennen.
            projected = {
                str(key): spec.project(value, asker, case.thresholds)
                for key, value in raw.items()
            }
            if not projected:
                return refuse("unknown_field")
            scope, value = _worst(projected)
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
    """Beantworte genau eine Nachfrage nach genau einem Feld."""
    party_id = str(context.node_config.get("party", "")).strip()
    try:
        asker, field, reason_code, case_id = read_ask(unwrap(message.content))
    except EnvelopeError as exc:
        return Message(
            content=wrap(refusal_record(party_id or "unknown", "?", exc.code)), reply_to=message
        )

    configured = str(context.node_config.get("case", "")).strip()
    if configured and configured != case_id:
        # Dieser Knoten ist fuer einen anderen Fall aufgesetzt. Nicht antworten,
        # nicht nachladen -- sonst waere die Knotenkonfiguration wirkungslos.
        return Message(
            content=wrap(refusal_record(party_id or "unknown", field, "quota")), reply_to=message
        )

    try:
        case = load_case(case_id)
        case.party_type(party_id)  # wirft, wenn dieser Knoten nicht Partei ist
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

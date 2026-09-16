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
    """Den Bezug einer Antwort auf die erlaubte Aufloesung bringen.

    Eine Wagennummer (`W02`) ist kein Geheimnis -- sie steht in der gemeinsamen
    Meldung. Eine Ladungsklasse ist eines: sie faellt unter `cargo_class` und
    darf den Frager nur in der Aufloesung erreichen, die die Matrix ihm dort
    zugesteht. Ohne diese Zeile waere `scope` ein Seitenkanal um die Matrix
    herum.
    """
    if not scope:
        return ""
    if scope not in vocabulary("cargo_class"):
        return scope
    try:
        return str(FIELDS["cargo_class"].project(scope, asker, thresholds))
    except EnvelopeError:
        # Der Frager darf die Ladungsklasse gar nicht kennen. Dann auch nicht
        # als Bezug -- der Wert selbst bleibt gueltig.
        return ""


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
            # Mehrwertig: je Wagen, Konsignation oder Ladungsklasse.
            candidates = {str(k): v for k, v in raw.items() if not str(k).startswith("_")}
            if not candidates:
                return refuse("unknown_field")
            # Erst den Bezug waehlen, nach einer KANONISCHEN Schwere -- welche
            # Konsignation die kritischste ist, darf nicht davon abhaengen, wer
            # fragt. Dann den Wert fuer den Frager projizieren.
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
            # Der Bezug muss durch dieselbe Matrix wie der Wert. Sonst waere
            # `scope` ein unauditierter Seitenkanal: "customer_stock = gelb
            # @pharmaceutical" verraet die Ladungsklasse, die der Bewerter nur
            # grob sehen darf. Gefunden von scripts/wire_proof.py.
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


def answer_bundle(
    case: Case, party_id: str, asker: str, plan: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    """Den ganzen Frageplan beantworten, Feld fuer Feld mit `answer_ask`.

    Gebuendelt wird nur der Transport. Jedes Feld geht einzeln durch Matrix und
    Skalar-Riegel -- ein Feld kann abgelehnt werden, ohne die anderen zu kippen.
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
    """Beantworte den ganzen Frageplan in einer Nachricht.

    Eine Nachricht statt dreizehn: jede Nachricht startet auf dem Knoten einen
    ClientApp-Prozess, und dreizehn davon kosteten 69-127 s.
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

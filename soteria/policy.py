"""Der Bewerter als Regelmaschine. Sieht nur Projektionen.

Diese Datei kennt keine Fall-ID und keine hinterlegte Wahrheit -- sie bekommt
Ampeln, Schwellen und Flags und entscheidet daraus. `tests/test_policy.py`
prueft das, indem es den Quelltext nach Fallnamen durchsucht. Waere hier
irgendwo `if case_id == "s3"`, waere die Trefferquote eine Zahl ueber sich
selbst.

**Ehrlichkeit:** die Reihenfolge der Regeln wurde gegen die bekannten Faelle
geschrieben. Ihre Trefferquote ist daher eine Konsistenzpruefung, keine
Behauptung. Die Quote ueber die Holdout-Faelle, die der Datenstrang nicht zeigt,
ist die einzige Zahl, die etwas behauptet.

Die Reihenfolge der Regeln ist die Reihenfolge der Unumkehrbarkeit:
Sicherheit vor Machbarkeit vor Haftung vor Kosten.
"""

from __future__ import annotations

from typing import Any, Mapping

# In welcher Reihenfolge der Bewerter fragt: (Feld, Grund).
# `market_sensitive` steht bewusst an zweiter Stelle: die Quarantaene muss
# greifen, bevor irgendetwas anderes passiert.
ASK_PLAN: tuple[tuple[str, str], ...] = (
    ("temperature_curve", "safety"),
    ("market_sensitive", "confidentiality"),
    ("cargo_class", "safety"),
    ("route_weakness", "feasibility"),
    ("alt_route_status", "feasibility"),
    ("road_access", "feasibility"),
    ("locality_class", "safety"),
    ("replacement_available", "feasibility"),
    ("cooling_required", "safety"),
    ("customer_stock", "time"),
    ("customer_urgency", "time"),
    ("contract_penalty", "liability"),
    ("contract_deadline_h", "liability"),
)


def _is(sheets: Mapping[str, Any], field: str, *values: Any) -> bool:
    return sheets.get(field) in values


def decide(
    sheets: Mapping[str, Any],
    flags: tuple[str, ...],
    missing: tuple[str, ...],
    situation: Mapping[str, Any] | None = None,
) -> tuple[tuple[str, ...], str]:
    """Waehle Maßnahmen aus Ampeln, Schwellen, Flags und der gemeinsamen Meldung.

    `sheets`    Feldname -> projizierter Wert, wie er vom Knoten kam.
    `flags`     Lagekennzeichen, aus den Daten abgeleitet.
    `missing`   Parteien, die nicht geantwortet haben.
    `situation` Die Meldung, die alle sehen duerfen: `track_blocked`,
                `train_operational`, `severity`. Kein Geheimnis -- der Fahrer
                hat sie gemeldet.
    """
    sit = dict(situation or {})
    blocked = bool(sit.get("track_blocked"))
    operational = str(sit.get("train_operational", "normal"))
    immobilized = operational == "immobilized"
    inhabited = _is(sheets, "locality_class", "village", "town_edge", "dense_urban")

    # 1 Gefahrgut beschaedigt und der Zug kommt nicht weg. Nichtwissen ueber ein
    #   moegliches Leck ist selbst der Grund anzuhalten und zu melden -- erst
    #   recht neben Wohnbebauung.
    if "hazmat" in flags and (immobilized or inhabited):
        return ("stop_train", "notify_authority"), "safety"

    # 2 Strecke unpassierbar. Keine Maßnahme am Zug hilft, er muss herum -- und
    #   nur, wenn es eine Umleitung gibt.
    if blocked or _is(sheets, "route_weakness", "rot"):
        if _is(sheets, "alt_route_status", "available", "available_short", "long_detour"):
            return ("alt_transport",), "feasibility"
        # Keine Umleitung. Umladen braucht eine Strasse.
        if _is(sheets, "road_access", "gruen", "gelb") and not _is(
            sheets, "replacement_available", "rot"
        ):
            return ("reload",), "feasibility"
        return ("hold", "contact"), "feasibility"

    # 3 Ladung ausserhalb des Fensters. Umladen nur, wenn es Ersatz gibt.
    if _is(sheets, "temperature_curve", "rot"):
        if _is(sheets, "replacement_available", "gruen", "gelb"):
            return ("cool", "reload"), "safety"
        return ("cool", "hold"), "safety"

    # 4 Eine Partei fehlt und die Ladung ist verderblich: konservativ handeln und
    #   die Luecke nennen. Nicht entscheiden ist keine Option.
    if missing and "perishable" in flags:
        return ("cool", "hold"), "missing_data"

    # 5 Lebensgefahr oder kritische Dringlichkeit beim Kunden, und die Frist wird
    #   knapp. Der Bewerter weiss nicht, welcher Kunde -- nur wie dringend.
    if _is(sheets, "customer_urgency", "rot") and _is(sheets, "contract_deadline_h", "below"):
        if _is(sheets, "replacement_available", "gruen"):
            return ("reload",), "time"
        return ("contact",), "time"

    # 6 Vertragsstrafe ueber der Schwelle, und Umladen ist machbar. Wie hoch sie
    #   ist, erfaehrt der Bewerter nicht -- nur dass sie darueber liegt.
    if _is(sheets, "contract_penalty", "above") and not _is(
        sheets, "replacement_available", "rot"
    ):
        return ("reload",), "liability"

    # 7 Kuehlung angeschlagen, aber die Ware noch im Fenster und der Kunde hat
    #   Bestand. Kuehlen ist billig und haelt alle Optionen offen; eine teure
    #   Maßnahme waere hier Verschwendung. Das ist die Regel, fuer die die Ampel
    #   auf dem Bestand erfunden ist.
    if _is(sheets, "temperature_curve", "gelb") and _is(sheets, "cooling_required", True):
        if _is(sheets, "customer_stock", "gruen"):
            return ("cool",), "safety"
        return ("cool", "hold"), "safety"

    # 8 Alles gruen und der Zug faehrt. `sheets and not missing` ist wesentlich:
    #   ohne Antworten ist `temperature_curve` ebenfalls None, und "nichts
    #   bekannt" darf nicht wie "keine Kuehlladung" aussehen.
    if (
        sheets
        and not missing
        and operational == "normal"
        and not blocked
        and _is(sheets, "temperature_curve", "gruen", None)
    ):
        return ("proceed",), "cost"

    # 9 Nichts Belastbares. Halten ist die umkehrbarste Maßnahme.
    return ("hold",), ("missing_data" if (missing or not sheets) else "time")

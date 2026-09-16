"""Die Need-to-know-Matrix: wer welches Feld in welcher Aufloesung sieht.

Das ist das Produkt. Nicht die Prompts, nicht die Rollenbeschreibungen -- diese
Tabelle, geprueft in Python, bevor ein Modell laeuft.

Drei Begriffe:

- **Eigentuemer**: die Stelle, die den Rohwert haelt. Muss keine Agentenrolle
  sein: `route_weakness` und `market_sensitive` gehoeren `infra`, einer
  Datenquelle im Szenario. Sonst gaebe es fuer diese Felder keine Quelle.
- **Sichtbarkeit**: `raw` (Klartext), `coarse` (Grobklasse), `ampel`
  (gruen/gelb/rot), `schwelle` (above/below), `flag` (bool), `none` (gar nicht).
- **Projektor**: die Funktion, die den Rohwert in genau die erlaubte Aufloesung
  verwandelt. Der Bewerter erfaehrt **dass** der Bestand kritisch ist, nie
  **wie hoch** er ist.

Ein Aufruf mit `none` wirft `EnvelopeError("not_in_matrix")`. Das ist der
Ablehnungscode, der in der Demo auf dem Schirm erscheint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .envelope import ROLES, VISIBILITY, EnvelopeError

# Schwellen an einer Stelle, damit ein Szenario sie ueberschreiben kann, ohne
# dass irgendwo eine Zahl im Code klebt.
DEFAULT_THRESHOLDS: dict[str, Any] = {
    # Bestandsdeckung in Tagen: unter 1 rot, unter 3 gelb, sonst gruen.
    "stock_days_red": 1.0,
    "stock_days_amber": 3.0,
    # Vertragsstrafe in Euro, ab der die Schwelle "above" meldet.
    "penalty_eur": 50_000,
    # Ersatz: Ankunft in Minuten, bis zu der er als gruen gilt.
    "replacement_eta_amber_min": 120,
    # Temperatur: Abstand zur Grenze in Kelvin, unter dem es gelb wird.
    "temp_margin_k": 2.0,
    # Minuten ausserhalb des Fensters, ab denen es gelb wird.
    "temp_minutes_out_amber": 15,
    # Streckenschwaeche als Schwere 0..3.
    "route_severity_red": 3,
}

# Grobklassen fuer `cargo_class`. Wer nur `coarse` sieht, erfaehrt die
# Regulierungslage, nicht die Ware.
CARGO_COARSE: dict[str, str] = {
    "pharma_cooled": "regulated",
    "vaccine": "regulated",
    "chem_hazmat": "hazardous",
    "fuel": "hazardous",
    "fresh_food": "perishable",
    "flowers": "perishable",
    "machine_parts": "general",
    "steel": "general",
}


def _number(raw: Any, what: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise EnvelopeError("bad_value", f"{what} expects a number, got {raw!r}") from None


def _mapping(raw: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise EnvelopeError("bad_value", f"{what} expects an object, got {type(raw).__name__}")
    return raw


# --- Projektoren --------------------------------------------------------


def _raw(raw: Any, thresholds: Mapping[str, Any]) -> Any:
    return raw


def _coarse_cargo(raw: Any, thresholds: Mapping[str, Any]) -> str:
    return CARGO_COARSE.get(str(raw), "general")


def _ampel_stock(raw: Any, thresholds: Mapping[str, Any]) -> str:
    days = _number(raw, "customer_stock")
    if days < float(thresholds["stock_days_red"]):
        return "rot"
    if days < float(thresholds["stock_days_amber"]):
        return "gelb"
    return "gruen"


def _schwelle_penalty(raw: Any, thresholds: Mapping[str, Any]) -> str:
    return (
        "above"
        if _number(raw, "contract_penalty") > float(thresholds["penalty_eur"])
        else "below"
    )


def _ampel_temperature(raw: Any, thresholds: Mapping[str, Any]) -> str:
    curve = _mapping(raw, "temperature_curve")
    current = _number(curve.get("current_c"), "temperature_curve.current_c")
    limit = _number(curve.get("limit_c"), "temperature_curve.limit_c")
    minutes_out = _number(curve.get("minutes_out", 0), "temperature_curve.minutes_out")
    if current > limit:
        return "rot"
    if limit - current <= float(thresholds["temp_margin_k"]) or minutes_out >= float(
        thresholds["temp_minutes_out_amber"]
    ):
        return "gelb"
    return "gruen"


def _ampel_replacement(raw: Any, thresholds: Mapping[str, Any]) -> str:
    offer = _mapping(raw, "replacement_available")
    if not bool(offer.get("available")):
        return "rot"
    eta = _number(offer.get("eta_min", 0), "replacement_available.eta_min")
    return "gruen" if eta <= float(thresholds["replacement_eta_amber_min"]) else "gelb"


def _ampel_route(raw: Any, thresholds: Mapping[str, Any]) -> str:
    severity = _number(raw, "route_weakness")
    if severity >= float(thresholds["route_severity_red"]):
        return "rot"
    return "gelb" if severity > 0 else "gruen"


def _flag(raw: Any, thresholds: Mapping[str, Any]) -> bool:
    """Ein Flag ist immer ein bool. Ein Text wuerde Inhalt durchlassen."""
    return bool(raw)


@dataclass(frozen=True)
class Field:
    """Ein Feld mit Eigentuemer, Sichtbarkeiten und Projektoren je Aufloesung."""

    name: str
    owner: str
    kind: str
    visibility: Mapping[str, str]
    projectors: Mapping[str, Callable[[Any, Mapping[str, Any]], Any]]

    def __post_init__(self) -> None:
        missing = [r for r in ROLES if r not in self.visibility]
        if missing:
            raise EnvelopeError("bad_value", f"{self.name} says nothing about {missing}")
        bad = [v for v in self.visibility.values() if v not in VISIBILITY]
        if bad:
            raise EnvelopeError("bad_value", f"{self.name} has unknown visibilities {bad}")
        needed = {v for v in self.visibility.values() if v != "none"}
        absent = sorted(needed - set(self.projectors))
        if absent:
            raise EnvelopeError("bad_value", f"{self.name} lacks projectors for {absent}")

    def project(self, raw: Any, role: str, thresholds: Mapping[str, Any]) -> Any:
        level = self.visibility.get(role)
        if level is None:
            raise EnvelopeError("unknown_role", f"{role!r} is not one of {ROLES}")
        if level == "none":
            raise EnvelopeError("not_in_matrix", f"{self.name} is not visible to {role}")
        return self.projectors[level](raw, thresholds)


def _field(
    name: str,
    owner: str,
    kind: str,
    vis: Mapping[str, str],
    projectors: Mapping[str, Callable[[Any, Mapping[str, Any]], Any]],
) -> Field:
    full = {role: vis.get(role, "none") for role in ROLES}
    return Field(name=name, owner=owner, kind=kind, visibility=full, projectors=projectors)


# --- die Tabelle --------------------------------------------------------

FIELDS: dict[str, Field] = {
    f.name: f
    for f in (
        _field(
            "cargo_class",
            owner="supplier",
            kind="text",
            vis={"intake": "coarse", "assessor": "coarse", "supplier": "raw", "customer": "raw"},
            projectors={"raw": _raw, "coarse": _coarse_cargo},
        ),
        _field(
            "temperature_curve",
            owner="intake",
            kind="curve",
            vis={"intake": "raw", "assessor": "ampel", "supplier": "raw", "customer": "raw"},
            projectors={"raw": _raw, "ampel": _ampel_temperature},
        ),
        _field(
            "customer_stock",
            owner="customer",
            kind="number",
            vis={"assessor": "ampel", "customer": "raw"},
            projectors={"raw": _raw, "ampel": _ampel_stock},
        ),
        _field(
            "contract_penalty",
            owner="legal",
            kind="number",
            vis={"assessor": "schwelle", "legal": "raw"},
            projectors={"raw": _raw, "schwelle": _schwelle_penalty},
        ),
        _field(
            "route_weakness",
            owner="infra",
            kind="number",
            vis={"assessor": "ampel"},
            projectors={"ampel": _ampel_route},
        ),
        _field(
            "contact_person",
            owner="customer",
            kind="text",
            vis={"intake": "raw", "customer": "raw"},
            projectors={"raw": _raw},
        ),
        _field(
            "replacement_available",
            owner="supplier",
            kind="object",
            vis={"assessor": "ampel", "supplier": "raw", "customer": "ampel"},
            projectors={"raw": _raw, "ampel": _ampel_replacement},
        ),
        _field(
            "market_sensitive",
            owner="infra",
            kind="bool",
            vis={"intake": "flag", "assessor": "flag", "legal": "flag"},
            projectors={"flag": _flag},
        ),
    )
}


# --- Zugriff ------------------------------------------------------------


def _field_or_refuse(name: str) -> Field:
    try:
        return FIELDS[name]
    except KeyError:
        raise EnvelopeError("unknown_field", f"{name!r} is not a declared field") from None


def visibility(field_name: str, role: str) -> str:
    fld = _field_or_refuse(field_name)
    if role not in ROLES:
        raise EnvelopeError("unknown_role", f"{role!r} is not one of {ROLES}")
    return fld.visibility[role]


def project(field_name: str, raw: Any, role: str, thresholds: Mapping[str, Any]) -> Any:
    """Den Rohwert in genau die Aufloesung bringen, die `role` haben darf."""
    return _field_or_refuse(field_name).project(raw, role, thresholds)


def fields_for(role: str) -> tuple[str, ...]:
    """Alle Felder, die `role` ueberhaupt erreichen koennen."""
    if role not in ROLES:
        raise EnvelopeError("unknown_role", f"{role!r} is not one of {ROLES}")
    return tuple(n for n, f in FIELDS.items() if f.visibility[role] != "none")


def owners() -> dict[str, str]:
    return {name: f.owner for name, f in FIELDS.items()}


def matrix_table() -> str:
    """Die Tabelle als Markdown -- fuer README, Demo und Ereignisvertrag."""
    head = "| Feld | Eigentuemer | " + " | ".join(ROLES) + " |"
    rule = "|---" * (len(ROLES) + 2) + "|"
    lines = [head, rule]
    for name in FIELDS:
        fld = FIELDS[name]
        cells = [("—" if fld.visibility[r] == "none" else fld.visibility[r]) for r in ROLES]
        lines.append(f"| `{name}` | {fld.owner} | " + " | ".join(cells) + " |")
    return "\n".join(lines)

"""Die Need-to-know-Matrix: wer welches Feld in welcher Aufloesung sieht.

Das ist das Produkt. Und es ist **Daten**, nicht Code: die Tabelle steht in
`data/schema/field_catalogue.json`, dieses Modul laedt und validiert sie beim
Import. Ein neues Feld ist ein JSON-Eintrag; eine geaenderte Sichtbarkeit ist
eine geaenderte Zeile, die ein Mensch lesen und bestreiten kann, ohne Python zu
lesen. Nur eine neue *Art* von Projektion braucht Code -- eine Funktion hier und
ihren Namen in `known_projectors`.

Drei Begriffe:

- **Eigentuemer** (`owner`) ist ein Datensatztyp, nicht zwingend eine Rolle:
  `route_weakness` gehoert `network`, `market_sensitive` gehoert `carrier`. Jeder
  Datensatztyp wird von einem Parteityp gehalten (`record_types[...].held_by`),
  und ein Knoten laedt genau die Datensaetze seines Parteityps.
- **Sichtbarkeit** ist `raw`, `coarse`, `ampel`, `schwelle`, `flag`, `count` oder
  `none`. `none` heisst gar nicht und erzeugt `EnvelopeError("not_in_matrix")`.
- **Projektor** ist die Funktion, die den Rohwert auf die erlaubte Aufloesung
  bringt. Der Bewerter erfaehrt **dass** der Bestand knapp ist, nie **wie** knapp.

Ein Fehler im Katalog faellt beim Import auf, nicht im Lauf. Das ist Absicht:
eine kaputte Matrix darf nie ein Modell erreichen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping

from .envelope import ROLES, VISIBILITY, EnvelopeError

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "data" / "schema"
CATALOGUE_PATH = SCHEMA_DIR / "field_catalogue.json"
VOCABULARY_PATH = SCHEMA_DIR / "vocabularies.json"


class CatalogueError(ValueError):
    """Der Feldkatalog ist in sich widersprüchlich. Faellt beim Import auf."""


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CatalogueError(f"{path} does not exist") from None
    except json.JSONDecodeError as exc:
        raise CatalogueError(f"{path} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise CatalogueError(f"{path} must contain an object")
    return data


def _public(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Kommentarschluessel (`_comment`, `_note`) sind Dokumentation, keine Daten."""
    return {k: v for k, v in mapping.items() if not k.startswith("_")}


VOCABULARIES: dict[str, Any] = _public(_read(VOCABULARY_PATH))
_CATALOGUE: dict[str, Any] = _read(CATALOGUE_PATH)

CATALOGUE_VERSION: int = int(_CATALOGUE.get("catalogue_version", 0))
RECORD_TYPES: dict[str, Any] = _public(_CATALOGUE.get("record_types") or {})


def vocabulary(name: str) -> tuple[str, ...]:
    """Die erlaubten Werte eines Vokabulars, egal ob Liste oder Objekt."""
    raw = VOCABULARIES.get(name)
    if isinstance(raw, list):
        return tuple(raw)
    if isinstance(raw, dict):
        return tuple(k for k in raw if not k.startswith("_"))
    raise CatalogueError(f"{name!r} is not a vocabulary in {VOCABULARY_PATH.name}")


def coarse_of(vocab_name: str, value: Any) -> str:
    """Die Grobklasse eines Vokabelwerts, aus `vocabularies.json`.

    Die Abbildung steht bei den Werten, nicht hier -- eine neue Ladungsklasse
    bringt ihre Grobklasse selbst mit.
    """
    entry = (VOCABULARIES.get(vocab_name) or {}).get(str(value))
    if isinstance(entry, dict) and "coarse" in entry:
        return str(entry["coarse"])
    return "general"


# --- Projektoren --------------------------------------------------------
# Signatur: (Rohwert, Schwellen dieses Feldes) -> erlaubte Aufloesung.


def _number(raw: Any, what: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise EnvelopeError("bad_value", f"{what} expects a number, got {raw!r}") from None


def _mapping(raw: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise EnvelopeError("bad_value", f"{what} expects an object, got {type(raw).__name__}")
    return raw


def _raw(raw: Any, th: Mapping[str, Any]) -> Any:
    return raw


def _coarse_cargo(raw: Any, th: Mapping[str, Any]) -> str:
    return coarse_of("cargo_class", raw)


def _coarse_trade(raw: Any, th: Mapping[str, Any]) -> str:
    return coarse_of("trade", raw)


def _coarse_locality(raw: Any, th: Mapping[str, Any]) -> str:
    """Ortschaft grob: bewohnt oder nicht. Mehr braucht ein Vertragsagent nicht."""
    return "inhabited" if str(raw) in {"village", "town_edge", "dense_urban"} else "uninhabited"


def _ampel_stock(raw: Any, th: Mapping[str, Any]) -> str:
    days = _number(raw, "customer_stock")
    if days < float(th["red"]):
        return "rot"
    return "gelb" if days < float(th["amber"]) else "gruen"


def _ampel_temperature(raw: Any, th: Mapping[str, Any]) -> str:
    curve = _mapping(raw, "temperature_curve")
    current = _number(curve.get("current_c"), "temperature_curve.current_c")
    limit = _number(curve.get("limit_c"), "temperature_curve.limit_c")
    minutes_out = _number(curve.get("minutes_out", 0), "temperature_curve.minutes_out")
    if current > limit:
        return "rot"
    if limit - current <= float(th["margin_k"]) or minutes_out >= float(th["minutes_out_amber"]):
        return "gelb"
    return "gruen"


def _ampel_replacement(raw: Any, th: Mapping[str, Any]) -> str:
    offer = _mapping(raw, "replacement_available")
    if not bool(offer.get("available")):
        return "rot"
    eta = _number(offer.get("eta_min", 0), "replacement_available.eta_min")
    return "gruen" if eta <= float(th["eta_amber_min"]) else "gelb"


def _ampel_route(raw: Any, th: Mapping[str, Any]) -> str:
    """Zwei Rohformen: eine Schwere 0..3 oder ein alt_route_status."""
    if isinstance(raw, str):
        return {"none": "rot", "long_detour": "gelb",
                "available": "gruen", "available_short": "gruen"}.get(raw, "gelb")
    severity = _number(raw, "route_weakness")
    if severity >= float(th["red"]):
        return "rot"
    return "gelb" if severity > 0 else "gruen"


def _ampel_urgency(raw: Any, th: Mapping[str, Any]) -> str:
    return {"routine": "gruen", "elevated": "gelb",
            "critical": "rot", "life_safety": "rot"}.get(str(raw), "gelb")


def _ampel_road(raw: Any, th: Mapping[str, Any]) -> str:
    """Kann ein Lkw hier umladen? Ohne Strasse ist Umladen keine Option."""
    return {"none": "rot", "track_only": "rot", "single_lane": "gelb",
            "paved_two_lane": "gruen", "motorway_near": "gruen"}.get(str(raw), "gelb")


def _schwelle_money(raw: Any, th: Mapping[str, Any]) -> str:
    """`above` heisst: ueber der Schmerzgrenze. Die Zahl selbst bleibt beim Eigentuemer."""
    return "above" if _number(raw, "money") > float(th["limit"]) else "below"


def _schwelle_hours(raw: Any, th: Mapping[str, Any]) -> str:
    """`below` heisst: weniger Restzeit als die Grenze, die Frist wird knapp."""
    return "below" if _number(raw, "hours") < float(th["limit"]) else "above"


def _contact_line(raw: Any, th: Mapping[str, Any]) -> str:
    """Zustaendige Personen als eine Zeile.

    Ein Rohobjekt kann den Draht nicht ueberqueren (`ConfigRecord` traegt nur
    Skalare), eine Leitstelle braucht aber den Namen und die Nummer. Also ist
    die erlaubte Darstellung eines Ansprechpartners eine Zeile -- fuer die
    Rollen, denen die Matrix ihn zugesteht, und fuer keine andere.
    """
    people = raw if isinstance(raw, (list, tuple)) else [raw]
    out = []
    for person in people:
        if not isinstance(person, Mapping):
            out.append(str(person))
            continue
        parts = [str(person.get("name", "")).strip()]
        if person.get("function"):
            parts.append(str(person["function"]))
        if person.get("phone"):
            parts.append(str(person["phone"]))
        if person.get("hours"):
            parts.append(f"erreichbar {person['hours']}")
        out.append(", ".join(p for p in parts if p))
    return " | ".join(o for o in out if o)


def _curve_line(raw: Any, th: Mapping[str, Any]) -> str:
    """Die Kuehlkurve als eine Zeile, aus demselben Grund wie `_contact_line`."""
    curve = _mapping(raw, "temperature_curve")
    return (
        f"{curve.get('current_c')} C (Soll {curve.get('setpoint_c')}, "
        f"Grenze {curve.get('limit_c')}, {curve.get('minutes_out', 0)} min ausserhalb)"
    )


def _flag(raw: Any, th: Mapping[str, Any]) -> bool:
    """Ein Flag ist immer ein bool. Ein Text wuerde Inhalt durchlassen."""
    return bool(raw)


def _count(raw: Any, th: Mapping[str, Any]) -> int:
    return len(raw) if isinstance(raw, (list, tuple, dict)) else (0 if raw is None else 1)


PROJECTORS: dict[str, Callable[[Any, Mapping[str, Any]], Any]] = {
    "raw": _raw,
    "coarse_cargo": _coarse_cargo,
    "coarse_trade": _coarse_trade,
    "coarse_locality": _coarse_locality,
    "ampel_stock": _ampel_stock,
    "ampel_temperature": _ampel_temperature,
    "ampel_replacement": _ampel_replacement,
    "ampel_route": _ampel_route,
    "ampel_urgency": _ampel_urgency,
    "ampel_road": _ampel_road,
    "schwelle_money": _schwelle_money,
    "schwelle_hours": _schwelle_hours,
    "contact_line": _contact_line,
    "curve_line": _curve_line,
    "flag": _flag,
    "count": _count,
}


@dataclass(frozen=True)
class Field:
    """Ein Feld des Katalogs, beim Import validiert."""

    name: str
    owner: str
    kind: str
    visibility: Mapping[str, str]
    projectors: Mapping[str, str]
    thresholds: Mapping[str, Any]
    per: str | None = None
    vocabulary: str | None = None
    flags: tuple[str, ...] = ()
    note: str = ""

    @property
    def held_by(self) -> str:
        """Der Parteityp, auf dessen Knoten der Rohwert physisch liegt."""
        return str((RECORD_TYPES.get(self.owner) or {}).get("held_by", "unknown"))

    @property
    def speaks_as(self) -> str:
        """Die Agentenrolle, die fuer diesen Datensatz antwortet."""
        return str((RECORD_TYPES.get(self.owner) or {}).get("speaks_as", ""))

    def project(self, raw: Any, role: str, thresholds: Mapping[str, Any] | None = None) -> Any:
        level = self.visibility.get(role)
        if level is None:
            raise EnvelopeError("unknown_role", f"{role!r} is not one of {ROLES}")
        if level == "none":
            raise EnvelopeError("not_in_matrix", f"{self.name} is not visible to {role}")
        th = {**self.thresholds, **((thresholds or {}).get(self.name) or {})}
        return PROJECTORS[self.projectors[level]](raw, th)


def _build_fields() -> dict[str, Field]:
    declared_roles = tuple(_CATALOGUE.get("roles") or ())
    if declared_roles != ROLES:
        raise CatalogueError(
            f"{CATALOGUE_PATH.name} declares roles {declared_roles}, "
            f"but soteria.envelope.ROLES is {ROLES}"
        )
    known = set(_CATALOGUE.get("known_projectors") or ())
    unimplemented = sorted(known - set(PROJECTORS))
    if unimplemented:
        raise CatalogueError(
            f"known_projectors lists {unimplemented}, which soteria/matrix.py "
            "does not implement"
        )

    out: dict[str, Field] = {}
    for name, spec in _public(_CATALOGUE.get("fields") or {}).items():
        owner = str(spec.get("owner", ""))
        if owner not in RECORD_TYPES:
            raise CatalogueError(
                f"field {name!r}: owner={owner!r} is not a declared record_type "
                f"({sorted(RECORD_TYPES)})"
            )
        vis = {role: str((spec.get("visibility") or {}).get(role, "none")) for role in ROLES}
        bad = sorted({v for v in vis.values() if v not in VISIBILITY})
        if bad:
            raise CatalogueError(f"field {name!r}: unknown visibilities {bad}")
        projectors = {k: str(v) for k, v in (spec.get("projectors") or {}).items()}
        unknown = sorted(set(projectors.values()) - set(PROJECTORS))
        if unknown:
            raise CatalogueError(f"field {name!r}: unknown projectors {unknown}")
        for level in {v for v in vis.values() if v != "none"}:
            if level not in projectors:
                raise CatalogueError(f"field {name!r}: visibility {level!r} has no projector")
        voc = spec.get("vocabulary")
        if voc is not None and voc not in VOCABULARIES:
            raise CatalogueError(f"field {name!r}: vocabulary {voc!r} is not declared")
        out[name] = Field(
            name=name,
            owner=owner,
            kind=str(spec.get("kind", "unknown")),
            visibility=vis,
            projectors=projectors,
            thresholds=_public(spec.get("thresholds") or {}),
            per=spec.get("per"),
            vocabulary=voc,
            flags=tuple(spec.get("flags") or ()),
            note=str(spec.get("note", "")),
        )
    if not out:
        raise CatalogueError(f"{CATALOGUE_PATH.name} declares no fields")
    return out


FIELDS: dict[str, Field] = _build_fields()

# Schwellen je Feld, wie sie im Katalog stehen. Ein Szenario darf einzelne
# Felder ueberschreiben: {"customer_stock": {"red": 0.5}}.
DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    name: dict(f.thresholds) for name, f in FIELDS.items()
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


def project(
    field_name: str, raw: Any, role: str, thresholds: Mapping[str, Any] | None = None
) -> Any:
    """Den Rohwert in genau die Aufloesung bringen, die `role` haben darf."""
    return _field_or_refuse(field_name).project(raw, role, thresholds)


def fields_for(role: str) -> tuple[str, ...]:
    """Alle Felder, die `role` ueberhaupt erreichen koennen."""
    if role not in ROLES:
        raise EnvelopeError("unknown_role", f"{role!r} is not one of {ROLES}")
    return tuple(n for n, f in FIELDS.items() if f.visibility[role] != "none")


def owners() -> dict[str, str]:
    """Feld -> Datensatztyp, der den Rohwert haelt."""
    return {name: f.owner for name, f in FIELDS.items()}


def holders() -> dict[str, str]:
    """Feld -> Parteityp, auf dessen Knoten der Rohwert physisch liegt."""
    return {name: f.held_by for name, f in FIELDS.items()}


@lru_cache(maxsize=None)
def fields_held_by(party_type: str) -> tuple[str, ...]:
    """Die Felder, deren Rohwert auf einem Knoten dieses Parteityps liegt."""
    return tuple(n for n, f in FIELDS.items() if f.held_by in {party_type, "shared"})


def matrix_table() -> str:
    """Die Tabelle als Markdown -- fuer README, Demo und Ereignisvertrag."""
    head = "| Feld | Eigentuemer | haelt | " + " | ".join(ROLES) + " |"
    rule = "|---" * (len(ROLES) + 3) + "|"
    lines = [head, rule]
    for name, fld in FIELDS.items():
        cells = [("—" if fld.visibility[r] == "none" else fld.visibility[r]) for r in ROLES]
        lines.append(
            f"| `{name}` | {fld.owner} | {fld.held_by} | " + " | ".join(cells) + " |"
        )
    return "\n".join(lines)

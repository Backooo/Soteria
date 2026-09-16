"""Getippte Umschlaege. Kein Freitext ueberquert je eine Rollengrenze.

Jede Grenzueberschreitung in Soteria ist eine Instanz aus diesem Modul. Die
Pruefung sitzt in `__post_init__`, damit ein ungueltiger Umschlag nicht
existieren kann -- nicht als Bitte an das Modell, sondern in Python.

Jede Ablehnung ist ein Code aus `REFUSAL`. Ein Satz als Ablehnungsgrund waere
nicht zaehlbar, und die Zahl der Ablehnungen ist eine unserer vier Messgroessen.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

# --- Wertelisten --------------------------------------------------------

ROLES: tuple[str, ...] = ("intake", "assessor", "legal", "supplier", "customer")

MEASURE: tuple[str, ...] = (
    "proceed",
    "hold",
    "cool",
    "reload",
    "alt_transport",
    "contact",
    "stop_train",
    "notify_authority",
    "press",
)

REASON: tuple[str, ...] = (
    "cost",
    "liability",
    "time",
    "safety",
    "feasibility",
    "confidentiality",
    "missing_data",
)

REFUSAL: tuple[str, ...] = (
    "not_in_matrix",
    "no_grant",
    "grant_mismatch",
    "quarantine",
    "budget",
    "quota",
    "unknown_field",
    "unknown_role",
    "bad_value",
)

FLAG: tuple[str, ...] = ("market_sensitive", "hazmat", "perishable", "person_data")

# Wie ein Feld eine Rolle erreicht. `none` heisst: gar nicht.
VISIBILITY: tuple[str, ...] = ("raw", "coarse", "ampel", "schwelle", "flag", "none")

AMPEL: tuple[str, ...] = ("gruen", "gelb", "rot")
SCHWELLE: tuple[str, ...] = ("above", "below")


class EnvelopeError(ValueError):
    """Eine getippte Ablehnung. `code` ist immer aus `REFUSAL`."""

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in REFUSAL:
            raise ValueError(f"{code!r} is not a typed refusal; use one of {REFUSAL}")
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


# --- kanonische Form und Quittungsmaterial ------------------------------


def canonical(payload: Any) -> str:
    """Eine Darstellung, die nicht von der Schluesselreihenfolge abhaengt.

    Grundlage fuer jeden Digest: eine Freigabe gilt fuer genau diese Parameter,
    und `{"a":1,"b":2}` muss dieselbe Freigabe treffen wie `{"b":2,"a":1}`.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()[:16]


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise EnvelopeError(code, detail)


def _require_role(name: str, what: str) -> None:
    _require(name in ROLES, "unknown_role", f"{what}={name!r} is not one of {ROLES}")


def _require_measures(measures: tuple[str, ...]) -> None:
    _require(bool(measures), "bad_value", "at least one measure is required")
    unknown = [m for m in measures if m not in MEASURE]
    _require(not unknown, "bad_value", f"unknown measures {unknown}")
    _require(len(set(measures)) == len(measures), "bad_value", "a measure is listed twice")


# --- die Umschlaege -----------------------------------------------------


@dataclass(frozen=True)
class Report:
    """Die Meldung. Erzeugt von einem Menschen oder einem Sensor."""

    incident_id: str
    location: str
    ts: float
    cargo_class: str
    symptom: str
    reporter_role: str

    def __post_init__(self) -> None:
        _require(bool(self.incident_id.strip()), "bad_value", "incident_id is empty")
        _require(bool(self.location.strip()), "bad_value", "location is empty")
        _require(bool(self.symptom.strip()), "bad_value", "symptom is empty")
        _require(self.ts > 0, "bad_value", "ts must be a positive timestamp")
        _require_role(self.reporter_role, "reporter_role")

    def as_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "location": self.location,
            "ts": self.ts,
            "cargo_class": self.cargo_class,
            "symptom": self.symptom,
            "reporter_role": self.reporter_role,
        }


@dataclass(frozen=True)
class Ask:
    """Eine Nachfrage nach genau einem Feld, mit getipptem Grund."""

    from_role: str
    to_role: str
    field: str
    reason_code: str

    def __post_init__(self) -> None:
        _require_role(self.from_role, "from_role")
        _require_role(self.to_role, "to_role")
        _require(self.from_role != self.to_role, "bad_value", "a role cannot ask itself")
        _require(bool(self.field.strip()), "unknown_field", "field is empty")
        _require(
            self.reason_code in REASON,
            "bad_value",
            f"reason_code={self.reason_code!r} is not one of {REASON}",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_role": self.from_role,
            "to_role": self.to_role,
            "field": self.field,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class FactSheet:
    """Die Antwort einer Rolle: nur Felder, die die Matrix ihr zugesteht.

    `fields` enthaelt bereits *projizierte* Werte -- eine Ampel, eine Schwelle
    oder einen Rohwert, je nachdem, was `matrix.visibility()` fuer den Empfaenger
    erlaubt. Der Rohwert verlaesst die besitzende Rolle nie, wenn die Matrix das
    nicht ausdruecklich vorsieht.
    """

    role: str
    fields: Mapping[str, Any]
    flags: tuple[str, ...] = ()
    ts: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        _require_role(self.role, "role")
        unknown = [f for f in self.flags if f not in FLAG]
        _require(not unknown, "bad_value", f"unknown flags {unknown}")

    @property
    def answered(self) -> int:
        return len(self.fields)

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "fields": dict(self.fields),
            "flags": list(self.flags),
            "answered": self.answered,
            "ts": self.ts,
        }


@dataclass(frozen=True)
class Advice:
    """Die Empfehlung einer Rolle. Eine Empfehlung ist keine Entscheidung."""

    role: str
    measures: tuple[str, ...]
    reason_code: str
    deadline_min: int
    tier: int = 0

    def __post_init__(self) -> None:
        _require_role(self.role, "role")
        _require_measures(self.measures)
        _require(self.reason_code in REASON, "bad_value", f"reason_code={self.reason_code!r}")
        _require(self.deadline_min >= 0, "bad_value", "deadline_min must be >= 0")
        _require(0 <= self.tier <= 3, "bad_value", "tier must be between 0 and 3")

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "measures": list(self.measures),
            "reason_code": self.reason_code,
            "deadline_min": self.deadline_min,
            "tier": self.tier,
        }


@dataclass(frozen=True)
class Coverage:
    """Wie vollstaendig die Entscheidung war. Gehoert in jede Entscheidung."""

    answered: int
    asked: int
    roles_missing: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require(self.asked >= 0 and self.answered >= 0, "bad_value", "counts must be >= 0")
        _require(
            self.answered <= self.asked,
            "bad_value",
            f"answered={self.answered} exceeds asked={self.asked}",
        )
        for role in self.roles_missing:
            _require_role(role, "roles_missing")

    def as_dict(self) -> dict[str, Any]:
        return {
            "answered": self.answered,
            "asked": self.asked,
            "roles_missing": list(self.roles_missing),
        }


@dataclass(frozen=True)
class Decision:
    """Die Entscheidung des Bewerters, mit Stufe, Freigaben und Quittung.

    Mehrere Maßnahmen, weil vier der sechs Szenarien eine Antwort aus zwei
    Maßnahmen haben. Die Stufe ist das Maximum der beteiligten Stufen -- eine
    Entscheidung ist so schwer umkehrbar wie ihr schwerster Teil.
    """

    measures: tuple[str, ...]
    params: Mapping[str, Any]
    tier: int
    grants: tuple[str, ...]
    coverage: Coverage
    reason_code: str
    receipt_hash: str

    def __post_init__(self) -> None:
        _require_measures(self.measures)
        _require(1 <= self.tier <= 3, "bad_value", "tier must be 1, 2 or 3")
        _require(self.reason_code in REASON, "bad_value", f"reason_code={self.reason_code!r}")
        _require(bool(self.receipt_hash), "bad_value", "receipt_hash is empty")

    def as_dict(self) -> dict[str, Any]:
        return {
            "measures": list(self.measures),
            "params": dict(self.params),
            "tier": self.tier,
            "grants": list(self.grants),
            "coverage": self.coverage.as_dict(),
            "reason_code": self.reason_code,
            "receipt_hash": self.receipt_hash,
        }


@dataclass(frozen=True)
class Review:
    """Die Nachbewertung durch einen Menschen, Tage spaeter."""

    incident_id: str
    human_verdict: str
    quality_1_5: int
    attribution: Mapping[str, float]

    def __post_init__(self) -> None:
        _require(bool(self.incident_id.strip()), "bad_value", "incident_id is empty")
        _require(
            self.human_verdict in MEASURE,
            "bad_value",
            f"human_verdict={self.human_verdict!r} is not a measure",
        )
        _require(1 <= self.quality_1_5 <= 5, "bad_value", "quality_1_5 must be 1..5")
        for role in self.attribution:
            _require_role(role, "attribution")

    def as_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "human_verdict": self.human_verdict,
            "quality_1_5": self.quality_1_5,
            "attribution": dict(self.attribution),
        }

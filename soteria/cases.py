"""Einen Fall laden -- und zwar je Knoten nur, was diesem Knoten gehoert.

Die Falldatei `data/<case>/<case>_case.json` ist das Koordinationsdokument: sie
nennt die Quellen, die Foederationen, wer welchen Wagen bestellt hat, die
Telemetrie, die Schluessel und die hinterlegte richtige Entscheidung.

`facts_for_party()` ist die wichtige Funktion. Sie oeffnet **nur** die Dateien,
die der genannten Partei gehoeren. Auf dem Knoten des Kunden existiert die
Vertragsstrafe eines anderen Kunden nicht im Speicher -- ein Leck ist dort nicht
verboten, es ist unmoeglich. Das ist Zeilenschutz durch die Foederation, neben
dem Feldschutz durch die Matrix.

Mehrwertige Felder: einige Felder haengen an einem Wagen (`per: "wagon"`), einer
Konsignation oder einer Ladungsklasse. Ein Knoten antwortet dann fuer die
**schlimmste** Bezugsgroesse und nennt sie als `scope`. Der Bewerter fragt also
"ist irgendein Wagen aus dem Fenster?" und bekommt "rot, W02" -- was genau die
Frage ist, die eine Leitstelle stellt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Mapping

from .envelope import FLAG, EnvelopeError
from .matrix import FIELDS, RECORD_TYPES

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Rang einer projizierten Antwort. Hoeher = schlimmer. Wird gebraucht, um bei
# einem mehrwertigen Feld die schlimmste Bezugsgroesse zu waehlen.
_RANK: dict[Any, int] = {
    "gruen": 0, "gelb": 1, "rot": 2,
    False: 0, True: 1,
    "below": 0, "above": 1,
}


def _read(path: Path) -> dict[str, Any]:
    full = path if path.is_absolute() else ROOT / path
    try:
        data = json.loads(full.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise EnvelopeError("bad_value", f"{path} does not exist") from None
    except json.JSONDecodeError as exc:
        raise EnvelopeError("bad_value", f"{path} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise EnvelopeError("bad_value", f"{path} must contain an object")
    return data


def _public(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in mapping.items() if not str(k).startswith("_")}


@dataclass(frozen=True)
class Case:
    """Ein Vorfall, wie ihn alle Beteiligten sehen duerfen.

    Enthaelt **keine** Rohwerte einer Partei -- nur die Koordination: wer
    mitspielt, welche Datei wem gehoert, welche Wagen wem, und die Wahrheit fuer
    die Messung. Die Rohwerte holt `facts_for_party()`, je Knoten getrennt.
    """

    case_id: str
    title: str
    sources: Mapping[str, Any]
    federations: tuple[Mapping[str, Any], ...]
    wagon_consignees: Mapping[str, str]
    measurements: Mapping[str, Any]
    thresholds: Mapping[str, Any]
    keys: tuple[Mapping[str, Any], ...]
    truth: Mapping[str, Any]
    offline_parties: tuple[str, ...]
    carrier_overrides: Mapping[str, Any]

    @property
    def party_ids(self) -> tuple[str, ...]:
        return tuple(str(f.get("party_id")) for f in self.federations)

    def party_type(self, party_id: str) -> str:
        for fed in self.federations:
            if fed.get("party_id") == party_id:
                return str(fed.get("party_type"))
        raise EnvelopeError("unknown_role", f"{party_id!r} is not a federation of {self.case_id}")

    def roles_of(self, party_id: str) -> tuple[str, ...]:
        for fed in self.federations:
            if fed.get("party_id") == party_id:
                return tuple(fed.get("speaks_as") or ())
        return ()

    @property
    def flags(self) -> tuple[str, ...]:
        """Lagekennzeichen, aus dem Vorfall und dem Zug abgeleitet.

        Bewusst abgeleitet und nicht von Hand gepflegt: `hazmat` ist gesetzt,
        weil ein Gefahrgutwagen im Zug ist, nicht weil jemand daran gedacht hat.
        """
        incident = _read(Path(str(self.sources["incident"])))
        train = _read(Path(str(self.sources["train"])))
        classes = {str(w.get("cargo_class")) for w in (train.get("wagons") or [])}
        out: list[str] = []
        if "hazmat" in classes:
            out.append("hazmat")
        if classes & {"perishable", "pharmaceutical"}:
            out.append("perishable")
        if bool(_public(self.carrier_overrides).get("market_sensitive")):
            out.append("market_sensitive")
        # Der Melder ist eine Person; seine Daten liegen im Fall.
        out.append("person_data")
        del incident
        return tuple(f for f in out if f in FLAG)

    @property
    def report(self) -> dict[str, Any]:
        """Die Meldung, so wie sie alle sehen duerfen. Ohne Personendaten."""
        incident = _read(Path(str(self.sources["incident"])))
        train = _read(Path(str(self.sources["train"])))
        classes = sorted({str(w.get("cargo_class")) for w in (train.get("wagons") or [])})
        from .matrix import coarse_of

        return {
            "incident_id": str(incident.get("incident_id", "")),
            "train_id": str(incident.get("train_id", "")),
            "location": str(incident.get("location", "")),
            "ts": str(incident.get("timestamp", "")),
            "symptom": str(incident.get("symptom", "")),
            "incident_type": str(incident.get("incident_type", "")),
            "severity": str(incident.get("severity", "")),
            "train_operational": str(incident.get("train_operational", "")),
            "track_blocked": bool(incident.get("track_blocked")),
            "wagon_count": int(train.get("wagon_count") or 0),
            "affected_wagons": [
                str(w.get("wagon_id")) for w in (incident.get("affected_wagons") or [])
            ],
            # Nur die Grobklassen. Welcher Wagen welche Ware traegt, steht hier nicht.
            "cargo_classes_coarse": sorted({coarse_of("cargo_class", c) for c in classes}),
        }


def load_case(case_id: str) -> Case:
    path = DATA / case_id / f"{case_id}_case.json"
    raw = _read(path)
    if raw.get("case_id") != case_id:
        raise EnvelopeError(
            "bad_value", f"{path.name}: case_id={raw.get('case_id')!r} does not match {case_id!r}"
        )
    return Case(
        case_id=case_id,
        title=str(raw.get("title", case_id)),
        sources=_public(raw.get("sources") or {}),
        federations=tuple(raw.get("federations") or ()),
        wagon_consignees=dict(raw.get("wagon_consignees") or {}),
        measurements=_public(raw.get("measurements") or {}),
        thresholds=dict(raw.get("thresholds") or {}),
        keys=tuple(raw.get("keys") or ()),
        truth=_public(raw.get("truth") or {}),
        offline_parties=tuple(raw.get("offline_parties") or ()),
        carrier_overrides=_public(raw.get("carrier_overrides") or {}),
    )


def available_cases() -> tuple[str, ...]:
    import re

    pattern = re.compile(r"^[sh]\d+$")
    return tuple(
        sorted(
            d.name
            for d in DATA.iterdir()
            if d.is_dir() and pattern.match(d.name) and (d / f"{d.name}_case.json").exists()
        )
    )


# --- Rohwerte, je Knoten getrennt ---------------------------------------


def _party_file(case: Case, party_id: str) -> dict[str, Any] | None:
    """Die Parteidatei dieses Knotens -- und nur diese."""
    party_type = case.party_type(party_id)
    if party_type == "carrier":
        return _read(Path(str(case.sources["carrier"])))
    if party_type == "supplier":
        return _read(Path(str(case.sources["supplier"])))
    for rel in case.sources.get("customers") or []:
        data = _read(Path(str(rel)))
        if data.get("party_id") == party_id:
            return data
    return None


def _own_contracts(case: Case, party_id: str) -> list[dict[str, Any]]:
    """Nur die Vertraege, in denen dieser Knoten Partei ist oder die er fuehrt.

    Der Kern des Zeilenschutzes: Kunde 2 findet Vertrag 1 hier nicht, weil seine
    `party_id` nicht in dessen `parties` steht.
    """
    out: list[dict[str, Any]] = []
    for rel in case.sources.get("contracts") or []:
        data = _read(Path(str(rel)))
        parties = [str(p) for p in (data.get("parties") or ())]
        administers = str(data.get("administered_by", "")) == party_id
        if party_id in parties or administers:
            out.append(data)
    return out


def _rankable(value: Any) -> bool:
    """Ob eine Antwort einen Schweregrad hat. Ein Rohobjekt ist nicht hashbar."""
    try:
        return value in _RANK
    except TypeError:
        return False


def _worst(candidates: Mapping[str, Any]) -> tuple[str, Any]:
    """Die schlimmste Bezugsgroesse und ihr Wert.

    Bei rangbaren Antworten (Ampel, Schwelle, bool) die schlimmste; sonst die
    erste, damit ein nicht rangbares Feld nicht stillschweigend die Bedeutung
    wechselt.
    """
    if not candidates:
        raise EnvelopeError("unknown_field", "no value for any scope")
    items = list(candidates.items())
    if all(_rankable(v) for _, v in items):
        return max(items, key=lambda kv: _RANK[kv[1]])
    return items[0]


def raw_records_for_party(case: Case, party_id: str) -> dict[str, dict[str, Any]]:
    """Die Rohwerte, die auf dem Knoten dieser Partei liegen.

    Rueckgabe: Datensatztyp -> {Feldname -> Rohwert oder {scope -> Rohwert}}.
    Was hier nicht drin ist, kann der Knoten nicht herausgeben.
    """
    party_type = case.party_type(party_id)
    out: dict[str, dict[str, Any]] = {}

    if party_type == "carrier":
        incident = _read(Path(str(case.sources["incident"])))
        train = _read(Path(str(case.sources["train"])))
        network = _read(Path(str(case.sources["network"])))
        reporter = _read(Path(str(case.sources["reporter"])))
        carrier = _party_file(case, party_id) or {}

        affected = {str(w.get("wagon_id")) for w in (incident.get("affected_wagons") or [])}
        by_wagon = {str(w.get("wagon_id")): w for w in (train.get("wagons") or [])}

        # `cargo_class` haengt am Wagen. Der Betreiber fuehrt den Frachtbrief,
        # also liegt er hier -- aber nur fuer die betroffenen Wagen, denn nur
        # die sind Gegenstand des Vorfalls.
        out["train"] = {
            "cargo_class": {
                wid: str(by_wagon[wid].get("cargo_class"))
                for wid in sorted(affected)
                if wid in by_wagon
            }
        }
        curves = dict((case.measurements.get("temperature_curve") or {}))
        out["incident"] = {"temperature_curve": {k: v for k, v in curves.items() if not str(k).startswith("_")}}
        out["network"] = _public((network.get("records") or {}).get("network") or {})
        out["reporter"] = _public((reporter.get("records") or {}).get("reporter") or {})
        base = _public((carrier.get("records") or {}).get("carrier") or {})
        out["carrier"] = {**base, **_public(case.carrier_overrides)}

    elif party_type == "supplier":
        supplier = _party_file(case, party_id) or {}
        out["supplier"] = _public((supplier.get("records") or {}).get("supplier") or {})

    elif party_type == "customer":
        customer = _party_file(case, party_id) or {}
        if customer is None:
            raise EnvelopeError("unknown_role", f"no party file for {party_id!r}")
        block = _public((customer.get("records") or {}).get("customer") or {})
        consignments = block.pop("consignments", {}) or {}
        # Je Konsignation ein Wert; `_worst` waehlt spaeter die kritischste.
        per_class: dict[str, dict[str, Any]] = {}
        for klass, entry in consignments.items():
            for field_name, value in _public(entry).items():
                per_class.setdefault(field_name, {})[str(klass)] = value
        out["customer"] = {**block, **per_class}

    else:
        raise EnvelopeError("unknown_role", f"unknown party_type {party_type!r}")

    # Vertraege: nur die eigenen. Bei mehreren gilt der schaerfste, also der mit
    # der hoechsten Strafe -- ein Knoten fuehrt in unseren Faellen genau einen.
    contracts = _own_contracts(case, party_id)
    if contracts:
        merged: dict[str, Any] = {}
        for contract in contracts:
            for field_name, value in _public((contract.get("records") or {}).get("contract") or {}).items():
                merged.setdefault(field_name, {})[str(contract.get("contract_id"))] = value
        out["contract"] = {
            k: (next(iter(v.values())) if len(v) == 1 else v) for k, v in merged.items()
        }

    # Leere Datensatzbloecke wegwerfen, damit ein Knoten nicht behauptet, etwas
    # zu fuehren, was er nicht hat.
    return {k: v for k, v in out.items() if v and any(_nonempty(x) for x in v.values())}


def _nonempty(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value)
    return value is not None


def fields_on_party(case: Case, party_id: str) -> tuple[str, ...]:
    """Die Felder, die dieser Knoten tatsaechlich beantworten kann."""
    records = raw_records_for_party(case, party_id)
    out: list[str] = []
    for record_type, block in records.items():
        for field_name, value in block.items():
            if field_name in FIELDS and FIELDS[field_name].owner == record_type and _nonempty(value):
                out.append(field_name)
    return tuple(sorted(out))

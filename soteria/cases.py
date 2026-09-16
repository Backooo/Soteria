"""Load a case -- and per node only what belongs to that node.

The case file `data/<case>/<case>_case.json` is the coordination document: it
names the sources, the federations, who ordered which wagon, the telemetry, the
keys and the stored correct decision.

`facts_for_party()` is the important function. It opens **only** the files that
belong to the named party. On the customer's node, another customer's contract
penalty does not exist in memory -- a leak there is not forbidden, it is
impossible. That is row-level protection through the federation, alongside
field-level protection through the matrix.

Multi-valued fields: some fields hang off a wagon (`per: "wagon"`), a
consignment or a cargo class. A node then answers for the **worst** reference
unit and names it as `scope`. So the assessor asks "is any wagon out of its
window?" and gets "rot (red), W02" -- which is exactly the question a control
centre asks.
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

# Rank of a projected answer. Higher = worse. Needed to pick the worst
# reference unit of a multi-valued field.
_RANK: dict[Any, int] = {
    "gruen": 0, "gelb": 1, "rot": 2,
    False: 0, True: 1,
    "below": 0, "above": 1,
    # Cargo classes, coarse and fine: hazmat beats pharma beats fresh goods
    # beats general cargo. So a train carrying both names the hazmat wagon as
    # the worst, not whichever was listed first.
    # coarse (a coarse class is never named like a fine value, otherwise the
    # coarsening could not be checked -- hence "cooled", not "perishable"):
    "general": 0, "cooled": 1, "regulated": 2, "hazardous": 3,
    # fine:
    "general_goods": 0, "perishable": 1, "livestock": 1, "high_value": 1,
    "pharmaceutical": 2, "hazmat": 3,
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
    """An incident as all participants may see it.

    Contains **no** raw values of any party -- only the coordination: who takes
    part, which file belongs to whom, which wagons to whom, and the ground truth
    for measurement. The raw values are fetched by `facts_for_party()`,
    separately per node.
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
    # Kept separately, because `_public` drops every `_` key -- and
    # `truth._status` must not get lost: otherwise every evaluation would treat
    # an unconfirmed ground truth as confirmed.
    truth_status: str = ""

    @property
    def truth_confirmed(self) -> bool:
        return bool(self.truth) and not self.truth_status.upper().startswith("PROPOSAL")

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
        """Situation markers, derived from the incident and the train.

        Deliberately derived rather than maintained by hand: `hazmat` is set
        because there is a hazmat wagon in the train, not because someone
        remembered it.
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
        # The reporter is a person; their data is part of the case.
        out.append("person_data")
        del incident
        return tuple(f for f in out if f in FLAG)

    @property
    def affected_cargo_classes(self) -> tuple[str, ...]:
        """The cargo classes of the damaged wagons.

        Part of the shared report: the driver reported which wagons are damaged,
        and what they carry is on the consignment note. The supplier needs it to
        be able to answer "can you replace this" at all.
        """
        incident = _read(Path(str(self.sources["incident"])))
        train = _read(Path(str(self.sources["train"])))
        by_wagon = {str(w.get("wagon_id")): str(w.get("cargo_class")) for w in (train.get("wagons") or [])}
        affected = [str(w.get("wagon_id")) for w in (incident.get("affected_wagons") or [])]
        return tuple(sorted({by_wagon[w] for w in affected if w in by_wagon}))

    @property
    def report(self) -> dict[str, Any]:
        """The report as everyone may see it. Without personal data."""
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
            # Only the coarse classes. Which wagon carries which goods is not in here.
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
        truth_status=str((raw.get("truth") or {}).get("_status", "")),
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


# --- raw values, separated per node -------------------------------------


def _party_file(case: Case, party_id: str) -> dict[str, Any] | None:
    """This node's party file -- and only that one."""
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
    """Only the contracts this node is a party to or administers.

    The core of row-level protection: customer 2 does not find contract 1 here,
    because its `party_id` is not in that contract's `parties`.
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
    """Whether an answer has a severity. A raw object is not hashable."""
    try:
        return value in _RANK
    except TypeError:
        return False


def _worst(candidates: Mapping[str, Any]) -> tuple[str, Any]:
    """The worst reference unit and its value.

    For rankable answers (traffic light, threshold, bool) the worst; otherwise
    the first, so a non-rankable field does not silently change its meaning.
    """
    if not candidates:
        raise EnvelopeError("unknown_field", "no value for any scope")
    items = list(candidates.items())
    if all(_rankable(v) for _, v in items):
        return max(items, key=lambda kv: _RANK[kv[1]])
    return items[0]


def raw_records_for_party(case: Case, party_id: str) -> dict[str, dict[str, Any]]:
    """The raw values that live on this party's node.

    Returns: record type -> {field name -> raw value or {scope -> raw value}}.
    What is not in here, the node cannot hand out.
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

        # `cargo_class` hangs off the wagon. The operator keeps the consignment
        # note, so it lives here -- but only for the affected wagons, because
        # only they are the subject of the incident.
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
        block = _public((supplier.get("records") or {}).get("supplier") or {})
        # The supplier can replace many things. But the question is only about
        # what is damaged on this train -- otherwise it would answer about
        # hazmat that does not occur in this incident. Which classes are
        # affected is part of the shared report, not a secret of any party.
        in_scope = case.affected_cargo_classes
        out["supplier"] = {
            field_name: (
                {k: v for k, v in value.items() if k in in_scope}
                if isinstance(value, Mapping) and in_scope
                else value
            )
            for field_name, value in block.items()
        }

    elif party_type == "customer":
        customer = _party_file(case, party_id) or {}
        if customer is None:
            raise EnvelopeError("unknown_role", f"no party file for {party_id!r}")
        block = _public((customer.get("records") or {}).get("customer") or {})
        consignments = block.pop("consignments", {}) or {}
        # One value per consignment; `_worst` later picks the most critical.
        per_class: dict[str, dict[str, Any]] = {}
        for klass, entry in consignments.items():
            for field_name, value in _public(entry).items():
                per_class.setdefault(field_name, {})[str(klass)] = value
        out["customer"] = {**block, **per_class}

    else:
        raise EnvelopeError("unknown_role", f"unknown party_type {party_type!r}")

    # Contracts: only its own. With several, the strictest applies, i.e. the one
    # with the highest penalty -- in our cases a node administers exactly one.
    contracts = _own_contracts(case, party_id)
    if contracts:
        merged: dict[str, Any] = {}
        for contract in contracts:
            for field_name, value in _public((contract.get("records") or {}).get("contract") or {}).items():
                merged.setdefault(field_name, {})[str(contract.get("contract_id"))] = value
        out["contract"] = {
            k: (next(iter(v.values())) if len(v) == 1 else v) for k, v in merged.items()
        }

    # Drop empty record blocks, so a node does not claim to hold something it
    # does not have.
    return {k: v for k, v in out.items() if v and any(_nonempty(x) for x in v.values())}


def _nonempty(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value)
    return value is not None


def fields_on_party(case: Case, party_id: str) -> tuple[str, ...]:
    """The fields this node can actually answer."""
    records = raw_records_for_party(case, party_id)
    out: list[str] = []
    for record_type, block in records.items():
        for field_name, value in block.items():
            if field_name in FIELDS and FIELDS[field_name].owner == record_type and _nonempty(value):
                out.append(field_name)
    return tuple(sorted(out))

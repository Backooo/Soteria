"""Selbstbedienung fuer den Datenstrang: prueft den ganzen Datenbaum.

    uv run python scripts/validate_data.py              # alles
    uv run python scripts/validate_data.py data/s3      # ein Fall

Braucht kein Modell, kein Netz, keinen SuperLink. Leere Ausgabe und
Rueckgabewert 0 heisst: in Ordnung. Jede Meldung nennt Datei, Schluesselpfad und
was erwartet war. Zeilen mit WARNING blockieren nicht.

Geprueft wird, was ein Mensch nicht zuverlaessig im Kopf haelt:
  * jeder Wert gegen sein Vokabular,
  * jedes Feld gegen den Katalog (Eigentuemer, Form, Projektor),
  * jede Tatsache gegen ihren Eigentuemer -- eine Tatsache unter dem falschen
    Eigentuemer ist genau das Leck, das die Matrix verhindern soll,
  * jeder Vertrag gegen seine Parteien,
  * jede Stufe gegen die Zahl verschiedener Schluessel.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Ein Fallverzeichnis heisst s1..sN (bekannt) oder h1..hN (Holdout). `data/schema`
# fiele sonst in dasselbe Muster.
CASE_DIR_RE = re.compile(r"^[sh]\d+$")
DATA = ROOT / "data"
SCHEMA = DATA / "schema"

TIER = {
    "proceed": 1, "hold": 1, "cool": 1,
    "reload": 2, "alt_transport": 2, "contact": 2,
    "stop_train": 3, "notify_authority": 3, "press": 3,
}
KEYS_REQUIRED = {1: 0, 2: 1, 3: 2}


def _load(path: Path, out: list[str]) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        out.append(f"{path}: file does not exist")
        return None
    except json.JSONDecodeError as exc:
        out.append(f"{path}: not valid JSON -- {exc}")
        return None
    if not isinstance(data, dict):
        out.append(f"{path}: top level must be an object")
        return None
    return data


def _vocab_keys(vocab: Any) -> set[str]:
    """Ein Vokabular ist entweder eine Liste oder ein Objekt mit Metadaten."""
    if isinstance(vocab, list):
        return set(vocab)
    if isinstance(vocab, dict):
        return {k for k in vocab if not k.startswith("_")}
    return set()


def check_schema(out: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    vocabs = _load(SCHEMA / "vocabularies.json", out) or {}
    catalogue = _load(SCHEMA / "field_catalogue.json", out) or {}
    if not catalogue:
        return vocabs, catalogue

    roles = catalogue.get("roles") or []
    known = set(catalogue.get("known_projectors") or ())
    records = {k: v for k, v in (catalogue.get("record_types") or {}).items() if not k.startswith("_")}

    for name, spec in (catalogue.get("fields") or {}).items():
        where = f"field_catalogue.json: fields.{name}"
        if spec.get("owner") not in records:
            out.append(f"{where}: owner={spec.get('owner')!r} is not a declared record_type "
                       f"({sorted(records)})")
        vis = spec.get("visibility") or {}
        missing = [r for r in roles if r not in vis]
        if missing:
            out.append(f"{where}: visibility says nothing about {missing}")
        projectors = spec.get("projectors") or {}
        unknown = sorted(set(projectors.values()) - known)
        if unknown:
            out.append(f"{where}: unknown projectors {unknown}; add them to known_projectors "
                       "and implement them in soteria/matrix.py")
        for level in set(vis.values()):
            if level != "none" and level not in projectors:
                out.append(f"{where}: visibility uses {level!r} but no projector for it")
        voc = spec.get("vocabulary")
        if voc and voc not in vocabs:
            out.append(f"{where}: vocabulary={voc!r} is not in vocabularies.json")
    return vocabs, catalogue


def _record_blocks(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in (data.get("records") or {}).items() if not k.startswith("_")}


def check_party_or_source(path: Path, vocabs: dict, catalogue: dict, out: list[str]) -> None:
    """Prueft eine Partei-, Vertrags- oder Netzdatei gegen den Katalog."""
    data = _load(path, out)
    if data is None:
        return
    fields = catalogue.get("fields") or {}
    owner_of = {n: s.get("owner") for n, s in fields.items()}

    for record_type, block in _record_blocks(data).items():
        if record_type not in (catalogue.get("record_types") or {}):
            out.append(f"{path.name}: records.{record_type} is not a declared record_type")
            continue
        if not isinstance(block, dict):
            out.append(f"{path.name}: records.{record_type} must be an object")
            continue
        for key, value in block.items():
            if key.startswith("_") or key == "consignments":
                continue
            if key not in fields:
                out.append(f"{path.name}: records.{record_type}.{key} is not a declared field "
                           "(add it to field_catalogue.json or remove it here)")
                continue
            if owner_of[key] != record_type:
                out.append(f"{path.name}: {key} belongs to record type {owner_of[key]!r}, "
                           f"not {record_type!r} -- a fact under the wrong owner is exactly "
                           "the leak the matrix prevents")
            spec = fields[key]
            voc = spec.get("vocabulary")
            if voc and isinstance(value, str):
                allowed = _vocab_keys(vocabs.get(voc))
                if value not in allowed:
                    out.append(f"{path.name}: {key}={value!r} is not in vocabulary {voc!r} "
                               f"({sorted(allowed)})")

        # Konsignationen eines Kunden: je Ladungsklasse Bestand und Dringlichkeit.
        consignments = block.get("consignments")
        if isinstance(consignments, dict):
            cargo = _vocab_keys(vocabs.get("cargo_class"))
            urgency = _vocab_keys(vocabs.get("urgency"))
            for klass, entry in consignments.items():
                w = f"{path.name}: consignments.{klass}"
                if klass not in cargo:
                    out.append(f"{w}: {klass!r} is not a cargo_class ({sorted(cargo)})")
                if not isinstance(entry, dict):
                    out.append(f"{w}: must be an object")
                    continue
                stock = entry.get("customer_stock")
                if not isinstance(stock, (int, float)) or isinstance(stock, bool):
                    out.append(f"{w}.customer_stock: must be a number (days of cover)")
                if entry.get("customer_urgency") not in urgency:
                    out.append(f"{w}.customer_urgency: {entry.get('customer_urgency')!r} "
                               f"is not in {sorted(urgency)}")


def check_contract(path: Path, party_ids: set[str], out: list[str]) -> None:
    data = _load(path, out)
    if data is None:
        return
    parties = data.get("parties")
    if not isinstance(parties, list) or len(parties) < 2:
        out.append(f"{path.name}: parties must list at least the customer and the supplier")
        return
    for pid in parties:
        if pid not in party_ids:
            out.append(f"{path.name}: parties names {pid!r}, which is no file in data/parties/")
    if not data.get("administered_by"):
        out.append(f"{path.name}: administered_by must name the carrier whose legal agent holds it")


def check_case(case_dir: Path, vocabs: dict, catalogue: dict, party_ids: set[str],
               out: list[str]) -> None:
    cid = case_dir.name
    case = _load(case_dir / f"{cid}_case.json", out)
    if case is None:
        return
    name = f"{cid}_case.json"
    if case.get("case_id") != cid:
        out.append(f"{name}: case_id={case.get('case_id')!r} does not match the directory {cid!r}")

    sources = case.get("sources") or {}
    for key in ("incident", "train", "reporter", "network", "carrier", "supplier"):
        if key not in sources:
            out.append(f"{name}: sources is missing {key!r}")
        elif not (ROOT / str(sources[key])).exists():
            out.append(f"{name}: sources.{key} points at {sources[key]!r}, which does not exist")
    for key in ("customers", "contracts"):
        listed = sources.get(key) or []
        if not listed:
            out.append(f"{name}: sources.{key} is empty -- a case needs at least one")
        for rel in listed:
            if not (ROOT / str(rel)).exists():
                out.append(f"{name}: sources.{key} points at {rel!r}, which does not exist")

    feds = case.get("federations") or []
    types = [f.get("party_type") for f in feds if isinstance(f, dict)]
    for required in ("carrier", "supplier", "customer"):
        if required not in types:
            out.append(f"{name}: federations has no {required} node")
    for fed in feds:
        if isinstance(fed, dict) and fed.get("party_id") not in party_ids:
            out.append(f"{name}: federations names {fed.get('party_id')!r}, "
                       "which is no file in data/parties/")

    # Die Melderrolle ist ein Mensch, keine Agentenrolle.
    reporter = _load(ROOT / str(sources.get("reporter", "")), out) if sources.get("reporter") else None
    if reporter:
        rec = (reporter.get("records") or {}).get("reporter") or {}
        role = rec.get("reporter_role")
        humans = _vocab_keys(vocabs.get("reporter_role"))
        if role not in humans:
            out.append(f"{cid}_reporter.json: reporter_role={role!r} is not in {sorted(humans)}")
        if role in (catalogue.get("roles") or []):
            out.append(f"{cid}_reporter.json: reporter_role={role!r} is an AGENT role; "
                       "a reporter is a human, never an agent")

    # Wagen: jeder Wagen des Zuges braucht einen Besteller, jeder Besteller eine Foederation.
    train = _load(ROOT / str(sources.get("train", "")), out) if sources.get("train") else None
    if train:
        wagons = {w.get("wagon_id") for w in (train.get("wagons") or [])}
        consignees = case.get("wagon_consignees") or {}
        for wid in sorted(wagons - set(consignees)):
            out.append(f"{name}: WARNING wagon {wid} has no consignee in wagon_consignees")
        fed_ids = {f.get("party_id") for f in feds if isinstance(f, dict)}
        for wid, pid in consignees.items():
            if wid not in wagons:
                out.append(f"{name}: wagon_consignees names {wid!r}, which the train does not have")
            if pid not in fed_ids:
                out.append(f"{name}: wagon_consignees gives {wid} to {pid!r}, which is not a "
                           "federation in this case")

    # Telemetrie nur fuer Wagen, die es gibt.
    if train:
        wagons = {w.get("wagon_id") for w in (train.get("wagons") or [])}
        for field, per_wagon in (case.get("measurements") or {}).items():
            if field.startswith("_"):
                continue
            if field not in (catalogue.get("fields") or {}):
                out.append(f"{name}: measurements.{field} is not a declared field")
            if isinstance(per_wagon, dict):
                for wid in per_wagon:
                    if wid not in wagons:
                        out.append(f"{name}: measurements.{field} names wagon {wid!r}, "
                                   "which the train does not have")

    for pid in case.get("offline_parties") or []:
        if pid not in {f.get("party_id") for f in feds if isinstance(f, dict)}:
            out.append(f"{name}: offline_parties names {pid!r}, which is not a federation here")

    truth = case.get("truth")
    if not isinstance(truth, dict):
        out.append(f"{name}: truth is missing -- without it the hit rate cannot be measured")
        return
    measures = truth.get("measures")
    measure_vocab = _vocab_keys(vocabs.get("measure"))
    if not isinstance(measures, list) or not measures:
        out.append(f"{name}: truth.measures must be a non-empty list")
    else:
        unknown = [m for m in measures if m not in measure_vocab]
        if unknown:
            out.append(f"{name}: truth.measures has unknown {unknown}")
        else:
            want = max(TIER[m] for m in measures)
            if truth.get("tier") != want:
                out.append(f"{name}: truth.tier={truth.get('tier')!r} but {measures} implies {want}")
            need = KEYS_REQUIRED[want]
            keys = case.get("keys") or []
            for i, key in enumerate(keys):
                if not isinstance(key, dict):
                    out.append(f"{name}: keys[{i}] must be an object")
                    continue
                human = key.get("human_id")
                if not isinstance(human, str) or not human.strip():
                    out.append(f"{name}: keys[{i}].human_id is missing")
                elif human in (catalogue.get("roles") or []):
                    out.append(f"{name}: keys[{i}].human_id={human!r} is an agent role; "
                               "an agent cannot sign a grant")
                if key.get("measure") not in measure_vocab:
                    out.append(f"{name}: keys[{i}].measure={key.get('measure')!r} is not a measure")
            for measure in measures:
                if TIER[measure] == 1:
                    continue
                signers = {k.get("human_id") for k in keys
                           if isinstance(k, dict) and k.get("measure") == measure}
                if truth.get("expect_refusal") is None and len(signers) < KEYS_REQUIRED[TIER[measure]]:
                    out.append(f"{name}: {measure!r} is tier {TIER[measure]} and needs "
                               f"{KEYS_REQUIRED[TIER[measure]]} distinct keys, {len(signers)} given "
                               "-- add keys or set truth.expect_refusal")
    if truth.get("reason_code") not in _vocab_keys(vocabs.get("reason_code")):
        out.append(f"{name}: truth.reason_code={truth.get('reason_code')!r} is not a reason_code")
    if not str(truth.get("why", "")).strip():
        out.append(f"{name}: truth.why must say in one sentence why this is right")
    overlap = set(truth.get("measures") or ()) & set(truth.get("must_not") or ())
    if overlap:
        out.append(f"{name}: truth lists {sorted(overlap)} in both measures and must_not")
    if str(truth.get("_status", "")).startswith("VORSCHLAG"):
        out.append(f"{name}: WARNING truth is still marked VORSCHLAG -- "
                   "der Datenspezialist muss sie bestaetigen")


def main() -> int:
    targets = [Path(a) for a in sys.argv[1:]]
    out: list[str] = []
    vocabs, catalogue = check_schema(out)
    if not catalogue:
        for line in out:
            print(line)
        return 1

    party_files = sorted((DATA / "parties").glob("*.json"))
    party_ids = {(_load(p, out) or {}).get("party_id") for p in party_files}
    party_ids.discard(None)

    for path in party_files + sorted((DATA / "network").glob("*.json")):
        check_party_or_source(path, vocabs, catalogue, out)
    for path in sorted((DATA / "contracts").glob("*.json")):
        check_party_or_source(path, vocabs, catalogue, out)
        check_contract(path, party_ids, out)

    case_dirs = targets or sorted(
        d for d in DATA.iterdir() if d.is_dir() and CASE_DIR_RE.match(d.name)
    )
    for case_dir in case_dirs:
        if not case_dir.is_dir():
            out.append(f"{case_dir}: not a directory")
            continue
        check_case(case_dir, vocabs, catalogue, party_ids, out)

    for line in out:
        print(line)
    errors = sum(1 for line in out if "WARNING" not in line)
    warnings = len(out) - errors
    print(f"\n{len(catalogue.get('fields') or {})} Felder, {len(party_ids)} Parteien, "
          f"{len(case_dirs)} Faelle geprueft: {errors} Fehler, {warnings} Warnungen")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

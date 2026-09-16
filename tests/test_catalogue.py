"""Der Feldkatalog ist Daten -- also muss ein Fehler darin beim Import auffallen.

Eine kaputte Matrix darf nie ein Modell erreichen. Diese Tests laden jeweils
einen absichtlich beschaedigten Katalog in einem Unterprozess und pruefen, dass
der Import scheitert, nicht erst der Lauf.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from soteria.matrix import (
    CATALOGUE_PATH,
    CATALOGUE_VERSION,
    FIELDS,
    PROJECTORS,
    RECORD_TYPES,
    VOCABULARIES,
    coarse_of,
    vocabulary,
)

ROOT = Path(__file__).resolve().parents[1]


def test_the_catalogue_is_the_single_source_of_the_matrix():
    """Kein Feld steht in matrix.py, das nicht im Katalog steht."""
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    declared = {k for k in catalogue["fields"] if not k.startswith("_")}
    assert set(FIELDS) == declared
    assert CATALOGUE_VERSION >= 1


def test_every_declared_projector_is_implemented():
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    assert set(catalogue["known_projectors"]) <= set(PROJECTORS)


def test_vocabularies_answer_for_both_shapes():
    """Ein Vokabular ist eine Liste oder ein Objekt mit Metadaten."""
    assert "pharmaceutical" in vocabulary("cargo_class")   # Objekt
    assert "restricted" in vocabulary("train_operational")  # Liste
    with pytest.raises(Exception):
        vocabulary("does_not_exist")


def test_coarse_mapping_lives_with_the_values_not_in_code():
    """Eine neue Ladungsklasse bringt ihre Grobklasse selbst mit."""
    assert coarse_of("cargo_class", "pharmaceutical") == "regulated"
    assert coarse_of("cargo_class", "hazmat") == "hazardous"
    assert coarse_of("trade", "hospital") == "care"
    assert coarse_of("cargo_class", "voellig_neu") == "general"


def test_reporter_roles_are_never_agent_roles():
    """Ein Melder ist ein Mensch. Die Vokabulare duerfen sich nicht ueberschneiden."""
    from soteria.envelope import ROLES

    assert not set(vocabulary("reporter_role")) & set(ROLES)


def test_every_record_type_names_a_party_and_a_speaking_role():
    from soteria.envelope import ROLES

    for name, spec in RECORD_TYPES.items():
        assert spec.get("held_by") in {"carrier", "customer", "supplier", "shared"}, name
        assert spec.get("speaks_as") in ROLES, name


def _import_with_broken_catalogue(tmp_path: Path, mutate) -> subprocess.CompletedProcess:
    """Kopiere das Projekt-Schema, beschaedige es, importiere soteria.matrix."""
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    mutate(catalogue)
    schema = tmp_path / "data" / "schema"
    schema.mkdir(parents=True)
    (schema / "field_catalogue.json").write_text(json.dumps(catalogue), encoding="utf-8")
    (schema / "vocabularies.json").write_text(
        (CATALOGUE_PATH.parent / "vocabularies.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    pkg = tmp_path / "soteria"
    pkg.mkdir()
    for module in ("__init__.py", "envelope.py", "matrix.py"):
        (pkg / module).write_text(
            (ROOT / "soteria" / module).read_text(encoding="utf-8"), encoding="utf-8"
        )
    return subprocess.run(
        [sys.executable, "-c", "import soteria.matrix"],
        cwd=tmp_path, capture_output=True, text=True,
    )


@pytest.mark.parametrize(
    "label,mutate,needle",
    [
        ("Eigentuemer ist kein Datensatztyp",
         lambda c: c["fields"]["customer_stock"].__setitem__("owner", "nirgendwo"),
         "not a declared record_type"),
        ("Projektor ist nicht implementiert",
         lambda c: c["fields"]["customer_stock"]["projectors"].__setitem__("ampel", "ampel_magie"),
         "unknown projectors"),
        ("Sichtbarkeit ohne Projektor",
         lambda c: c["fields"]["route_weakness"]["visibility"].__setitem__("legal", "schwelle"),
         "has no projector"),
        ("unbekannte Sichtbarkeitsstufe",
         lambda c: c["fields"]["customer_stock"]["visibility"].__setitem__("legal", "vielleicht"),
         "unknown visibilities"),
        ("Rollenliste passt nicht zu envelope.ROLES",
         lambda c: c.__setitem__("roles", ["intake", "assessor"]),
         "but soteria.envelope.ROLES is"),
        ("known_projectors nennt etwas Unimplementiertes",
         lambda c: c["known_projectors"].append("ampel_telepathie"),
         "does not implement"),
        ("Katalog ohne Felder",
         lambda c: c.__setitem__("fields", {}),
         "declares no fields"),
    ],
)
def test_a_broken_catalogue_fails_at_import(tmp_path, label, mutate, needle):
    run = _import_with_broken_catalogue(tmp_path, mutate)
    assert run.returncode != 0, f"{label}: der Import ging durch"
    assert needle in run.stderr, f"{label}: erwartete {needle!r}, bekam:\n{run.stderr[-600:]}"


def test_no_object_valued_field_uses_the_plain_raw_projector():
    """Ein Rohobjekt kann den Draht nicht ueberqueren (ConfigRecord traegt nur
    Skalare). Ein Objektfeld mit dem schlichten `raw`-Projektor liefert der Rolle,
    der die Matrix es zugesteht, daher `bad_value` statt der Antwort.

    Die Regel wurde erst fuer zwei Felder einzeln angewandt und dann beim dritten
    vergessen. Dieser Test macht sie systematisch.
    """
    offenders = [
        name for name, f in FIELDS.items()
        if f.kind == "object" and f.projectors.get("raw") == "raw"
    ]
    assert not offenders, (
        f"{offenders} sind Objektfelder mit schlichtem raw-Projektor; "
        "gib ihnen einen skalaren Projektor (siehe contact_line, curve_line, offer_line)"
    )


def test_every_projection_to_every_allowed_role_is_a_scalar():
    """Der Beweis zur Regel: jedes Feld, jede erlaubte Rolle, echte Falldaten."""
    from soteria.cases import available_cases, load_case, raw_records_for_party
    from soteria.envelope import ROLES
    from soteria.wire import SCALARS

    checked = 0
    for case_id in available_cases():
        case = load_case(case_id)
        for party_id in case.party_ids:
            for record_type, block in raw_records_for_party(case, party_id).items():
                for field_name, raw in block.items():
                    if field_name not in FIELDS:
                        continue
                    spec = FIELDS[field_name]
                    values = raw.values() if isinstance(raw, dict) and spec.per else [raw]
                    for value in values:
                        for role in ROLES:
                            if spec.visibility[role] == "none":
                                continue
                            projected = spec.project(value, role, case.thresholds)
                            assert isinstance(projected, SCALARS), (
                                f"{case_id}/{field_name} an {role}: {type(projected).__name__}"
                            )
                            checked += 1
    assert checked > 100

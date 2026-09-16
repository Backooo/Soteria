"""The field catalogue is data -- so an error in it must show up on import.

A broken matrix must never reach a model. Each of these tests loads a
deliberately damaged catalogue in a subprocess and checks that the import fails,
not just the run.
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
    """No field is in matrix.py that is not in the catalogue."""
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    declared = {k for k in catalogue["fields"] if not k.startswith("_")}
    assert set(FIELDS) == declared
    assert CATALOGUE_VERSION >= 1


def test_every_declared_projector_is_implemented():
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    assert set(catalogue["known_projectors"]) <= set(PROJECTORS)


def test_vocabularies_answer_for_both_shapes():
    """A vocabulary is a list or an object with metadata."""
    assert "pharmaceutical" in vocabulary("cargo_class")   # object
    assert "restricted" in vocabulary("train_operational")  # list
    with pytest.raises(Exception):
        vocabulary("does_not_exist")


def test_coarse_mapping_lives_with_the_values_not_in_code():
    """A new cargo class brings its own coarse class along."""
    assert coarse_of("cargo_class", "pharmaceutical") == "regulated"
    assert coarse_of("cargo_class", "hazmat") == "hazardous"
    assert coarse_of("trade", "hospital") == "care"
    assert coarse_of("cargo_class", "brand_new") == "general"


def test_reporter_roles_are_never_agent_roles():
    """A reporter is a human. The vocabularies must not overlap."""
    from soteria.envelope import ROLES

    assert not set(vocabulary("reporter_role")) & set(ROLES)


def test_every_record_type_names_a_party_and_a_speaking_role():
    from soteria.envelope import ROLES

    for name, spec in RECORD_TYPES.items():
        assert spec.get("held_by") in {"carrier", "customer", "supplier", "shared"}, name
        assert spec.get("speaks_as") in ROLES, name


def _import_with_broken_catalogue(tmp_path: Path, mutate) -> subprocess.CompletedProcess:
    """Copy the project schema, damage it, import soteria.matrix."""
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
        ("owner is not a record type",
         lambda c: c["fields"]["customer_stock"].__setitem__("owner", "nowhere"),
         "not a declared record_type"),
        ("projector is not implemented",
         lambda c: c["fields"]["customer_stock"]["projectors"].__setitem__("ampel", "ampel_magic"),
         "unknown projectors"),
        ("visibility without a projector",
         lambda c: c["fields"]["route_weakness"]["visibility"].__setitem__("legal", "schwelle"),
         "has no projector"),
        ("unknown visibility level",
         lambda c: c["fields"]["customer_stock"]["visibility"].__setitem__("legal", "maybe"),
         "unknown visibilities"),
        ("role list does not match envelope.ROLES",
         lambda c: c.__setitem__("roles", ["intake", "assessor"]),
         "but soteria.envelope.ROLES is"),
        ("known_projectors names something unimplemented",
         lambda c: c["known_projectors"].append("ampel_telepathy"),
         "does not implement"),
        ("catalogue without fields",
         lambda c: c.__setitem__("fields", {}),
         "declares no fields"),
    ],
)
def test_a_broken_catalogue_fails_at_import(tmp_path, label, mutate, needle):
    run = _import_with_broken_catalogue(tmp_path, mutate)
    assert run.returncode != 0, f"{label}: the import went through"
    assert needle in run.stderr, f"{label}: expected {needle!r}, got:\n{run.stderr[-600:]}"


def test_no_object_valued_field_uses_the_plain_raw_projector():
    """A raw object cannot cross the wire (ConfigRecord only carries scalars).
    An object field with the plain `raw` projector therefore delivers
    `bad_value` instead of the answer to the role the matrix grants it to.

    The rule was first applied to two fields one by one and then forgotten for
    the third. This test makes it systematic.
    """
    offenders = [
        name for name, f in FIELDS.items()
        if f.kind == "object" and f.projectors.get("raw") == "raw"
    ]
    assert not offenders, (
        f"{offenders} are object fields with a plain raw projector; "
        "give them a scalar projector (see contact_line, curve_line, offer_line)"
    )


def test_every_projection_to_every_allowed_role_is_a_scalar():
    """The proof of the rule: every field, every allowed role, real case data."""
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
                                f"{case_id}/{field_name} to {role}: {type(projected).__name__}"
                            )
                            checked += 1
    assert checked > 100

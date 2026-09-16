"""The proof: no raw value reaches a role that may not have it.

    uv run python scripts/wire_proof.py          # all cases
    uv run python scripts/wire_proof.py s3

**What is measured here, and why the naive version was wrong.** The first
attempt asked "is any raw value on the wire?" and reported 17 leaks --
including `contract_penalty = 9000` to the contract agent and the cooling curve
to the supplier. The matrix explicitly grants both to those roles. A detector
without a denominator reports authorised disclosure as a violation and is
therefore worthless, and "0 leaks" would be a claim about something that was
never measured.

The right question has a denominator: for every (role, field) pair where the
matrix does **not** say `raw`, no raw value of that field may appear in the
answer. Authorised disclosure is counted and reported separately, so it stays
visible how large the denominator actually is.

ALL role/field/node combinations are checked, not only those of the ask plan --
a malicious party asks exactly what it is not supposed to ask.
`soteria.party_app.answer_ask` is used, the same code the federation runs; only
the transport is a call instead of a socket.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from soteria.cases import available_cases, load_case, raw_records_for_party
from soteria.envelope import ROLES
from soteria.matrix import FIELDS, visibility
from soteria.party_app import answer_ask

# Shorter strings prove nothing: "0", "1", "no" appear everywhere by chance.
_MIN_NEEDLE = 3


def _needles(value: Any, out: set[str]) -> None:
    """The strings a wire capture would show as a raw value of this field."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if not str(key).startswith("_"):
                _needles(inner, out)
        return
    if isinstance(value, (list, tuple)):
        for inner in value:
            _needles(inner, out)
        return
    if isinstance(value, bool) or value is None:
        return
    text = str(value)
    if len(text) >= _MIN_NEEDLE:
        out.add(text)


def _raw_needles_by_field(case: Any) -> dict[str, set[str]]:
    """field -> the raw strings any node holds for it."""
    out: dict[str, set[str]] = {}
    for party_id in case.party_ids:
        for _record_type, block in raw_records_for_party(case, party_id).items():
            for field_name, value in block.items():
                if field_name in FIELDS:
                    out.setdefault(field_name, set())
                    _needles(value, out[field_name])
    return out


def prove(case_id: str, verbose: bool = True) -> dict[str, Any]:
    case = load_case(case_id)
    needles = _raw_needles_by_field(case)

    print(f"\n{'=' * 78}\n{case_id}: {case.title}\n{'=' * 78}")
    if verbose:
        print(f"{'Asker':<10} {'Node':<10} {'Field':<22} {'allowed':<9} Answer")
        print("-" * 78)

    attempts = refused = authorised_raw = 0
    rows: list[dict[str, Any]] = []
    violations: list[str] = []
    cross_field: list[str] = []

    for asker in ROLES:
        for party_id in case.party_ids:
            if asker in case.roles_of(party_id):
                continue  # a role does not ask its own node
            for field in FIELDS:
                reply = answer_ask(case, party_id, asker, field, "confidentiality")
                if reply["code"] == "unknown_field":
                    continue  # the node does not hold it -- no boundary touched
                attempts += 1
                level = visibility(field, asker)
                blob = json.dumps(reply, sort_keys=True, default=str)
                rows.append({
                    "asker": asker,
                    "party_id": party_id,
                    "party_type": case.party_type(party_id),
                    "field": field,
                    "allowed": level,
                    "outcome": ("refused" if reply["code"]
                                else "raw" if level == "raw" else "projected"),
                    "code": reply["code"],
                    # The value is only included where it actually reached the asker.
                    "value": "" if reply["code"] else reply["value"],
                    "scope": reply["scope"],
                })

                if reply["code"]:
                    refused += 1
                    if verbose:
                        print(f"{asker:<10} {party_id.split('_')[0]:<10} {field:<22} "
                              f"{level:<9} REFUSED {reply['code']}")
                    continue

                shown = str(reply["value"])[:28]
                scope = f" @{reply['scope']}" if reply["scope"] else ""
                if verbose:
                    print(f"{asker:<10} {party_id.split('_')[0]:<10} {field:<22} "
                          f"{level:<9} {shown}{scope}")

                if level == "raw":
                    # Authorised disclosure. It is the denominator, not the error.
                    authorised_raw += 1
                    continue

                # The actual check: a non-raw resolution must not contain any raw
                # value of this field.
                for needle in sorted(needles.get(field, set())):
                    if needle in blob:
                        violations.append(
                            f"{asker} got {field!r} as {level!r}, but {needle!r} "
                            f"is in the answer from {party_id}"
                        )
                # And no answer about X may drag along a raw value of Y.
                for other, other_needles in needles.items():
                    if other == field:
                        continue
                    if visibility(other, asker) == "raw":
                        continue
                    for needle in sorted(other_needles):
                        if len(needle) >= 6 and needle in blob:
                            cross_field.append(
                                f"answer on {field!r} to {asker} contained {needle!r} "
                                f"from {other!r}"
                            )

    print("-" * 78)
    print(f"{attempts} boundary crossings attempted  |  {refused} refused  |  "
          f"{authorised_raw} authorised raw disclosures  |  "
          f"{attempts - refused - authorised_raw} projected answers")
    checked = sum(len(v) for v in needles.values())
    print(f"{checked} raw strings checked against every answer where the matrix "
          "does not say 'raw'.")
    for line in violations + cross_field:
        print(f"  VIOLATION  {line}")
    if not violations and not cross_field:
        print("  no violation.")
    return {
        "case_id": case_id,
        "attempts": attempts,
        "refused": refused,
        "authorised_raw": authorised_raw,
        "needles": checked,
        "violations": violations + cross_field,
        "rows": rows,
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    quiet = "--quiet" in sys.argv
    ids = args or list(available_cases())
    results = [prove(case_id, verbose=not quiet) for case_id in ids]

    attempts = sum(r["attempts"] for r in results)
    refused = sum(r["refused"] for r in results)
    authorised = sum(r["authorised_raw"] for r in results)
    needles = sum(r["needles"] for r in results)
    violations = [f"{r['case_id']}: {v}" for r in results for v in r["violations"]]

    if "--json" in sys.argv:
        out = Path(__file__).resolve().parents[1] / "view" / "fixtures" / "boundary.json"
        out.write_text(json.dumps({
            "_comment": "Generated by scripts/wire_proof.py --json. Every boundary crossing "
                        "a party could attempt, and what came of it.",
            "cases": [{k: v for k, v in r.items()} for r in results],
        }, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        print(f"\nwritten: {out.relative_to(out.parents[2])}")

    print(f"\n{'=' * 78}")
    print(f"{len(ids)} cases  |  {attempts} boundary crossings  |  {refused} refused  |  "
          f"{authorised} authorised raw disclosures  |  {needles} raw values checked")
    if violations:
        print(f"\nFAILED -- {len(violations)} violation(s):")
        for line in violations:
            print(f"  {line}")
        return 1
    print("\nPASSED. No raw value reached a role that may not have it.")
    print(f"The denominator is reported alongside: {refused} attempts were refused with a type, and")
    print(f"{authorised} raw disclosures are authorised and reported as such -- so the")
    print("test distinguishes between the two instead of flagging every disclosure.")
    print("Not because a prompt forbids it: the projection runs on the party's node,")
    print("and a ConfigRecord only carries scalars.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

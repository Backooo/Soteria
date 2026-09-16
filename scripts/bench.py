"""The four numbers. From runs, not from gut feeling.

    uv run python scripts/bench.py

Runs every case through the same `Assessor` class as the federation, checks the
boundary proof and writes `view/fixtures/bench.json` for the case overview.

**What each number claims -- and what it does not.**

1. Time to decision. The logic is measured without transport; the real
   federation takes 3-7 s (docs/RISKS.md). Both are reported. The phone-chain
   baseline is an ASSUMPTION, not a measurement.
2. Hit rate. Split into known cases and holdout. `policy.py` was written
   against the known cases, so their rate is a consistency check. As long as
   the ground truth is marked PROPOSAL, it is also unconfirmed -- and that is
   stated next to the number.
3. Tightness. From scripts/wire_proof.py, with a denominator: attempted
   crossings, refused ones, authorised raw disclosures, violations.
4. Behaviour with a gap. Every case is run a second time with the customer
   offline. No case has that built in -- so it is generated, and it says so.
"""

from __future__ import annotations

import dataclasses
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from record_run import Recorder, local_sender  # noqa: E402
from wire_proof import prove  # noqa: E402

from soteria.assessor_app import run_incident  # noqa: E402
from soteria.cases import available_cases, load_case  # noqa: E402
from soteria.charter import Budget  # noqa: E402
from soteria.envelope import EnvelopeError  # noqa: E402
from soteria.ledger import Ledger  # noqa: E402
from soteria.policy import ASK_PLAN  # noqa: E402

OUT = HERE.parent / "view" / "fixtures" / "bench.json"

# ASSUMPTION, not a measurement. We did not time a phone chain.
BASELINE_MINUTES = 47
BASELINE_SOURCE = (
    "Assumed duration of a phone chain across five parties, including call-backs. "
    "Not measured -- an assumption that is reported as such."
)

# From docs/RISKS.md, measured on the real federation with the bundled ask
# (one message per node). Before, with 13 rounds: 69.1 / 126.9 / 68.0 s.
FEDERATION_SECONDS = {"s1": 6.4, "s2": 6.2, "s3": 3.2}


def _run(case: Any) -> tuple[dict[str, Any] | None, str | None, float, list[dict]]:
    recorder = Recorder()
    ledger = Ledger(
        Budget(max_delegations=len(ASK_PLAN) + 2, max_depth=2,
               seconds=240.0, max_connector_calls=0),
        recorder,
    )
    started = time.perf_counter()
    try:
        decision = run_incident(case, ledger, local_sender(case)).as_dict()
        refusal = None
    except EnvelopeError as exc:
        decision, refusal = None, exc.code
    return decision, refusal, time.perf_counter() - started, recorder.events


def _hit(decision: dict | None, refusal: str | None, truth: dict) -> bool:
    expected_refusal = truth.get("expect_refusal")
    if expected_refusal:
        return refusal == expected_refusal
    if not decision:
        return False
    if set(decision["measures"]) != set(truth.get("measures") or ()):
        return False
    return not (set(decision["measures"]) & set(truth.get("must_not") or ()))


def main() -> int:
    cases: list[dict[str, Any]] = []
    for case_id in available_cases():
        case = load_case(case_id)
        truth = dict(case.truth)
        decision, refusal, seconds, events = _run(case)

        # Number 4: same situation, the customer does not answer.
        customers = tuple(
            str(f["party_id"]) for f in case.federations if f.get("party_type") == "customer"
        )
        gap_decision, gap_refusal, _, _ = _run(
            dataclasses.replace(case, offline_parties=customers)
        )

        cases.append({
            "id": case_id,
            "title": case.title,
            "holdout": case_id.startswith("h"),
            "truth": sorted(truth.get("measures") or ()),
            "truth_reason": truth.get("reason_code"),
            "truth_confirmed": case.truth_confirmed,
            "decided": sorted(decision["measures"]) if decision else [],
            "decided_reason": decision["reason_code"] if decision else None,
            "refusal": refusal,
            "hit": _hit(decision, refusal, truth),
            "reason_matches": bool(decision) and decision["reason_code"] == truth.get("reason_code"),
            "tier": decision["tier"] if decision else 0,
            "grants": decision["grants"] if decision else [],
            "receipt_hash": decision["receipt_hash"] if decision else "",
            "seconds_logic": round(seconds, 4),
            "seconds_federation": FEDERATION_SECONDS.get(case_id),
            "quarantined": any(e["type"] == "soteria.quarantine" for e in events),
            "gap": {
                "offline": list(customers),
                "decided": sorted(gap_decision["measures"]) if gap_decision else [],
                "reason": gap_decision["reason_code"] if gap_decision else None,
                "refusal": gap_refusal,
            },
        })

    known = [c for c in cases if not c["holdout"]]
    holdout = [c for c in cases if c["holdout"]]
    unconfirmed = [c["id"] for c in cases if not c["truth_confirmed"]]

    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        proofs = [prove(c["id"], verbose=False) for c in cases]
    boundary = {
        "attempts": sum(p["attempts"] for p in proofs),
        "refused": sum(p["refused"] for p in proofs),
        "authorised_raw": sum(p["authorised_raw"] for p in proofs),
        "violations": sum(len(p["violations"]) for p in proofs),
    }

    fed = [v for v in FEDERATION_SECONDS.values() if v]
    numbers = {
        "1_time": {
            "logic_median_ms": round(statistics.median(c["seconds_logic"] for c in cases) * 1000, 1),
            "federation_median_s": round(statistics.median(fed), 1) if fed else None,
            "federation_max_s": max(fed) if fed else None,
            "baseline_minutes": BASELINE_MINUTES,
            "baseline_is_assumption": True,
        },
        "2_hits": {
            "known": f"{sum(c['hit'] for c in known)}/{len(known)}",
            "holdout": f"{sum(c['hit'] for c in holdout)}/{len(holdout)}" if holdout else None,
            "reasons_matching": f"{sum(c['reason_matches'] for c in cases)}/{len(cases)}",
            "truth_unconfirmed": unconfirmed,
        },
        "3_boundary": boundary,
        "4_gap": {
            "cases": len(cases),
            "still_decided": sum(1 for c in cases if c["gap"]["decided"]),
        },
    }

    honesty = [
        {"claim": "No raw value reaches a role that may not have it",
         "real": f"{boundary['attempts']} boundary crossings attempted, {boundary['refused']} "
                 f"refused, {boundary['violations']} violations -- measured with a denominator",
         "simulated": "nothing. The boundary proof calls the node handlers directly; the same "
                      "code runs in the federation"},
        {"claim": "Three parties, three nodes",
         "real": "three SuperNodes with their own node-config, real Flower messages, all "
                 "three cases hit",
         "simulated": "the three nodes run on one machine"},
        {"claim": "One federation per party",
         "real": "one federation with three party nodes",
         "simulated": "a ServerApp in flwr cannot reach three SuperLinks together -- that "
                      "is the next stage, not the current state"},
        {"claim": "Decision in minutes instead of a phone chain",
         "real": f"logic {numbers['1_time']['logic_median_ms']} ms, federation "
                 f"{numbers['1_time']['federation_median_s']} s median",
         "simulated": f"the baseline of {BASELINE_MINUTES} min is an ASSUMPTION"},
        {"claim": "Hit rate",
         "real": f"{numbers['2_hits']['known']} on the known cases",
         "simulated": "the rules were written against exactly these cases -- a "
                      "consistency check, not a generalisation. "
                      + ("The ground truth is also unconfirmed (PROPOSAL). " if unconfirmed else "")
                      + ("Holdout cases are missing." if not holdout else "")},
        {"claim": "Agents",
         "real": "one assessor as a ServerApp, party nodes as ClientApps",
         "simulated": "the assessor is a rule engine, not a language model. The party nodes "
                      "need none: a projection is a function"},
        {"claim": "Data",
         "real": "schema, validation, vocabularies",
         "simulated": "all data is invented -- no real railway data, people or companies"},
        {"claim": "Receipts",
         "real": "chain across the whole incident, verify() recomputes it",
         "simulated": "16 hex characters of SHA-256 -- a checksum, not cryptography "
                      "for real emergencies"},
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": time.time(),
        "baseline_source": BASELINE_SOURCE,
        "numbers": numbers,
        "cases": cases,
        "honesty": honesty,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    t, h, b, g = (numbers["1_time"], numbers["2_hits"], numbers["3_boundary"], numbers["4_gap"])
    print("Soteria -- the four numbers\n" + "=" * 72)
    print(f"1 Time      logic {t['logic_median_ms']} ms  |  federation {t['federation_median_s']} s "
          f"median, {t['federation_max_s']} s max  |  baseline {t['baseline_minutes']} min (ASSUMPTION)")
    print(f"2 Hits      known {h['known']}  |  holdout {h['holdout'] or 'no cases'}  |  "
          f"reason matches {h['reasons_matching']}")
    if h["truth_unconfirmed"]:
        print(f"            WARNING: ground truth unconfirmed for {', '.join(h['truth_unconfirmed'])}")
    print(f"3 Tightness {b['attempts']} crossings  |  {b['refused']} refused  |  "
          f"{b['authorised_raw']} authorised  |  {b['violations']} violations")
    print(f"4 Gap       {g['still_decided']}/{g['cases']} cases decided although the customer is silent")
    print("=" * 72)
    for c in cases:
        gap = ", ".join(c["gap"]["decided"]) or f"NONE ({c['gap']['refusal']})"
        print(f"  {'HIT     ' if c['hit'] else 'MISMATCH'} {c['id']:<4} "
              f"{', '.join(c['decided']) or c['refusal']:<30} reason {c['decided_reason']:<12}"
              f"{'' if c['reason_matches'] else '(expected ' + str(c['truth_reason']) + ')'}")
        print(f"           without customer: {gap} ({c['gap']['reason']})")
    print(f"\nwritten: {OUT.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

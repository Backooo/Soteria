"""Bring the incident fixtures into the shape of the Vite frontend.

    uv run python scripts/export_frontend.py
    uv run python scripts/export_frontend.py --out "../soteria-frontend/Soteria - Frontend/src/data/soteria.json"

Reads `view/fixtures/s*.json` and writes, per incident (key: `incident_id`), exactly
the fields the frontend would otherwise take from mocks:

- `recommendation`, `soteriaTier`, `marketSensitive` for `IncidentAlert`
- `consensus[]` in the shape of `SoteriaConsensusItem`
- `decision`: the decision as a structure (measures, tier, approvals, reason)
- `events`: the unchanged event stream, for the Agent Live Console

The adapter **renames and phrases**; it invents no values and never undoes a
projection: every value comes from an event in the stream. Never from `data/`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "view" / "fixtures"
DEFAULT_OUT = ROOT / "view" / "frontend" / "soteria.json"

MEASURE_LABEL = {
    "proceed": "Proceed",
    "hold": "Hold train",
    "cool": "Cool cargo",
    "reload": "Reload cargo",
    "alt_transport": "Switch to alternative transport",
    "contact": "Contact customer",
    "stop_train": "Stop train",
    "notify_authority": "Notify authority",
    "press": "Inform press",
}

TIER_LABEL = {
    1: "Tier 1 · reversible, executed autonomously",
    2: "Tier 2 · one human key",
    3: "Tier 3 · hard to reverse, two human keys",
}

REASON_LABEL = {
    "safety": "Safety",
    "feasibility": "Feasibility",
    "time": "Time pressure",
    "liability": "Liability",
    "confidentiality": "Confidentiality",
    "cost": "Cost",
    "missing_data": "Missing data",
}

# Which field represents each role in its tile. Pure selection, not a value.
ROLE_FIELD = {
    "intake": "temperature_curve",
    "legal": "contract_penalty",
    "supplier": "replacement_available",
    "customer": "customer_stock",
}

ROLE_LABEL = {
    "intake": "Intake (damage)",
    "assessor": "Assessor",
    "legal": "Legal (contract)",
    "supplier": "Supplier",
    "customer": "Customer",
}

# The frontend types only know these visibility levels.
FRONTEND_VISIBILITY = {"raw": "raw", "ampel": "ampel", "schwelle": "schwelle"}


def _fact_text(fact: dict[str, Any]) -> str:
    vis, value = fact["visibility"], fact["value"]
    if vis == "ampel":
        shown = f"traffic light {str(value).upper()}"
    elif vis == "schwelle":
        shown = f"threshold {'exceeded' if value == 'above' else 'not reached'}"
    else:
        shown = f"{vis}: {value}"
    scope = f" ({fact['scope']})" if fact.get("scope") else ""
    return f"{fact['field']}{scope}: {shown}"


def _recommendation(events: list[dict[str, Any]]) -> tuple[str, int | None]:
    decision = next((e for e in events if e["type"] == "soteria.decision"), None)
    if decision is None:
        nd = next((e for e in events if e["type"] == "soteria.no_decision"), None)
        return (f"No decision: {nd['code']}" if nd else "No decision"), None
    measures = ", ".join(MEASURE_LABEL.get(m, m) for m in decision["measures"])
    keys = len(decision["grants"])
    grants = f", {keys} key(s) ({', '.join(decision['grants'])})" if keys else ", autonomous"
    return f"{measures} — Tier {decision['tier']}{grants}", decision["tier"]


def _decision(events: list[dict[str, Any]]) -> dict[str, Any]:
    """The decision as a structure: what, how binding, who approved, why."""
    decision = next((e for e in events if e["type"] == "soteria.decision"), None)
    if decision is None:
        nd = next((e for e in events if e["type"] == "soteria.no_decision"), None)
        return {"status": "blocked", "code": nd["code"] if nd else "unknown", "measures": []}
    required = next((e for e in events if e["type"] == "soteria.grant.required"), {})
    return {
        "status": "decided",
        "measures": [{"code": m, "label": MEASURE_LABEL.get(m, m)} for m in decision["measures"]],
        "tier": decision["tier"],
        "tierLabel": TIER_LABEL.get(decision["tier"], f"Tier {decision['tier']}"),
        "keysNeeded": required.get("keys_needed", len(decision["grants"])),
        "grants": decision["grants"],
        "reasonCode": decision["reason_code"],
        "reasonLabel": REASON_LABEL.get(decision["reason_code"], decision["reason_code"]),
        "coverage": decision["coverage"],
        "receiptHash": decision["receipt_hash"],
        "decidedBy": decision.get("decided_by", "policy"),
        "model": decision.get("model", ""),
        "rationale": decision.get("rationale", ""),
    }


def export_case(fixture: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    events = fixture["events"]
    opened = next(e for e in events if e["type"] == "soteria.incident.open")
    quarantine = next((e for e in events if e["type"] == "soteria.quarantine"), None)
    facts = [e for e in events if e["type"] == "soteria.fact"]
    done = next((e for e in events if e["type"] == "soteria.done"), {})
    missing = {
        p
        for e in events
        if e["type"] == "soteria.coverage"
        for p in e["parties_missing"]
    }
    missing_types = {
        e["party_type"] for e in events if e["type"] == "soteria.role.ready" and e["party_id"] in missing
    }

    recommendation, tier = _recommendation(events)
    consensus: list[dict[str, Any]] = []
    for role, field in ROLE_FIELD.items():
        fact = next((f for f in facts if f["role"] == role and f["field"] == field), None)
        if quarantine and quarantine["trigger_role"] == role:
            status = "quarantined"
        elif fact is None or role in missing_types:
            status = "pending"
        else:
            status = "verified"
        consensus.append({
            "role": role,
            "label": ROLE_LABEL[role],
            "status": status,
            "needToKnowVisibility": FRONTEND_VISIBILITY.get(fact["visibility"], "blocked") if fact else "blocked",
            "lastFact": _fact_text(fact) if fact else "no answer",
        })
    consensus.insert(1, {
        "role": "assessor",
        "label": ROLE_LABEL["assessor"],
        "status": "verified" if tier is not None else "restricted",
        "needToKnowVisibility": "ampel",
        "lastFact": f"{recommendation} · {done.get('answers', 0)}/{done.get('asks', 0)} answered"
                    + (" · receipt chain verified" if done.get("receipt_chain_verified") else ""),
    })

    return opened["incident_id"], {
        "caseId": opened["case_id"],
        "trainId": opened["train_id"],
        "timestamp": fixture["case"]["report"].get("ts", ""),
        "recommendation": recommendation,
        "soteriaTier": tier,
        "marketSensitive": quarantine is not None,
        "blockedChannels": quarantine["blocked_channels"] if quarantine else [],
        "receiptHead": done.get("receipt_head"),
        "consensus": consensus,
        "decision": _decision(events),
        # The unchanged event stream, for the Agent Live Console
        "events": events,
    }


def export_all(fixtures: Path = FIXTURES) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in sorted(fixtures.glob("s[0-9]*.json")):
        incident_id, entry = export_case(json.loads(path.read_text()))
        out[incident_id] = entry
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    data = export_all()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(data)} incidents -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

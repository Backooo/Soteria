"""The assessor's reasoning on a hosted LLM via a Flower AgentApp, guarded by code.

The model decides *which* measures to take. It runs as the AgentApp in
`agent/` on SuperGrid, where Flower provides the model access -- no API key of
our own. Code decides everything that must not depend on a model:

- The model sees only what the assessor sees: traffic lights, thresholds, flags,
  coarse classes and the shared driver report. Never a raw value from a party.
- Unknown measures and malformed answers are rejected.
- Safety floor: a tier-3 measure the rule policy requires (stop_train,
  notify_authority, press) is added back if the model dropped it, and the event
  says so.
- Tier, human keys and quarantine are enforced afterwards by `grants` and the
  ledger, exactly as for the rule policy.
- If SuperGrid is unreachable, the rule policy decides alone and the event says
  `decided_by = "policy_fallback"`. A fallback is never labelled as model output.

Configuration (ServerApp run config, or environment for local scripts):

    model      = "flower-endeavor-v1.0"   SOTERIA_MODEL
    llm        = true                     SOTERIA_LLM=0 disables the model call
    federation = "supergrid"              SOTERIA_AGENT_FEDERATION

Requires a valid `flwr login supergrid` session on the machine that runs the assessor.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .grants import TIER

DEFAULT_MODEL = "flower-endeavor-v1.0"
DEFAULT_FEDERATION = "supergrid"
AGENT_BUNDLE = Path(os.getenv("SOTERIA_AGENT_BUNDLE") or Path(__file__).resolve().parents[1] / "agent")
RESULT_PREFIX = "SOTERIA_LLM "
# A FAB cannot carry a nested pyproject.toml (non-overridable built-in exclude in
# flwr/cli/build.py), so the bundle ships its manifest under this name and we
# materialize a runnable copy when the ServerApp runs from the installed FAB.
FAB_MANIFEST = "pyproject.fab.toml"
REASON_CODES = ("safety", "feasibility", "time", "liability", "cost", "missing_data")
MODEL_TIMEOUT_SECONDS = 150.0

# The prompt lives in agent/soteria_assessor_agent/agent_app.py, next to the model call.



@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = True
    model: str = DEFAULT_MODEL
    federation: str = DEFAULT_FEDERATION

    @classmethod
    def from_run_config(cls, run_config: Mapping[str, Any]) -> "LLMConfig":
        enabled = run_config.get("llm", True)
        model = run_config.get("model", DEFAULT_MODEL)
        federation = run_config.get("federation", DEFAULT_FEDERATION)
        return cls(enabled=bool(enabled), model=str(model or DEFAULT_MODEL),
                   federation=str(federation or DEFAULT_FEDERATION))

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            enabled=os.getenv("SOTERIA_LLM", "1").strip() not in ("0", "false", "no"),
            model=os.getenv("SOTERIA_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            federation=os.getenv("SOTERIA_AGENT_FEDERATION", DEFAULT_FEDERATION).strip() or DEFAULT_FEDERATION,
        )


@dataclass(frozen=True)
class Proposal:
    measures: tuple[str, ...]
    reason_code: str
    decided_by: str                     # "llm" | "policy_fallback" | "policy"
    model: str
    rationale: str = ""
    policy_measures: tuple[str, ...] = ()
    floor_added: tuple[str, ...] = ()
    error: str = ""
    latency_seconds: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def as_event(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "decided_by": self.decided_by,
            "measures": list(self.measures),
            "reason_code": self.reason_code,
            "rationale": self.rationale,
            "policy_measures": list(self.policy_measures),
            "agrees_with_policy": set(self.measures) == set(self.policy_measures),
            "floor_added": list(self.floor_added),
            "error": self.error,
            "latency_seconds": self.latency_seconds,
        }


def _prompt(sheets: Mapping[str, Any], flags: tuple[str, ...], missing: tuple[str, ...],
            situation: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "driver_report": dict(situation),
            "flags": list(flags),
            "parties_missing": list(missing),
            "signals": dict(sheets),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def parse_answer(text: str) -> tuple[tuple[str, ...], str, str]:
    """Strictly parse the model's JSON answer. Raises ValueError on anything off."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model answer")
    data = json.loads(match.group(0))
    measures = data.get("measures")
    if not isinstance(measures, list) or not measures:
        raise ValueError("measures must be a non-empty list")
    unknown = [m for m in measures if m not in TIER]
    if unknown:
        raise ValueError(f"unknown measures {unknown}")
    reason = str(data.get("reason_code", ""))
    if reason not in REASON_CODES:
        raise ValueError(f"unknown reason_code {reason!r}")
    rationale = str(data.get("rationale", ""))[:400]
    # Stable order, no duplicates
    ordered = tuple(dict.fromkeys(str(m) for m in measures))
    return ordered, reason, rationale


def _flwr_cli() -> str:
    candidate = Path(sys.executable).with_name("flwr")
    return str(candidate) if candidate.exists() else "flwr"


def parse_run_output(output: str) -> tuple[str, str]:
    """Find the AgentApp's result line in `flwr run --stream` output. Returns (model, text)."""
    clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
    for line in reversed(clean.splitlines()):
        idx = line.find(RESULT_PREFIX)
        if idx >= 0:
            data = json.loads(line[idx + len(RESULT_PREFIX):])
            return str(data.get("model", "")), str(data.get("text", ""))
    raise ValueError("no SOTERIA_LLM result line in AgentApp output")


def bundle_dir() -> Path:
    """A directory `flwr run` accepts: the repo bundle, or a temp copy built from the FAB."""
    if (AGENT_BUNDLE / "pyproject.toml").is_file():
        return AGENT_BUNDLE
    manifest = AGENT_BUNDLE / FAB_MANIFEST
    if not manifest.is_file():
        raise FileNotFoundError(f"agent bundle missing at {AGENT_BUNDLE} (set SOTERIA_AGENT_BUNDLE)")
    target = Path(tempfile.gettempdir()) / f"soteria-agent-{manifest.stat().st_mtime_ns}"
    if not (target / "pyproject.toml").is_file():
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(AGENT_BUNDLE, target)
        (target / FAB_MANIFEST).replace(target / "pyproject.toml")
    if not (target / "LICENSE").is_file():
        # The bundle manifest requires a LICENSE; inside the FAB it lives at the app root.
        root_license = AGENT_BUNDLE.parent / "LICENSE"
        if root_license.is_file():
            shutil.copyfile(root_license, target / "LICENSE")
    return target


def _call_model(config: LLMConfig, prompt: str, timeout: float) -> tuple[str, str]:
    """Run the assessor AgentApp on SuperGrid with the projected signals as input."""
    encoded = base64.b64encode(prompt.encode("utf-8")).decode("ascii")
    run_config = f'agent.input_b64="{encoded}" agent.model="{config.model}"'
    completed = subprocess.run(
        [_flwr_cli(), "run", str(bundle_dir()), config.federation, "--stream",
         "--run-config", run_config],
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    output = completed.stdout + "\n" + completed.stderr
    try:
        return parse_run_output(output)
    except ValueError as exc:
        # Without the CLI's own words, a failed run is indistinguishable from a
        # silent one -- and the fallback would hide why the model never answered.
        tail = " / ".join(
            line.strip() for line in re.sub(r"\x1b\[[0-9;]*m", "", output).splitlines()
            if line.strip()
        )[-300:]
        raise ValueError(f"{exc} (exit {completed.returncode}; output: {tail})") from exc


def propose(
    config: LLMConfig,
    sheets: Mapping[str, Any],
    flags: tuple[str, ...],
    missing: tuple[str, ...],
    situation: Mapping[str, Any],
    policy: tuple[tuple[str, ...], str],
    time_left: float,
) -> Proposal:
    """The model's decision within guardrails, or the rule policy with the reason why."""
    policy_measures, policy_reason = policy

    def fallback(error: str, latency: float = 0.0) -> Proposal:
        return Proposal(
            measures=policy_measures, reason_code=policy_reason,
            decided_by="policy_fallback" if config.enabled else "policy",
            model=config.model if config.enabled else "",
            policy_measures=policy_measures, error=error, latency_seconds=latency,
        )

    if not config.enabled:
        return fallback("llm disabled")

    started = time.monotonic()
    try:
        model, text = _call_model(config, _prompt(sheets, flags, missing, situation),
                                  timeout=max(5.0, min(MODEL_TIMEOUT_SECONDS, time_left - 10.0)))
        measures, reason, rationale = parse_answer(text)
    except Exception as exc:  # any model failure falls back, visibly
        return fallback(f"{type(exc).__name__}: {str(exc)[:160]}", round(time.monotonic() - started, 2))

    floor = tuple(m for m in policy_measures if TIER[m] == 3 and m not in measures)
    return Proposal(
        measures=measures + floor,
        reason_code="safety" if floor else reason,
        decided_by="llm",
        model=model or config.model,
        rationale=rationale,
        policy_measures=policy_measures,
        floor_added=floor,
        latency_seconds=round(time.monotonic() - started, 2),
    )

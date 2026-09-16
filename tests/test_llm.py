"""Guardrails around the LLM decision: parsing, safety floor, visible fallback."""

import pytest

from soteria import llm
from soteria.llm import LLMConfig, parse_answer, parse_run_output, propose

SHEETS = {"temperature_curve": "rot", "locality_class": "town_edge"}
SITUATION = {"track_blocked": True, "train_operational": "immobilized", "severity": "high"}
POLICY = (("stop_train", "notify_authority"), "safety")


def _fake_model(text):
    return lambda config, prompt, timeout: ("flower-endeavor-v1.0", text)


def test_parse_answer_rejects_unknown_measures():
    with pytest.raises(ValueError):
        parse_answer('{"measures": ["launch_rocket"], "reason_code": "safety"}')


def test_parse_run_output_finds_the_result_line_between_logs():
    out = 'INFO : noise\n\x1b[32mSOTERIA_LLM {"model": "m", "text": "hi"}\x1b[0m\nINFO :\n'
    assert parse_run_output(out) == ("m", "hi")


def test_llm_decision_is_used_and_labelled(monkeypatch):
    monkeypatch.setattr(llm, "_call_model", _fake_model(
        '{"measures": ["stop_train", "notify_authority", "cool"], "reason_code": "safety", "rationale": "r"}'))
    p = propose(LLMConfig(), SHEETS, ("hazmat",), (), SITUATION, POLICY, time_left=200)
    assert p.decided_by == "llm"
    assert p.measures == ("stop_train", "notify_authority", "cool")
    assert p.model == "flower-endeavor-v1.0"


def test_safety_floor_adds_back_dropped_tier3_measures(monkeypatch):
    monkeypatch.setattr(llm, "_call_model", _fake_model(
        '{"measures": ["hold"], "reason_code": "cost", "rationale": "r"}'))
    p = propose(LLMConfig(), SHEETS, ("hazmat",), (), SITUATION, POLICY, time_left=200)
    assert set(p.floor_added) == {"stop_train", "notify_authority"}
    assert p.reason_code == "safety"


def test_model_failure_falls_back_to_policy_and_says_so(monkeypatch):
    def boom(config, prompt, timeout):
        raise TimeoutError("supergrid unreachable")
    monkeypatch.setattr(llm, "_call_model", boom)
    p = propose(LLMConfig(), SHEETS, ("hazmat",), (), SITUATION, POLICY, time_left=200)
    assert p.decided_by == "policy_fallback"
    assert p.measures == POLICY[0]
    assert "unreachable" in p.error


def test_prompt_carries_only_projections():
    prompt = llm._prompt(SHEETS, ("hazmat",), (), SITUATION)
    assert set(__import__("json").loads(prompt)) == {"driver_report", "flags", "parties_missing", "signals"}


def test_fab_manifest_matches_the_bundle_manifest():
    """The FAB copy of the agent manifest must not drift from the real one."""
    from soteria.llm import AGENT_BUNDLE, FAB_MANIFEST
    assert (AGENT_BUNDLE / "pyproject.toml").read_text() == (AGENT_BUNDLE / FAB_MANIFEST).read_text()

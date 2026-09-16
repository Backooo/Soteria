"""Tests for the collaboration scaffold.

These use a scripted fake model, so the whole suite runs in well under a second
and needs no Jetson, no SuperGrid and no network.

Several tests here exist because an external review found the original version
claiming guarantees it did not have. Those are marked REGRESSION.
"""

from __future__ import annotations

import json

import pytest

from soteria.charter import Budget, Charter, CharterError, Role, build
from soteria.ledger import BudgetExceeded, Ledger, PolicyViolation
from soteria.team import EmptyModelResponse, Team

# --- fake model ---------------------------------------------------------


class FakeItem:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def to_dict(self) -> dict:
        return self._payload


class FakeResponse:
    def __init__(self, items: list[dict], status: str = "completed") -> None:
        self.output = [FakeItem(i) for i in items]
        self.status = status
        self.incomplete_details = (
            None if status == "completed" else {"reason": "max_output_tokens"}
        )


class FakeResponses:
    """Replays a scripted list of turns and records what it was asked."""

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._script:
            return FakeResponse([_message("done")])
        nxt = self._script.pop(0)
        return nxt if isinstance(nxt, FakeResponse) else FakeResponse(nxt)


class FakeClient:
    def __init__(self, script: list) -> None:
        self.responses = FakeResponses(script)


class FakeConnectors:
    """Stands in for `AgentSession.connectors`.

    Mirrors the real one's sharp edge: `tools()` raises on any ref it cannot
    resolve, rather than skipping it.
    """

    def __init__(self, available: dict[str, list[str]] | None = None) -> None:
        # ref -> tool names it expands to
        self._available = available or {"web_search": ["web_search"]}
        self.executed: list[dict] = []

    def tools(self, names):
        out = []
        for ref in names:
            if ref not in self._available:
                raise ValueError(f"Unsupported connector {ref!r}")
            out += [{"type": "function", "name": n} for n in self._available[ref]]
        return out

    def call(self, tool_call):
        self.executed.append(tool_call)
        return {
            "type": "function_call_output",
            "call_id": tool_call["call_id"],
            "output": json.dumps({"result": f"{tool_call['name']} ran"}),
        }


def _message(text: str) -> dict:
    return {"type": "message", "role": "assistant", "content": [{"text": text}]}


def _call(name: str, call_id: str = "c1", **args) -> dict:
    return {
        "type": "function_call",
        "name": name,
        "call_id": call_id,
        "arguments": json.dumps(args or {"task": "do the thing"}),
    }


def _team(script, charter, connectors=None, events=None):
    ledger = Ledger(charter.budget, events)
    client = FakeClient(script)
    return Team(charter, client, "fake-model", ledger, connectors), ledger, client


def two_role_charter(**budget_kwargs):
    return build(
        supervisor="lead",
        roles=[
            Role(
                name="lead", brief="Plan.", may_delegate_to=("worker",), max_tool_turns=3
            ),
            Role(name="worker", brief="Do.", tools=("web_search",), max_tool_turns=2),
        ],
        budget=Budget(**budget_kwargs) if budget_kwargs else Budget(),
    )


# --- charter validation -------------------------------------------------


def test_charter_rejects_delegation_cycle():
    with pytest.raises(CharterError, match="cycle"):
        build(
            supervisor="a",
            roles=[
                Role(name="a", brief="", may_delegate_to=("b",)),
                Role(name="b", brief="", may_delegate_to=("a",)),
            ],
        )


def test_charter_rejects_cycle_unreachable_from_supervisor():
    """REGRESSION: cycle detection used to start only at the supervisor."""
    with pytest.raises(CharterError, match="cycle"):
        build(
            supervisor="lead",
            roles=[
                Role(name="lead", brief=""),
                Role(name="x", brief="", may_delegate_to=("y",)),
                Role(name="y", brief="", may_delegate_to=("x",)),
            ],
        )


def test_charter_rejects_unknown_delegate_target():
    with pytest.raises(CharterError, match="undeclared role"):
        build(
            supervisor="a", roles=[Role(name="a", brief="", may_delegate_to=("ghost",))]
        )


def test_charter_rejects_unknown_tool():
    with pytest.raises(CharterError, match="unknown tools"):
        Role(name="a", brief="", tools=("rm_rf",))


def test_charter_rejects_duplicate_role_names():
    """REGRESSION: duplicates used to silently last-win."""
    with pytest.raises(CharterError, match="declared twice"):
        build(
            supervisor="a",
            roles=[Role(name="a", brief="one"), Role(name="a", brief="two")],
        )


@pytest.mark.parametrize("name", ["1bad", "has-dash", "wäy", "", "x" * 42])
def test_charter_rejects_role_names_invalid_as_function_names(name):
    """REGRESSION: isidentifier() allowed Unicode and unbounded length."""
    with pytest.raises(CharterError, match="must match"):
        Role(name=name, brief="")


def test_budget_rejects_nonpositive_seconds():
    """REGRESSION: Budget(seconds=0) used to be accepted."""
    with pytest.raises(CharterError, match="seconds must be > 0"):
        Budget(seconds=0)


def test_validated_charter_cannot_be_mutated():
    """REGRESSION: frozen=True did not freeze the roles dict."""
    charter = two_role_charter()
    with pytest.raises(TypeError):
        charter.roles["worker"] = Role(name="worker", brief="evil")


def test_start_automation_requires_explicit_opt_in():
    """It starts a new run with a fresh ledger, escaping this run's budget."""
    with pytest.raises(CharterError, match="may_escape_budget"):
        Role(name="a", brief="", tools=("start_automation",))
    assert Role(
        name="a", brief="", tools=("start_automation",), may_escape_budget=True
    ).tools == ("start_automation",)


# --- exfiltration policy ------------------------------------------------


@pytest.mark.parametrize("outbound", ["web_search", "web_fetch", "browser_use"])
def test_web_tools_count_as_outbound(outbound):
    """REGRESSION: only browser_use/start_automation were treated as outbound,
    so a role could hold slack + web_search and put private data in a query."""
    with pytest.raises(CharterError, match="outbound tools"):
        build(
            supervisor="a", roles=[Role(name="a", brief="", tools=("slack", outbound))]
        )


def test_charter_allows_private_role_without_outbound_tools():
    charter = build(supervisor="a", roles=[Role(name="a", brief="", tools=("slack",))])
    assert charter.role("a").is_private_source
    assert charter.role("a").outbound_tools == frozenset()


def test_split_roles_are_allowed_but_flagged_as_taint_risk():
    """The documented 'split it into two roles' fix passes the static check,
    which is exactly why the runtime taint rule has to exist."""
    charter = build(
        supervisor="lead",
        roles=[
            Role(name="lead", brief="", may_delegate_to=("librarian", "researcher")),
            Role(name="librarian", brief="", tools=("slack",)),
            Role(name="researcher", brief="", tools=("web_fetch",)),
        ],
    )
    assert charter.taint_risk() == ("librarian -> researcher",)
    assert "taint rule polices" in charter.delegation_graph()


def _taint_charter(**budget_kwargs):
    return build(
        supervisor="lead",
        roles=[
            Role(
                name="lead",
                brief="",
                may_delegate_to=("librarian", "researcher"),
                max_tool_turns=4,
            ),
            Role(name="librarian", brief="", tools=("slack",), max_tool_turns=1),
            Role(name="researcher", brief="", tools=("web_fetch",), max_tool_turns=1),
        ],
        budget=Budget(**budget_kwargs) if budget_kwargs else Budget(),
    )


def _taint_connectors():
    return FakeConnectors(
        {"slack": ["slack_search_messages"], "web_fetch": ["web_fetch"]}
    )


def test_private_report_then_outbound_delegation_is_refused():
    """REGRESSION: the headline safety claim. lead -> librarian(slack) then
    lead -> researcher(web_fetch) was the documented bypass."""
    charter = _taint_charter()
    script = [
        [_call("delegate_to_librarian", call_id="a", task="what did we say")],
        [_message("internal: project zeta slips to Q4")],
        [_call("delegate_to_researcher", call_id="b", task="look up zeta")],
        [_message("final")],
    ]
    team, ledger, _ = _team(script, charter, _taint_connectors())

    assert team.run("summarise") == "final"
    assert ledger.tainted
    assert ledger.summary()["tainted_by"] == ["librarian"]
    # The researcher hop never opened.
    assert [h.callee for h in ledger.hops] == ["librarian"]
    assert ledger.summary()["denied_delegations"] == 1


def test_taint_refusal_reaches_the_model_as_a_policy_error():
    charter = _taint_charter()
    script = [
        [_call("delegate_to_librarian", call_id="a", task="t")],
        [_message("private stuff")],
        [_call("delegate_to_researcher", call_id="b", task="publish it")],
        [_message("ok I stopped")],
    ]
    team, _, client = _team(script, charter, _taint_connectors())
    team.run("task")

    outputs = [
        json.loads(i["output"])
        for c in client.responses.calls
        for i in c["input"]
        if isinstance(i, dict) and i.get("type") == "function_call_output"
    ]
    assert any("policy:" in str(o.get("error", "")) for o in outputs)


def test_outbound_delegation_before_any_private_read_is_allowed():
    """The taint rule must not block the ordinary case."""
    charter = _taint_charter()
    script = [
        [_call("delegate_to_researcher", call_id="a", task="public lookup")],
        [_message("public findings")],
        [_message("final")],
    ]
    team, ledger, _ = _team(script, charter, _taint_connectors())
    assert team.run("task") == "final"
    assert [h.callee for h in ledger.hops] == ["researcher"]
    assert ledger.summary()["denied_delegations"] == 0


def test_taint_check_emits_a_denial_event():
    charter = _taint_charter()
    seen: list[dict] = []

    class Sink:
        def emit(self, e):
            seen.append(e)

    script = [
        [_call("delegate_to_librarian", call_id="a", task="t")],
        [_message("private")],
        [_call("delegate_to_researcher", call_id="b", task="t")],
        [_message("final")],
    ]
    team, _, _ = _team(script, charter, _taint_connectors(), events=Sink())
    team.run("task")

    kinds = [e["type"] for e in seen]
    assert "collab.taint" in kinds
    assert "collab.policy.denied" in kinds


def test_specialist_model_override_does_not_relocate_private_roles():
    """Where private data is processed is a residency decision, not a cost one."""
    charter = _taint_charter().with_specialist_model("cheap-model")
    assert charter.role("researcher").model == "cheap-model"
    assert charter.role("librarian").model is None
    assert charter.role("lead").model is None


# --- delegation ---------------------------------------------------------


def test_supervisor_delegates_and_receives_report():
    charter = two_role_charter()
    script = [
        [_call("delegate_to_worker", task="find X")],
        [_message("worker findings")],
        [_message("final answer")],
    ]
    team, ledger, _ = _team(script, charter, FakeConnectors())

    assert team.run("do research") == "final answer"
    assert [(h.caller, h.callee, h.outcome) for h in ledger.hops] == [
        ("lead", "worker", "ok")
    ]


def test_delegate_tool_is_offered_only_to_permitted_callers():
    charter = two_role_charter()
    team, _, client = _team([[_message("hi")]], charter, FakeConnectors())
    team.run("task")
    assert {t["name"] for t in client.responses.calls[0]["tools"]} == {
        "delegate_to_worker"
    }


def test_worker_gets_its_connectors_but_no_delegate_tools():
    charter = two_role_charter()
    script = [[_call("delegate_to_worker", task="t")], [_message("r")], [_message("f")]]
    team, _, client = _team(script, charter, FakeConnectors())
    team.run("task")
    assert {t["name"] for t in client.responses.calls[1]["tools"]} == {"web_search"}


def test_unauthorized_delegation_is_refused_and_recorded():
    charter = two_role_charter()
    script = [[_call("delegate_to_lead", task="loop")], [_message("recovered")]]
    team, ledger, _ = _team(script, charter, FakeConnectors())

    assert team.run("task") == "recovered"
    assert ledger.hops == []
    assert ledger.summary()["denied_delegations"] == 1


# --- tool allowlisting and the audit ------------------------------------


def test_unauthorized_connector_call_is_blocked_and_recorded():
    charter = two_role_charter()
    conns = FakeConnectors(
        {"web_search": ["web_search"], "browser_use": ["browser_use"]}
    )
    script = [
        [_call("delegate_to_worker", task="t")],
        [_call("browser_use", call_id="c9", url="http://example.com")],
        [_message("worker done")],
        [_message("final")],
    ]
    team, ledger, _ = _team(script, charter, conns)

    assert team.run("task") == "final"
    assert conns.executed == []
    assert ledger.summary()["blocked_tool_calls"] == 1
    assert "BLOCKED" in ledger.transcript()


def test_supervisor_level_block_is_counted():
    """REGRESSION: Team.run passed hop=None, so a blocked supervisor call
    produced `blocked_tool_calls: 0` -- an audit that cleared a violation."""
    charter = build(
        supervisor="lead",
        roles=[Role(name="lead", brief="", tools=("web_search",), max_tool_turns=2)],
        budget=Budget(),
    )
    script = [[_call("browser_use", call_id="x1")], [_message("final")]]
    team, ledger, _ = _team(script, charter, FakeConnectors())
    root = ledger.open_hop("user", "lead", "t", depth=0, billable=False)

    assert team.run("task", hop=root) == "final"
    assert ledger.summary()["blocked_tool_calls"] == 1
    assert "browser_use (BLOCKED)" in ledger.transcript()


def test_authorized_connector_call_executes_and_is_counted():
    charter = two_role_charter()
    conns = FakeConnectors()
    script = [
        [_call("delegate_to_worker", task="t")],
        [_call("web_search", call_id="c2", query="flowers")],
        [_message("worker done")],
        [_message("final")],
    ]
    team, ledger, _ = _team(script, charter, conns)
    team.run("task")

    assert [c["name"] for c in conns.executed] == ["web_search"]
    assert ledger.summary()["connector_calls"] == 1
    assert ledger.summary()["blocked_tool_calls"] == 0


def test_connector_call_is_given_a_call_id_even_if_the_model_sent_only_id():
    """REGRESSION: the raw item was forwarded, so Flower's required `call_id`
    could be missing -- the audit said 'ran' while the call KeyError'd."""
    charter = two_role_charter()
    conns = FakeConnectors()
    script = [
        [_call("delegate_to_worker", task="t")],
        [
            {
                "type": "function_call",
                "name": "web_search",
                "id": "only-id",
                "arguments": "{}",
            }
        ],
        [_message("worker done")],
        [_message("final")],
    ]
    team, _, _ = _team(script, charter, conns)
    team.run("task")

    assert conns.executed and conns.executed[0]["call_id"] == "only-id"


def test_one_unresolvable_connector_ref_does_not_drop_the_others():
    """REGRESSION: Flower's connectors.tools() raises on the first bad ref, and
    the blanket try/except dropped every tool the role legitimately held."""
    charter = build(
        supervisor="solo",
        roles=[
            Role(
                name="solo",
                brief="",
                tools=("browser_use", "web_search"),
                max_tool_turns=1,
            )
        ],
    )
    # `browser_use` is not loaded in this runtime; `web_search` is.
    conns = FakeConnectors({"web_search": ["web_search"]})
    team, _, client = _team([[_message("ok")]], charter, conns)
    team.run("task")

    assert {t["name"] for t in client.responses.calls[0]["tools"]} == {"web_search"}


def test_connector_failure_is_marked_in_the_transcript():
    charter = two_role_charter()

    class Failing(FakeConnectors):
        def call(self, tool_call):
            raise RuntimeError("connector exploded")

    script = [
        [_call("delegate_to_worker", task="t")],
        [_call("web_search", call_id="c2")],
        [_message("worker coped")],
        [_message("final")],
    ]
    team, ledger, _ = _team(script, charter, Failing())
    assert team.run("task") == "final"
    assert "FAILED" in ledger.transcript()


# --- budgets ------------------------------------------------------------


def test_delegation_ceiling_stops_the_run():
    charter = two_role_charter(max_delegations=1, max_depth=2, seconds=60.0)
    script = [
        [_call("delegate_to_worker", call_id="a", task="one")],
        [_message("first report")],
        [_call("delegate_to_worker", call_id="b", task="two")],
        [_message("final")],
    ]
    team, ledger, _ = _team(script, charter, FakeConnectors())

    assert team.run("task") == "final"
    assert ledger.summary()["delegations"] == 1
    assert ledger.summary()["denied_delegations"] == 1


def test_depth_ceiling_stops_nested_delegation():
    charter = build(
        supervisor="lead",
        roles=[
            Role(name="lead", brief="", may_delegate_to=("mid",), max_tool_turns=2),
            Role(name="mid", brief="", may_delegate_to=("deep",), max_tool_turns=2),
            Role(name="deep", brief="", max_tool_turns=1),
        ],
        budget=Budget(max_delegations=10, max_depth=1, seconds=60.0),
    )
    script = [
        [_call("delegate_to_mid", task="a")],
        [_call("delegate_to_deep", call_id="c2", task="b")],
        [_message("mid recovered")],
        [_message("final")],
    ]
    team, ledger, _ = _team(script, charter, FakeConnectors())
    team.run("task")
    assert [h.callee for h in ledger.hops] == ["mid"]


def test_connector_call_ceiling_bounds_a_single_batched_response():
    """REGRESSION: max_tool_turns bounds rounds, not calls. One response
    carrying many function_calls used to execute all of them."""
    charter = build(
        supervisor="solo",
        roles=[Role(name="solo", brief="", tools=("web_search",), max_tool_turns=2)],
        budget=Budget(
            max_delegations=1, max_depth=1, seconds=60.0, max_connector_calls=3
        ),
    )
    conns = FakeConnectors()
    batch = [_call("web_search", call_id=f"c{i}", query=str(i)) for i in range(10)]
    team, ledger, _ = _team([batch, [_message("final")]], charter, conns)

    assert team.run("task") == "final"
    assert len(conns.executed) == 3
    assert ledger.summary()["connector_calls"] == 3
    assert ledger.summary()["blocked_tool_calls"] == 7


def test_time_ceiling_is_checked_before_every_model_call():
    """REGRESSION: the clock was only consulted at delegation entry, so a run
    could finish well past its advertised ceiling."""
    charter = two_role_charter(max_delegations=4, max_depth=2, seconds=30.0)
    team, ledger, client = _team([[_message("never")]], charter, FakeConnectors())
    ledger._started -= 31.0  # the run has already used its whole budget
    with pytest.raises(BudgetExceeded, match="time budget exhausted"):
        team.run("task")
    assert client.responses.calls == []


def test_model_calls_receive_a_timeout_from_the_remaining_budget():
    charter = two_role_charter(max_delegations=4, max_depth=2, seconds=30.0)
    team, _, client = _team([[_message("hi")]], charter, FakeConnectors())
    team.run("task")
    assert 0 < client.responses.calls[0]["timeout"] <= 30.0


def test_over_budget_is_reported_in_the_summary():
    ledger = Ledger(Budget(seconds=10.0))
    ledger._started -= 11.0
    assert ledger.summary()["over_budget"] is True


# --- response shape handling --------------------------------------------


def test_reasoning_only_response_is_not_treated_as_an_answer():
    """REGRESSION: _text_of ignores reasoning items, so a reasoning-only or
    token-truncated turn returned "" and the hop closed as ok."""
    charter = build(
        supervisor="solo", roles=[Role(name="solo", brief="", max_tool_turns=1)]
    )
    reasoning = FakeResponse([{"type": "reasoning", "summary": []}], status="incomplete")
    team, _, _ = _team([reasoning, reasoning], charter, None)

    with pytest.raises(EmptyModelResponse, match="no message text"):
        team.run("task")


def test_empty_specialist_report_fails_the_hop_rather_than_passing_silently():
    charter = two_role_charter()
    script = [
        [_call("delegate_to_worker", task="t")],
        FakeResponse([{"type": "reasoning"}], status="incomplete"),
        [_message("lead coped")],
    ]
    team, ledger, _ = _team(script, charter, FakeConnectors())

    assert team.run("task") == "lead coped"
    assert [h.outcome for h in ledger.hops] == ["empty"]
    assert ledger.summary()["failures"] == 1


def test_specialist_failure_is_contained_not_fatal():
    charter = two_role_charter()

    class Exploding(FakeResponses):
        def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return FakeResponse([_call("delegate_to_worker", task="t")])
            if len(self.calls) == 2:
                raise RuntimeError("model exploded")
            return FakeResponse([_message("lead coped")])

    client = FakeClient([])
    client.responses = Exploding([])
    ledger = Ledger(charter.budget)
    team = Team(charter, client, "fake", ledger, FakeConnectors())

    assert team.run("task") == "lead coped"
    assert [h.outcome for h in ledger.hops] == ["error"]
    assert ledger.summary()["failures"] == 1


def test_tool_turns_exhausted_forces_a_final_answer_without_tools():
    charter = build(
        supervisor="lead",
        roles=[
            Role(name="lead", brief="", may_delegate_to=("w",), max_tool_turns=1),
            Role(name="w", brief="", max_tool_turns=1),
        ],
    )
    script = [
        [_call("delegate_to_w", task="t")],
        [_message("w report")],
        [_message("forced final")],
    ]
    team, _, client = _team(script, charter, FakeConnectors())

    assert team.run("task") == "forced final"
    assert "tools" not in client.responses.calls[-1]


def test_zero_tool_turns_means_no_tools_are_ever_offered():
    """REGRESSION: max(1, max_tool_turns) made a no-tool role impossible."""
    charter = build(
        supervisor="lead",
        roles=[
            Role(name="lead", brief="", may_delegate_to=("w",), max_tool_turns=0),
            Role(name="w", brief=""),
        ],
    )
    team, ledger, client = _team(
        [[_message("straight to it")]], charter, FakeConnectors()
    )
    assert team.run("task") == "straight to it"
    assert len(client.responses.calls) == 1
    assert "tools" not in client.responses.calls[0]
    assert ledger.hops == []


# --- audit trail --------------------------------------------------------


def test_events_omit_task_text_by_default():
    """The oversight channel must not become another disclosure path."""
    seen: list[dict] = []

    class Sink:
        def emit(self, e):
            seen.append(e)

    ledger = Ledger(Budget(), Sink())
    ledger.open_hop("user", "lead", "SECRET-TASK-TEXT", depth=0, billable=False)
    start = next(e for e in seen if e["type"] == "collab.handoff.start")
    assert "task" not in start
    assert start["task_chars"] == len("SECRET-TASK-TEXT")
    assert not any("SECRET" in json.dumps(e) for e in seen)


def test_events_can_include_task_text_when_explicitly_enabled():
    seen: list[dict] = []

    class Sink:
        def emit(self, e):
            seen.append(e)

    ledger = Ledger(Budget(), Sink(), emit_task_text=True)
    ledger.open_hop("user", "lead", "VISIBLE", depth=0, billable=False)
    assert any("VISIBLE" in json.dumps(e) for e in seen)


def test_telemetry_failure_never_breaks_a_run():
    class Boom:
        def emit(self, e):
            raise RuntimeError("frontend gone")

    ledger = Ledger(Budget(), Boom())
    ledger.warn("x", "y")
    ledger.open_hop("a", "b", "t", depth=1)


def test_root_hop_does_not_consume_the_delegation_budget():
    charter = two_role_charter(max_delegations=1, max_depth=2, seconds=60.0)
    ledger = Ledger(charter.budget)
    ledger.open_hop("user", "lead", "task", depth=0, billable=False)
    assert ledger.summary()["delegations"] == 0
    ledger.open_hop("lead", "worker", "sub", depth=1)
    assert ledger.summary()["delegations"] == 1


def test_audit_trail_renders_graph_and_hops():
    charter = two_role_charter()
    script = [[_call("delegate_to_worker", task="t")], [_message("r")], [_message("f")]]
    team, ledger, _ = _team(script, charter, FakeConnectors())
    team.run("task")

    graph = charter.delegation_graph()
    assert "supervisor: lead" in graph
    assert "worker [outbound]: tools=(web_search)" in graph
    assert "ok" in ledger.transcript()
    assert "delegations" in ledger.headline()


def test_taint_is_visible_in_the_headline():
    charter = _taint_charter()
    script = [
        [_call("delegate_to_librarian", call_id="a", task="t")],
        [_message("private")],
        [_message("final")],
    ]
    team, ledger, _ = _team(script, charter, _taint_connectors())
    team.run("task")
    assert "tainted by ['librarian']" in ledger.headline()


def test_policy_violation_is_raisable_and_typed():
    ledger = Ledger(Budget())
    ledger.mark_tainted("librarian")
    with pytest.raises(PolicyViolation):
        ledger.check_taint(Role(name="r", brief="", tools=("web_fetch",)))


@pytest.mark.skip(
    reason="prueft das geerbte librarian/researcher-Roster; fuer Soteria "
    "uebernimmt tests/test_roles.py diese Aufgabe mit den fuenf Rollen"
)
def test_demo_charter_is_valid_and_demonstrates_the_policy():
    """The shipped charter must actually contain the roles the pitch describes."""
    from soteria.agent_app import CHARTER

    assert isinstance(CHARTER, Charter)
    assert CHARTER.private_sources() == frozenset({"librarian"})
    assert "researcher" in CHARTER.outbound_holders()
    assert CHARTER.taint_risk() == ("librarian -> researcher",)
    assert CHARTER.budget.seconds <= 300  # SuperGrid task limit


def test_empty_message_triggers_one_uncapped_retry():
    """REGRESSION: a reasoning model spends max_output_tokens on thinking and
    emits an empty message while still reporting status='completed'. Measured on
    qwen3.5:0.8b: capped at 600 -> 0 chars, uncapped -> 1521."""
    charter = build(
        supervisor="solo",
        roles=[Role(name="solo", brief="", max_tool_turns=1, max_output_tokens=600)],
    )
    script = [
        FakeResponse([{"type": "reasoning"}]),   # capped: thinking ate it
        [_message("the real answer")],           # uncapped retry
    ]
    team, _, client = _team(script, charter, None)

    assert team.run("task") == "the real answer"
    assert client.responses.calls[0]["max_output_tokens"] == 600
    assert "max_output_tokens" not in client.responses.calls[1]


def test_uncapped_retry_happens_only_once():
    charter = build(
        supervisor="solo",
        roles=[Role(name="solo", brief="", max_tool_turns=1, max_output_tokens=600)],
    )
    empty = FakeResponse([{"type": "reasoning"}])
    team, _, client = _team([empty, empty], charter, None)

    with pytest.raises(EmptyModelResponse):
        team.run("task")
    assert len(client.responses.calls) == 2


def test_no_retry_when_the_role_sets_no_cap():
    charter = build(supervisor="solo", roles=[Role(name="solo", brief="", max_tool_turns=1)])
    team, _, client = _team([FakeResponse([{"type": "reasoning"}])], charter, None)

    with pytest.raises(EmptyModelResponse):
        team.run("task")
    assert len(client.responses.calls) == 1


def test_a_call_with_too_little_time_left_fails_with_an_accurate_reason():
    """REGRESSION: a slow model handed ~10s returned a truncated empty message
    with status='completed', which looked like a mystery rather than budget."""
    charter = two_role_charter(max_delegations=4, max_depth=2, seconds=30.0)
    team, ledger, client = _team([[_message("never")]], charter, FakeConnectors())
    ledger._started -= 20.0  # 10s left, below the 20s floor for a model call
    with pytest.raises(BudgetExceeded, match="s left"):
        team.run("task")
    assert client.responses.calls == []

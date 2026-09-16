"""The collaboration charter: who may talk to whom, with which tools, on what budget.

Flower 1.35 gives an AgentApp a model, connectors, events and run state. It does
not give it a way to call another agent. This module is the missing piece: a
declarative description of an agent team that can be checked *before* any model
runs, so the delegation graph is data rather than prompt text.

## What this layer does and does not guarantee

It **does** guarantee, in Python rather than in a prompt:

- a role can only delegate to the targets it declares;
- a role is only ever offered the connectors it declares;
- the delegation graph is acyclic, so the bill is bounded;
- no single role both reads private data and holds an outbound tool.

It **does not** claim to track secrets through free text. A supervisor is a
model, and "pass only what is required" is a request, not a control. The
run-level taint rule in `ledger.py` is the enforceable part: once a private
report enters a run, delegation to any role holding an outbound tool is refused.
That is deliberately coarse. It is sound precisely because it never inspects
strings.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

# Every built-in Flower connector can carry bytes off the box: `browser_use` and
# `start_automation` obviously, but a `web_search` query string and a `web_fetch`
# URL are exfiltration channels too. Treating only the first two as "outbound"
# was the original hole here.
OUTBOUND_CONNECTORS = frozenset(
    {"web_search", "web_fetch", "browser_use", "start_automation"}
)

# Connectors that reach a user's private account data.
ACCOUNT_CONNECTORS = frozenset({"attio", "github", "notion", "slack"})

BUILTIN_CONNECTORS = OUTBOUND_CONNECTORS
KNOWN_CONNECTORS = BUILTIN_CONNECTORS | ACCOUNT_CONNECTORS

# `start_automation` schedules a *new* run with a fresh ledger, so it escapes
# this run's budget entirely. A role may hold it only by opting in explicitly.
BUDGET_ESCAPING_CONNECTORS = frozenset({"start_automation"})

# A delegate tool is named `delegate_to_<role>`. The Responses API constrains
# function names to [A-Za-z0-9_-]{1,64}, so cap the role name well inside that.
# `str.isidentifier()` accepted Unicode and unbounded length and would have
# produced a schema the API rejects at call time.
ROLE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")


class CharterError(ValueError):
    """Raised when a team description is internally inconsistent."""


@dataclass(frozen=True)
class Role:
    """One specialist in the team.

    `tools` is a least-privilege allowlist of connector *references*. Note the
    granularity honestly: an account reference such as `github` expands to every
    tool that connector exposes (`github_search_code`, `github_get_file_content`
    ...). Flower has no per-action grant, so least privilege here is
    per-provider, not per-action.
    """

    name: str
    brief: str
    tools: tuple[str, ...] = ()
    may_delegate_to: tuple[str, ...] = ()
    sees_private_data: bool = False
    max_tool_turns: int = 2
    # Optional per-role overrides. `model` lets cheap specialists run on a small
    # model while the supervisor keeps a strong one; `max_output_tokens` keeps a
    # rambling specialist from eating the run's time budget.
    model: str | None = None
    max_output_tokens: int | None = None
    # Opt-in for `start_automation`, which can outlive and out-spend this run.
    may_escape_budget: bool = False

    def __post_init__(self) -> None:
        if not ROLE_NAME_RE.match(self.name):
            raise CharterError(
                f"Role name {self.name!r} must match {ROLE_NAME_RE.pattern} "
                "so that delegate_to_<role> is a valid function name"
            )
        unknown = set(self.tools) - KNOWN_CONNECTORS
        if unknown:
            raise CharterError(
                f"Role {self.name!r} requests unknown tools: {sorted(unknown)}"
            )
        if len(set(self.tools)) != len(self.tools):
            raise CharterError(f"Role {self.name!r} lists a tool twice")
        if len(set(self.may_delegate_to)) != len(self.may_delegate_to):
            raise CharterError(f"Role {self.name!r} lists a delegate twice")
        if self.max_tool_turns < 0:
            raise CharterError(f"Role {self.name!r} max_tool_turns must be >= 0")
        if self.max_output_tokens is not None and self.max_output_tokens < 1:
            raise CharterError(f"Role {self.name!r} max_output_tokens must be >= 1")
        escaping = set(self.tools) & BUDGET_ESCAPING_CONNECTORS
        if escaping and not self.may_escape_budget:
            raise CharterError(
                f"Role {self.name!r} holds {sorted(escaping)}, which starts a new "
                "run with a fresh budget; set may_escape_budget=True to accept that"
            )

    @property
    def is_private_source(self) -> bool:
        """Whether this role can produce text derived from private account data."""
        return self.sees_private_data or bool(set(self.tools) & ACCOUNT_CONNECTORS)

    @property
    def outbound_tools(self) -> frozenset[str]:
        """The subset of this role's tools that can carry bytes off the box."""
        return frozenset(set(self.tools) & OUTBOUND_CONNECTORS)


@dataclass(frozen=True)
class Budget:
    """Hard ceilings enforced in code, not asked of the model."""

    max_delegations: int = 6
    max_depth: int = 2
    # SuperGrid caps a single task at 5 minutes, so a ceiling much above that
    # cannot actually be reached there -- the platform kills the run first.
    seconds: float = 240.0
    # `max_tool_turns` bounds response *rounds*, not calls: one response may
    # carry many function_calls and the dispatch loop runs all of them. This is
    # the ceiling on connector executions for the whole run.
    max_connector_calls: int = 24

    def __post_init__(self) -> None:
        if self.max_delegations < 1 or self.max_depth < 1:
            raise CharterError("Budget ceilings must be >= 1")
        if self.max_connector_calls < 0:
            raise CharterError("max_connector_calls must be >= 0")
        if not self.seconds > 0:
            raise CharterError("Budget.seconds must be > 0")


@dataclass(frozen=True)
class Charter:
    """A complete, validated description of a collaborating agent team."""

    supervisor: str
    roles: Mapping[str, Role]
    budget: Budget = field(default_factory=Budget)

    def __post_init__(self) -> None:
        if self.supervisor not in self.roles:
            raise CharterError(f"Supervisor {self.supervisor!r} is not a declared role")
        for name, role in self.roles.items():
            if name != role.name:
                raise CharterError(f"Role keyed {name!r} is named {role.name!r}")
            for target in role.may_delegate_to:
                if target not in self.roles:
                    raise CharterError(
                        f"Role {role.name!r} delegates to undeclared role {target!r}"
                    )
                if target == role.name:
                    raise CharterError(f"Role {role.name!r} delegates to itself")
        self._reject_cycles()
        self._reject_exfiltration()
        # Freeze the mapping so a validated charter cannot be edited afterwards.
        # `frozen=True` only stops attribute rebinding, not dict mutation.
        if not isinstance(self.roles, MappingProxyType):
            object.__setattr__(self, "roles", MappingProxyType(dict(self.roles)))

    def _reject_cycles(self) -> None:
        """A cycle in the delegation graph is an unbounded bill. Refuse it.

        Walks from every role, not just the supervisor: an unreachable cycle is
        still a latent one the moment someone changes the supervisor.
        """
        visiting: set[str] = set()
        done: set[str] = set()

        def walk(name: str, trail: tuple[str, ...]) -> None:
            if name in visiting:
                loop = " -> ".join(trail + (name,))
                raise CharterError(f"Delegation cycle: {loop}")
            if name in done:
                return
            visiting.add(name)
            for target in self.roles[name].may_delegate_to:
                walk(target, trail + (name,))
            visiting.discard(name)
            done.add(name)

        for name in self.roles:
            walk(name, ())

    def _reject_exfiltration(self) -> None:
        """A role holding private data must not also hold an outbound channel.

        This is the *static* half of the rule and it only sees one role at a
        time. The composition `lead(web_fetch) -> librarian(slack)` passes here
        and is caught at runtime by the ledger's taint rule instead.
        """
        for role in self.roles.values():
            if role.is_private_source and role.outbound_tools:
                raise CharterError(
                    f"Role {role.name!r} both reads private data and holds "
                    f"outbound tools {sorted(role.outbound_tools)}; "
                    "split it into two roles"
                )

    def private_sources(self) -> frozenset[str]:
        return frozenset(n for n, r in self.roles.items() if r.is_private_source)

    def outbound_holders(self) -> frozenset[str]:
        return frozenset(n for n, r in self.roles.items() if r.outbound_tools)

    def taint_risk(self) -> tuple[str, ...]:
        """Role pairs where a private report could reach an outbound tool.

        Not an error -- this is the shape most useful teams have. It is what the
        runtime taint rule exists to police, and worth printing so a reviewer can
        see the policy is load-bearing rather than decorative.
        """
        private, outbound = self.private_sources(), self.outbound_holders()
        return tuple(sorted(f"{p} -> {o}" for p in private for o in outbound))

    def with_specialist_model(self, model: str | None) -> Charter:
        """Return a copy where every non-supervisor role runs on `model`.

        Lets the same charter run a big supervisor against a hosted model while
        the specialists run somewhere cheap and small. Roles that already pin
        their own model keep it.

        Private-data roles are deliberately *not* moved. Where private data gets
        processed is a data-residency decision, not a cost one, so a blanket
        "put the specialists on the cheap endpoint" must never silently relocate
        it. Such a role keeps the operator-chosen primary model unless its own
        `Role(model=...)` pins it somewhere on purpose.
        """
        if not model:
            return self
        roles = {
            name: (
                role
                if (
                    name == self.supervisor
                    or role.model is not None
                    or role.is_private_source
                )
                else replace(role, model=model)
            )
            for name, role in self.roles.items()
        }
        return Charter(supervisor=self.supervisor, roles=roles, budget=self.budget)

    def role(self, name: str) -> Role:
        try:
            return self.roles[name]
        except KeyError:
            raise CharterError(f"Unknown role {name!r}") from None

    def delegation_graph(self) -> str:
        """Render the graph for the demo slide and the audit header."""
        lines = [f"supervisor: {self.supervisor}"]
        for name in sorted(self.roles):
            role = self.roles[name]
            targets = ", ".join(role.may_delegate_to) or "-"
            tools = ", ".join(role.tools) or "none"
            marks = []
            if role.is_private_source:
                marks.append("private")
            if role.outbound_tools:
                marks.append("outbound")
            flag = f" [{'+'.join(marks)}]" if marks else ""
            lines.append(f"  {name}{flag}: tools=({tools}) -> ({targets})")
        risk = self.taint_risk()
        if risk:
            lines.append(f"  taint rule polices: {', '.join(risk)}")
        return "\n".join(lines)


def build(supervisor: str, roles: list[Role], budget: Budget | None = None) -> Charter:
    """Construct a validated Charter from a list of roles."""
    seen: dict[str, Role] = {}
    for role in roles:
        if role.name in seen:
            raise CharterError(f"Role {role.name!r} is declared twice")
        seen[role.name] = role
    return Charter(supervisor=supervisor, roles=seen, budget=budget or Budget())

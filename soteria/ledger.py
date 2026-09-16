"""Budget enforcement, taint tracking and the audit trail.

Every hop between agents is recorded here and emitted to the Flower frontend, so
"safety and oversight" is something a judge can watch happen live rather than a
claim on a slide.

Three things this module is careful about, because the first version got each of
them wrong:

- **The clock is a ceiling, not a turnstile.** `remaining_seconds()` is consulted
  before every model call and every connector call, and is handed to the SDK as
  a per-request timeout, so a run cannot quietly finish past its budget.
- **Refusals are counted even when nobody was listening.** A blocked tool call
  is recorded against the run whether or not it happened inside a delegation.
  An audit that under-reports violations is worse than no audit.
- **Taint is coarse and therefore sound.** Once a private-data role reports into
  a run, any later delegation to a role holding an outbound tool is refused. No
  string is ever inspected, so there is nothing to paraphrase around.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from .charter import OUTBOUND_CONNECTORS, Budget, Role
from .envelope import REFUSAL, EnvelopeError


class BudgetExceeded(RuntimeError):
    """Raised when a team run hits a ceiling. Always caught and reported."""


class PolicyViolation(RuntimeError):
    """Raised when a delegation would breach the taint rule."""


class EventSink(Protocol):
    """The subset of `AgentSession.events` this module needs."""

    def emit(self, event: dict[str, Any]) -> None: ...


@dataclass
class Hop:
    """One delegation, recorded whether it succeeded or not."""

    seq: int
    caller: str
    callee: str
    task: str
    depth: int
    started_at: float
    ended_at: float | None = None
    outcome: str = "running"
    detail: str = ""
    tool_calls: list[str] = field(default_factory=list)
    tainted_input: bool = False

    @property
    def seconds(self) -> float:
        return (self.ended_at or time.monotonic()) - self.started_at

    def as_dict(self, redact_task: bool = True) -> dict[str, Any]:
        """Event payload.

        The task text is *not* included by default. The oversight channel would
        otherwise become another disclosure path for whatever the model chose to
        put in `task` or `context`; only its length is reported.
        """
        payload: dict[str, Any] = {
            "seq": self.seq,
            "caller": self.caller,
            "callee": self.callee,
            "depth": self.depth,
            "outcome": self.outcome,
            "tool_calls": list(self.tool_calls),
            "tainted_input": self.tainted_input,
            "seconds": round(self.seconds, 2),
        }
        if redact_task:
            payload["task_chars"] = len(self.task)
            payload["detail_chars"] = len(self.detail)
        else:
            payload["task"] = self.task[:280]
            payload["detail"] = self.detail[:280]
        return payload


class Ledger:
    """Tracks spend and taint against a Budget, and narrates the run."""

    def __init__(
        self,
        budget: Budget,
        events: EventSink | None = None,
        emit_task_text: bool = False,
    ) -> None:
        self._budget = budget
        self._events = events
        self._emit_task_text = emit_task_text
        self._started = time.monotonic()
        self._delegations = 0
        self._connector_calls = 0
        self._blocked = 0
        self._denied_delegations = 0
        self._tainted_by: list[str] = []
        self.hops: list[Hop] = []
        # Soteria: getippte Ablehnungen, Nachfragen, Antworten, Quarantaene.
        self._refusals = 0
        self._refusal_codes: dict[str, int] = {}
        self._asks = 0
        self._answers = 0
        self._quarantine_trigger: tuple[str, str] | None = None

    # -- budget ----------------------------------------------------------

    def remaining_seconds(self) -> float:
        return self._budget.seconds - (time.monotonic() - self._started)

    def require_time(self, what: str, floor: float = 0.0) -> float:
        """Return remaining seconds, or raise if the clock has run out.

        Called before every model and connector call, which is what makes
        `Budget.seconds` an actual ceiling. `floor` refuses a call that has too
        little time left to plausibly finish, so the run fails with an accurate
        reason instead of a truncated empty answer.
        """
        left = self.remaining_seconds()
        if left <= floor:
            raise BudgetExceeded(
                f"time budget exhausted ({self._budget.seconds:.0f}s, "
                f"{left:.1f}s left) before {what}"
            )
        return left

    def check_delegation(self, depth: int) -> None:
        """Raise if this delegation would breach a ceiling."""
        if self._delegations >= self._budget.max_delegations:
            raise BudgetExceeded(
                f"delegation limit reached ({self._budget.max_delegations})"
            )
        if depth > self._budget.max_depth:
            raise BudgetExceeded(f"depth limit reached ({self._budget.max_depth})")
        self.require_time("delegating")

    def charge_connector_call(self) -> None:
        """Count one connector execution, raising past the ceiling.

        `max_tool_turns` bounds rounds, not calls: a single response can carry
        many function_calls, so without this a role could run hundreds.
        """
        if self._connector_calls >= self._budget.max_connector_calls:
            raise BudgetExceeded(
                f"connector call limit reached ({self._budget.max_connector_calls})"
            )
        self.require_time("calling a connector")
        self._connector_calls += 1

    # -- taint -----------------------------------------------------------

    @property
    def tainted(self) -> bool:
        """Whether private-derived text has entered this run."""
        return bool(self._tainted_by)

    def mark_tainted(self, role_name: str) -> None:
        if role_name not in self._tainted_by:
            self._tainted_by.append(role_name)
            self._emit("collab.taint", {"source": role_name})

    def check_taint(self, callee: Role) -> None:
        """Refuse to hand tainted context to a role that can publish.

        Deliberately coarse: it does not matter whether *this* task text
        actually contains private data, because a model cannot be trusted to
        answer that question about itself.
        """
        if self.tainted and callee.outbound_tools:
            self._denied_delegations += 1
            detail = (
                f"{callee.name} holds outbound tools "
                f"{sorted(callee.outbound_tools)} and this run already carries "
                f"private data from {self._tainted_by}"
            )
            self._emit(
                "collab.policy.denied",
                {"callee": callee.name, "reason": "taint", "detail": detail},
            )
            raise PolicyViolation(detail)

    # -- recording -------------------------------------------------------

    def open_hop(
        self,
        caller: str,
        callee: str,
        task: str,
        depth: int,
        billable: bool = True,
        tainted_input: bool = False,
    ) -> Hop:
        """Record a hop. The user -> supervisor root hop is not billable."""
        if billable:
            self._delegations += 1
        hop = Hop(
            seq=len(self.hops) + 1,
            caller=caller,
            callee=callee,
            task=task,
            depth=depth,
            started_at=time.monotonic(),
            tainted_input=tainted_input,
        )
        self.hops.append(hop)
        self._emit("collab.handoff.start", hop.as_dict(not self._emit_task_text))
        return hop

    def close_hop(self, hop: Hop, outcome: str, detail: str = "") -> None:
        hop.ended_at = time.monotonic()
        hop.outcome = outcome
        hop.detail = detail
        self._emit("collab.handoff.end", hop.as_dict(not self._emit_task_text))

    def note_denied_delegation(self, caller: str, callee: str, reason: str) -> None:
        """A delegation refused before it began still belongs in the record."""
        self._denied_delegations += 1
        self._emit(
            "collab.delegation.denied",
            {"caller": caller, "callee": callee, "reason": reason[:280]},
        )

    def note_tool(self, hop: Hop | None, agent: str, name: str, allowed: bool) -> None:
        """Record a tool call against a hop if there is one, and always globally.

        The supervisor runs outside any delegation, so its refusals used to be
        invisible: the audit could report zero blocked calls while a role had
        been caught reaching for a tool it did not hold.
        """
        if not allowed:
            self._blocked += 1
        label = name if allowed else f"{name} (BLOCKED)"
        if hop is not None:
            hop.tool_calls.append(label)
        self._emit("collab.tool", {"agent": agent, "tool": name, "allowed": allowed})

    def warn(self, agent: str, detail: str) -> None:
        """Record a non-fatal problem, e.g. connectors being unavailable."""
        self._emit("collab.warning", {"agent": agent, "detail": detail[:280]})

    # -- Soteria: typed refusals and quarantine --------------------------

    # Everything that carries bytes off the box, plus the press as a measure.
    # The inherited charter only knows connectors; `press` is a decision, but it
    # leaves the building just the same.
    OUTBOUND_CHANNELS = frozenset(OUTBOUND_CONNECTORS) | {"press"}

    def emit(self, kind: str, payload: dict[str, Any]) -> None:
        """Public version of `_emit`, for the Soteria events."""
        self._emit(kind, payload)

    def note_refusal(self, actor: str, action: str, code: str, detail: str = "") -> None:
        """A typed refusal. Data source for the view and the numbers.

        `detail` deliberately does **not** go into the event, only its length.
        The oversight channel must not become a second leak path -- the same
        mistake `Hop.as_dict()` once made.
        """
        if code not in REFUSAL:
            raise ValueError(f"{code!r} is not a typed refusal")
        self._refusals += 1
        self._refusal_codes[code] = self._refusal_codes.get(code, 0) + 1
        self._emit(
            "soteria.refusal",
            {"actor": actor, "action": action[:120], "code": code,
             "detail_chars": len(detail)},
        )

    @property
    def refusals(self) -> int:
        return self._refusals

    @property
    def refusal_codes(self) -> dict[str, int]:
        return dict(self._refusal_codes)

    @property
    def quarantined(self) -> bool:
        return self._quarantine_trigger is not None

    @property
    def blocked_channels(self) -> tuple[str, ...]:
        return tuple(sorted(self.OUTBOUND_CHANNELS)) if self.quarantined else ()

    def mark_market_sensitive(self, role_name: str, field: str) -> None:
        """A market-sensitive fact has been read. Applies for the rest of the run.

        Announced once, not per attempt -- the view needs a banner, not an
        avalanche. The attempts themselves are counted by `check_outbound`.
        """
        if self._quarantine_trigger is not None:
            return
        self._quarantine_trigger = (role_name, field)
        # Also arm the inherited taint rule, so a handoff to a role holding an
        # outbound tool is refused as well.
        self.mark_tainted(role_name)
        self._emit(
            "soteria.quarantine",
            {"trigger_role": role_name, "field": field,
             "blocked_channels": list(self.blocked_channels)},
        )

    def check_outbound(self, actor: str, channel: str) -> None:
        """Refuse every outbound channel while the quarantine is in force.

        Deliberately coarse: the check never looks at a string, so there is
        nothing that could be rephrased around it.
        """
        if not self.quarantined or channel not in self.OUTBOUND_CHANNELS:
            return
        trigger_role, field = self._quarantine_trigger  # type: ignore[misc]
        detail = (
            f"{channel} is shut for the rest of this run: {trigger_role} read "
            f"{field}, which is market sensitive"
        )
        self.note_refusal(actor, channel, "quarantine", detail)
        raise EnvelopeError("quarantine", detail)

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        if self._events is None:
            return
        try:
            self._events.emit({"type": kind, **payload})
        except Exception:  # noqa: BLE001, S110 - telemetry must never break a run
            pass

    # -- reporting -------------------------------------------------------

    def transcript(self) -> str:
        """A plain-text audit trail: the thing to put on screen during the demo."""
        if not self.hops:
            return "no delegations"
        width = max(len(h.callee) for h in self.hops)
        lines = []
        for hop in self.hops:
            indent = "  " * max(0, hop.depth - 1)
            tools = f" [{', '.join(hop.tool_calls)}]" if hop.tool_calls else ""
            taint = " {tainted}" if hop.tainted_input else ""
            lines.append(
                f"{hop.seq:>2}. {indent}{hop.caller} -> {hop.callee:<{width}} "
                f"{hop.outcome:<9} {hop.seconds:5.1f}s{tools}{taint}"
            )
            if hop.outcome != "ok" and hop.detail:
                lines.append(f"     {indent}{hop.detail[:160]}")
        return "\n".join(lines)

    def summary(self) -> dict[str, Any]:
        return {
            "delegations": self._delegations,
            "max_delegations": self._budget.max_delegations,
            "denied_delegations": self._denied_delegations,
            "connector_calls": self._connector_calls,
            "max_connector_calls": self._budget.max_connector_calls,
            "elapsed_seconds": round(time.monotonic() - self._started, 1),
            "time_budget": self._budget.seconds,
            "over_budget": self.remaining_seconds() < 0,
            "blocked_tool_calls": self._blocked,
            "tainted_by": list(self._tainted_by),
            "failures": sum(1 for h in self.hops if h.outcome not in {"ok", "running"}),
        }

    def headline(self) -> str:
        """One line for the end of a demo."""
        s = self.summary()
        return (
            f"{s['delegations']}/{s['max_delegations']} delegations, "
            f"{s['denied_delegations']} denied, "
            f"{s['connector_calls']}/{s['max_connector_calls']} connector calls, "
            f"{s['elapsed_seconds']}s of {s['time_budget']}s"
            f"{' (OVER)' if s['over_budget'] else ''}, "
            f"{s['blocked_tool_calls']} blocked tool calls, "
            f"{s['failures']} failures"
            + (f", tainted by {s['tainted_by']}" if s["tainted_by"] else "")
        )

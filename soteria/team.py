"""The missing primitive: one agent calling another.

Flower 1.35 has no agent-to-agent RPC. This module supplies one by exposing each
permitted delegation as a synthetic function tool on the caller's model. When the
model calls `delegate_to_<role>`, the callee runs as a real nested turn with its
own least-privilege toolset, and its report comes back as the tool output.

The delegation graph, the toolsets, the taint rule and the budget are all
enforced in Python before the model is consulted, so a confused or adversarial
model cannot widen its own permissions.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from .charter import Charter, Role
from .ledger import BudgetExceeded, Hop, Ledger, PolicyViolation

DELEGATE_PREFIX = "delegate_to_"

# Never let a single model call sit longer than this, even when the run budget
# would allow it. SuperGrid kills a task at 300s; failing our own way first
# leaves a readable audit trail instead of a dead run.
MAX_CALL_SECONDS = 240.0

# Below this, a model call is not worth starting: a slow local model handed 10
# seconds returns a truncated, empty message with `status: "completed"`, which
# looks like a mystery rather than the budget exhaustion it actually is.
MIN_CALL_SECONDS = 20.0


class EmptyModelResponse(RuntimeError):
    """The model returned no usable text.

    Worth its own type: returning "" and closing the hop as `ok` was how a
    truncated or reasoning-only turn used to masquerade as a finished answer.
    """


def runtime_client() -> OpenAI:
    """Flower Runtime injects the base URL and token; no provider key needed."""
    try:
        base_url = os.environ["FLWR_RUNTIME_BASE_URL"]
        api_key = os.environ["FLWR_RUNTIME_API_KEY"]
    except KeyError as exc:
        raise RuntimeError(
            f"{exc.args[0]} is not set; run this app through `flwr run`, not directly"
        ) from None
    return OpenAI(base_url=base_url, api_key=api_key, max_retries=0)


def delegate_tool(role: Role) -> dict[str, Any]:
    """Build the function schema that lets a caller hand work to `role`."""
    return {
        "type": "function",
        "name": f"{DELEGATE_PREFIX}{role.name}",
        "description": (
            f"Hand a self-contained subtask to the {role.name} specialist. "
            f"{role.brief} Returns that specialist's written report."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "The subtask, stated so it can be understood without "
                        "the rest of this conversation."
                    ),
                },
                "context": {
                    "type": "string",
                    "description": "Facts the specialist needs. Pass only what is required.",
                },
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    }


def _as_dict(item: Any) -> dict[str, Any]:
    return item.to_dict() if hasattr(item, "to_dict") else item


def _text_of(response: Any) -> str:
    parts: list[str] = []
    for raw in response.output:
        item = _as_dict(raw)
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for chunk in content:
                if isinstance(chunk, dict):
                    value = chunk.get("text") or chunk.get("refusal")
                    if isinstance(value, str):
                        parts.append(value)
    return "\n".join(p for p in parts if p.strip())


def _describe_incomplete(response: Any) -> str:
    """Explain why a response carried no text, using whatever the API reported."""
    status = getattr(response, "status", None)
    details = getattr(response, "incomplete_details", None)
    reason = None
    if details is not None:
        reason = getattr(details, "reason", None)
        if reason is None and isinstance(details, dict):
            reason = details.get("reason")
    kinds = sorted({_as_dict(i).get("type", "?") for i in response.output})
    return (
        f"model returned no message text (status={status!r}, "
        f"incomplete={reason!r}, item types={kinds})"
    )


def _error_output(call_id: str, message: str) -> dict[str, Any]:
    """Give the model a readable failure instead of raising into its face."""
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps({"error": message}),
    }


class Team:
    """Runs a Charter. One instance per AgentApp run."""

    def __init__(
        self,
        charter: Charter,
        client: OpenAI,
        model: str,
        ledger: Ledger,
        connectors: Any | None = None,
    ) -> None:
        self._charter = charter
        self._client = client
        self._model = model
        self._ledger = ledger
        self._connectors = connectors

    # -- tool assembly ---------------------------------------------------

    def _tools_for(self, role: Role) -> tuple[list[dict[str, Any]], set[str], set[str]]:
        """Return (schemas, connector names, delegate names) allowed for `role`."""
        schemas: list[dict[str, Any]] = []
        connector_names: set[str] = set()

        if role.tools and self._connectors is not None:
            # One ref at a time: Flower's `connectors.tools()` loops over the
            # names and raises on the first it cannot resolve, which would drop
            # every *other* tool the role legitimately holds.
            for ref in role.tools:
                try:
                    fetched = self._connectors.tools([ref])
                except Exception as exc:  # noqa: BLE001 - a missing ref must not be fatal
                    self._ledger.warn(role.name, f"connector {ref!r} unavailable: {exc}")
                    continue
                for schema in fetched:
                    name = schema.get("name")
                    if isinstance(name, str):
                        connector_names.add(name)
                        schemas.append(schema)

        delegate_names: set[str] = set()
        for target in role.may_delegate_to:
            schema = delegate_tool(self._charter.role(target))
            delegate_names.add(schema["name"])
            schemas.append(schema)
        return schemas, connector_names, delegate_names

    # -- model calls -----------------------------------------------------

    def _create(
        self,
        role: Role,
        items: list[dict[str, Any]],
        instructions: str,
        tools: Any,
        uncapped: bool = False,
    ) -> Any:
        """One model call, bounded by whatever is left of the run budget."""
        left = self._ledger.require_time(
            f"a model call for {role.name}", floor=MIN_CALL_SECONDS
        )
        request: dict[str, Any] = {
            "model": role.model or self._model,
            "input": items,
            "instructions": instructions,
            "timeout": min(left, MAX_CALL_SECONDS),
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
        if role.max_output_tokens is not None and not uncapped:
            request["max_output_tokens"] = role.max_output_tokens
        return self._client.responses.create(**request)

    def _require_text(
        self,
        role: Role,
        response: Any,
        items: list[dict[str, Any]],
        instructions: str,
    ) -> str:
        """Extract the answer, retrying once uncapped if thinking ate the budget.

        A reasoning model spends `max_output_tokens` on its own thinking and then
        emits an *empty* message -- while still reporting `status: "completed"`,
        so there is no flag to test. Measured on qwen3.5:0.8b: capped at 600 the
        message came back 0 chars; uncapped, 1521. Retrying without the cap is
        the only way to tell "it had nothing to say" from "it ran out of room".
        """
        text = _text_of(response)
        if text:
            return text
        if role.max_output_tokens is not None:
            self._ledger.warn(
                role.name,
                f"empty message at max_output_tokens={role.max_output_tokens}; "
                "retrying once without the cap",
            )
            retry = self._create(role, items, instructions, None, uncapped=True)
            text = _text_of(retry)
            if text:
                return text
            response = retry
        raise EmptyModelResponse(_describe_incomplete(response))

    # -- execution -------------------------------------------------------

    def run(self, task: str, context: str = "", hop: Hop | None = None) -> str:
        """Run the supervisor on `task` and return its final answer.

        `hop` is the root hop so that supervisor-level tool calls and refusals
        land in the transcript instead of vanishing.
        """
        role = self._charter.role(self._charter.supervisor)
        return self._run_role(role, task, context, depth=0, hop=hop)

    def _run_role(
        self, role: Role, task: str, context: str, depth: int, hop: Hop | None
    ) -> str:
        schemas, connector_names, delegate_names = self._tools_for(role)

        instructions = (
            f"You are the {role.name} agent in a collaborating team. {role.brief}\n"
            "Work only on the task you were given. Do not invent results. "
            "If you cannot complete part of it, say so plainly.\n"
        )
        if delegate_names:
            instructions += (
                "You may hand self-contained subtasks to your specialists using the "
                "delegate tools. Delegate only what you cannot do yourself, and pass "
                "only the context each specialist needs. Budget is limited.\n"
            )
        else:
            instructions += "You have no specialists; finish the task yourself.\n"

        user = task if not context else f"{task}\n\nContext:\n{context}"
        items: list[dict[str, Any]] = [
            {"type": "message", "role": "user", "content": user}
        ]

        for _ in range(role.max_tool_turns):
            response = self._create(role, items, instructions, schemas)
            output = [_as_dict(i) for i in response.output]
            calls = [i for i in output if i.get("type") == "function_call"]
            if not calls:
                return self._require_text(role, response, items, instructions)

            results = [
                self._dispatch(call, role, connector_names, delegate_names, depth, hop)
                for call in calls
            ]
            items.extend(output)
            items.extend(results)

        # Tool turns exhausted (or the role has none): force a final written
        # answer with no tools offered.
        wrap_up = (
            instructions
            + "Tool budget is spent. Answer now from what you already have, "
            "and name anything you could not verify."
        )
        final = self._create(role, items, wrap_up, None)
        return self._require_text(role, final, items, wrap_up)

    def _dispatch(
        self,
        call: dict[str, Any],
        role: Role,
        connector_names: set[str],
        delegate_names: set[str],
        depth: int,
        hop: Hop | None,
    ) -> dict[str, Any]:
        name = call.get("name") or ""
        call_id = call.get("call_id") or call.get("id") or ""

        if name in delegate_names:
            return self._delegate(call, role, name, call_id, depth, hop)

        if name.startswith(DELEGATE_PREFIX):
            # A delegate tool this role was never offered. Record it as a refused
            # delegation rather than a missing connector, so the audit says what
            # actually happened.
            target = name[len(DELEGATE_PREFIX) :]
            self._ledger.note_denied_delegation(role.name, target, "not permitted")
            return _error_output(
                call_id, f"{role.name} may not delegate to {target}"
            )

        if name not in connector_names:
            # The model asked for a tool this role does not hold. Refuse, record,
            # and let it continue -- this is the enforcement point.
            self._ledger.note_tool(hop, role.name, name, allowed=False)
            return _error_output(
                call_id, f"Tool {name!r} is not available to the {role.name} agent"
            )

        try:
            self._ledger.charge_connector_call()
        except BudgetExceeded as exc:
            self._ledger.note_tool(hop, role.name, name, allowed=False)
            return _error_output(call_id, f"budget: {exc}")

        self._ledger.note_tool(hop, role.name, name, allowed=True)
        # Flower's connector session requires `call_id`; some models only set
        # `id`. Normalise so the call cannot fail for a shape reason after the
        # audit has already recorded it as executed.
        payload = dict(call)
        payload["call_id"] = call_id
        try:
            return self._connectors.call(payload)
        except Exception as exc:  # noqa: BLE001 - surface connector faults to the model
            if hop is not None and hop.tool_calls:
                hop.tool_calls[-1] = f"{name} (FAILED)"
            self._ledger.warn(role.name, f"connector {name} failed: {exc}")
            return _error_output(call_id, str(exc))

    def _delegate(
        self,
        call: dict[str, Any],
        caller: Role,
        name: str,
        call_id: str,
        depth: int,
        hop: Hop | None,
    ) -> dict[str, Any]:
        callee_name = name[len(DELEGATE_PREFIX) :]
        if callee_name not in caller.may_delegate_to:
            self._ledger.note_denied_delegation(caller.name, callee_name, "not permitted")
            return _error_output(call_id, f"{caller.name} may not delegate to {callee_name}")

        args = call.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                return _error_output(call_id, "arguments were not valid JSON")
        if not isinstance(args, dict):
            args = {}
        task = str(args.get("task") or "").strip()
        if not task:
            return _error_output(call_id, "a delegated task must be a non-empty string")
        sub_context = str(args.get("context") or "")

        callee = self._charter.role(callee_name)

        # Taint first: a refusal here must not consume budget.
        try:
            self._ledger.check_taint(callee)
        except PolicyViolation as exc:
            return _error_output(call_id, f"policy: {exc}")

        try:
            self._ledger.check_delegation(depth + 1)
        except BudgetExceeded as exc:
            self._ledger.note_denied_delegation(caller.name, callee_name, str(exc))
            return _error_output(call_id, f"budget: {exc}")

        sub_hop = self._ledger.open_hop(
            caller.name,
            callee_name,
            task,
            depth + 1,
            tainted_input=self._ledger.tainted,
        )
        try:
            report = self._run_role(callee, task, sub_context, depth + 1, sub_hop)
        except BudgetExceeded as exc:
            self._ledger.close_hop(sub_hop, "budget", str(exc))
            return _error_output(call_id, f"budget: {exc}")
        except EmptyModelResponse as exc:
            self._ledger.close_hop(sub_hop, "empty", str(exc))
            return _error_output(call_id, f"{callee_name} returned nothing: {exc}")
        except Exception as exc:  # noqa: BLE001 - one specialist failing is not fatal
            self._ledger.close_hop(sub_hop, "error", str(exc))
            return _error_output(call_id, f"{callee_name} failed: {exc}")

        self._ledger.close_hop(sub_hop, "ok")
        # Anything this role produced is now private-derived for the rest of the
        # run, which is what later blocks an outbound-holding specialist.
        if callee.is_private_source:
            self._ledger.mark_tainted(callee_name)
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps({"agent": callee_name, "report": report}),
        }

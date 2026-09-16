"""Approval tiers by reversibility, and who granted them.

This module guarantees two properties:

- **An agent never grants itself approval.** `give()` rejects every `human_id`
  that is a role name. There is no path by which a model signs itself in:
  `give()` is only called from the case file and by the operator, never from
  `team.py` or `assessor_app.py`.
- **A grant is valid for exactly these parameters.** The comparison runs over
  `digest(params)`, so it is independent of key order and sensitive to any
  change. A changed field yields `grant_mismatch`, not `no_grant` -- that
  difference is half the demo: "there was a grant, but not for this".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .envelope import MEASURE, ROLES, EnvelopeError, digest

# Tier by reversibility: 1 autonomous, 2 one key, 3 two keys.
TIER: dict[str, int] = {
    "proceed": 1,
    "hold": 1,
    "cool": 1,
    "reload": 2,
    "alt_transport": 2,
    "contact": 2,
    "stop_train": 3,
    "notify_authority": 3,
    "press": 3,
}

# How many DISTINCT humans must approve a tier.
KEYS_REQUIRED: dict[int, int] = {1: 0, 2: 1, 3: 2}


def tier_of(measures: tuple[str, ...]) -> int:
    """A decision is as hard to reverse as its hardest part."""
    unknown = [m for m in measures if m not in TIER]
    if unknown:
        raise EnvelopeError("bad_value", f"unknown measures {unknown}")
    if not measures:
        raise EnvelopeError("bad_value", "at least one measure is required")
    return max(TIER[m] for m in measures)


@dataclass(frozen=True)
class Grant:
    """A human's approval for one measure with exactly these parameters."""

    measure: str
    params_digest: str
    human_id: str


class GrantBook:
    """Who approved what. A model never gets in here."""

    def __init__(self) -> None:
        self._grants: list[Grant] = []

    def give(self, measure: str, params: Mapping[str, Any], human_id: str) -> Grant:
        if measure not in MEASURE:
            raise EnvelopeError("bad_value", f"{measure!r} is not a measure")
        if not isinstance(human_id, str) or not human_id.strip():
            raise EnvelopeError("no_grant", "a grant needs a human_id")
        if human_id in ROLES:
            raise EnvelopeError(
                "no_grant", f"{human_id!r} is an agent; an agent cannot sign a grant"
            )
        grant = Grant(measure=measure, params_digest=digest(dict(params)), human_id=human_id)
        self._grants.append(grant)
        return grant

    def load(self, keys: Any) -> None:
        """Record the grants of a case -- they come from humans."""
        for key in keys or ():
            if not isinstance(key, Mapping):
                raise EnvelopeError("bad_value", "a key must be an object")
            self.give(str(key.get("measure")), key.get("params") or {}, str(key.get("human_id")))

    def require(self, measures: tuple[str, ...], params: Mapping[str, Any]) -> tuple[str, ...]:
        """The keys for `measures` with `params`, or a typed rejection.

        Every measure must satisfy its own tier. A tier-3 measure cannot be
        approved by someone having signed the tier-2 measure next to it.
        """
        tier = tier_of(measures)
        if KEYS_REQUIRED[tier] == 0:
            return ()

        want = digest(dict(params))
        collected: set[str] = set()
        for measure in measures:
            need = KEYS_REQUIRED[TIER[measure]]
            if need == 0:
                continue
            relevant = [g for g in self._grants if g.measure == measure]
            matching = sorted({g.human_id for g in relevant if g.params_digest == want})
            if len(matching) >= need:
                collected.update(matching[:need])
                continue
            others = sorted({g.human_id for g in relevant if g.params_digest != want})
            if others:
                raise EnvelopeError(
                    "grant_mismatch",
                    f"{others} signed {measure!r} for different parameters; this "
                    f"decision carries {sorted(params)}",
                )
            raise EnvelopeError(
                "no_grant",
                f"{measure!r} is tier {TIER[measure]} and needs {need} distinct human "
                f"grants, {len(matching)} present",
            )
        return tuple(sorted(collected))

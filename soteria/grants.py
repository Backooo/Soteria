"""Freigabestufen nach Umkehrbarkeit, und wer sie erteilt hat.

Zwei Eigenschaften garantiert dieses Modul:

- **Ein Agent erteilt sich keine Freigabe.** `give()` weist jede `human_id`
  zurueck, die ein Rollenname ist. Es gibt keinen Pfad, auf dem ein Modell sich
  eintraegt: `give()` wird nur aus der Falldatei und von der Bedienung gerufen,
  nie aus `team.py` oder `assessor_app.py`.
- **Eine Freigabe gilt fuer genau diese Parameter.** Der Vergleich laeuft ueber
  `digest(params)`, also unabhaengig von der Schluesselreihenfolge und
  empfindlich fuer jede Aenderung. Ein geaendertes Feld ergibt `grant_mismatch`,
  nicht `no_grant` -- der Unterschied ist die halbe Demo: "es lag eine Freigabe
  vor, aber nicht fuer das hier".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .envelope import MEASURE, ROLES, EnvelopeError, digest

# Stufe nach Umkehrbarkeit: 1 autonom, 2 ein Schluessel, 3 zwei Schluessel.
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

# Wie viele VERSCHIEDENE Menschen eine Stufe freigeben muessen.
KEYS_REQUIRED: dict[int, int] = {1: 0, 2: 1, 3: 2}


def tier_of(measures: tuple[str, ...]) -> int:
    """Eine Entscheidung ist so schwer umkehrbar wie ihr schwerster Teil."""
    unknown = [m for m in measures if m not in TIER]
    if unknown:
        raise EnvelopeError("bad_value", f"unknown measures {unknown}")
    if not measures:
        raise EnvelopeError("bad_value", "at least one measure is required")
    return max(TIER[m] for m in measures)


@dataclass(frozen=True)
class Grant:
    """Die Freigabe eines Menschen fuer eine Maßnahme mit genau diesen Parametern."""

    measure: str
    params_digest: str
    human_id: str


class GrantBook:
    """Wer was freigegeben hat. Ein Modell kommt hier nicht hinein."""

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
        """Die Freigaben eines Falls eintragen -- sie stammen von Menschen."""
        for key in keys or ():
            if not isinstance(key, Mapping):
                raise EnvelopeError("bad_value", "a key must be an object")
            self.give(str(key.get("measure")), key.get("params") or {}, str(key.get("human_id")))

    def require(self, measures: tuple[str, ...], params: Mapping[str, Any]) -> tuple[str, ...]:
        """Die Schluessel fuer `measures` mit `params`, oder eine getippte Ablehnung.

        Jede Maßnahme muss ihre eigene Stufe erfuellen. Eine Stufe-3-Maßnahme
        laesst sich nicht dadurch freigeben, dass jemand die Stufe-2-Maßnahme
        daneben unterschrieben hat.
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

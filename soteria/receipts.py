"""Verkettete Quittungen. Jede haelt den Kopf der vorherigen.

Eine einzelne Quittung sagt "das ist passiert". Eine Kette sagt zusaetzlich "und
nichts davor wurde nachtraeglich geaendert", denn jeder Eintrag geht in den Hash
des naechsten ein. `verify()` rechnet sie nach; ein geaendertes Feld irgendwo in
der Mitte faellt auf.

Der Hash ist auf 16 Hex-Zeichen gekuerzt. Das ist keine Kryptografie fuer den
Ernstfall, sondern eine Pruefsumme, die auf eine Folie passt -- und das steht so
in der Ehrlichkeitstabelle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .envelope import digest

GENESIS = "0" * 16


@dataclass(frozen=True)
class Receipt:
    seq: int
    kind: str
    payload_digest: str
    prev: str
    hash: str


class ReceiptChain:
    def __init__(self) -> None:
        self._receipts: list[Receipt] = []

    @property
    def head(self) -> str:
        return self._receipts[-1].hash if self._receipts else GENESIS

    def __len__(self) -> int:
        return len(self._receipts)

    @staticmethod
    def _link(seq: int, kind: str, payload_digest: str, prev: str) -> str:
        return digest({"seq": seq, "kind": kind, "payload": payload_digest, "prev": prev})

    def append(self, kind: str, payload: Mapping[str, Any]) -> Receipt:
        seq = len(self._receipts) + 1
        payload_digest = digest(dict(payload))
        prev = self.head
        receipt = Receipt(
            seq=seq,
            kind=kind,
            payload_digest=payload_digest,
            prev=prev,
            hash=self._link(seq, kind, payload_digest, prev),
        )
        self._receipts.append(receipt)
        return receipt

    def verify(self) -> bool:
        prev = GENESIS
        for i, receipt in enumerate(self._receipts, start=1):
            if receipt.seq != i or receipt.prev != prev:
                return False
            if receipt.hash != self._link(
                receipt.seq, receipt.kind, receipt.payload_digest, prev
            ):
                return False
            prev = receipt.hash
        return True

    def as_list(self) -> list[dict[str, Any]]:
        return [
            {"seq_in_chain": r.seq, "kind": r.kind, "hash": r.hash, "prev": r.prev}
            for r in self._receipts
        ]

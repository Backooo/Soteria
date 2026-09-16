"""Chained receipts. Each one holds the head of the previous one.

A single receipt says "this happened". A chain also says "and nothing before it
was changed afterwards", because every entry goes into the hash of the next.
`verify()` recomputes them; a changed field anywhere in the middle shows up.

The hash is truncated to 16 hex characters. That is not cryptography for real
emergencies but a checksum that fits on a slide -- and the honesty table says
exactly that.
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

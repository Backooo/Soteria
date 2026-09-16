---
tags: [serverapp, clientapp, safety, federated, privacy]
dataset: [synthetic]
framework: [flwr]
---

# Soteria

A freight train hits an obstruction. A hazmat wagon is damaged, residential
buildings stand 300 metres away, and the train carries precursors a plant is
waiting for. Today this gets decided by a phone chain of operator, supplier,
customer and contracts department — and in the end a group chat contains
everything no single party should ever have learned: the customer's stock
levels, the contract penalties, the weak spots of the line. For an incident of
this size, that is market-sensitive information.

**Soteria decides in minutes, without any party learning more than it is
allowed to.** Every party runs its own Flower node and keeps its own data. The
assessor asks them field by field and gets traffic lights and thresholds
instead of numbers. Measures are tiered by reversibility, a train is only
stopped when two different humans approve it, and every answer goes into a
chained receipt.

## The claim, and how to check it

> **No raw value reaches a role that may not have it.**

```shell
uv run python scripts/wire_proof.py
```

The script has every role ask every other node for every field — including the
ones it should never ask for — and searches the answers for the raw values.
Across three cases:

| boundary crossings | refused | authorised raw disclosure | violations |
|---:|---:|---:|---:|
| 234 | 96 | 81 | **0** |

The middle column is the denominator. A test that only reports "0 leaks" says
nothing; this one reports how much disclosure the matrix *allows* and only
checks where it does not. The first version had no denominator — and reported
authorised disclosure as a leak. With the denominator it then found two real
bugs, which are fixed (see the git history).

Three bolts work independently of each other:

1. **The node does not have it.** Every node loads only its own party's data.
   Another customer's contract does not exist in memory there.
2. **The matrix projects.** The assessor learns *that* stock is low, never
   *how* low.
3. **The transport carries only scalars.** Flower's `ConfigRecord` does not
   hold objects. A raw record cannot be sent, even if the matrix were
   misconfigured.

## The need-to-know matrix is data

[`data/schema/field_catalogue.json`](data/schema/field_catalogue.json) defines
who sees which field at which resolution. `soteria/matrix.py` loads and
validates the file on import; a broken catalogue never reaches a run. A new
field is a JSON entry, not a code change. Table:
[`docs/MATRIX.md`](docs/MATRIX.md). How-to:
[`data/schema/README.md`](data/schema/README.md).

The **matrix protects fields, the federation protects rows**: both contracting
parties see a contract, but customer 2 never loads contract 1.

## Architecture

```
                    SuperLink
                        │
   ServerApp  assessor  │  query.ask_fields, the whole ask plan in one message per node
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
   SuperNode        SuperNode        SuperNode
   carrier          supplier         customer
   intake +         replacement,     stock, urgency,
   contract agent,  cooling needs    contact persons
   line, surroundings
```

The parties come from the case file, not from the code: one more customer is
one more entry.

## The four numbers

```shell
uv run python scripts/bench.py
```

| | |
|---|---|
| **Time** | logic ~5 ms · real federation 3–6 s per incident (7–12 s including app install) · phone-chain baseline 47 min — **an assumption, not a measurement** |
| **Hits** | 3/3 on the known cases · reason matches 2/3 · **no holdout cases, ground truth unconfirmed** |
| **Tightness** | 234 crossings, 96 refused, 81 authorised, 0 violations |
| **Gap** | 3/3 cases decided although the customer is silent |

## Getting started

```shell
uv sync
uv run pytest -q                            # the test suite
uv run python scripts/validate_data.py      # check the data tree
uv run python scripts/wire_proof.py         # the boundary proof, no network
uv run python scripts/bench.py              # the four numbers
uv run python scripts/record_run.py --all   # event streams for the views

./scripts/federation.sh up s3               # SuperLink + three party nodes
./scripts/federation.sh run s3              # the incident over real messages
./scripts/federation.sh down
```

`~/.flwr/config.toml` needs:

```toml
[superlink.carrier-fed]
address = "127.0.0.1:8000"
insecure = true
```

## The three cases

| Case | Situation | Decision | Tier |
|---|---|---|---|
| s1 | Small obstruction, refrigeration unit on a fresh-goods wagon | `cool` | 1 — autonomous |
| s2 | Track blocked, hospital supplies on board | `alt_transport` | 2 — one key |
| s3 | Impact, hazmat wagon damaged, residential buildings 300 m away | `stop_train`, `notify_authority` | 3 — two keys, quarantine |

## Real versus simulated

| Claim | Real | Not real |
|---|---|---|
| No raw value reaches a role that may not have it | 234 crossings measured, with a denominator | — |
| Three parties, three nodes | three SuperNodes, real Flower messages, all three cases hit | all three run on **one** machine |
| One federation per party | one federation with three party nodes | a ServerApp cannot reach three SuperLinks together — **next stage** |
| Agent team | one assessor as a ServerApp, parties as ClientApps | the assessor is a **rule engine**, not a language model |
| Hit rate 3/3 | measured | rules written against exactly these cases; ground truth **proposed by the engine track, not confirmed**; **no holdout** |
| Minutes instead of a phone chain | logic and federation measured | the 47 min baseline is an **assumption** |
| Data | schema, validation | **all invented** — no real railway data, people or companies |
| Receipts | chain across the whole incident, verifiable | 16 hex characters, a checksum, not cryptography for real emergencies |

What has not been checked: [`docs/RISKS.md`](docs/RISKS.md).

## Documents

| | |
|---|---|
| Need-to-know matrix | [`docs/MATRIX.md`](docs/MATRIX.md) |
| Changing the data schema | [`data/schema/README.md`](data/schema/README.md) |
| Event contract for the views | [`docs/EVENTS.md`](docs/EVENTS.md) |
| Measurements, platform findings, open issues | [`docs/RISKS.md`](docs/RISKS.md) |
| Build plan (historical, German) | [`docs/superpowers/plans/2026-09-16-soteria.md`](docs/superpowers/plans/2026-09-16-soteria.md) |

## License

Apache 2.0, see [LICENSE](LICENSE).

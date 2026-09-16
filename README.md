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
| **Time** | logic ~5 ms · real federation 3-6 s per incident · **with the model call 50-90 s** · phone-chain baseline 47 min - **an assumption, not a measurement** |
| **Hits** | s1 matches the stored answer; in s2 and s3 the model adds reversible measures on top · **no holdout cases, ground truth unconfirmed** |
| **Tightness** | 234 crossings, 96 refused, 81 authorised, 0 violations |
| **Gap** | 3/3 cases decided although the customer is silent |

## What it looks like

The operator dashboard. Three concurrent incidents, each one switchable; the
open card shows the decision the agents reached, who decided it and the receipt
hash. Map, fleet cards and the bottom metrics are mock — the decision block is
not.

![Operator dashboard with the decision for the hazmat incident](docs/images/dashboard.png)

The Agent Live Console, opened from the green button in the sidebar. It shows
the flow from the report through the three party nodes to the model, the
approvals and the receipt chain. **Run live** starts a real run on the local
federation and streams its events while they happen.

![Agent Live Console replaying the s3 incident](docs/images/agent-live-console.png)

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

The dashboard, the console and a live run:

```shell
uv run python scripts/bridge.py             # live bridge on 127.0.0.1:8765
cd "Soteria - Frontend" && npm install && npm run dev
```

Then open http://localhost:5173 for the dashboard, and the **Agent Live
Console** button in the incident sidebar for
http://localhost:5173/console.html. **Run live** there needs the bridge and a
valid `flwr login supergrid`, because the assessor calls the model on SuperGrid.
Without the bridge the console replays the recorded runs and says so.

Mapbox needs a token in `Soteria - Frontend/.env.local`:

```
VITE_MAPBOX_ACCESS_TOKEN=pk....
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

The tier and the keys are decided by code. The measures come from the model,
which in s2 and s3 adds a reversible measure (`cool`, `hold`) to the stored
answer above.

## Real versus simulated

| Claim | Real | Not real |
|---|---|---|
| No raw value reaches a role that may not have it | 234 crossings measured, with a denominator | — |
| Three parties, three nodes | three SuperNodes, real Flower messages, all three cases hit | all three run on **one** machine |
| One federation per party | one federation with three party nodes | a ServerApp cannot reach three SuperLinks together — **next stage** |
| Agent team | one assessor as a ServerApp, parties as ClientApps | — |
| The decision is made by an LLM | `flower-endeavor-v1.0` decides the measures, as a Flower AgentApp on SuperGrid, from projections only | the guardrails are code, not the model: unknown measures rejected, tier-3 safety floor from the rule policy, human keys and quarantine unchanged |
| Hit rate | s1 matches the stored answer; in s2 and s3 the model adds reversible measures (`cool`, `hold`) on top, so the benchmark counts them as a **mismatch** | rules and stored answers written against exactly these cases; ground truth **not confirmed**; **no holdout** |
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

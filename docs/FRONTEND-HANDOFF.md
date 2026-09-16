# Frontend integration — handoff for a new session

**As of 16 Sep 2026, 15:44, hackathon day.** Feature freeze 16:30, demo prep 17:15,
demos from 17:30.

This document is **a plan, not an implementation.** It contains everything a new session
needs to connect the Vite frontend to the Soteria backend sensibly. What is marked
**verified** here was backed by the source code or a run. What is marked **unverified**
must be checked by the new session first.

---

## 1 Task

Verbatim from the user (translated from German):

> The frontend is on GitHub, please analyse it and see how you can sensibly connect the
> backend to it. Do not change anything in the frontend without asking for permission
> first, and make sure you carry over the necessary functions. If something is missing,
> mock data from the frontend is fine too, it is a hack demo for presenting.

Translated into working rules:

| Rule | Concretely means |
|---|---|
| **Do not change the frontend without permission** | Also no `vite.config.*`, no `.env`, no `package.json`, no renaming. Every frontend change is proposed individually and signed off. |
| **Carry over functions** | Whatever the frontend needs and the backend does not deliver is added **in the backend** (new endpoint, new field, new event). |
| **Mock data is fine** | Where a real connection endangers the demo, the frontend's mocks stay. This is reported as simulated in the honesty table (`README.md`). |
| **Hack demo** | Robustness on stage beats completeness. A path that works without a network must always exist. |

---

## 2 Where the frontend is — still open

At the time of this document **the frontend was just being uploaded** and could not be found.
Searched (15:40, account `kaiser-data`):

- `Backooo/Soteria`: only `main` and `feat/soteria-engine`, no forks, no PRs
- all repos of the collaborators `Backooo`, `denizbekirDB2`, `saribx`, `kaiser-data`
- GitHub search for "soteria": only unrelated projects

**First step of the new session:** ask the user for the link if it is not in the first
message. If the repo is private, `kaiser-data` must be a collaborator.

```shell
gh api repos/Backooo/Soteria/branches --jq '.[].name'          # new branch?
gh repo list Backooo --limit 10 --json name,updatedAt           # new repo?
```

---

## 3 The backend in ten lines

Repo `Backooo/Soteria`, branch **`feat/soteria-engine`**, locally at
`/Users/marty/claude-projects/hackathon/collabarative_agent_hack/Soteria`. 163 tests green.

- **What it does:** A freight train is damaged. Three parties (operator, supplier, customer)
  each run a Flower SuperNode and keep their own data. An assessor (ServerApp) asks them
  field by field, gets traffic lights and thresholds instead of numbers, decides on a measure,
  obtains human approvals by reversibility and records everything in a receipt chain.
- **Runs for real:** three SuperNodes, real Flower messages, all three cases hit the stored
  decision, **3–6 s** per incident (7–12 s including app installation).
- **Boundary proof:** 234 attempted boundary crossings, 96 refused, 81 authorised, **0 violations**.
- **On Flower Hub:** uploaded as `kaiser-data/soteria`. The Hub version still contains an
  outdated file — see §10.

| Case | Situation | Decision | Tier |
|---|---|---|---|
| `s1` | Refrigeration unit on a fresh-goods wagon | `cool` | 1, autonomous |
| `s2` | Track blocked, hospital supplies | `alt_transport` | 2, one key |
| `s3` | Hazmat wagon damaged, residential buildings 300 m away | `stop_train`, `notify_authority` | 3, two keys, **quarantine** |

More detail: `README.md`, `docs/RISKS.md`, build plan `docs/superpowers/plans/2026-09-16-soteria.md`.

---

## 4 Verified platform facts that shape the integration

Flower **1.37.0** (pulled by `uv sync`, not 1.35). Paths relative to
`.venv/lib/python3.12/site-packages/flwr/`.

| # | Finding | Evidence | Consequence for the frontend |
|---|---|---|---|
| F1 | The SuperLink's Control API runs over **HTTP on port 8000** | `flower-superlink` log: *"Starting the SuperLink Control HTTP API on 127.0.0.1:8000"* | not 9093, as older notes say |
| F2 | The Control API requires **`Content-Type: application/protobuf`** — binary, not JSON | `supercore/protobuf/translation.py:235-241`, `supercore/protobuf/constants.py:18` | A browser would have to encode protobuf. **Do not call it directly from the frontend.** |
| F3 | The SuperLink has **no CORS allowance** | `grep CORSMiddleware` across `superlink/` and `supercore/`: no hit | Vite (5173) is rejected by 8000 |
| F4 | Endpoints: `/v1/control/start-run`, `/stream-run-events`, `/stream-logs`, `/list-runs` | `superlink/routers/control/router.py:132-244` | for the bridge, not for the browser |
| F5 | `stream-run-events` delivers **only task events**, and those are written **only by an AgentApp** (`agent.events.emit`) or a model task | `superlink/servicer/control/control_handlers.py:884-918`; writers: `supercore/task_process/agent/session.py`, `task_process/model/task.py` | A **ServerApp produces no run events.** Its output only exists as logs. |
| F6 | With `agentapp` in the bundle, the **ServerApp is never run** | `superlink/servicer/control/control_handlers.py:2159` | An AgentApp in the same bundle switches off the federation |
| F7 | An AgentApp has **no `Grid`**, so it cannot reach the party nodes | `agentapp/base.py` | An AgentApp cannot replace the federation |
| F8 | `print()` from the ServerApp shows up in the stream of `flwr run --stream` | observed in the 15:25 runs: `=== Soteria: …`, `Measures: …` | One event per stdout line is a workable transport |

**Unverified, check first:**

- **U1** Do the ServerApp's `print` lines arrive **line by line, live** in the stream, or buffered
  at the end of the run? Only their arrival was observed. A run takes 3–6 s — "all at once at the
  end" would be tolerable for the demo, but not for a live timeline. `print(..., flush=True)`
  probably helps; **measure, do not assume.**
- **U2** `fastapi` 0.138 and `uvicorn` 0.49 are importable in the venv, but **only indirectly via
  flwr**, not declared in `pyproject.toml`. Add them explicitly to a dependency group for the
  bridge (`[dependency-groups] bridge = [...]`), do not silently rely on them.
- **U3** The stream output of `flwr run --stream` contains install logs, warnings and ANSI colour
  codes between the payload lines. The filter needs a unique prefix.

Tools available: Node 24.10, npm 11.6, pnpm 10.33.

---

## 5 What the backend already delivers to the frontend today

Three kinds of data, **all as JSON files without a running server**. Contract: `docs/EVENTS.md`
(written from the real events, not from the plan).

| File | Content | Generated by |
|---|---|---|
| `view/fixtures/s1.json` … `s3.json` | One incident: `{case, outcome, events}`. 49/50/53 events with `seq`, `t`, `type` | `uv run python scripts/record_run.py --all` |
| `view/fixtures/boundary.json` | Boundary proof: `{cases:[{case_id, attempts, refused, authorised_raw, needles, violations, rows:[{asker, party_id, party_type, field, allowed, outcome, code, value, scope}]}]}` | `uv run python scripts/wire_proof.py --json --quiet` |
| `view/fixtures/bench.json` | The four numbers and the honesty table: `{numbers:{1_time, 2_hits, 3_boundary, 4_gap}, cases:[…], honesty:[…]}` | `uv run python scripts/bench.py` |

Event types in `events` (in stream order): `soteria.incident.open`,
`soteria.role.ready`, `soteria.receipt`, `soteria.ask`, `soteria.fact`, `collab.taint`,
`soteria.quarantine`, `soteria.disagreement`, `soteria.refusal`, `soteria.coverage`,
`soteria.grant.required`, `soteria.grant.given`, `soteria.decision`, `soteria.no_decision`,
`soteria.done`. Fields per type: `docs/EVENTS.md`.

**Important for the demo:** `s1`–`s3` contain **zero** `soteria.refusal` events. The
blocking moment ("supplier asks for customer stock → `not_in_matrix`") is only in
`boundary.json`. That is correct — in the real flow only the assessor asks, and it asks
nothing it may not see.

**Values a frontend can rely on:** traffic light (`ampel`) `gruen`/`gelb`/`rot` (green/yellow/red,
without umlauts), threshold (`schwelle`) `above`/`below`, coarse classes
`general`/`cooled`/`regulated`/`hazardous`, tiers 1/2/3, party types `carrier`/`supplier`/`customer`.

---

## 6 Integration options

The right choice depends on **what the frontend expects** — that is phase A. The options
up front, ordered by risk:

| | Option | Real | Effort | Frontend change | Stage risk |
|---|---|---|---|---|---|
| **O1** | Frontend loads the **fixture files** (`view/fixtures/*.json`) | recorded real runs | minimal | possibly data path/import | none, works without a network |
| **O2** | **Bridge**: small Python server starts the real federation and streams events as JSON via **SSE** | live | 30–45 min | API base URL | medium: SuperLink + 3 nodes must be running |
| **O3** | Frontend talks to the **SuperLink directly** | live | high | large | high — F2 (protobuf), F3 (no CORS) |
| **O4** | **AgentApp** for the frontend events | live | high | medium | **switches off the federation** — F6, F7 |

**Recommendation: O1 as the foundation, O2 as a bonus. Not O3 or O4.**

- O1 must **always** work, whatever else happens. That is the stage path.
- O2 makes the claim "really runs over a federation" visible, but is allowed to fail.
- **Same event shape for O1 and O2.** Then the switch in the frontend is a single source
  (file or stream), and everything above it stays the same.

### Why not the AgentApp

The AgentApp is built exactly for frontends in Flower (F5), but in Soteria:
1. in the same bundle it switches off the ServerApp and thus the federation (F6),
2. as a separate bundle it cannot reach the party nodes (F7) — its events would not be
   the federation's.

Only build an AgentApp if the organisers require it **as a mandatory submission** (open, §10),
and then as a separate bundle, honestly labelled.

---

## 7 Phase A — analyse the frontend (without changes)

The result of this phase is **a table**: what the frontend needs → where the backend
delivers it from → gap.

1. **Clone, do not modify.** Into a separate directory next to `Soteria/`, e.g.
   `/Users/marty/claude-projects/hackathon/collabarative_agent_hack/soteria-frontend`.
   Commit nothing, push nothing, write no dependencies into the repo.
2. **Build and start** it to see the current state (`npm install` / `pnpm install`, then
   `dev`). Screenshots or notes per view.
3. **Find the data access.** Search for: `fetch(`, `axios`, `EventSource`, `WebSocket`,
   `import.meta.env`, `VITE_`, `/api`, `localhost`, `mock`, `fixture`, `.json` imports,
   stores (Zustand/Redux/Pinia/Context).
4. **Inventory the mocks.** Where are they, what shape do they have, which view uses which?
   The mock shape **is** the requirement for the backend.
5. **Derive the data model.** For every view: which fields, which values, which order,
   does it need live updates or is a final state enough?
6. **Match against §5.** For every field: does it exist in the fixtures? Under which name? At
   which resolution (raw, traffic light, threshold)?
7. **Security check of the frontend.** Does a view show a value the matrix does not grant a
   role (e.g. the contract penalty as a number in an "assessor" view, the customer's stock in
   days, names of contact persons)? **Then the view itself is a leak.** Do not change it —
   report and ask. The matrix is in `docs/MATRIX.md`.

**The table that must exist at the end:**

| View | needs | mock today | backend source | gap | proposal |
|---|---|---|---|---|---|
| … | … | … | `s3.json` → `soteria.decision.measures` | none | direct |
| … | … | … | — | missing | backend adds it / mock stays |

**Show this table to the user before phase B starts.** They decide there which
frontend changes they allow.

---

## 8 Phase B — the integration

Only after phase A and with the user's permission for every frontend change.

### B1 — Adapter, if the shapes differ (backend side)

If the frontend's mock shape does not match `docs/EVENTS.md`, an adapter is added **in the
backend** that produces exactly the mock shape — the frontend is not rebuilt.

- Location: `scripts/export_frontend.py` (new). Reads `view/fixtures/*.json`, writes the
  frontend's shape, e.g. to `view/frontend/…`.
- Rule: the adapter **renames and restructures**, it **invents no values** and **resolves no
  projection**. No raw value that the event does not contain.
- Test: `tests/test_export_frontend.py` — the exported shape contains no raw value that was not
  already in the source event. Reusable: `scripts/wire_proof.py:_needles`.

### B2 — The bridge (option O2), if live is wanted

```
Vite (5173) ──HTTP──► Bridge (Python, 8765) ──subprocess──► flwr run --stream ──► SuperLink 8000 ──► 3 SuperNodes
              SSE        filters SOTERIA_EVENT lines
```

**Backend change 1 — the ServerApp emits its events.** Today
`soteria/assessor_app.py:343` builds the ledger **without a receiver** (`Ledger(budget, None)`). So
the real federation run produces no events; only `record_run.py` records them.
Add: a receiver that prints every event as one line.

```python
class _StdoutEvents:
    """Every event as one prefixed JSON line, for the bridge."""
    PREFIX = "SOTERIA_EVENT "

    def __init__(self) -> None:
        self._seq = 0
        self._t0 = time.monotonic()

    def emit(self, event: dict) -> None:
        self._seq += 1
        line = {"seq": self._seq, "t": round(time.monotonic() - self._t0, 3), **event}
        print(self.PREFIX + json.dumps(line, ensure_ascii=False, default=str), flush=True)
```

Same shape as `scripts/record_run.py:Recorder` — `seq` and `t` are assigned the same way.
**Measure U1** first: do the lines arrive live?

**Backend change 2 — the bridge** `scripts/bridge.py` (new):

| Endpoint | Does | Response |
|---|---|---|
| `GET /api/cases` | list cases (`soteria.cases.available_cases`) | JSON |
| `GET /api/fixtures/{name}` | serve one fixture (reject path traversal!) | JSON |
| `GET /api/run/{case}/stream` | `federation.sh up {case}`, then `flwr run . carrier-fed --stream --run-config 'case="{case}"'`; send every `SOTERIA_EVENT` line as SSE `data:` | `text/event-stream` |
| `GET /api/health` | SuperLink and nodes reachable? | JSON |

- **Allow CORS in the bridge** for `http://localhost:5173` (`fastapi.middleware.cors`).
  Then the frontend needs **no** `vite.config` change, only a base URL — and even that is a
  frontend change, so ask.
- **Bind only to `127.0.0.1`.** The bridge starts processes; it does not belong on the hackathon Wi-Fi.
- **Check case codes against `available_cases()`** before they go into a command line. Never
  pass unchecked text to `subprocess`.
- After the run ends, send the `soteria.done` event and close the stream.
- If the run fails: an event `soteria.bridge.error` with the reason, then close. The
  frontend falls back to O1.

**Frontend side (only with permission):** make the source switchable — fixture file or
`new EventSource("http://127.0.0.1:8765/api/run/s3/stream")`. The event shape is identical,
so nothing above the source changes.

Bridge dependencies (U2): declare `fastapi`, `uvicorn` explicitly.

### B3 — Tests

- `tests/test_bridge.py`: case-code check rejects `../` and unknown values; the fixture endpoint
  only serves files from `view/fixtures/`; the line filter ignores non-prefixed lines and
  ANSI codes (U3).
- The existing 163 tests must stay green.

---

## 9 Phase C — gaps

For every gap from the phase A table, in this order:

1. **Is the value already in an event, just named differently?** → adapter (B1).
2. **Can it be derived honestly from backend data without violating the matrix?** → add it
   in the backend (new field in the event, update `docs/EVENTS.md`, test).
3. **Would it disclose a raw value the role may not see?** → **do not deliver it.**
   Tell the user which view requires it, and ask.
4. **Is it pure presentation** (maps, train images, colours, texts)? → the frontend mock
   stays. Record it as simulated in `README.md` → "Real versus simulated".

Do **not** connect from the backend, however tempting:
- The stored ground truth (`case.truth`) in a **live** view — the assessor does not know it,
  so the live view does not show it. In a case overview it is right, labelled
  "unconfirmed" there (§10).
- Anything straight from `data/` in the browser. A view that shows more than the
  event stream is a leak itself.

---

## 10 Open points and risks

| # | Point | Effect | Who |
|---|---|---|---|
| R1 | **`truth` blocks are `_status: "PROPOSAL"`**, guessed by the engine track, not confirmed by the data specialist | The 3/3 hit rate may only be shown as "unconfirmed". `bench.json` → `numbers.2_hits.truth_unconfirmed` | data specialist |
| R2 | **AgentApp as mandatory submission?** `PREP.md` says "working AgentApp"; Soteria is ServerApp/ClientApp | If mandatory: build a separate bundle (F6) | ask the organisers |
| R3 | **Hub version outdated.** The first upload contained `soteria/scenarios/s1_pharma_cooling.json` (removed in git since `0c32e85`). The second upload failed with 401 | Re-upload: `uv run flwr login supergrid`, then **immediately** `uv run flwr app publish .` — the token expires after a few minutes and is not refreshed | user logs in, session uploads |
| R4 | **U1** unverified: stdout lines live or buffered? | Decides whether O2 can carry a live timeline | new session, first |
| R5 | s2 gets the measures right, but reasons with `feasibility` instead of `safety` | Report honestly, do not hide | — |
| R6 | No holdout (`h1`–`h4`) | Hit rate is only a consistency check | data specialist |
| R7 | Federation runtime: the first run after `up` installs the app (7–12 s wall clock) | Do a full run once before the demo | demo prep |

---

## 11 Commands

```shell
cd /Users/marty/claude-projects/hackathon/collabarative_agent_hack/Soteria

uv run pytest -q                                  # 163 green, 1 skipped
uv run python scripts/validate_data.py            # 0 errors, 3 warnings (R1)

uv run python scripts/record_run.py --all         # view/fixtures/s1..s3.json
uv run python scripts/wire_proof.py --json --quiet # view/fixtures/boundary.json
uv run python scripts/bench.py                    # view/fixtures/bench.json

./scripts/federation.sh up s3                     # SuperLink + 3 SuperNodes
./scripts/federation.sh run s3                    # real run, 3–6 s
./scripts/federation.sh down
```

`~/.flwr/config.toml` (verified, backup at `config.toml.bak-1528`):

```toml
[superlink.carrier-fed]
address = "127.0.0.1:8000"
insecure = true

[superlink.supergrid]
address = "api.flower.ai"
```

**Ports:** 8000 SuperLink Control/Runtime · 9092 Fleet (SuperNodes) · 9094–9096 SuperNodes ·
5173 Vite · 8765 bridge (proposal).

---

## 12 Where everything is

| What | Where |
|---|---|
| Backend repo | `Backooo/Soteria`, branch `feat/soteria-engine` |
| Local | `/Users/marty/claude-projects/hackathon/collabarative_agent_hack/Soteria` |
| Event contract | `docs/EVENTS.md` |
| Need-to-know matrix | `docs/MATRIX.md`, data: `data/schema/field_catalogue.json` |
| Measurements, platform findings | `docs/RISKS.md` |
| Build plan and revisions | `docs/superpowers/plans/2026-09-16-soteria.md` |
| Changing the data schema | `data/schema/README.md` |
| Assessor (ServerApp) | `soteria/assessor_app.py` — `Assessor`, `run_incident`, ledger without receiver at line 343 |
| Party node (ClientApp) | `soteria/party_app.py` — `answer_ask`, `answer_bundle` |
| Recording without a SuperLink | `scripts/record_run.py` — `Recorder`, `local_sender`, `record` |
| Boundary proof | `scripts/wire_proof.py` — `prove`, `_needles` |
| Predecessor document | `../SOTERIA-HANDOFF.md` (state before the federation, partly outdated) |
| Frontend | **still unknown** — §2 |

---

## 13 First three steps of the new session

1. Read this document, then `docs/EVENTS.md`. Ask the user for the frontend link (§2).
2. **Measure U1**, in parallel with cloning: print a `SOTERIA_EVENT` line with `flush=True` as a
   test in a throwaway branch, run `federation.sh run s3`, and check whether the lines arrive during
   the run or only at the end. Record the result in `docs/RISKS.md`.
3. Phase A (§7) up to the table — **then stop** and show the table to the user.

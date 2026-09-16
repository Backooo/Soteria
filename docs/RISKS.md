# Risks and findings, measured on the day

What is written here was measured or read in the source code — not remembered.

## The federation runs — measured

Three SuperNodes, one SuperLink, real Flower messages, locally on one machine.
Measured twice, because the first measurement exposed a risk for the live demo:

| Case | Decision | Tier | Keys | Ground truth | 13 rounds | **bundled** |
|---|---|---|---|---|---:|---:|
| s1 | `cool` | 1 | none | HIT | 69.1 s | **6.4 s** |
| s2 | `alt_transport` | 2 | ops-lead-rheinrail-1 | HIT | 126.9 s | **6.2 s** |
| s3 | `stop_train`, `notify_authority` | 3 | ops-lead + safety-officer | HIT | 68.0 s | **3.2 s** |

In s3 the quarantine kicks in (`browser_use`, `press`, `start_automation`,
`web_fetch`, `web_search` shut). Wall-clock time from `flwr run` to the result,
including the app installation on the SuperLink, was 7–12 s.

**What the speed-up was.** Every Flower message starts a ClientApp process on
the node. 13 ask rounds × 3 nodes were 39 process starts. Now one message per
node carries the whole ask plan (`query.ask_fields`), and the reply is a
`RecordDict` with one `ConfigRecord` per field. The transport is bundled, not
the check — every field still goes through the matrix and the scalar bolt
individually, and `tests/test_bundle.py` demonstrates for s1–s3 that the bundled
answer equals the single-field answer, field by field.

**Finding on the reasoning:** s2 gets the measures right but justifies them with
`feasibility`; the stored ground truth says `safety`. The hit rate counts
measures, not reasons — this has to be reported openly, not hidden.

## Platform findings, backed by the source code

1. **A FAB with an `agentapp` never runs the ServerApp.**
   `superlink/servicer/control/control_handlers.py:2159`:
   `TaskType.AGENT_APP if "agentapp" in components else TaskType.SERVER_APP`.
   Validation (`common/config.py:355-388`) allows all three components at once;
   execution picks exactly one. That is why Soteria is a ServerApp/ClientApp
   bundle. **An AgentApp would be a second bundle.**

2. **Model and federation do not meet.** `AgentSession` has no `Grid`
   (`agentapp/base.py`), and `FLWR_RUNTIME_BASE_URL`/`_API_KEY` are only set
   for AgentApps (`supercore/task_process/agent/run_agentapp.py`). So the party
   nodes have no model — and need none, a projection is a function.

3. **The control port has changed.** `uv sync` pulled **flwr 1.37.0**. There the
   SuperLink serves the Control API over HTTP on **8000**, not on 9093 as in
   1.35. The handoff note "9093, not 8000" is **wrong** for this version.
   `~/.flwr/config.toml` → `[superlink.carrier-fed] address = "127.0.0.1:8000"`.

4. **`Grid.create_message` is deprecated in 1.37** — replaced by the `Message`
   constructor.

## Build

- `flwr build` validates the component path (missing module = abort).
- `fab-include` patterns must match **at least one file**, otherwise abort.
- The FAB contains the code and all data under `data/` (41 files).

## Open

- **`flwr app publish .` never run.** Needs `flwr login supergrid`, and that
  blocks the shell with a browser login. Must run before 16:30.
- **SuperGrid:** Soteria needs its own SuperNodes with `node-config`. Whether
  SuperGrid accepts external SuperNodes is unchecked. The local SuperLink is the
  safe path (Track 2 allows it).
- **Three machines:** not attempted. The code reads the party from
  `--node-config`, so it should work — "should" is not checked.
- **The `truth` blocks are a `PROPOSAL`** from the engine track, not confirmed by
  the data specialist. As long as that holds, the hit rate is a number about our
  own guess and must be labelled as such in the presentation.
- **No AgentApp.** See finding 1. The mandatory submission says "working
  AgentApp"; Track 2 allows a ServerApp. Clarify with the organisers.
- **No holdout.** Without `h1`–`h4`, every hit rate is only a consistency check.

## Skipped inherited test

`tests/test_harness.py::test_demo_charter_is_valid_and_demonstrates_the_policy`
checks the inherited `librarian`/`researcher` roster. Skipped, not deleted, so
its origin stays visible.

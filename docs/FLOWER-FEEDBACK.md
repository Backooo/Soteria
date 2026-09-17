# Notes and suggestions for Flower

Findings from building Soteria at the Collaborative Agent Hackathon (Berlin, 16 September 2026) and
the day after. Every claim below names the file in the installed package or the output we saw, so
each item can be checked or filed as an issue.

**Environment:** `flwr==1.37.0` (installed by `uv sync` from `flwr>=1.35,<2.0`), Python 3.12,
macOS 15, local SuperLink plus three SuperNodes, and SuperGrid for the model calls.

Paths are relative to the installed package, e.g.
`.venv/lib/python3.12/site-packages/flwr/`.

## What worked well, and why it mattered for us

- **`ConfigRecord` carries scalars only.** This is the third bolt of our privacy argument: a raw
  record cannot be put on the wire even if our own matrix were misconfigured. A typed transport
  turned a policy promise into a structural one.
- **`agent.events.emit()` plus `flwr run --stream`.** We had a frontend-visible event stream from an
  AgentApp within minutes of first opening the API.
- **Content-addressed app installs** (`~/.flwr/apps/<publisher>.<name>.<version>.<hash>`) made it
  obvious which build a run actually used — which is how we found the packaging bug in item 4.
- **`flwr app publish`** to the Hub was a single command once logged in.

---

## 1. A ServerApp or ClientApp cannot call the model API

**Type:** enhancement · **Impact:** high for agent teams that also federate

Only an AgentApp process receives model credentials:
`supercore/task_process/agent/run_agentapp.py` sets `FLWR_RUNTIME_BASE_URL` and
`FLWR_RUNTIME_API_KEY` (`_set_runtime_environment`, ~line 290), and the Runtime endpoint
authenticates exactly one AgentApp bearer token
(`superlink/routers/runtime/responses.py:121`, *"Authenticate exactly one AgentApp Bearer token"*).
`Context` (`app/message/context.py`) carries `run_id`, `node_id`, `node_config`, `state`,
`run_config`, `series_id` — no model handle.

Consequence: our decision-making agent is a ServerApp (it needs `Grid` to reach the party nodes), so
to use a model it shells out to `flwr run <agent-bundle> supergrid --stream` and parses stdout —
one subprocess and one full app install per decision, and the host needs an interactive
`flwr login`. That is a lot of machinery for "ask a model one question".

**Suggestion:** expose the same OpenAI-compatible runtime endpoint to ServerApp and ClientApp
processes, opt-in per run (`[tool.flwr.app.config] model_access = true`), or provide
`context.model` / a small `flwr.model` client that resolves credentials the same way.

## 2. `agentapp` in a bundle silently disables the ServerApp

**Type:** docs + guardrail · **Impact:** medium

`superlink/servicer/control/control_handlers.py:2159`:

```python
return TaskType.AGENT_APP if "agentapp" in components else TaskType.SERVER_APP
```

A bundle that declares both components runs only the AgentApp. Nothing warns; the federation simply
never starts. We lost time to this before reading the source, and it forced the two-bundle design we
now ship (`agent/` is a separate app).

**Suggestion:** reject a bundle that declares `agentapp` together with `serverapp`/`clientapp` with
an explicit error, or document the precedence prominently. A one-line warning at run start
("bundle declares agentapp, ServerApp will not run") would have saved the whole detour.

## 3. An AgentApp has no `Grid`

**Type:** enhancement · **Impact:** high for "collaborative agents"

`agentapp/base.py`: `AgentSession` exposes `connectors` and `events` — nothing else. An AgentApp
therefore cannot send a `Message` to a SuperNode, so it cannot talk to the parties of a federation.
Combined with item 1, agents and federations are two disjoint worlds: the side that can reach the
data cannot reach a model, and the side that can reach a model cannot reach the data.

For a hackathon whose brief is *safe collaboration of agent teams*, this is the central gap. Every
team we spoke to hit some version of it.

**Suggestion:** either give `AgentSession` access to a `Grid` (even read-only, one round-trip per
call), or close the gap from the other side as in item 1. Either one makes "an agent that consults
distributed parties" expressible in one app.

## 4. A FAB cannot carry a nested app bundle — and fails two different ways

**Type:** bug (silent) + UX · **Impact:** high, cost us a demo cycle

Our ServerApp starts a second bundle that ships inside the same app. Two built-in FAB rules make
that impossible, and neither is visible until runtime:

- `common/constant.py:85` excludes `pyproject.toml` as a **bare gitignore-style pattern**, which
  matches at *any* depth, so `agent/pyproject.toml` is dropped. Listing it under `fab-include`
  changes nothing: `cli/build.py:417-419` explicitly treats such removals as *"expected removals
  and should not be flagged"*. The build succeeds, the file is missing, and the failure appears
  later inside the installed app.
- `common/constant.py:71-80`: the built-in include for a licence is `/LICENSE`, root-anchored.
  So `agent/LICENSE` is not a candidate file at all, and listing it produces a hard error —
  *"Pattern in `fab-include` did not match any files: `agent/LICENSE`"* — even though the file
  exists and is tracked.

Same goal, two opposite behaviours: one silently ignores the include, the other refuses the build.

Our workaround: ship the nested manifest as `agent/pyproject.fab.toml`, copy the tree to a temp
directory at runtime, rename the manifest back, and copy the app-root `LICENSE` in beside it
(`soteria/llm.py:bundle_dir`).

**Suggestion, in order of usefulness:**
1. Warn when a user `fab-include` pattern is nullified by a built-in exclude — silence here is the
   whole bug.
2. Make the built-in `pyproject.toml` exclude root-anchored (`/pyproject.toml`), matching the
   `/LICENSE` convention.
3. Consider a first-class "sub-app" concept: an app that ships another app it may launch.

## 5. A ServerApp cannot emit run events

**Type:** enhancement · **Impact:** high for anything with a UI

Run events exist (`superlink/servicer/control/control_handlers.py:846 stream_run_events`), but the
publisher is the AgentApp session (`supercore/task_process/agent/session.py:99 emit`). A ServerApp
has no equivalent, so everything it knows is log text.

For a live view of a federation we therefore print `SOTERIA_EVENT {json}` lines with `flush=True`
and run a small FastAPI bridge that re-parses them into SSE (`scripts/bridge.py`). It works, but it
means a public protocol made of stdout lines, plus ANSI stripping, plus a process babysitter.

**Suggestion:** `context.events.emit(dict)` for ServerApp and ClientApp, forwarded into the same
run-event stream that `stream-run-events` already serves. This is the single change that would most
improve demos built on Flower.

## 6. The SuperLink HTTP APIs are not reachable from a browser

**Type:** enhancement / docs · **Impact:** medium

The Control API speaks protobuf (`supercore/protobuf/constants.py:18`,
`PROTOBUF_MEDIA_TYPE = "application/protobuf"`), and there is no CORS middleware anywhere in
`superlink/` or `supercore/` (no `CORSMiddleware` import in the package). So a Vite dev server on
:5173 cannot read run state or events, and every web UI needs its own local bridge process.

**Suggestion:** an optional CORS allowlist in the SuperLink config, plus a read-only JSON or SSE
endpoint for run events. A flag like `--dev-cors http://localhost:5173` would be enough for
hackathon and demo use.

## 7. `flwr login <app-dir> <federation>` fails with a migration error

**Type:** UX · **Impact:** small, but it hits during a demo

Running the older form printed:

> Cannot migrate configuration: No `[tool.flwr.federations]` section found in `…/pyproject.toml`.
> This is expected if the migration has been previously carried out. Use `--help` after your command
> to see the new usage pattern.

The message explains a migration, not the mistake. The fix is simply `flwr login supergrid`.

**Suggestion:** when the first positional argument is an existing directory that has no
`[tool.flwr.federations]`, say so directly: *"`flwr login` no longer takes an app directory — run
`flwr login <federation>`"*.

## 8. Hub publishing: expiring session, version conflict, upload timeout

**Type:** UX · **Impact:** medium during time-boxed events

Three things in one publishing session:

- `Upload failed with status 401: {"detail":"Not authenticated"}` a few minutes after runs against
  SuperGrid had been working — the session had expired, and the message does not say so.
- `Upload failed with status 409: {"detail":"this version already exists"}` — correct, but the fix
  (bump `version` in `pyproject.toml`) is not mentioned.
- One publish died with `Network error: … Read timed out. (read timeout=120)` after uploading the
  file list, on a conference wifi.

**Suggestion:** on 401, say "your Flower session has expired, run `flwr login <federation>`"; on 409,
name the field to bump; make the upload timeout configurable or the upload resumable.

## 9. Structured output for the runtime responses API

**Type:** enhancement · **Impact:** medium · **Not tested by us**

Our AgentApp asks the model for one JSON object and we validate it strictly before it can influence
a decision (`soteria/llm.py:parse_answer`: measures must exist in the catalogue, `reason_code` must
be known, anything else is rejected and the run falls back to the rule policy). Every call we
inspected returned valid JSON, but the guarantee is ours, not the platform's.

If the runtime endpoint already forwards `response_format` / JSON-schema constraints to the model,
this deserves a line in the docs. If it does not, it is worth adding: a schema-constrained response
is what makes a model's output safe to hand to an executor.

## 10. Port and version drift is hard on returning users

**Type:** docs · **Impact:** small

Our notes from `flwr` 1.35 said the CLI talks to the SuperLink on **9093**; in 1.37 the log line is
*"Starting the SuperLink Control HTTP API on 127.0.0.1:8000"*
(`superlink/cli/flower_superlink.py:499`). A stale note produced a confident, wrong debugging
session.

**Suggestion:** when a connection to a known-old control port is refused, hint at the new one; and
keep a short "what changed between 1.35 and 1.37 for app authors" note in the release docs.

---

## If we could ask for exactly two things

1. **`context.events.emit()` for ServerApp and ClientApp** (item 5) — it turns any federation into
   something you can watch, and removes the stdout-protocol-plus-bridge pattern that every demo
   team reinvents.
2. **Model access from a ServerApp, or `Grid` from an AgentApp** (items 1 and 3) — one of the two,
   so that "agents that collaborate across parties" is a single app instead of two apps and a
   subprocess.

Everything else on this list is a message, a warning or a doc line.

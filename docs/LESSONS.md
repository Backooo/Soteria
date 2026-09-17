# What we learned building Soteria

Written the day after the Collaborative Agent Hackathon (Berlin, 16 September 2026), from a
repository that went from empty to a running federation, an LLM-backed assessor, a dashboard and a
live console in one day. Everything below is something that cost us time or changed the design —
not general advice.

Platform findings and suggestions for Flower live in [`FLOWER-FEEDBACK.md`](FLOWER-FEEDBACK.md).

---

## 1. A fallback that is not visible in the data will be mistaken for the real thing

The assessor calls a model. If the call fails, the rule policy decides instead. That is a good
design — and it nearly produced a false claim.

When we first ran the LLM path on the real federation, every event said the decision came from
`flower-endeavor-v1.0`… except it had not. The ServerApp runs from the **installed FAB**, the agent
bundle was not inside it, the call failed in 0.88 s, and the rule policy answered. The run looked
identical from the outside: same measures, same tier, same receipts, same duration to a human eye.

What saved us was that the fallback carries its reason in the event:

```json
{"type": "soteria.model.decision", "decided_by": "policy_fallback",
 "error": "FileNotFoundError: agent bundle missing at /Users/…/.flwr/apps/…"}
```

**Rule we would keep:** every result that can come from two sources carries *which source produced
it*, in the data, not in a log line — and the UI prints it. `decided_by: "llm" | "policy_fallback"
| "policy"` is three words in a JSON payload and it is the difference between a demo and a claim.

It happened twice more. After the packaging fix, live runs still fell back — and the event only
said `ValueError: no SOTERIA_LLM result line in AgentApp output`, because we had thrown the
subprocess output away. Once the error carried the CLI's own words, the cause was one line long:
the materialized bundle had no `LICENSE`, so its own build failed before the model was ever called.
**An error message that does not quote the tool it called is a dead end.**

A related version of the same mistake was pointed out to us in review earlier that day: the repo
had model code in `team.py` that nothing imported, so the system was a distributed expert system
while the README implied agents. Dead code that *looks* like the feature is worse than no code.

## 2. A detector without a denominator measures nothing

The privacy claim is "no raw value reaches a role that may not have it". The first version of
`scripts/wire_proof.py` reported "0 leaks" — and was worthless, because it never showed how many
disclosures the matrix *allows*. Once we printed the denominator (234 crossings, 96 refused, 81
authorised, 0 violations), two real bugs appeared immediately: a scope side channel and a
coarse-name collision. Both are fixed; both were invisible while the number was just "0".

**Rule:** a safety metric needs the count of things that were allowed, next to the count of things
that were blocked. A test that can only print zero prints zero when it is broken, too.

## 3. Put the guardrails outside the model, and let them contradict it

The model picks the measures. It cannot pick the tier, the number of human keys, the need-to-know
projections or the quarantine — those are code, applied to whatever the model returns. Concretely:
unknown measures are rejected, and a tier-3 measure the rule policy requires is added back if the
model drops it.

The honest consequence showed up straight away: with the model deciding, s1 still matches the
stored answer, while in s2 and s3 the model adds reversible measures (`cool`, `hold`) on top, and
the benchmark counts that as a mismatch. We left the number as a mismatch and wrote why in the
README instead of adjusting the prompt until the benchmark went green. A benchmark you tune to your
own stored answers stops being evidence.

## 4. One event stream, three consumers

Every run emits one flat, ordered event stream: `seq`, `t`, `type`, plus typed fields per event
(`docs/EVENTS.md`). The same shape feeds:

- the recorded fixtures (`scripts/record_run.py`),
- the frontend export (`scripts/export_frontend.py`),
- the live bridge (`scripts/bridge.py`), which forwards one JSON line per event.

Because the shape is identical, the console's replay mode and its live mode are the same renderer
with a different source, and the dashboard needed no knowledge of either. When we added the model,
two new event types (`soteria.model.request`, `soteria.model.decision`) appeared in all three
places for free.

**Rule:** decide the event contract before the UI. A stream that only exists as log text forces
every consumer to invent its own parser.

## 5. Build the offline path first, then the live one

The demo path that must never fail was recorded runs loaded from JSON — no network, no SuperLink,
no model. The live path (bridge → real federation → SuperGrid model call) was added on top and can
fail without taking the demo down. On stage that ordering is worth more than any feature: a live
run needs a SuperLink, three SuperNodes, a FAB build, a valid login and a model call, and each of
those can fail in a room with 58 people on one wifi.

What we would not repeat: the console originally fell back to replay when the bridge was
unreachable. That is exactly the failure from lesson 1 in UI form — it makes a broken live run look
like a working one. It now shows a red banner and requires a click to go back to replay.

## 6. Measure the platform, do not remember it

Three separate notes in this project were wrong because they were written from memory of an earlier
version: the Control API port (9093 → 8000), the `flwr login` command form, and the assumption that
an AgentApp could reach the party nodes. Each cost a debugging cycle in the middle of a time-boxed
build. The fix that worked was boring: every platform claim in our docs names the file and line in
the installed `flwr` package, or the log line we read.

## 7. Two agents in one repo need file reservations

A second Claude session translated the whole app from German to English while this session was
building the LLM path — in the same working trees. What kept that from becoming a merge disaster
was an explicit protocol: each session announced the files it was editing, waited for an
acknowledgement, and released them by name when done ("released: assessor_app.py, policy.py").

It still nearly went wrong once: both sessions regenerated `view/fixtures/` within a minute of each
other, each with a different assessor version. Generated artefacts need an owner just like source
files do.

## 8. What we deliberately did not build

- **Holdout cases.** The hit rate is a consistency check against cases the rules were written
  against. Without `h1`–`h4` it claims nothing, and the README says so.
- **One federation per party.** A ServerApp cannot reach three SuperLinks at once, so "one
  federation per party" is one federation with three party nodes.
- **Cryptographic receipts.** The chain is 16 hex characters of a hash — tamper-evident for a demo,
  not a signature scheme.
- **Direct browser access to the SuperLink.** It speaks protobuf and sends no CORS headers; a small
  local bridge was the honest way in.

## 9. Numbers we ended the day with

| | |
|---|---|
| Boundary crossings attempted / refused / authorised / violations | 234 / 96 / 81 / 0 |
| Federation run, no model call | 3–6 s per incident |
| Federation run with the SuperGrid model call | 41 s measured live; 50–84 s for the recorded runs |
| Events in one s3 run | 55 |
| Live runs before one reached the model | 4 |
| Tests | 188 passed, 1 skipped |
| Model calls we inspected | 5, all returned valid JSON on the first attempt |

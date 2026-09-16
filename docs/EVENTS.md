# Event contract — for the two views

Written from the **real** events in `view/fixtures/`, not from the plan.
Regenerate:

```shell
uv run python scripts/record_run.py --all          # view/fixtures/s1.json, s2.json, s3.json
uv run python scripts/wire_proof.py --json --quiet  # view/fixtures/boundary.json
```

Adding a new field to an event is allowed. Renaming or removing a field only
after agreement.

**Both views: one HTML file, CSS and JS inline, no external requests** — no CDN,
no Google Fonts. 58 people share the Wi-Fi. Load the JSON via `fetch`, with a
file picker as a fallback for `file://`.

**The view never shows a value that is not in the event.** No lookups in
`data/`, no enrichment. A view that shows more than the stream is a leak itself.

---

## File 1: `view/fixtures/<case>.json` — one incident

```json
{
  "case":    {"id": "s3", "title": "...", "report": {...}, "flags": [...],
              "parties": [{"party_id": "...", "party_type": "carrier"}], "truth": {...}},
  "outcome": {"decision": {...} | null, "refusal": "grant_mismatch" | null},
  "events":  [{"seq": 1, "t": 0.0, "type": "soteria.incident.open", ...}]
}
```

`seq` is gapless from 1. `t` is seconds since start — for replay at the original
pace. `case.truth` is for the case overview (F2), **not** for the live view: the
assessor does not know the ground truth, so the live view does not show it
either.

### Events, in the order they arrive

| `type` | Fields | What the view does with it |
|---|---|---|
| `soteria.incident.open` | `case_id`, `incident_id`, `train_id`, `location`, `symptom`, `severity` (`low`/`medium`/`high`), `train_operational` (`normal`/`restricted`/`immobilized`), `track_blocked` (bool), `affected_wagons[]`, `cargo_classes_coarse[]`, `flags[]` | Header. `cargo_classes_coarse` is already coarsened (`general`, `cooled`, `regulated`, `hazardous`) — the fine goods are never in the stream |
| `soteria.role.ready` | `party_id`, `party_type` (`carrier`/`supplier`/`customer`), `speaks_as[]`, `online` | One tile per **party** (= federation). `carrier` speaks as `intake` and `legal` |
| `soteria.ask` | `from_role` (always `assessor`), `field`, `reason_code`, `visibility` | Line leaving the assessor, labelled with field and resolution |
| `soteria.fact` | `role`, `field`, `visibility`, `value`, `scope`, `flags[]` | The answer. See "Values" below. `scope` is the wagon number (`W02`) or a **coarse** cargo class, empty if there is no reference unit |
| `soteria.receipt` | `seq_in_chain`, `kind` (`incident`/`fact`/`refusal`/`disagreement`/`decision`), `hash`, `prev` | Receipt chain, as a list of short hashes. Every `prev` is the `hash` before it |
| `collab.taint` | `source` | Only in s3, right before the quarantine. May be ignored |
| `soteria.quarantine` | `trigger_role`, `field`, `blocked_channels[]` | **Full-width banner:** "Market sensitive — all outbound channels shut", with the channel list. Only occurs in s3 |
| `soteria.disagreement` | `field`, `held`, `offered`, `role` | Two parties contradict each other about the same contract. Does not occur in s1–s3 but can — highlight in yellow then |
| `soteria.refusal` | `actor`, `action`, `code`, `detail_chars` | **Red, code in large type.** Zero times in s1–s3 — the blocking moment comes from `boundary.json`, see below |
| `soteria.coverage` | `answered`, `asked`, `parties_expected[]`, `parties_missing[]` | "13 of 13 answered". If a party is missing: "Decided without customer_…" |
| `soteria.grant.required` | `measures[]`, `tier` (1/2/3), `keys_needed` (0/1/2) | As many key symbols as `keys_needed`, open |
| `soteria.grant.given` | `measures[]`, `human_id`, `keys_have`, `keys_needed` | Close one key, `human_id` next to it. s2: one, s3: two |
| `soteria.decision` | `measures[]`, `params`, `tier`, `grants[]`, `coverage`, `reason_code`, `receipt_hash`, `parties_missing[]`, `scopes` | **The decision card**, the main visual. `receipt_hash` is the head of the chain across the whole incident |
| `soteria.no_decision` | `code`, `detail_chars` | Instead of `decision`, when a grant is missing or does not match (`no_grant`, `grant_mismatch`) |
| `soteria.done` | `elapsed_seconds`, `refusals`, `refusal_codes`, `asks`, `answers`, `quarantined`, `receipt_chain_verified`, `receipt_head` | Footer. Make `receipt_chain_verified: true` visible |

### Values the view may rely on

| If `visibility` is | then `value` is | Display |
|---|---|---|
| `ampel` (traffic light) | `"gruen"` / `"gelb"` / `"rot"` (green / yellow / red) | Coloured dot. Umlaut deliberately omitted |
| `schwelle` (threshold) | `"above"` / `"below"` | Arrow. For `contract_penalty`, `above` means "over the pain threshold"; for `contract_deadline_h`, `below` means "deadline getting tight" |
| `flag` | `true` / `false` | Symbol |
| `coarse` | a coarse class | Text |
| `raw` | text or number | Text. **Only** the operator's operational data reaches the assessor raw (`alt_route_status`, `locality_class`) |

Roles: `intake`, `assessor`, `legal`, `supplier`, `customer` — these are
**agents**. Reporters (`driver`, `police` …) are humans and do not appear in the
stream.

Measures: `proceed`, `hold`, `cool` (tier 1) · `reload`, `alt_transport`,
`contact` (tier 2) · `stop_train`, `notify_authority`, `press` (tier 3).

### What happens in the three cases

| Case | Decision | Tier | Keys | The picture |
|---|---|---|---|---|
| s1 | `cool` | 1 | 0 | Temperature yellow, stock green → just cool. The traffic light prevents the expensive transshipment |
| s2 | `alt_transport` | 2 | 1 | Track blocked, urgency red, deadline tight → diversion, one key |
| s3 | `stop_train`, `notify_authority` | 3 | 2 | **Quarantine banner**, two keys, hazmat next to residential buildings |

---

## File 2: `view/fixtures/boundary.json` — the boundary proof

**This is where the blocking moment is.** Every boundary crossing a party could
attempt — every role asks every other node for every field — and what came of
it.

```json
{"cases": [{
  "case_id": "s3", "attempts": 78, "refused": 32, "authorised_raw": 27, "needles": 31,
  "violations": [],
  "rows": [
    {"asker": "supplier", "party_id": "customer_c3_chemiewerk", "party_type": "customer",
     "field": "customer_stock", "allowed": "none", "outcome": "refused",
     "code": "not_in_matrix", "value": "", "scope": ""}
  ]
}]}
```

`outcome` is `refused` (red), `projected` (the party got a traffic light or
threshold instead of the number) or `raw` (the matrix allows it — do **not** show
it as a violation). `violations` is empty; if anything were in there, it would
be a real leak.

The demo line: **the supplier asks for the customer's stock →
`not_in_matrix`.** Found in `rows` with `asker == "supplier"` and
`field == "customer_stock"`.

---

## Task F1 — live view, `view/index.html`

Loads `fixtures/s1.json` … `s3.json` (selectable), replays `events` by `t`. In
this order of importance:

1. `soteria.quarantine` as a banner (s3)
2. The decision card from `soteria.decision`, with tier, keys, `receipt_hash`
3. The party tiles from `soteria.role.ready` with the incoming traffic lights
4. A timeline of the `ask`/`fact` pairs
5. A "Boundary proof" tab from `boundary.json`: the `refused` rows in red, and
   the counts `attempts` / `refused` / `authorised_raw` / `violations` on top

## Task F2 — case overview, `view/cases.html`

Loads `fixtures/bench.json` (coming next). Until then: the three incident files
directly — `case.truth.measures` against `outcome.decision.measures`.

Must show: ground truth against decision per case, the tier, and the honesty
table. **The `truth` blocks still carry `_status: "PROPOSAL…"`** — as long as
that is the case, label them "unconfirmed", not as a result.

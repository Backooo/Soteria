# Data schema — how to change it

Everything here is **invented**. No real railway data, no real people, no real
companies. The honesty table of the submission says exactly that.

Check as often as you like — needs no model, no network, no SuperLink:

```shell
uv run python scripts/validate_data.py
uv run python scripts/validate_data.py data/s3          # just one case
```

Empty output and exit code 0 means: all good.

## Why there are two layers

- **`vocabularies.json`** — the closed value lists. What is a valid
  `cargo_class`, a valid `trade`, a valid `urgency`.
- **`field_catalogue.json`** — the need-to-know matrix as data: which field is
  shown to whom at which resolution, with which projector and which threshold.
  `soteria/matrix.py` loads this file and validates it on import.

That way the actual security decision — who sees what — is readable and
disputable in one place, without reading Python.

A note on two German terms that remain as enum values: the visibility `ampel`
means *traffic light* (values `gruen`/`gelb`/`rot` = green/yellow/red), and
`schwelle` means *threshold* (values `above`/`below`).

## The four common changes

**Add a value** (new cargo class, new trade, new urgency): add it to
`vocabularies.json`. Done. For `cargo_class` and `trade` a `coarse` entry
belongs with it, because the assessor only sees the coarse class.

**Add a field:** an entry under `fields` in `field_catalogue.json`:

```json
"wagon_seal_intact": {
  "owner": "incident",
  "kind": "bool", "per": "wagon",
  "note": "Whether the wagon's seal is intact.",
  "projectors": {"raw": "raw", "flag": "flag"},
  "visibility": {"intake": "raw", "assessor": "flag", "legal": "none",
                 "supplier": "none", "customer": "flag"}
}
```

Required: `owner` is a record type from `record_types`; `visibility` names
**all five** roles; every resolution other than `none` needs a projector; every
projector name must be listed in `known_projectors`. Otherwise the validator
tells you what is missing.

**Remove a field:** delete the entry. The validator then reports every data
file that still holds it — clean up and run it again.

**Change who sees what:** edit `visibility`. `none` means not at all and yields
`not_in_matrix` on access. Careful: if you give a role `raw`, the raw value
leaves the owner's node — exactly what the matrix is meant to prevent, so only
do it on purpose.

**A new KIND of projection** (not a traffic light, not a threshold, but
something new): add a function in `soteria/matrix.py` and list its name in
`known_projectors`. This is the only case that needs code.

## Adding a party

Another customer is a file in `data/parties/` and an entry in the case file's
`federations`. **Nothing in the code changes** — `s3` already runs two customer
federations at the same time.

```json
{
  "party_id": "customer_c4_grossmarkt",
  "party_type": "customer",
  "display_name": "Grossmarkt Sued (fictional)",
  "records": {
    "customer": {
      "customer_trade": "wholesale_market",
      "consignments": {"perishable": {"customer_stock": 1.5, "customer_urgency": "elevated"}},
      "contact_person": [{"name": "...", "function": "...", "phone": "...", "hours": "..."}]
    }
  }
}
```

**A train belongs to one customer.** For the demo it stays that way: all wagons
of a train have the same consignee, so exactly one decision is made per
incident, and its tier is the highest one involved. Several customers on one
train are structurally possible — `federations` is a list and
`wagon_consignees` binds per wagon — but no case uses it, and we do not claim it
in the demo.

Every cargo class in the train needs a consignment at the consignee, otherwise
the assessor has no stock and no urgency for that wagon. The validator tells you
which one is missing.

On top of that, a contract in `data/contracts/` whose `parties` name the new
customer and the supplier. **Contract data is specific to a (customer,
supplier) pair:** both contracting parties load the file, the operator's
contract agent administers it, and another customer never loads it. That is
row-level protection by the federation, not field-level protection by the
matrix — both apply, and the combination is the point.

## Adding a case

A directory `data/s4/` with `s4_incident.json`, `s4_train.json`,
`s4_reporter.json` and `s4_case.json`. The case file is the binding: it names
the sources, the federations, who ordered which wagon, the telemetry, the keys
and the **stored correct decision**.

Without `truth` the case is worthless for measurement — the hit rate is one of
our four numbers. `truth.tier` must match the maximum of the tiers
(1: `proceed`/`hold`/`cool` · 2: `reload`/`alt_transport`/`contact` ·
3: `stop_train`/`notify_authority`/`press`), and tier 2 needs one, tier 3 two
**distinct** `human_id`s in `keys`.

`truth.must_not` is optional and valuable: it names measures that would be
wrong. A hit that also picks a `must_not` measure does not count.

While the ground truth has not been confirmed by the data specialist, its
`_status` starts with `PROPOSAL`; the validator warns about it and the bench
reports the hit rate as unconfirmed.

## Reporters are humans

`reporter_role` is `driver`, `dispatcher`, `yard_staff`, `sensor` or `police` —
all **humans** (or devices), **not AI agents**. A reporter passes the incident
to the intake. Their name is personal data and never leaves the operator's
node.

The five **agent** roles are `intake`, `assessor`, `legal`, `supplier`,
`customer`. They are listed under `roles` in `field_catalogue.json` and must
never be confused with `reporter_role`.

## Holdout — please read

More cases come after `s1`–`s3`. Write four of them as `h1`–`h4` and **do not
show them to the engine track.** The rule engine `soteria/policy.py` is written
against the known cases; their hit rate is therefore only a consistency check.
The rate over the holdout cases is the only number that claims anything. It may
be bad — it just has to be honest.

Good holdout cases are uncomfortable: one where `proceed` is right even though
everything looks red. One with two measures that contradict each other. One
where a party does not answer (`offline_parties`). One where the grant was given
for different parameters than the decision carries (`truth.expect_refusal`
= `"grant_mismatch"`).

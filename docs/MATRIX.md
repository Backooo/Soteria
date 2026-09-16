# Need-to-know matrix

Generated from `data/schema/field_catalogue.json` (version 1), 16 fields.
**Do not edit by hand** — change the catalogue and regenerate:

```shell
uv run python -c "from soteria.matrix import matrix_table; print(matrix_table())"
```

`raw` = plain text · `coarse` = coarse class · `ampel` (traffic light) = gruen/gelb/rot (green/yellow/red) · `schwelle` (threshold) = above/below · `flag` = bool · `—` = not at all

| Field | Owner | held by | intake | assessor | legal | supplier | customer |
|---|---|---|---|---|---|---|---|
| `cargo_class` | train | carrier | coarse | coarse | — | raw | raw |
| `temperature_curve` | incident | carrier | raw | ampel | — | raw | raw |
| `customer_stock` | customer | customer | — | ampel | — | — | raw |
| `customer_urgency` | customer | customer | — | ampel | — | — | raw |
| `customer_trade` | customer | customer | — | coarse | raw | — | raw |
| `contact_person` | customer | customer | raw | — | — | — | raw |
| `contract_penalty` | contract | shared | — | schwelle | raw | raw | raw |
| `contract_deadline_h` | contract | shared | — | schwelle | raw | raw | raw |
| `liability_cap` | contract | shared | — | — | raw | raw | raw |
| `replacement_available` | supplier | supplier | — | ampel | — | raw | ampel |
| `cooling_required` | supplier | supplier | flag | flag | — | raw | raw |
| `route_weakness` | network | carrier | — | ampel | — | — | — |
| `alt_route_status` | network | carrier | raw | raw | — | — | — |
| `road_access` | network | carrier | raw | ampel | — | ampel | — |
| `locality_class` | network | carrier | raw | raw | coarse | — | — |
| `market_sensitive` | carrier | carrier | flag | flag | flag | — | — |

## How to read it

**Owner** is the record type that holds the raw value. **held by** is the party
type on whose node it physically lives — `shared` means: both contracting
parties load it, each only its own row.

Accessing a `—` field raises `EnvelopeError("not_in_matrix")`.

The assessor holds **no raw field of another party**. Where it sees `raw`, it is
operational data of its own organisation (alternative route, surroundings of
the accident site) — nothing a customer, a supplier or a contract entrusted to
it. `tests/test_matrix.py::test_the_assessor_holds_no_raw_field_of_another_party`
checks this.

Two layers of protection work together: the **matrix protects fields**, the
**federation protects rows**. Customer 2 does not see contract 1, because its
node never loads it.

To change it: see [`../data/schema/README.md`](../data/schema/README.md).

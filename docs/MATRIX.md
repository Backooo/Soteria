# Need-to-know-Matrix

Erzeugt aus `data/schema/field_catalogue.json` (Version 1), 16 Felder.
**Nicht von Hand aendern** — den Katalog aendern und neu erzeugen:

```shell
uv run python -c "from soteria.matrix import matrix_table; print(matrix_table())"
```

`raw` = Klartext · `coarse` = Grobklasse · `ampel` = gruen/gelb/rot · `schwelle` = above/below · `flag` = bool · `—` = gar nicht

| Feld | Eigentuemer | haelt | intake | assessor | legal | supplier | customer |
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

## Wie das zu lesen ist

**Eigentuemer** ist der Datensatztyp, der den Rohwert fuehrt. **haelt** ist der
Parteityp, auf dessen Knoten er physisch liegt — `shared` heisst: beide
Vertragsparteien laden ihn, jede nur ihre eigene Zeile.

Ein Zugriff auf ein `—`-Feld wirft `EnvelopeError("not_in_matrix")`.

Der Bewerter haelt **kein Rohfeld einer anderen Partei**. Wo er `raw` sieht, sind
es Betriebsdaten seiner eigenen Organisation (Alternativroute, Umgebung der
Unfallstelle) — nichts, was ein Kunde, ein Zulieferer oder ein Vertrag ihm
anvertraut hat. `tests/test_matrix.py::test_the_assessor_holds_no_raw_field_of_another_party`
prueft das.

Zwei Schutzebenen wirken zusammen: die **Matrix schuetzt Felder**, die
**Foederation schuetzt Zeilen**. Kunde 2 sieht Vertrag 1 nicht, weil sein Knoten
ihn nie laedt.

Aendern: siehe [`../data/schema/README.md`](../data/schema/README.md).

# Need-to-know-Matrix

Erzeugt aus `soteria/matrix.py`. Nicht von Hand aendern.

`raw` = Klartext · `coarse` = Grobklasse · `ampel` = gruen/gelb/rot · `schwelle` = above/below · `flag` = bool · `—` = gar nicht

| Feld | Eigentuemer | intake | assessor | legal | supplier | customer |
|---|---|---|---|---|---|---|
| `cargo_class` | supplier | coarse | coarse | — | raw | raw |
| `temperature_curve` | intake | raw | ampel | — | raw | raw |
| `customer_stock` | customer | — | ampel | — | — | raw |
| `contract_penalty` | legal | — | schwelle | raw | — | — |
| `route_weakness` | infra | — | ampel | — | — | — |
| `contact_person` | customer | raw | — | — | — | raw |
| `replacement_available` | supplier | — | ampel | — | raw | ampel |
| `market_sensitive` | infra | flag | flag | flag | — | — |


Ein Zugriff auf ein `—`-Feld wirft `EnvelopeError("not_in_matrix")`.

Der `assessor` haelt **kein einziges** `raw`-Feld: der Agent mit der meisten
Macht hat die wenigsten Rohdaten. Das ist keine Bescheidenheit, das ist die
Konstruktion.

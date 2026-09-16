# Datenschema — wie man es ändert

Alles hier ist **erfunden**. Keine echten Bahndaten, keine echten Personen, keine
echten Firmen. Das steht so in der Ehrlichkeitstabelle der Abgabe.

Prüfen, so oft du willst — braucht kein Modell, kein Netz, keinen SuperLink:

```shell
uv run python scripts/validate_data.py
uv run python scripts/validate_data.py data/s3          # nur ein Fall
```

Leere Ausgabe und Rückgabewert 0 heißt: in Ordnung.

## Warum es zwei Ebenen gibt

- **`vocabularies.json`** — die geschlossenen Wertelisten. Was ist eine gültige
  `cargo_class`, ein gültiges `Gewerbe`, eine gültige `urgency`.
- **`field_catalogue.json`** — die Need-to-know-Matrix als Daten: welches Feld
  wem in welcher Auflösung gezeigt wird, mit welchem Projektor und welcher
  Schwelle. `soteria/matrix.py` lädt diese Datei und validiert sie beim Import.

Damit ist die eigentliche Sicherheitsentscheidung — wer sieht was — an einer
Stelle lesbar und bestreitbar, ohne Python zu lesen.

## Die vier häufigen Änderungen

**Einen Wert hinzufügen** (neue Ladungsklasse, neues Gewerbe, neue Dringlichkeit):
in `vocabularies.json` eintragen. Fertig. Bei `cargo_class` und `trade` gehört
ein `coarse`-Eintrag dazu, weil der Bewerter nur die Grobklasse sieht.

**Ein Feld hinzufügen:** Eintrag unter `fields` in `field_catalogue.json`:

```json
"wagon_seal_intact": {
  "owner": "incident",
  "kind": "bool", "per": "wagon",
  "note": "Ob die Plombe des Wagens unverletzt ist.",
  "projectors": {"raw": "raw", "flag": "flag"},
  "visibility": {"intake": "raw", "assessor": "flag", "legal": "none",
                 "supplier": "none", "customer": "flag"}
}
```

Pflicht: `owner` ist ein Datensatztyp aus `record_types`; `visibility` nennt
**alle fünf** Rollen; für jede Auflösung außer `none` muss ein Projektor da sein;
jeder Projektorname muss in `known_projectors` stehen. Der Validator sagt sonst,
was fehlt.

**Ein Feld entfernen:** Eintrag löschen. Der Validator meldet danach jede
Datendatei, die es noch führt — aufräumen und nochmal laufen lassen.

**Wer was sieht ändern:** `visibility` bearbeiten. `none` heißt gar nicht und
erzeugt bei Zugriff `not_in_matrix`. Achtung: wenn du einer Rolle `raw` gibst,
verlässt der Rohwert den Knoten des Eigentümers — genau das soll die Matrix
verhindern, also nur mit Absicht.

**Eine neue ART von Projektion** (nicht Ampel, nicht Schwelle, sondern etwas
Neues): Funktion in `soteria/matrix.py` ergänzen, Namen in `known_projectors`
eintragen. Das ist der einzige Fall, der Code braucht.

## Eine Partei hinzufügen

Ein weiterer Kunde ist eine Datei in `data/parties/` und ein Eintrag in
`federations` der Falldatei. **Nichts im Code ändert sich** — `s3` fährt schon
zwei Kundenföderationen gleichzeitig.

```json
{
  "party_id": "customer_c4_grossmarkt",
  "party_type": "customer",
  "display_name": "Grossmarkt Sued (erfunden)",
  "records": {
    "customer": {
      "customer_trade": "wholesale_market",
      "consignments": {"perishable": {"customer_stock": 1.5, "customer_urgency": "elevated"}},
      "contact_person": [{"name": "...", "function": "...", "phone": "...", "hours": "..."}]
    }
  }
}
```

Dazu ein Vertrag in `data/contracts/`, dessen `parties` den neuen Kunden und den
Zulieferer nennt. **Vertragsdaten sind (Kunde, Zulieferer)-spezifisch:** beide
Vertragsparteien laden die Datei, der Vertragsagent des Betreibers führt sie, und
ein anderer Kunde lädt sie nie. Das ist Zeilenschutz durch die Föderation, nicht
Feldschutz durch die Matrix — beides wirkt, und die Kombination ist der Punkt.

## Einen Fall hinzufügen

Ein Verzeichnis `data/s4/` mit `s4_incident.json`, `s4_train.json`,
`s4_reporter.json` und `s4_case.json`. Die Falldatei ist die Bindung: sie nennt
die Quellen, die Föderationen, wer welchen Wagen bestellt hat, die Telemetrie,
die Schlüssel und die **hinterlegte richtige Entscheidung**.

Ohne `truth` ist der Fall wertlos für die Messung — die Trefferquote ist eine
unserer vier Zahlen. `truth.tier` muss zum Maximum der Stufen passen
(1: `proceed`/`hold`/`cool` · 2: `reload`/`alt_transport`/`contact` ·
3: `stop_train`/`notify_authority`/`press`), und Stufe 2 braucht einen,
Stufe 3 zwei **verschiedene** `human_id` in `keys`.

`truth.must_not` ist optional und wertvoll: es nennt Maßnahmen, die falsch wären.
Ein Treffer, der auch eine `must_not`-Maßnahme wählt, zählt nicht.

## Melder sind Menschen

`reporter_role` ist `driver`, `dispatcher`, `yard_staff`, `sensor` oder `police` —
alles **Menschen** (bzw. Geräte), **keine KI-Agenten**. Ein Melder gibt den
Vorfall an die Aufnahme. Sein Name sind Personendaten und verlässt den
Betreiberknoten nicht.

Die fünf **Agenten**rollen sind `intake`, `assessor`, `legal`, `supplier`,
`customer`. Sie stehen in `field_catalogue.json` unter `roles` und dürfen nie
mit `reporter_role` verwechselt werden.

## Holdout — bitte lesen

Nach `s1`–`s3` kommen weitere Fälle. Schreib davon vier als `h1`–`h4` und
**zeig sie dem Engine-Strang nicht.** Die Regelmaschine `soteria/policy.py` wird
gegen die bekannten Fälle geschrieben; deren Trefferquote ist deshalb nur eine
Konsistenzprüfung. Die Quote über die Holdout-Fälle ist die einzige Zahl, die
etwas behauptet. Sie darf schlecht sein — sie muss nur ehrlich sein.

Gute Holdout-Fälle sind unbequem: einer, in dem `proceed` richtig ist, obwohl
alles rot aussieht. Einer mit zwei Maßnahmen, die sich widersprechen. Einer, in
dem eine Partei nicht antwortet (`offline_parties`). Einer, in dem die Freigabe
für andere Parameter erteilt wurde als die Entscheidung trägt (`truth.expect_refusal`
= `"grant_mismatch"`).

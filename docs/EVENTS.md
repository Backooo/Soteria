# Ereignisvertrag — für die beiden Ansichten

Geschrieben aus den **echten** Ereignissen in `view/fixtures/`, nicht aus dem Plan.
Neu erzeugen:

```shell
uv run python scripts/record_run.py --all          # view/fixtures/s1.json, s2.json, s3.json
uv run python scripts/wire_proof.py --json --quiet  # view/fixtures/boundary.json
```

Ein neues Feld in einem Ereignis ist erlaubt. Ein umbenanntes oder entferntes Feld
nur nach Absprache.

**Beide Ansichten: eine HTML-Datei, CSS und JS inline, keine externen Requests** —
kein CDN, keine Google Fonts. Das Wifi teilen sich 58 Leute. Lade die JSON per
`fetch`, mit einem Datei-Auswahlfeld als Rückfall für `file://`.

**Die Ansicht zeigt nie einen Wert, der nicht im Ereignis steht.** Kein Nachschlagen
in `data/`, kein Anreichern. Eine Ansicht, die mehr zeigt als der Strom, ist selbst
ein Leck.

---

## Datei 1: `view/fixtures/<case>.json` — ein Vorfall

```json
{
  "case":    {"id": "s3", "title": "...", "report": {...}, "flags": [...],
              "parties": [{"party_id": "...", "party_type": "carrier"}], "truth": {...}},
  "outcome": {"decision": {...} | null, "refusal": "grant_mismatch" | null},
  "events":  [{"seq": 1, "t": 0.0, "type": "soteria.incident.open", ...}]
}
```

`seq` lückenlos ab 1. `t` Sekunden seit Beginn — zum Nachspielen im Originaltempo.
`case.truth` ist für die Fallübersicht (F2), **nicht** für die Live-Ansicht: der
Bewerter kennt die Wahrheit nicht, also zeigt die Live-Ansicht sie auch nicht.

### Ereignisse, in der Reihenfolge, in der sie kommen

| `type` | Felder | Was die Ansicht damit tut |
|---|---|---|
| `soteria.incident.open` | `case_id`, `incident_id`, `train_id`, `location`, `symptom`, `severity` (`low`/`medium`/`high`), `train_operational` (`normal`/`restricted`/`immobilized`), `track_blocked` (bool), `affected_wagons[]`, `cargo_classes_coarse[]`, `flags[]` | Kopfzeile. `cargo_classes_coarse` ist bereits vergröbert (`general`, `cooled`, `regulated`, `hazardous`) — die feine Ware steht nie im Strom |
| `soteria.role.ready` | `party_id`, `party_type` (`carrier`/`supplier`/`customer`), `speaks_as[]`, `online` | Eine Kachel je **Partei** (= Föderation). `carrier` spricht als `intake` und `legal` |
| `soteria.ask` | `from_role` (immer `assessor`), `field`, `reason_code`, `visibility` | Linie vom Bewerter weg, beschriftet mit Feld und Auflösung |
| `soteria.fact` | `role`, `field`, `visibility`, `value`, `scope`, `flags[]` | Die Antwort. Siehe „Werte" unten. `scope` ist die Wagennummer (`W02`) oder eine **grobe** Ladungsklasse, leer wenn es keinen Bezug gibt |
| `soteria.receipt` | `seq_in_chain`, `kind` (`incident`/`fact`/`refusal`/`disagreement`/`decision`), `hash`, `prev` | Quittungskette, als Liste kurzer Hashes. Jeder `prev` ist der `hash` davor |
| `collab.taint` | `source` | Nur in s3, unmittelbar vor der Quarantäne. Darf ignoriert werden |
| `soteria.quarantine` | `trigger_role`, `field`, `blocked_channels[]` | **Banner über die ganze Breite:** „Kursrelevant — alle Ausgänge gesperrt", mit der Kanalliste. Kommt nur in s3 |
| `soteria.disagreement` | `field`, `held`, `offered`, `role` | Zwei Parteien widersprechen sich über denselben Vertrag. Kommt in s1–s3 nicht vor, kann aber — dann gelb hervorheben |
| `soteria.refusal` | `actor`, `action`, `code`, `detail_chars` | **Rot, Code groß.** In s1–s3 null Mal — der Blockade-Moment kommt aus `boundary.json`, siehe unten |
| `soteria.coverage` | `answered`, `asked`, `parties_expected[]`, `parties_missing[]` | „13 von 13 beantwortet". Fehlt eine Partei: „Entschieden ohne customer_…" |
| `soteria.grant.required` | `measures[]`, `tier` (1/2/3), `keys_needed` (0/1/2) | So viele Schlüsselsymbole wie `keys_needed`, offen |
| `soteria.grant.given` | `measures[]`, `human_id`, `keys_have`, `keys_needed` | Einen Schlüssel schließen, `human_id` daneben. s2: einer, s3: zwei |
| `soteria.decision` | `measures[]`, `params`, `tier`, `grants[]`, `coverage`, `reason_code`, `receipt_hash`, `parties_missing[]`, `scopes` | **Die Entscheidungskarte**, Hauptbild. `receipt_hash` ist der Kopf der Kette über den ganzen Vorfall |
| `soteria.no_decision` | `code`, `detail_chars` | Statt `decision`, wenn eine Freigabe fehlt oder nicht passt (`no_grant`, `grant_mismatch`) |
| `soteria.done` | `elapsed_seconds`, `refusals`, `refusal_codes`, `asks`, `answers`, `quarantined`, `receipt_chain_verified`, `receipt_head` | Fußzeile. `receipt_chain_verified: true` sichtbar machen |

### Werte, auf die sich die Ansicht verlassen darf

| Wenn `visibility` ist | dann ist `value` | Darstellung |
|---|---|---|
| `ampel` | `"gruen"` / `"gelb"` / `"rot"` | Farbpunkt. Umlaut absichtlich weggelassen |
| `schwelle` | `"above"` / `"below"` | Pfeil. Bei `contract_penalty` heißt `above` „über der Schmerzgrenze"; bei `contract_deadline_h` heißt `below` „Frist wird knapp" |
| `flag` | `true` / `false` | Symbol |
| `coarse` | eine Grobklasse | Text |
| `raw` | Text oder Zahl | Text. **Nur** Betriebsdaten des Betreibers erreichen den Bewerter roh (`alt_route_status`, `locality_class`) |

Rollen: `intake`, `assessor`, `legal`, `supplier`, `customer` — das sind **Agenten**.
Melder (`driver`, `police` …) sind Menschen und tauchen im Strom nicht auf.

Maßnahmen: `proceed`, `hold`, `cool` (Stufe 1) · `reload`, `alt_transport`, `contact`
(Stufe 2) · `stop_train`, `notify_authority`, `press` (Stufe 3).

### Was in den drei Fällen passiert

| Fall | Entscheidung | Stufe | Schlüssel | Das Bild |
|---|---|---|---|---|
| s1 | `cool` | 1 | 0 | Temperatur gelb, Bestand grün → nur kühlen. Die Ampel verhindert das teure Umladen |
| s2 | `alt_transport` | 2 | 1 | Gleis blockiert, Dringlichkeit rot, Frist knapp → Umleitung, ein Schlüssel |
| s3 | `stop_train`, `notify_authority` | 3 | 2 | **Quarantäne-Banner**, zwei Schlüssel, Gefahrgut neben Wohnbebauung |

---

## Datei 2: `view/fixtures/boundary.json` — der Grenzbeweis

**Hier ist der Blockade-Moment.** Jeder Grenzübertritt, den eine Partei versuchen
könnte — jede Rolle fragt jeden fremden Knoten nach jedem Feld —, und was daraus wurde.

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

`outcome` ist `refused` (rot), `projected` (die Partei bekam eine Ampel/Schwelle
statt der Zahl) oder `raw` (die Matrix erlaubt es — **nicht** als Verstoß zeigen).
`violations` ist leer; stünde dort etwas, wäre es ein echtes Leck.

Die Demo-Zeile: **der Zulieferer fragt nach dem Bestand des Kunden →
`not_in_matrix`.** In `rows` zu finden mit `asker == "supplier"` und
`field == "customer_stock"`.

---

## Auftrag F1 — Live-Ansicht, `view/index.html`

Lädt `fixtures/s1.json` … `s3.json` (Auswahl), spielt `events` nach `t` ab. In dieser
Reihenfolge der Wichtigkeit:

1. `soteria.quarantine` als Banner (s3)
2. Die Entscheidungskarte aus `soteria.decision`, mit Stufe, Schlüsseln, `receipt_hash`
3. Die Parteikacheln aus `soteria.role.ready` mit den eingehenden Ampeln
4. Eine Zeitleiste der `ask`/`fact`-Paare
5. Ein Reiter „Grenzbeweis" aus `boundary.json`: die `refused`-Zeilen rot, oben die
   Zählung `attempts` / `refused` / `authorised_raw` / `violations`

## Auftrag F2 — Fallübersicht, `view/cases.html`

Lädt `fixtures/bench.json` (kommt als Nächstes). Bis dahin: die drei Vorfall-Dateien
direkt — `case.truth.measures` gegen `outcome.decision.measures`.

Muss zeigen: Wahrheit gegen Entscheidung je Fall, die Stufe, und die Ehrlichkeitstabelle.
**Die `truth`-Blöcke tragen noch `_status: "VORSCHLAG"`** — solange das so ist, als
„unbestätigt" kennzeichnen, nicht als Ergebnis.

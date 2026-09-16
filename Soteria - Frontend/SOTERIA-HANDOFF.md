# Soteria — Handoff und Bauplan

**Stand: 16. September 2026, Hackathon-Tag, geschrieben während Build 2.**
Dieses Dokument ist vollständig: Wer es liest, kann ohne Rückfragen bauen.
Kontext zur Veranstaltung steht in `PREP.md`, der Zustand des vorhandenen
Harness in `HANDOFF.md`, die Aufwärmübungen in `WARMUP.md`.

---

## 1 Was wir bauen

**Soteria — die Lebensretterin.** Ein Agententeam, das bei einem Schaden im
Güterverkehr in Minuten zu einer Entscheidung kommt, **ohne dass eine Partei
mehr erfährt, als sie erfahren darf.**

Ein Schaden wird gemeldet. Fünf Agenten, die zu verschiedenen Organisationen
gehören, tragen zusammen, was jeder für sich weiß. Der Bewerter entscheidet:
weiterfahren, halten, kühlen, umladen, alternativ transportieren, kontaktieren,
stoppen, melden. Tage später bewertet ein Mensch den Fall, und daraus lernt das
System — aber nur strengere Schwellen, niemals mehr Rechte.

### Warum das trägt

- **Kein Beteiligter darf alles wissen.** Der Zulieferer darf die Bestände und
  Dringlichkeiten des Kunden nicht sehen, der Kunde nicht die Schwachstellen der
  Infrastruktur, niemand von außen den Ladungsinhalt.
- **Ein großer Schaden ist kursrelevant.** Wer ihn früh ausplaudert, produziert
  Insiderhandel und Börsenverluste.
- **Heute läuft das über Telefonketten und eine WhatsApp-Gruppe**, in der am Ende
  alles steht. Unser Protokoll ist schneller als die Gruppe und hinterlässt als
  Einziges Quittungen.

### Passung zur Ausschreibung

| Anforderung | Wie Soteria sie erfüllt |
|---|---|
| Aufgabe automatisieren | Entscheidung in Minuten statt Telefonkonferenz |
| Schleifen zwischen Agenten | Nachfrage-Schleife, plus Nachbewertung durch Menschen |
| Verteilte Maschinen und Daten | Eine Föderation je Partei (Ausbaustufe), Rollen mit getrennten Daten (Minimum) |
| Sicherheit und Aufsicht | Need-to-know-Matrix in Code, Stufen nach Umkehrbarkeit, Quarantäne für Kursrelevantes, Quittungen |
| Auf SuperGrid lauffähig | AgentApp, keine Sonderinfrastruktur nötig |
| Auf Flower Hub veröffentlicht | `flwr app publish .` |

---

## 2 Plattform — geprüfte Fakten, nicht aus dem Gedächtnis

Alles hier wurde in dieser Session am Quellcode oder an der CLI verifiziert.

### API-Oberfläche von `AgentSession` (flwr 1.35)

```python
agent.connectors.tools([ref])     # Schemata holen — IMMER nur eine Referenz
agent.connectors.call(tool_call)  # ausführen, tool_call braucht "call_id"
agent.events.emit(event)          # strukturiertes Ereignis ans Frontend
agent.responses.create(request)   # Modellantwort
context.state.config_records      # Zustand über Läufe hinweg, unter context.locked()
```

Mehr gibt es nicht. **Kein `call_agent`, keine Delegation.** Deshalb existiert das
Harness: Jede erlaubte Übergabe wird dem Modell als synthetisches Funktionstool
`delegate_to_<rolle>` angeboten.

### Connectors (im Quellcode bestätigt)

Ohne Konto: `web_search`, `web_fetch`, `browser_use`, `start_automation`
Mit OAuth: `github`, `slack`, `notion`, `attio`

Für Soteria brauchen wir **keinen** Connector. Alle Daten sind lokale Fixtures.
Optional `web_fetch` für Wetter oder eine präparierte Seite im Angriffstest.

### Fallen, die Zeit gekostet haben

| Falle | Wirkung |
|---|---|
| CLI spricht Port **9093**, nicht 8000 | „Connection to the SuperLink is unavailable“ |
| `tools()` mit mehreren Referenzen | eine unbekannte Referenz kippt alle |
| fehlende `call_id` | Werkzeug läuft nicht, Audit behauptet das Gegenteil |
| SuperGrid: **5 Minuten pro Aufgabe** | langer Lauf stirbt ohne Vorwarnung |
| Modell-Timeout 180 s | mit `FLWR_MODEL_API_TIMEOUT` hochsetzen |
| gedeckelte Tokens bei denkenden Modellen | leere Antwort, Status trotzdem „completed“ |
| Kontoreferenz = alle Werkzeuge des Connectors | Rechte pro Aktion gibt es nicht |
| globales `flwr` ist **1.23.0** | zu alt, kennt weder `chat` noch `agentapp` — immer `uv run` im Projekt |

### CLI, die wir brauchen

```shell
uv run flwr login supergrid          # blockiert alles andere, Browser-Anmeldung
uv run flwr run . supergrid --stream --run-config 'agent.input="..."'
uv run flwr ls --format json         # Läufe, Grundlage für die Ansicht
uv run flwr log <RUN_ID>
uv run flwr app publish .            # Hub, bewertete Abgabe
uv run flwr app review @flwrlabs/hackathon-collab-agent-recipe   # Rezept ansehen, an der Signatur ABBRECHEN
```

**Blockierend:** In `~/.flwr/config.toml` fehlt der Eintrag für SuperGrid. Ohne ihn
bricht jeder CLI-Befehl mit „No SuperLink connection set“ ab:

```shell
printf '\n[superlink.supergrid]\naddress = "supergrid.flower.ai"\n' >> ~/.flwr/config.toml
uv run flwr login supergrid
```

### Wo Code läuft

Eine **AgentApp läuft serverseitig** (SuperExec neben dem SuperLink), **SuperNodes
führen ClientApps aus**. Agenten und Datenknoten sind also zwei verschiedene Apps.
Für Soteria im Minimum irrelevant: Alle fünf Rollen laufen in **einer** AgentApp.

---

## 3 Architektur

### Die fünf Rollen

| Rolle | Kennt | Darf nicht |
|---|---|---|
| **intake** (Schadensagent) | Meldung, Melder, Symptom, Ort, Zeit | Vertragsstrafen, Bestände, Streckendaten |
| **assessor** (Bewerter) | alles als Ampel oder Schwelle, nie als Zahl | Rohwerte, Klartext aus fremden Häusern |
| **legal** (Vertragsagent) | Vertrag, Fristen, Strafen, Haftung | Ansprechpartner, Bestände, Ladungsinhalt |
| **supplier** (Zulieferer) | Ware, Ersatz, Produktionslage, Kühlbedarf | Bestände und Dringlichkeiten des Kunden |
| **customer** (Kundenagent) | Ansprechpartner, Dringlichkeit, Bestände, Produktwissen | Streckenschwachstellen, Vertragsstrafen |

Der **assessor ist der Mediator**: Er sammelt, fragt nach, wägt ab und entscheidet.
Er ist bewusst der Agent mit den **wenigsten** Rohdaten.

### Die Need-to-know-Matrix (das eigentliche Produkt)

Nicht die Prompts, nicht die Rollen — diese Tabelle in Code ist das Produkt.
`raw` = Klartext, `ampel` = rot/gelb/grün, `schwelle` = über/unter Grenze, `—` = gar nicht.

| Feld | intake | assessor | legal | supplier | customer |
|---|---|---|---|---|---|
| `cargo_class` | grob | grob | — | raw | raw |
| `temperature_curve` | raw | ampel | — | raw | raw |
| `customer_stock` | — | **ampel** | — | — | raw |
| `contract_penalty` | — | **schwelle** | raw | — | — |
| `route_weakness` | — | **ampel** | — | — | — |
| `contact_person` | raw | — | — | — | raw |
| `replacement_available` | — | ampel | — | raw | ampel |
| `market_sensitive` | Flag | Flag | Flag | — | — |

Der assessor entscheidet also auf Ampeln und Schwellen. Er muss wissen, **dass**
der Bestand kritisch ist, nicht **wie hoch** er ist. Das ist dasselbe Scoresystem
wie in `MEDIATOR.html`, hier unter Zeitdruck.

### Entscheidungen nach Umkehrbarkeit

| Stufe | Maßnahmen | Freigabe |
|---|---|---|
| **1 autonom** | `ask`, `hold`, `cool` | keine, innerhalb Budget |
| **2 ein Schlüssel** | `reload`, `alt_transport`, `contact` | eine menschliche Freigabe |
| **3 zwei Schlüssel** | `stop_train`, `notify_authority`, `press` | zwei verschiedene Menschen |

Ein Modell erteilt sich niemals selbst eine Freigabe. Eine Freigabe gilt für genau
eine Maßnahme mit genau diesen Parametern — ein geändertes Feld ergibt
`grant_mismatch`.

### Quarantäne für Kursrelevantes

Sobald ein Agent eine Tatsache mit `market_sensitive = true` gelesen hat, ist für
den **Rest des Laufs** jeder ausgehende Kanal gesperrt (`web_search`, `web_fetch`,
`browser_use`, `start_automation`, `press`). Übernommen aus `collab/charter.py`,
dort schon getestet.

### Entscheiden mit Lücken

Antwortet eine Rolle nicht (Kunde nachts um drei), entscheidet das System trotzdem
und nennt die Abdeckung: *„Entschieden ohne customer. Fallback: `cool` + `hold`.“*
Konservative Vorgabe je Entscheidungstyp, sichtbar im Protokoll.

---

## 4 Der Umschlag

Bezeichner im Code englisch (passt zum vorhandenen `collab/`), Oberfläche deutsch.
**Kein Freitext überquert je eine Grenze.** Schemaprüfung im Code, keine Bitte im Prompt.

```python
Report   { incident_id, location, ts, cargo_class, symptom, reporter_role }
Ask      { to_role, field, reason_code }                  # Nachfrage
FactSheet{ role, fields{}, flags[], coverage, ts }        # nur erlaubte Felder
Advice   { measure, tier, reason_code, deadline_min }     # Empfehlung einer Rolle
Decision { measure, params{}, grants[], coverage, receipt_hash }
Review   { incident_id, human_verdict, quality_1_5, attribution{} }
```

**Feste Wertelisten**

```python
MEASURE   = ["proceed","hold","cool","reload","alt_transport","contact","stop_train","notify_authority","press"]
REASON    = ["cost","liability","time","safety","feasibility","confidentiality","missing_data"]
REFUSAL   = ["not_in_matrix","no_grant","grant_mismatch","quarantine","budget","quota","unknown_field"]
FLAG      = ["market_sensitive","hazmat","perishable","person_data"]
COVERAGE  = {"answered": int, "asked": int, "roles_missing": [str]}
```

Jede Ablehnung ist ein **getippter Grund**, kein Satz. Das ist gleichzeitig die
Datenquelle für die Ansicht und für die Lernschleife.

---

## 5 Ablauf eines Vorfalls

1. **Meldung** — Mensch oder Sensor erzeugt `Report`. Der intake prüft auf
   Vollständigkeit und stellt `Ask` an den Melder, bis die Pflichtfelder stehen.
2. **Verteilung** — der assessor fragt gezielt: je Rolle ein `Ask` pro Feld. Die
   Matrix entscheidet, ob er `raw`, `ampel` oder `schwelle` bekommt.
3. **Rückfragen** — jede Rolle darf ihrerseits `Ask` stellen (höchstens zwei Runden,
   Budget). Das ist der sichtbare Teil der Zusammenarbeit.
4. **Empfehlungen** — legal, supplier, customer liefern je ein `Advice`.
5. **Entscheidung** — der assessor wählt eine Maßnahme, die Stufe bestimmt die
   Freigaben. Alles bekommt eine verkettete Quittung.
6. **Nachbewertung** — Tage später `Review` durch einen Menschen. Daraus:
   Entscheidungsqualität pro Typ, Beitragszuschreibung pro Rolle, strengere Schwellen.

**Zeitbudget:** 240 Sekunden Gesamt, damit SuperGrids 5-Minuten-Grenze nie greift.
Jeder Modellaufruf bekommt die Restzeit als Timeout, wie in `collab/ledger.py`.

---

## 6 Was schon existiert und wiederverwendet wird

In `collab-agent/` (56 Tests grün, 1,18 s, heute geprüft):

| Datei | Was daraus wird |
|---|---|
| `collab/charter.py` | Rollen, erlaubte Übergaben, Werkzeugrechte, Quarantäne → **Need-to-know-Matrix ergänzen** |
| `collab/ledger.py` | Budget, Wanduhr, Quittungen, Ereignisse → **Stufen und Freigaben ergänzen** |
| `collab/team.py` | Dispatch, Nachfrage-Schleife, Fehlerabfang → **`Ask`-Runden ergänzen** |
| `collab/agent_app.py` | AgentApp, Rollenbesetzung → **fünf Soteria-Rollen** |
| `scripts/policy_demo.py` | deterministische Vorführung → **Vorlage für `incident_demo.py`** |
| `tests/test_collab.py` | Muster für Regressionstests |

Externe Reviews in `reviews/` (codex, grok, grok-brainstorm) haben vier echte Löcher
gefunden, die dort bereits geschlossen sind: Websuche als Exfiltrationskanal, die
Rollenaufteilung als Umgehung, Zeitbudget nur am Eingang geprüft, geschönte Zähler.
**Diese Fehler nicht erneut einbauen.**

---

## 7 Zielstruktur

```
soteria/
  charter.py       Rollen, Matrix, Stufen, Quarantäne     ← P1
  envelope.py      Typen, Wertelisten, Schemaprüfung      ← P1
  ledger.py        Budget, Quittungen, Freigaben          ← P1
  team.py          Dispatch, Ask-Runden, Ausfälle         ← P1/P2
  agent_app.py     AgentApp, Rollen, Ereignisse           ← P2
  grading.py       Review, Zuschreibung, Schwellen        ← P4
  scenarios/
    s1_pharma_cooling.json  ... s6_customer_offline.json  ← P4
scripts/
  incident_demo.py  deterministischer Bühnenlauf          ← P2
  bench.py          sechs Szenarien, Zahlen               ← P4
view/
  index.html        Live-Ansicht aus dem Ereignisstrom    ← P3
tests/
  test_matrix.py    Matrix hält, auch über Rollenketten
  test_tiers.py     Stufe 3 ohne zwei Schlüssel = Ablehnung
  test_quarantine.py  nach market_sensitive kein Ausgang
  test_coverage.py  Entscheidung ohne Rolle, Fallback greift
```

---

## 8 Die sechs Szenarien

Jedes mit hinterlegter richtiger Entscheidung, sonst ist die Trefferquote wertlos.

| # | Lage | Richtige Entscheidung | Was es prüft |
|---|---|---|---|
| 1 | Kühlausfall bei Pharma, Ersatzkühlung am nächsten Terminal | `cool` + `reload` | Dringlichkeit schlägt Kosten |
| 2 | Frischware, zwei Stunden Verzug, Kunde hat Bestand | `proceed` | Ampel Bestand verhindert teure Maßnahme |
| 3 | Kleiner Gefahrgutaustritt | `stop_train` + `notify_authority` | Stufe 3, zwei Schlüssel |
| 4 | Entgleisung, Strecke gesperrt, kursrelevant | `alt_transport`, kein Ausgang | Quarantäne greift sichtbar |
| 5 | Vertragsstrafe knapp über Schwelle gegen Umladekosten | `reload` | Schwelle statt Zahl reicht zum Abwägen |
| 6 | Kunde nicht erreichbar, Frischware | `cool` + `hold`, Abdeckung 4/5 | Entscheiden mit Lücke |

**Erfundene Daten, keine echten Bahndaten.** Das gehört so in die Präsentation.

---

## 9 Vier Stränge

| | Verantwortung | Erste Aufgabe | Fertig wenn |
|---|---|---|---|
| **P1 Grenze** | Matrix, Umschlag, Stufen, Quittungen | `envelope.py` und Matrix einfrieren, Attrappen verteilen | Ablehnungen kommen getippt, Tests grün |
| **P2 Agenten** | fünf Rollen, Ask-Schleife, Entscheidungslogik | SuperGrid-Login, dann intake allein | Szenario 1 läuft durch |
| **P3 Bühne** | Live-Ansicht, Zeitleiste, Ampeln, Blockaden | gegen aufgezeichneten Ereignisstrom bauen | Blockade ist auf dem Schirm sichtbar |
| **P4 Beweis** | Szenarien, Nachbewertung, Zahlen, Abgabe | sechs Szenarien mit Wahrheit schreiben | `bench.py` gibt vier Zahlen aus |

**Regel:** Nach dem Einfrieren ändert sich der Umschlag nur im Konsens. Jeder baut
gegen eine Attrappe der anderen Seite, damit niemand wartet. Beim Zusammenführen
fliegen die Attrappen raus — die Demo läuft nur auf echtem Code.

---

## 10 Zeitplan und Abbruchpunkte

| Zeit | Muss stehen | Sonst |
|---|---|---|
| +45 min | Matrix und Umschlag eingefroren | nichts anderes beginnen |
| 14:30 | Szenario 1 läuft, Ask-Schleife funktioniert | Ask-Runden auf eine begrenzen |
| 15:30 | Blockade und Quarantäne in der Ansicht sichtbar | Ansicht auf Ereignisliste reduzieren |
| 16:15 | sechs Szenarien, Zahlen stehen | auf drei Szenarien kürzen |
| 16:30 | **Funktionsstopp.** Hub, Repo, ein Probedurchlauf | — |
| 17:15 | Demo-Vorbereitung | — |

**Was zuerst geopfert wird:** Lernschleife, getrennte Föderationen, Modellvielfalt.
**Was bleiben muss:** ein Szenario mit sichtbarer Blockade und Quittung.

---

## 11 Was wir messen

1. **Zeit bis zur Entscheidung** gegen die dokumentierte Telefonkonferenz als Basis.
2. **Trefferquote** über sechs Szenarien gegen die hinterlegte Wahrheit.
3. **Dichtheit:** null Felder außerhalb der Matrix, dazu die Zahl blockierter Versuche.
4. **Verhalten mit Lücke:** Entscheidung und Abdeckung, wenn eine Rolle fehlt.

Die Zahlen kommen aus `bench.py`, nicht aus dem Bauchgefühl.

---

## 12 Demo, vier Minuten

| Zeit | Inhalt |
|---|---|
| 0:00 | Das Problem: Heute entscheidet eine Telefonkette, in der am Ende jeder alles weiß |
| 0:30 | Szenario 1 läuft live: Meldung, Nachfragen, Ampeln, Empfehlungen, Entscheidung |
| 1:45 | Der supplier fragt den Bestand des Kunden ab — **abgelehnt, `not_in_matrix`**, sichtbar |
| 2:15 | Szenario 4: kursrelevant, jeder Ausgang gesperrt, Quarantäne im Bild |
| 2:45 | Stufe 3: Zug stoppen braucht zwei Schlüssel, ein Feld geändert → `grant_mismatch` |
| 3:15 | Die vier Zahlen, dazu die Tabelle „echt gegen simuliert“ |
| 3:45 | Hub-Link und Repo |

---

## 13 Abgabe

- [ ] Läuft auf SuperGrid (`flwr run . supergrid --stream`)
- [ ] Auf Flower Hub veröffentlicht (`flwr app publish .`) — **vor 16:30, nicht um 17:00**
- [ ] GitHub-Repo öffentlich, README mit Architekturbild und Ehrlichkeitstabelle
- [ ] Projektbeschreibung: ein Absatz, der mit dem Problem beginnt, nicht mit der Technik
- [ ] `incident_demo.py` läuft deterministisch, ohne Modelllaune
- [ ] Ehrlichkeitstabelle: erfundene Szenarien, eine App statt fünf Rechner, keine echten Bahndaten

---

## 14 Offen und ungeprüft

- SuperGrid-Login der CLI fehlt noch, Eintrag in `~/.flwr/config.toml` ebenfalls.
- Hub-Publish wurde nie ausgeführt. Ein Probelauf vor 16:30 ist Pflicht.
- Getrennte Föderationen je Partei sind ungetestet; ob ein externer SuperNode über
  das Internet angenommen wird, wissen wir nicht.
- Das vorhandene Harness spricht das OpenAI-SDK statt `agent.responses.create`;
  Modell-Ein- und Ausgabe landen dadurch nicht im Flower-Lauf-Protokoll. Eine Jury
  kann das fragen. Umstellen ist eine echte Änderung, kein Handgriff.
- Kleine Modelle delegieren unzuverlässig. Für die Bühne zählt `incident_demo.py`
  mit gescriptetem Modell, echte Läufe nur als Zugabe.

## 15 Wo alles liegt

| Was | Wo |
|---|---|
| Vorhandenes Harness | `collab-agent/` |
| Externe Reviews | `reviews/codex.md`, `reviews/grok.md`, `reviews/grok-brainstorm.md` |
| Veranstaltungswissen | `PREP.md`, `HANDOFF.md` |
| Aufwärmen mit Flower | `WARMUP.md` |
| Ideenseiten (Quelle) | `IDEAS.html`, `MEDIATOR.html` → gebaut nach `site/` |
| Veröffentlicht | https://flower-agent-ideas.netlify.app · `/ideen.html` |
| Netlify-Projekt | `flower-agent-ideas`, ID `2a85fd71-4648-453c-9835-785480fe6fe1` |

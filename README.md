---
tags: [serverapp, clientapp, safety, federated, privacy]
dataset: [synthetic]
framework: [flwr]
---

# Soteria

Ein Güterzug prallt gegen ein Hindernis. Ein Gefahrgutwagen ist beschädigt, 300
Meter entfernt stehen Wohnhäuser, im Zug liegen Vorprodukte, auf die ein Werk
wartet. Heute entscheidet darüber eine Telefonkette aus Betreiber, Zulieferer,
Kunde und Vertragsabteilung — und am Ende steht in einer Gruppe alles, was jede
einzelne Partei nie hätte erfahren dürfen: die Bestände des Kunden, die
Vertragsstrafen, die Schwachstellen der Strecke. Bei einem Vorfall dieser Größe
ist das kursrelevant.

**Soteria entscheidet in Minuten, ohne dass eine Partei mehr erfährt, als sie
erfahren darf.** Jede Partei betreibt ihren eigenen Flower-Knoten und behält
ihre Daten. Der Bewerter fragt sie Feld für Feld und bekommt Ampeln und
Schwellen statt Zahlen. Maßnahmen sind nach Umkehrbarkeit gestuft, ein Zug wird
nur angehalten, wenn zwei verschiedene Menschen es freigeben, und jede Antwort
geht in eine verkettete Quittung.

## Die Aussage, und wie man sie nachprüft

> **Kein Rohwert erreicht eine Rolle, die ihn nicht haben darf.**

```shell
uv run python scripts/wire_proof.py
```

Das Skript lässt jede Rolle jeden fremden Knoten nach jedem Feld fragen — auch
nach dem, was sie nie fragen sollte — und sucht in den Antworten nach den
Rohwerten. Über drei Fälle:

| Grenzübertritte | abgelehnt | erlaubte Rohoffenlegung | Verstöße |
|---:|---:|---:|---:|
| 234 | 96 | 81 | **0** |

Die mittlere Spalte ist der Nennwert. Ein Test, der nur „0 Lecks" meldet, sagt
nichts; dieser weist aus, wie viel Offenlegung die Matrix *erlaubt*, und prüft
nur dort, wo sie es nicht tut. Die erste Fassung hatte diesen Nennwert nicht —
und meldete erlaubte Offenlegung als Leck. Mit Nennwert fand sie dann zwei echte
Fehler, die behoben sind (siehe Git-Historie).

Drei Riegel wirken unabhängig voneinander:

1. **Der Knoten hat es nicht.** Jeder Knoten lädt nur die Daten seiner Partei.
   Der Vertrag eines anderen Kunden existiert dort nicht im Speicher.
2. **Die Matrix projiziert.** Der Bewerter erfährt, *dass* der Bestand knapp
   ist, nie *wie* knapp.
3. **Der Transport trägt nur Skalare.** Flowers `ConfigRecord` nimmt kein
   Objekt auf. Ein Rohdatensatz lässt sich nicht verschicken, selbst wenn die
   Matrix falsch gepflegt wäre.

## Die Need-to-know-Matrix ist Daten

[`data/schema/field_catalogue.json`](data/schema/field_catalogue.json) legt fest,
wer welches Feld in welcher Auflösung sieht. `soteria/matrix.py` lädt und
validiert die Datei beim Import; ein kaputter Katalog erreicht nie einen Lauf.
Ein neues Feld ist ein JSON-Eintrag, keine Codeänderung. Tabelle:
[`docs/MATRIX.md`](docs/MATRIX.md). Anleitung:
[`data/schema/README.md`](data/schema/README.md).

Die **Matrix schützt Felder, die Föderation schützt Zeilen**: Verträge sehen
beide Vertragsparteien, aber Kunde 2 lädt Vertrag 1 nie.

## Architektur

```
                    SuperLink
                        │
   ServerApp  assessor  │  query.ask_field, ein Feld je Nachricht
   (Bewerter)           │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
   SuperNode        SuperNode        SuperNode
   carrier          supplier         customer
   Aufnahme +       Ersatz,          Bestand, Dringlich-
   Vertragsagent,   Kühlbedarf       keit, Ansprechpartner
   Strecke, Umgebung
```

Die Parteien kommen aus der Falldatei, nicht aus dem Code: ein weiterer Kunde ist
ein weiterer Eintrag.

## Die vier Zahlen

```shell
uv run python scripts/bench.py
```

| | |
|---|---|
| **Zeit** | Logik ~10 ms · echte Föderation 69 s im Median, 127 s maximal · Basislinie Telefonkette 47 min — **eine Annahme, keine Messung** |
| **Treffer** | 3/3 auf den bekannten Fällen · Begründung passt 2/3 · **keine Holdout-Fälle, Wahrheit unbestätigt** |
| **Dichtheit** | 234 Übertritte, 96 abgelehnt, 81 erlaubt, 0 Verstöße |
| **Lücke** | 3/3 Fälle entschieden, obwohl der Kunde schweigt |

## Loslegen

```shell
uv sync
uv run pytest -q                            # 151 Tests
uv run python scripts/validate_data.py      # Datenbaum prüfen
uv run python scripts/wire_proof.py         # der Grenzbeweis, ohne Netz
uv run python scripts/bench.py              # die vier Zahlen
uv run python scripts/record_run.py --all   # Ereignisströme für die Ansichten

./scripts/federation.sh up s3               # SuperLink + drei Parteiknoten
./scripts/federation.sh run s3              # der Vorfall über echte Nachrichten
./scripts/federation.sh down
```

`~/.flwr/config.toml` braucht:

```toml
[superlink.carrier-fed]
address = "127.0.0.1:8000"
insecure = true
```

## Die drei Fälle

| Fall | Lage | Entscheidung | Stufe |
|---|---|---|---|
| s1 | Kleines Hindernis, Kühlaggregat an einem Frischwarenwagen | `cool` | 1 — autonom |
| s2 | Gleis blockiert, Klinikversorgung im Zug | `alt_transport` | 2 — ein Schlüssel |
| s3 | Aufprall, Gefahrgutwagen beschädigt, Wohnbebauung 300 m | `stop_train`, `notify_authority` | 3 — zwei Schlüssel, Quarantäne |

## Echt gegen simuliert

| Behauptung | Echt | Nicht echt |
|---|---|---|
| Kein Rohwert erreicht eine Rolle, die ihn nicht haben darf | 234 Übertritte gemessen, mit Nennwert | — |
| Drei Parteien, drei Knoten | drei SuperNodes, echte Flower-Nachrichten, alle drei Fälle getroffen | alle drei laufen auf **einem** Rechner |
| Eine Föderation je Partei | eine Föderation mit drei Parteiknoten | drei SuperLinks erreicht ein ServerApp nicht gemeinsam — **Ausbaustufe** |
| Agententeam | ein Bewerter als ServerApp, Parteien als ClientApps | der Bewerter ist eine **Regelmaschine**, kein Sprachmodell |
| Trefferquote 3/3 | gemessen | Regeln gegen genau diese Fälle geschrieben; Wahrheit vom Engine-Strang **vorgeschlagen, nicht bestätigt**; **kein Holdout** |
| Minuten statt Telefonkette | Logik und Föderation gemessen | Basislinie 47 min ist eine **Annahme** |
| Daten | Schema, Validierung | **alles erfunden** — keine echten Bahndaten, Personen, Firmen |
| Quittungen | Kette über den ganzen Vorfall, nachprüfbar | 16 Hex-Zeichen, eine Prüfsumme, keine Kryptografie für den Ernstfall |

Was nicht geprüft ist: [`docs/RISKS.md`](docs/RISKS.md).

## Dokumente

| | |
|---|---|
| Need-to-know-Matrix | [`docs/MATRIX.md`](docs/MATRIX.md) |
| Datenschema ändern | [`data/schema/README.md`](data/schema/README.md) |
| Ereignisvertrag für die Ansichten | [`docs/EVENTS.md`](docs/EVENTS.md) |
| Gemessenes, Plattformbefunde, Offenes | [`docs/RISKS.md`](docs/RISKS.md) |
| Bauplan | [`docs/superpowers/plans/2026-09-16-soteria.md`](docs/superpowers/plans/2026-09-16-soteria.md) |

## Lizenz

Apache 2.0, siehe [LICENSE](LICENSE).

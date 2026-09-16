# Risiken und Befunde, am Tag gemessen

Was hier steht, ist gemessen oder am Quellcode nachgelesen — nicht erinnert.

## Die Föderation läuft — gemessen 15:25

Drei SuperNodes, ein SuperLink, echte Flower-Nachrichten, lokal auf einem Rechner:

| Fall | Entscheidung | Stufe | Schlüssel | Wahrheit | Dauer |
|---|---|---|---|---|---|
| s1 | `cool` | 1 | keine | TREFFER | 69,1 s |
| s2 | `alt_transport` | 2 | ops-lead-rheinrail-1 | TREFFER | **126,9 s** |
| s3 | `stop_train`, `notify_authority` | 3 | ops-lead + safety-officer | TREFFER | 68,0 s |

In s3 greift die Quarantäne (`browser_use`, `press`, `start_automation`,
`web_fetch`, `web_search` gesperrt).

**Befund zur Begründung:** s2 trifft die Maßnahmen, begründet sie aber mit
`feasibility`; die hinterlegte Wahrheit sagt `safety`. Die Trefferquote zählt
Maßnahmen, nicht Gründe — das ist offen auszuweisen, nicht zu verschweigen.

**Risiko Laufzeit:** 69–127 s bei 13 Nachfragerunden, mit großer Streuung. Das
passt zu Anlaufkosten der ClientApp-Unterprozesse, nicht zu der Logik (lokal
ohne Föderation: unter 0,1 s je Fall). Für die Bühne heißt das:
**den aufgezeichneten Lauf (`view/fixtures/`) zeigen**, den echten Lauf parallel
starten. Eine zwei Minuten stehende Bühne verliert jede Jury. Behebbar, falls Zeit
bleibt: alle Felder in **eine** Nachricht je Knoten bündeln statt 13 Runden.

## Plattformbefunde, am Quellcode belegt

1. **Ein FAB mit `agentapp` führt die ServerApp nie aus.**
   `superlink/servicer/control/control_handlers.py:2159`:
   `TaskType.AGENT_APP if "agentapp" in components else TaskType.SERVER_APP`.
   Die Validierung (`common/config.py:355-388`) erlaubt alle drei Komponenten
   gleichzeitig; die Ausführung wählt genau eine. Soteria ist deshalb ein
   ServerApp/ClientApp-Bundle. **Eine AgentApp wäre ein zweites Bundle.**

2. **Modell und Föderation treffen sich nicht.** `AgentSession` hat kein `Grid`
   (`agentapp/base.py`), und `FLWR_RUNTIME_BASE_URL`/`_API_KEY` werden nur für
   AgentApps gesetzt (`supercore/task_process/agent/run_agentapp.py`). Die
   Parteiknoten haben also kein Modell — und brauchen keins, eine Projektion ist
   eine Funktion.

3. **Der Control-Port hat sich geändert.** `uv sync` hat **flwr 1.37.0** gezogen.
   Der SuperLink bedient die Control API dort per HTTP auf **8000**, nicht wie in
   1.35 auf 9093. Die Notiz aus dem Handoff „9093, nicht 8000" ist für diese Version
   **falsch**. `~/.flwr/config.toml` → `[superlink.carrier-fed] address = "127.0.0.1:8000"`.

4. **`Grid.create_message` ist in 1.37 veraltet** — ersetzt durch den
   `Message`-Konstruktor.

## Build

- `flwr build` validiert den Komponentenpfad (fehlendes Modul = Abbruch).
- `fab-include`-Muster müssen **mindestens eine Datei** treffen, sonst Abbruch.
- Das FAB enthält den Code und alle Daten unter `data/` (41 Dateien).

## Offen

- **`flwr app publish .` nie ausgeführt.** Braucht `flwr login supergrid`, und das
  blockiert die Shell mit einer Browser-Anmeldung. Muss vor 16:30 laufen.
- **SuperGrid:** Soteria braucht eigene SuperNodes mit `node-config`. Ob SuperGrid
  externe SuperNodes annimmt, ist ungeprüft. Der lokale SuperLink ist der
  gesicherte Weg (Track 2 erlaubt ihn).
- **Drei Rechner:** nicht versucht. Der Code liest die Partei aus `--node-config`,
  also sollte es gehen — „sollte" ist nicht geprüft.
- **Die `truth`-Blöcke sind `VORSCHLAG`** des Engine-Strangs, vom Datenspezialisten
  nicht bestätigt. Solange das so ist, ist die Trefferquote eine Zahl über die
  eigene Vermutung und gehört so gekennzeichnet in die Präsentation.
- **Keine AgentApp.** Siehe Befund 1. Die Pflichtabgabe nennt „working AgentApp";
  Track 2 erlaubt eine ServerApp. Mit den Organisatoren klären.
- **Kein Holdout.** Ohne `h1`–`h4` ist jede Trefferquote nur eine Konsistenzprüfung.

## Übersprungener geerbter Test

`tests/test_harness.py::test_demo_charter_is_valid_and_demonstrates_the_policy`
prüft das geerbte `librarian`/`researcher`-Roster. Übersprungen, nicht gelöscht,
damit die Herkunft sichtbar bleibt.

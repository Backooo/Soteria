# Risiken und Befunde, am Tag gemessen

## `flwr build` — Publish-Rauchtest, 13:52 (Task 1)

Drei Befunde, alle beim ersten Versuch, alle vor 14:00 statt um 16:25:

1. **Der Build validiert den Komponentenpfad.** Ohne `soteria/agent_app.py`:
   `Unable to load module soteria.agent_app`. Ein Publish kann also nicht
   gelingen, solange die Komponente fehlt.
2. **`fab-include`-Muster müssen mindestens eine Datei treffen.**
   `"soteria/scenarios/*.json"` bricht den Build mit *Pattern in "fab-include"
   did not match any files*, solange das Verzeichnis leer ist. Deshalb liegt
   `s1_pharma_cooling.json` schon in Phase 0.
3. Danach: `Successfully built flwrlabs.soteria.0-2-0.<hash>.fab`.

**Offen:** `flwr app publish .` wurde noch nicht ausgeführt — es braucht
`flwr login supergrid`, und der Befehl blockiert die Shell mit einer
Browser-Anmeldung. Vor 16:30 nachziehen (Task 14).

## Platzhalter, der noch im Baum liegt

`soteria/agent_app.py` ist derzeit ein Stub, der `NotImplementedError` wirft.
Er existiert nur, damit `flwr build` während Phase 0 bis 2 grün bleibt.
**Task 14 ersetzt ihn.** Wird Task 14 geopfert, muss der Stub weg und der
`agentapp`-Eintrag aus `pyproject.toml` — ein reines ServerApp/ClientApp-Bundle
ist eine gültige Abgabe für Track 2.

## Übersprungener geerbter Test

`tests/test_harness.py::test_demo_charter_is_valid_and_demonstrates_the_policy`
prüft das geerbte `librarian`/`researcher`-Roster. Für Soteria übernimmt
`tests/test_roles.py` (Task 6) diese Aufgabe mit den fünf Rollen. Der Test ist
übersprungen, nicht gelöscht, damit die Herkunft sichtbar bleibt.

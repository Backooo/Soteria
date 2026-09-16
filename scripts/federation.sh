#!/usr/bin/env bash
# Die Foederation lokal: ein SuperLink, ein SuperNode je Partei des Falls.
#
#   ./scripts/federation.sh up s3      # startet SuperLink und die Knoten von s3
#   ./scripts/federation.sh run s3     # faehrt den Vorfall gegen die Knoten
#   ./scripts/federation.sh down       # raeumt auf
#
# Die Parteien kommen aus data/<case>/<case>_case.json -> federations. Ein
# weiterer Kunde dort ist hier ein weiterer Knoten; das Skript kennt keine Namen.
#
# Ports, und warum -- am Log von flwr 1.37 abgelesen, nicht erinnert:
#   9092  Fleet API          -- hierhin verbinden sich die SuperNodes
#   8000  Control + Runtime  -- hierhin spricht die flwr CLI. In flwr 1.35 war
#                               das 9093; ab 1.36/1.37 bedient der SuperLink die
#                               Control API per HTTP auf 8000. Die alte Notiz
#                               "9093, nicht 8000" ist fuer diese Version FALSCH.
#   9094+ Runtime-HTTP-API, ein Port je SuperNode
set -euo pipefail

CMD="${1:-up}"
CASE="${2:-s1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/.federation"
mkdir -p "$RUN"
cd "$ROOT"

down() {
  for f in "$RUN"/*.pid; do
    [ -e "$f" ] || continue
    pid="$(cat "$f")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "==> stoppe $(basename "$f" .pid) ($pid)"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$f"
  done
}

wait_port() {
  for _ in $(seq 1 60); do
    nc -z 127.0.0.1 "$1" 2>/dev/null && return 0
    sleep 0.25
  done
  return 1
}

parties() {
  uv run python -c "
import json, sys
d = json.load(open('data/$CASE/${CASE}_case.json'))
for f in d['federations']:
    print(f['party_id'])
"
}

case "$CMD" in
  down)
    down
    echo "==> abgeraeumt"
    ;;

  up)
    down
    [ -f "data/$CASE/${CASE}_case.json" ] || { echo "kein Fall $CASE" >&2; exit 2; }
    rm -f "$RUN/state.db"

    echo "==> SuperLink (Fleet 9092, Control 8000)"
    uv run flower-superlink --insecure --database "$RUN/state.db" \
      >"$RUN/superlink.log" 2>&1 &
    echo $! > "$RUN/superlink.pid"
    wait_port 9092 || { echo "SuperLink kam nicht hoch, siehe $RUN/superlink.log" >&2; exit 1; }
    wait_port 8000 || { echo "Control API kam nicht hoch, siehe $RUN/superlink.log" >&2; exit 1; }

    PORT=9094
    for PARTY in $(parties); do
      echo "==> SuperNode party=$PARTY case=$CASE (Runtime-API $PORT)"
      uv run flower-supernode --insecure \
        --superlink 127.0.0.1:9092 \
        --port "$PORT" \
        --node-config "party=\"$PARTY\" case=\"$CASE\"" \
        >"$RUN/$PARTY.log" 2>&1 &
      echo $! > "$RUN/$PARTY.pid"
      PORT=$((PORT + 1))
    done
    sleep 4
    echo
    echo "==> $(parties | wc -l | tr -d ' ') Knoten fuer $CASE gestartet. Logs: $RUN/"
    echo "==> weiter mit: ./scripts/federation.sh run $CASE"
    ;;

  run)
    uv run flwr run . carrier-fed --stream --run-config "case=\"$CASE\""
    ;;

  *)
    echo "usage: $0 {up|run|down} [case]" >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
# The federation, locally: one SuperLink, one SuperNode per party of the case.
#
#   ./scripts/federation.sh up s3      # starts the SuperLink and the nodes of s3
#   ./scripts/federation.sh run s3     # runs the incident against the nodes
#   ./scripts/federation.sh down       # cleans up
#
# The parties come from data/<case>/<case>_case.json -> federations. One more
# customer there is one more node here; the script knows no names.
#
# Ports, and why -- read off the flwr 1.37 log, not from memory:
#   9092  Fleet API          -- the SuperNodes connect here
#   8000  Control + Runtime  -- the flwr CLI talks here. In flwr 1.35 this was
#                               9093; from 1.36/1.37 the SuperLink serves the
#                               Control API over HTTP on 8000. The old note
#                               "9093, not 8000" is WRONG for this version.
#   9094+ Runtime HTTP API, one port per SuperNode
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
      echo "==> stopping $(basename "$f" .pid) ($pid)"
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
    echo "==> cleaned up"
    ;;

  up)
    down
    [ -f "data/$CASE/${CASE}_case.json" ] || { echo "no case $CASE" >&2; exit 2; }
    rm -f "$RUN/state.db"

    echo "==> SuperLink (Fleet 9092, Control 8000)"
    uv run flower-superlink --insecure --database "$RUN/state.db" \
      >"$RUN/superlink.log" 2>&1 &
    echo $! > "$RUN/superlink.pid"
    wait_port 9092 || { echo "SuperLink did not come up, see $RUN/superlink.log" >&2; exit 1; }
    wait_port 8000 || { echo "Control API did not come up, see $RUN/superlink.log" >&2; exit 1; }

    PORT=9094
    for PARTY in $(parties); do
      echo "==> SuperNode party=$PARTY case=$CASE (runtime API $PORT)"
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
    echo "==> $(parties | wc -l | tr -d ' ') nodes started for $CASE. Logs: $RUN/"
    echo "==> next: ./scripts/federation.sh run $CASE"
    ;;

  run)
    uv run flwr run . carrier-fed --stream --run-config "case=\"$CASE\""
    ;;

  *)
    echo "usage: $0 {up|run|down} [case]" >&2
    exit 2
    ;;
esac

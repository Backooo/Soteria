"""The live bridge: it forwards only real ServerApp events and never runs unchecked input."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fastapi.testclient import TestClient  # noqa: E402

import bridge  # noqa: E402


def test_an_event_line_is_parsed_even_behind_ansi_and_a_log_prefix():
    raw = '\x1b[32mINFO\x1b[0m :      SOTERIA_EVENT {"seq": 3, "type": "soteria.ask", "field": "x"}\n'
    kind, event = bridge.parse_line(raw)
    assert kind == "event"
    assert event == {"seq": 3, "type": "soteria.ask", "field": "x"}


def test_infrastructure_output_stays_a_log_line():
    kind, text = bridge.parse_line("\x1b[33mLoading project configuration...\x1b[0m\n")
    assert (kind, text) == ("log", "Loading project configuration...")


def test_a_broken_event_line_is_not_invented_into_an_event():
    assert bridge.parse_line("SOTERIA_EVENT {not json")[0] == "log"
    assert bridge.parse_line('SOTERIA_EVENT {"no_type": 1}')[0] == "log"


def test_an_unknown_case_never_reaches_a_command_line():
    client = TestClient(bridge.app)
    assert client.get("/api/run/..%2F..%2Fetc/stream").status_code == 404
    assert client.get("/api/run/s1;rm -rf/stream").status_code == 404
    assert client.get("/api/run/h99/stream").status_code == 404


def test_health_lists_the_real_cases():
    body = TestClient(bridge.app).get("/api/health").json()
    assert body["ok"] is True
    assert {"s1", "s2", "s3"} <= set(body["cases"])

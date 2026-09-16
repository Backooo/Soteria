"""Live bridge: runs a real incident on the real federation and streams its events.

    uv run python scripts/bridge.py            # listens on 127.0.0.1:8765

`GET /api/run/{case}/stream` is a Server-Sent-Events stream. For every request
the bridge:

1. restarts the local federation for that case (`scripts/federation.sh up`):
   a fresh SuperLink and one SuperNode per party of the case file,
2. builds and runs the app on it (`flwr run . carrier-fed --stream`), so the
   ServerApp and ClientApps come from the FAB built out of this directory,
3. forwards every `SOTERIA_EVENT` line the ServerApp prints as one SSE message.

Nothing here replays a recording. If the federation does not come up or the run
produces no events, the stream says so with `soteria.bridge.error` -- there is no
fallback to fixture files. Infrastructure output (SuperLink/SuperNode startup,
flwr install logs) is forwarded as `soteria.bridge.log`, so the console can show
that real processes ran.

Binds to 127.0.0.1 only: the bridge starts processes and must not be reachable
from the network.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from soteria.cases import available_cases  # noqa: E402

EVENT_PREFIX = "SOTERIA_EVENT "
FEDERATION = "carrier-fed"
HOST, PORT = "127.0.0.1", 8765
# A live run takes 50-85 s with the model call on SuperGrid; leave headroom.
RUN_TIMEOUT_SECONDS = 420.0
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

app = FastAPI(title="Soteria live bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):5173",
    allow_methods=["GET"],
    allow_headers=["*"],
)
_run_lock = asyncio.Lock()


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def parse_line(raw: str) -> tuple[str, Any]:
    """Classify one output line: ('event', dict) for a SOTERIA_EVENT, else ('log', text)."""
    line = ANSI.sub("", raw).rstrip("\r\n")
    at = line.find(EVENT_PREFIX)
    if at >= 0:
        try:
            event = json.loads(line[at + len(EVENT_PREFIX):])
        except json.JSONDecodeError:
            return "log", line
        if isinstance(event, dict) and isinstance(event.get("type"), str):
            return "event", event
    return "log", line


async def _stream_process(
    argv: list[str], source: str, env: dict[str, str], request: Request, counter: dict[str, int]
) -> AsyncIterator[str]:
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=ROOT, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    try:
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    raise asyncio.CancelledError
                yield ": keep-alive\n\n"
                continue
            if not raw:
                break
            kind, payload = parse_line(raw.decode("utf-8", errors="replace"))
            if kind == "event":
                counter["events"] += 1
                yield _sse({**payload, "origin": "federation"})
            elif payload.strip():
                yield _sse({"type": "soteria.bridge.log", "source": source, "line": payload[:400]})
        counter[f"{source}_exit"] = await proc.wait()
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "busy": _run_lock.locked(), "cases": list(available_cases())}


@app.get("/api/run/{case_id}/stream")
async def run_stream(case_id: str, request: Request) -> StreamingResponse:
    # Never pass unchecked text into a command line.
    if case_id not in available_cases():
        raise HTTPException(404, f"unknown case {case_id!r}")
    if _run_lock.locked():
        raise HTTPException(409, "a live run is already in progress")

    async def generate() -> AsyncIterator[str]:
        async with _run_lock:
            started = time.monotonic()
            counter = {"events": 0}
            env = {**os.environ, "PYTHONUNBUFFERED": "1", "NO_COLOR": "1"}
            yield _sse({"type": "soteria.bridge.stage", "stage": "federation_up", "case_id": case_id,
                        "detail": "restarting SuperLink and one SuperNode per party"})
            try:
                async for chunk in _stream_process(
                    ["./scripts/federation.sh", "up", case_id], "federation", env, request, counter
                ):
                    yield chunk
                if counter.get("federation_exit") != 0:
                    yield _sse({"type": "soteria.bridge.error", "stage": "federation_up",
                                "detail": f"federation.sh up exited with {counter.get('federation_exit')}"})
                    return

                yield _sse({"type": "soteria.bridge.stage", "stage": "flwr_run", "case_id": case_id,
                            "detail": f"flwr run . {FEDERATION} --stream (builds the FAB from Soteria/)"})
                run = _stream_process(
                    ["uv", "run", "flwr", "run", ".", FEDERATION, "--stream",
                     "--run-config", f'case="{case_id}"'],
                    "flwr", env, request, counter,
                )
                deadline = started + RUN_TIMEOUT_SECONDS
                async for chunk in run:
                    yield chunk
                    if time.monotonic() > deadline:
                        yield _sse({"type": "soteria.bridge.error", "stage": "flwr_run",
                                    "detail": f"no result after {RUN_TIMEOUT_SECONDS:.0f}s"})
                        return

                elapsed = round(time.monotonic() - started, 1)
                if counter["events"] == 0:
                    yield _sse({"type": "soteria.bridge.error", "stage": "flwr_run",
                                "detail": "the run produced no Soteria events "
                                          f"(flwr exit {counter.get('flwr_exit')})"})
                    return
                yield _sse({"type": "soteria.bridge.finished", "case_id": case_id,
                            "events": counter["events"], "flwr_exit": counter.get("flwr_exit"),
                            "elapsed_seconds": elapsed})
            except asyncio.CancelledError:
                return

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")

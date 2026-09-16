"""The assessor's reasoning step, running as a Flower AgentApp on SuperGrid.

Input is only what the assessor may see: traffic lights, thresholds, flags,
coarse classes and the driver's report. No raw party data ever reaches this app.

The model access comes from the Flower runtime (FLWR_RUNTIME_BASE_URL /
FLWR_RUNTIME_API_KEY, set by Flower for every AgentApp) -- no own API key.

Output: every model stream event goes to `agent.events`, and one final stdout
line `SOTERIA_LLM {json}` carries the model name and the answer text. The local
assessor parses that line strictly and applies its guardrails.
"""

import base64
import json
import os

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context
from openai import OpenAI

app = AgentApp()

MEASURES = {
    "proceed": 1, "hold": 1, "cool": 1,
    "reload": 2, "alt_transport": 2, "contact": 2,
    "stop_train": 3, "notify_authority": 3, "press": 3,
}
REASON_CODES = ("safety", "feasibility", "time", "liability", "cost", "missing_data")

INSTRUCTIONS = f"""You are the assessor in a freight-rail incident response.
You never see raw data from other companies. You receive only traffic lights
(gruen = green, gelb = yellow, rot = red), thresholds (above/below), boolean flags
and coarse cargo classes, plus the driver's report.

Choose the measures to take now. Prefer the most reversible measures that make
the situation safe. Safety comes before feasibility, feasibility before liability,
liability before cost. A damaged hazmat wagon on an immobilized train, or near
inhabited areas, requires stopping the train and notifying the authority. A
blocked track with an available diversion calls for alternative transport. A
yellow temperature with cooling required and a green customer stock calls only
for cooling.

Available measures and their reversibility tier:
{chr(10).join(f"- {m} (tier {t})" for m, t in MEASURES.items())}

Answer with ONE JSON object and nothing else:
{{"measures": ["<measure>", ...], "reason_code": "<one of {', '.join(REASON_CODES)}>",
  "rationale": "<max two sentences, no invented numbers>"}}"""


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    """Decide measures for one incident from projected signals."""
    encoded = context.run_config.get("agent.input_b64")
    model = str(context.run_config.get("agent.model") or "flower-endeavor-v1.0")
    if not isinstance(encoded, str) or not encoded.strip():
        raise ValueError("agent.input_b64 must carry the projected incident signals")
    signals = json.loads(base64.b64decode(encoded).decode("utf-8"))

    client = OpenAI(
        base_url=os.environ["FLWR_RUNTIME_BASE_URL"],
        api_key=os.environ["FLWR_RUNTIME_API_KEY"],
        max_retries=0,
    )
    stream = client.responses.create(
        model=model,
        instructions=INSTRUCTIONS,
        input=json.dumps(signals, ensure_ascii=False, sort_keys=True),
        stream=True,
    )

    output_text = []
    for event in stream:
        agent.events.emit(event.to_dict())
        if event.type in {"error", "response.failed"}:
            raise RuntimeError(f"Model response failed: {event}")
        if event.type == "response.output_text.delta":
            output_text.append(event.delta)

    print("SOTERIA_LLM " + json.dumps({"model": model, "text": "".join(output_text)}, ensure_ascii=False), flush=True)

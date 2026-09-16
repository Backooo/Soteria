"""PLATZHALTER fuer den Publish-Rauchtest. Task 14 ersetzt diese Datei."""
from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context

app = AgentApp()


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    raise NotImplementedError("Task 14")

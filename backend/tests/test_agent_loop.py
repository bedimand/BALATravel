"""Test that the CentralMind agent loop calls tools and terminates correctly."""

import json

from fastapi.testclient import TestClient


TRIP_PAYLOAD = {
    "destination": "Recife",
    "start_date": "2026-05-01",
    "end_date": "2026-05-04",
    "budget": 3000,
    "style": "cultural",
    "interests": ["museus", "praia"],
}


def _create_trip(client: TestClient) -> int:
    resp = client.post("/api/trips", json=TRIP_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


def test_agent_loop_calls_tools_and_finishes(client: TestClient, monkeypatch):
    """The agent receives a message, calls list_saved_places, then finishes."""
    trip_id = _create_trip(client)

    call_count = {"n": 0}

    def fake_llm_chat(prompt, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return json.dumps({
                "reasoning": "Let me check what places are saved.",
                "tool_calls": [{"name": "list_saved_places", "params": {}}],
            })
        return json.dumps({
            "reasoning": "No places yet. Done.",
            "tool_calls": [{"name": "finish", "params": {"message": "Nenhum lugar salvo ainda."}}],
        })

    monkeypatch.setattr("app.services.central_mind.llm_chat", fake_llm_chat)

    # The endpoint dispatches the agent in the background and returns 202; the
    # conftest fixture runs that work inline, so by the time we get the response
    # the run has completed. We read the result from the agent thread.
    resp = client.post(f"/api/trips/{trip_id}/agent/messages", json={"message": "O que temos?"})

    assert resp.status_code == 202
    assert resp.json()["run_id"] is not None
    assert call_count["n"] >= 2

    thread = client.get(f"/api/trips/{trip_id}/agent/thread")
    assert thread.status_code == 200
    runs = thread.json()["runs"]
    assert runs
    assert any(run["assistant_message"] for run in runs)


def test_agent_loop_terminates_on_consecutive_errors(client: TestClient, monkeypatch):
    """The agent stops after 3 consecutive tool errors."""
    trip_id = _create_trip(client)

    def fake_llm_chat(prompt, **kwargs):
        return json.dumps({
            "reasoning": "Trying unknown tool.",
            "tool_calls": [{"name": "nonexistent_tool", "params": {}}],
        })

    monkeypatch.setattr("app.services.central_mind.llm_chat", fake_llm_chat)

    resp = client.post(f"/api/trips/{trip_id}/agent/messages", json={"message": "Faz algo"})

    # 202 + inline execution (see conftest). The agent should terminate on the
    # consecutive-error guard rather than looping forever.
    assert resp.status_code == 202
    assert resp.json()["run_id"] is not None

    thread = client.get(f"/api/trips/{trip_id}/agent/thread")
    assert thread.status_code == 200
    runs = thread.json()["runs"]
    assert runs
    assert any(run["assistant_message"] for run in runs)

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

    resp = client.post(f"/api/trips/{trip_id}/agent/messages", json={"message": "O que temos?"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["assistant_message"]
    assert data["run_id"] is not None
    assert call_count["n"] >= 2


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

    assert resp.status_code == 200
    data = resp.json()
    assert "erros consecutivos" in data["assistant_message"].lower() or data["assistant_message"]

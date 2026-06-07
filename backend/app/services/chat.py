from __future__ import annotations

import json
import re
from datetime import time
from typing import Any

from app.models.entities import ItineraryVersion, Place, Trip
from app.schemas.trip import ChatResponse
from app.services.llm import LLMIntegrationError, llm_chat


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _summarize_items_for_prompt(itinerary: ItineraryVersion | None) -> str:
    if not itinerary or not itinerary.items:
        return "Sem itens ainda."
    # Include coordinates and type so the agent can rebuild a full day (set_day)
    # from the existing items without losing geo info.
    lines = []
    for item in sorted(itinerary.items, key=lambda item: (item.date, item.start_time)):
        coords = f" @({item.lat:.4f},{item.lng:.4f})" if item.lat and item.lng else ""
        lines.append(
            f"- id={item.id} | {item.date} {item.start_time.strftime('%H:%M')}-{item.end_time.strftime('%H:%M')} "
            f"| [{item.item_type}] {item.title}{coords}"
        )
    return "\n".join(lines)


def build_chat_response(trip: Trip, itinerary: ItineraryVersion | None, places: list[Place], user_message: str) -> ChatResponse:
    top_places = ", ".join(place.name for place in places[:6]) if places else "nenhuma atracao carregada"
    warnings = itinerary.warnings if itinerary else []
    prompt = (
        "Responda com JSON valido apenas, sem markdown.\n"
        "Formato:\n"
        "{\n"
        '  "assistant_message": "texto curto",\n'
        '  "proposed_changes": [\n'
        "    {\n"
        '      "type": "update_item|set_day|generate_itinerary",\n'
        '      "title": "titulo curto",\n'
        '      "reason": "justificativa curta",\n'
        '      "payload": { ... ver tipos abaixo ... }\n'
        "    }\n"
        "  ],\n"
        '  "warnings": ["..."]\n'
        "}\n\n"
        "Tipos de mudanca:\n"
        '- "update_item": ajustar UM item existente. payload: {"item_id": 123, "title": "...", "notes": "...", "start_time": "09:30:00", "end_time": "11:00:00"}\n'
        '- "set_day": redefinir um dia INTEIRO. VOCE decide a ordem e os horarios e envia a lista completa. '
        'payload: {"date": "AAAA-MM-DD", "items": [{"title": "...", "start_time": "09:00", "end_time": "10:30", "item_type": "museum", "lat": 38.7, "lng": -9.1, "notes": "..."}, ...]}. '
        "Os horarios nao podem se sobrepor. Use para 'reorganizar o dia', 'deixar a tarde mais leve', 'comecar mais tarde', 'trocar atividades'.\n"
        '- "generate_itinerary": refazer o roteiro do zero.\n\n'
        f"Destino: {trip.destination}\n"
        f"Periodo: {trip.start_date} ate {trip.end_date}\n"
        f"Estilo: {trip.style}\n"
        f"Interesses: {', '.join(trip.interests) if trip.interests else 'geral'}\n"
        f"Atracoes sugeridas: {top_places}\n"
        f"Itens atuais:\n{_summarize_items_for_prompt(itinerary)}\n"
        f"Warnings atuais: {', '.join(warnings) if warnings else 'nenhum'}\n"
        f"Mensagem do usuario: {user_message}\n"
        "Regras: proponha no maximo 3 mudancas, seja pratico, nunca sugira compra automatica. "
        "Escolha o tipo de mudanca que melhor atende ao pedido do usuario."
    )

    response_text = llm_chat(
        prompt,
        system_prompt=(
            "You are a travel copilot. Always answer in valid JSON only. "
            "Use Brazilian Portuguese for text fields. Do not include markdown."
        ),
        temperature=0.2,
    )

    parsed_payload = _extract_first_json_object(response_text) if response_text else None
    if not parsed_payload:
        raise LLMIntegrationError("OpenRouter returned invalid JSON for chat planning.")

    try:
        parsed_response = ChatResponse.model_validate(parsed_payload)
    except Exception as exc:
        raise LLMIntegrationError("OpenRouter returned an invalid chat response payload.") from exc
    if not parsed_response.proposed_changes:
        raise LLMIntegrationError("OpenRouter returned no proposed changes for chat planning.")
    return parsed_response


def _parse_time(value: Any) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value
    text = str(value).strip()
    if not text:
        return None
    return time.fromisoformat(text)


def parse_payload_time(payload: dict[str, Any], key: str) -> time | None:
    try:
        return _parse_time(payload.get(key))
    except Exception:
        return None

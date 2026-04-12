from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.models.entities import HotelOption, Place, Trip


settings = get_settings()


class LLMIntegrationError(RuntimeError):
    pass


def _extract_content(payload: dict) -> str | None:
    choices = payload.get("choices", [])
    if not choices:
        return None
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
        joined = " ".join(chunk.strip() for chunk in text_chunks if chunk.strip())
        return joined or None
    return None


def llm_chat(prompt: str | list[dict], system_prompt: str | None = None, temperature: float = 0.3) -> str:
    if not settings.openai_api_key:
        raise LLMIntegrationError("OPENAI_API_KEY is missing.")
    try:
        system_instruction = system_prompt or "You are a concise travel-planning assistant. Reply in Brazilian Portuguese."
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        
        response = httpx.post(
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": settings.openai_model,
                "messages": prompt if isinstance(prompt, list) else [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        content = _extract_content(response.json())
        if not content:
            raise LLMIntegrationError("LLM returned an empty response.")
        return content
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        raise LLMIntegrationError(f"LLM HTTP {exc.response.status_code}: {detail}") from exc
    except LLMIntegrationError:
        raise
    except Exception as exc:
        raise LLMIntegrationError(f"LLM request failed: {str(exc)}") from exc


def summarize_recommendations(trip: Trip, hotels: list[HotelOption], places: list[Place]) -> str:
    top_places = ", ".join(place.name for place in places[:3]) if places else "atracoes locais"
    prompt = (
        "Resuma em 2 frases um plano de atividades para uma viagem.\n"
        f"Destino: {trip.destination}\n"
        f"Interesses: {', '.join(trip.interests) or 'exploracao geral'}\n"
        f"Pontos sugeridos: {top_places}\n"
        "Explique como os lugares escolhidos combinam com o ritmo da viagem."
    )
    return llm_chat(prompt)


def summarize_itinerary(trip: Trip, days: int, warnings: list[str]) -> str:
    prompt = (
        "Escreva um resumo curto de roteiro em portugues do Brasil.\n"
        f"Destino: {trip.destination}\n"
        f"Dias: {days}\n"
        f"Estilo: {trip.style}\n"
        f"Avisos: {'; '.join(warnings) if warnings else 'nenhum'}\n"
        "Limite: 2 frases."
    )
    return llm_chat(prompt)

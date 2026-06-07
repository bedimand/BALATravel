from __future__ import annotations

import json
import time
import httpx

from app.core.config import get_settings
from app.models.entities import Trip


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
    """
    Sends a chat completion request with retry logic and provider fallback.
    Tries OpenAI/Custom endpoint first, then falls back to OpenRouter.
    """
    providers = []
    
    # Primary: Custom OpenAI-compatible endpoint or OpenAI itself
    if settings.openai_api_key:
        providers.append({
            "name": "Primary (Custom/OpenAI)",
            "api_key": settings.openai_api_key,
            "base_url": settings.openai_base_url.rstrip("/"),
            "model": settings.openai_model
        })
    
    # Fallback: OpenRouter
    if settings.openrouter_api_key:
        providers.append({
            "name": "Fallback (OpenRouter)",
            "api_key": settings.openrouter_api_key,
            "base_url": settings.openrouter_base_url.rstrip("/"),
            "model": settings.openrouter_model
        })

    if not providers:
        raise LLMIntegrationError("No LLM providers configured (OPENAI_API_KEY or OPENROUTER_API_KEY missing).")

    last_error = ""
    
    for provider in providers:
        max_retries = 3 if provider["name"].startswith("Primary") else 1
        
        for attempt in range(max_retries):
            try:
                system_instruction = system_prompt or "You are a concise travel-planning assistant. Reply in Brazilian Portuguese."
                headers = {
                    "Authorization": f"Bearer {provider['api_key']}",
                    "Content-Type": "application/json",
                }
                
                # Add OpenRouter specific headers if needed
                if "openrouter" in provider["base_url"].lower():
                    headers["HTTP-Referer"] = settings.openrouter_site_url or "http://localhost:3000"
                    headers["X-Title"] = settings.openrouter_app_name or "BALATravel"

                with httpx.Client(timeout=60.0) as client:
                    response = client.post(
                        f"{provider['base_url']}/chat/completions",
                        headers=headers,
                        json={
                            "model": provider["model"],
                            "messages": prompt if isinstance(prompt, list) else [
                                {"role": "system", "content": system_instruction},
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": temperature,
                        },
                    )
                    
                # Handle Cloudflare/Server issues specifically
                if response.status_code in [520, 522, 524, 500, 502, 503, 504]:
                    raise httpx.HTTPStatusError(
                        f"Server error {response.status_code}", 
                        request=response.request, 
                        response=response
                    )
                
                response.raise_for_status()
                
                try:
                    payload = response.json()
                except json.JSONDecodeError:
                    raise LLMIntegrationError(f"Provider {provider['name']} returned non-JSON response (likely an error page).")

                content = _extract_content(payload)
                if not content:
                    raise LLMIntegrationError(f"Provider {provider['name']} returned an empty response.")
                
                return content

            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
                last_error = str(exc)
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    time.sleep(wait_time)
                    continue
                # If all retries failed for this provider, we'll try the next provider
                break
            except Exception as exc:
                last_error = str(exc)
                break # Non-retryable error
    
    raise LLMIntegrationError(f"LLM exhausted all providers. Last error: {last_error}")


def critique_itinerary(trip: Trip, days_text: str) -> list[dict]:
    """Fresh-eyes LLM critic for the JUDGMENT problems deterministic rules can't see:
    venues scheduled at inappropriate/closed hours (a sit-down restaurant or bar at
    09:00), dull repetition, unrealistic pacing, a dud choice for the slot.

    This is a SEPARATE call from the planning agent — a second opinion, not the agent
    grading its own homework. Returns a list of {date, severity, message} advisory
    issues (never blocking). Best-effort: any failure returns [] so review never breaks.
    """
    system = (
        "You are a sharp, skeptical local travel expert reviewing a day-by-day itinerary. "
        "Find concrete problems a real traveler would actually hit — focus on JUDGMENT issues, "
        "not counting: a venue scheduled when it's closed or makes no sense for that hour "
        "(e.g. a full sit-down restaurant or a bar at 09:00 instead of a café/bakery), a poor "
        "choice for the slot, monotony (same kind of place over and over), an exhausting or "
        "illogical sequence. Do NOT restate generic rules; only flag things that are genuinely off. "
        "If the plan is sensible, return an empty list.\n"
        "Reply ONLY with JSON: {\"issues\":[{\"date\":\"YYYY-MM-DD\",\"message\":\"...\"}]}. "
        "Messages in Brazilian Portuguese, specific and short."
    )
    prompt = (
        f"Destino: {trip.destination}. Estilo: {trip.style or 'equilibrado'}.\n\n"
        f"Roteiro:\n{days_text}\n\n"
        "Liste apenas os problemas reais."
    )
    try:
        raw = llm_chat(prompt, system_prompt=system, temperature=0.3)
    except LLMIntegrationError:
        return []
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return []
        data = json.loads(raw[start:end + 1])
        issues = data.get("issues", [])
        out = []
        for it in issues:
            msg = str(it.get("message", "")).strip()
            if not msg:
                continue
            out.append({
                "date": str(it.get("date", "")).strip(),
                "severity": "critique",
                "message": msg,
            })
        return out
    except (json.JSONDecodeError, ValueError, AttributeError, TypeError):
        return []


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

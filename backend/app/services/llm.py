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

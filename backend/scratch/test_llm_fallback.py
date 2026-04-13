import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Mock settings
mock_settings = MagicMock()
mock_settings.openai_api_key = "fake_key"
mock_settings.openai_base_url = "https://unstable-mock-endpoint.com/v1"
mock_settings.openai_model = "gpt-4"
mock_settings.openrouter_api_key = "openrouter_key"
mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
mock_settings.openrouter_model = "google/palm-2-chat-bison"

import app.services.llm as llm_module

with patch("app.services.llm.get_settings", return_value=mock_settings):
    from app.services.llm import llm_chat
    import httpx

    # Mock success on second provider
    def side_effect(url, **kwargs):
        if "unstable-mock-endpoint" in url:
            # Simulate Cloudflare 520
            mock_resp = MagicMock()
            mock_resp.status_code = 520
            mock_resp.text = "Cloudflare 520 Error"
            mock_resp.request = MagicMock()
            raise httpx.HTTPStatusError("520", request=mock_resp.request, response=mock_resp)
        else:
            # Simulate OpenRouter Success
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "Resposta do OpenRouter (Fallback)"}}]
            }
            return mock_resp

    with patch("httpx.Client.post", side_effect=side_effect):
        print("Testando Fallback...")
        try:
            result = llm_chat("Oi")
            print(f"Sucesso! Resultado: {result}")
            assert "OpenRouter" in result
        except Exception as e:
            print(f"Falha no teste: {e}")
            sys.exit(1)

print("\nTeste concluído com sucesso!")

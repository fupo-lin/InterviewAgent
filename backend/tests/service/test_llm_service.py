import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from service.support import configure_backend_imports

configure_backend_imports()

from fastapi import HTTPException

from app.service.llm_service import LLMService


class CapturingLLMService(LLMService):
    def __init__(self) -> None:
        super().__init__()
        self.api_key = "test-key"
        self.calls = []

    async def _chat_completion(self, messages, temperature=0.7):
        self.calls.append({"messages": messages, "temperature": temperature})
        return '```json\n{"summary": "fixed"}\n```', {"raw": "repair"}


class LLMServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_repair_structured_output_uses_schema_errors_and_low_temperature(self):
        service = CapturingLLMService()

        repaired, raw_response = await service.repair_structured_output(
            prompt_id="evaluation",
            output={"summary": []},
            output_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
            },
            validation_errors=["output.summary: Input should be a valid string"],
        )

        self.assertEqual(repaired, {"summary": "fixed"})
        self.assertEqual(raw_response, {"raw": "repair"})
        self.assertEqual(len(service.calls), 1)
        call = service.calls[0]
        self.assertEqual(call["temperature"], 0.0)
        self.assertIn("Return only one JSON object", call["messages"][0]["content"])
        payload = call["messages"][1]["content"]
        self.assertIn('"prompt_id": "evaluation"', payload)
        self.assertIn("output.summary", payload)
        self.assertIn('"invalid_output": {"summary": []}', payload)

    async def test_chat_completion_maps_timeout_to_retryable_http_error(self):
        service = CapturingLLMService()
        service.api_base = "https://llm.example/v1"
        service.timeout_seconds = 12.5

        client = AsyncMock()
        client.post.side_effect = httpx.ReadTimeout("timed out")

        with patch("app.service.llm_service.httpx.AsyncClient") as async_client_class:
            async_client_class.return_value.__aenter__.return_value = client

            with self.assertRaises(HTTPException) as exc:
                await LLMService._chat_completion(service, [{"role": "user", "content": "hello"}])

        self.assertEqual(exc.exception.status_code, 504)
        self.assertIn("timed out", exc.exception.detail)
        async_client_class.assert_called_once_with(timeout=12.5)

    async def test_chat_completion_maps_provider_http_error_to_bad_gateway(self):
        service = CapturingLLMService()
        service.api_base = "https://llm.example/v1"

        request = httpx.Request("POST", "https://llm.example/v1/chat/completions")
        response = httpx.Response(429, request=request)
        client = AsyncMock()
        client.post.return_value = response

        with patch("app.service.llm_service.httpx.AsyncClient") as async_client_class:
            async_client_class.return_value.__aenter__.return_value = client

            with self.assertRaises(HTTPException) as exc:
                await LLMService._chat_completion(service, [{"role": "user", "content": "hello"}])

        self.assertEqual(exc.exception.status_code, 502)
        self.assertEqual(exc.exception.detail, "LLM provider returned HTTP 429.")

    async def test_chat_completion_returns_content_on_success(self):
        service = CapturingLLMService()
        service.api_base = "https://llm.example/v1"

        data = {"choices": [{"message": {"content": "ok"}}]}
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = data
        client = AsyncMock()
        client.post.return_value = response

        with patch("app.service.llm_service.httpx.AsyncClient") as async_client_class:
            async_client_class.return_value.__aenter__.return_value = client

            content, raw_response = await LLMService._chat_completion(
                service,
                [{"role": "user", "content": "hello"}],
                temperature=0.2,
            )

        self.assertEqual(content, "ok")
        self.assertEqual(raw_response, data)
        client.post.assert_awaited_once_with(
            "https://llm.example/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={
                "model": service.model,
                "messages": [{"role": "user", "content": "hello"}],
                "temperature": 0.2,
            },
        )


if __name__ == "__main__":
    unittest.main()

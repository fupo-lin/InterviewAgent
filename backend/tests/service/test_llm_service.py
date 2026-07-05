import unittest

from service.support import configure_backend_imports

configure_backend_imports()

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


if __name__ == "__main__":
    unittest.main()

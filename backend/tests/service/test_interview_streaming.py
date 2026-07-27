import json
import unittest

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.sse_streaming import sse_event


class InterviewStreamingTest(unittest.TestCase):
    def test_sse_event_encodes_named_event_and_json_payload(self):
        encoded = sse_event(
            {
                "event": "step",
                "step": "generate_followup",
                "status": "running",
            }
        )

        self.assertTrue(encoded.startswith("event: step\n"))
        self.assertTrue(encoded.endswith("\n\n"))
        data_line = [line for line in encoded.splitlines() if line.startswith("data: ")][0]
        payload = json.loads(data_line.removeprefix("data: "))
        self.assertEqual(payload["event"], "step")
        self.assertEqual(payload["step"], "generate_followup")


if __name__ == "__main__":
    unittest.main()

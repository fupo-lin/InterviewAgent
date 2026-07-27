import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.interview_runtime_router import InterviewRuntimeRouter


class InterviewRuntimeRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.router = InterviewRuntimeRouter()

    def test_routes_by_state_next_action(self):
        cases = [
            ("continue_current_topic", InterviewRuntimeRouter.CONTINUE_TOPIC),
            ("switch_topic_in_section", InterviewRuntimeRouter.SWITCH_TOPIC),
            ("move_next_section", InterviewRuntimeRouter.MOVE_NEXT_SECTION),
            ("wrap_up_interview", InterviewRuntimeRouter.WRAP_UP),
            ("finished", InterviewRuntimeRouter.FINISHED),
        ]
        for next_action, expected in cases:
            with self.subTest(next_action=next_action):
                decision = self.router.route_after_advance(
                    {"next_action": next_action},
                    SimpleNamespace(status="active", state={}),
                )

                self.assertEqual(decision.route, expected)

    def test_execution_finished_wins_over_next_action(self):
        decision = self.router.route_after_advance(
            {"next_action": "continue_current_topic"},
            SimpleNamespace(status="finished", state={}),
        )

        self.assertEqual(decision.route, InterviewRuntimeRouter.FINISHED)
        self.assertEqual(decision.reason, "execution_status_finished")

    def test_falls_back_to_execution_state_next_action(self):
        decision = self.router.route_after_advance(
            {},
            SimpleNamespace(
                status="active",
                state={"next_action": {"type": "move_next_section"}},
            ),
        )

        self.assertEqual(decision.route, InterviewRuntimeRouter.MOVE_NEXT_SECTION)


if __name__ == "__main__":
    unittest.main()

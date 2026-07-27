import unittest

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.interview_decision_policy import CodeDecisionPolicy, DecisionPolicyInput


class InterviewDecisionPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = CodeDecisionPolicy()

    def test_target_rounds_move_next_is_policy_decision_not_execution_hard_rule(self):
        result = self.policy.decide(
            DecisionPolicyInput(
                topic_judge_result={
                    "next_action": "continue_current_topic",
                    "reason": "candidate has one more weak area",
                    "confidence": "high",
                },
                execution_state={},
                current_section={"section_key": "system_design"},
                current_section_index=0,
                section_count=2,
                completed_rounds=3,
                target_rounds=3,
                open_threads=[],
            )
        )

        self.assertEqual(result.final_action, "move_next_section")
        self.assertEqual(result.source, "decision_policy")
        self.assertEqual(
            result.conflict_resolution,
            "target_rounds_reached_overrode_continue_without_open_threads",
        )

    def test_target_rounds_do_not_close_section_when_open_thread_exists(self):
        result = self.policy.decide(
            DecisionPolicyInput(
                topic_judge_result={
                    "next_action": "continue_current_topic",
                    "reason": "follow the Redis consistency highlight",
                },
                execution_state={},
                current_section={"section_key": "cache"},
                current_section_index=0,
                section_count=2,
                completed_rounds=3,
                target_rounds=3,
                open_threads=[
                    {
                        "section_key": "cache",
                        "status": "open",
                        "highlight": "Redis consistency tradeoff",
                    }
                ],
            )
        )

        self.assertEqual(result.final_action, "continue_current_topic")
        self.assertEqual(result.source, "topic_judge")

    def test_high_value_open_thread_overrides_judge_move_next(self):
        result = self.policy.decide(
            DecisionPolicyInput(
                topic_judge_result={
                    "next_action": "move_next_section",
                    "reason": "section has enough coverage",
                },
                execution_state={},
                current_section={"section_key": "cache"},
                current_section_index=0,
                section_count=2,
                completed_rounds=3,
                target_rounds=3,
                open_threads=[
                    {
                        "section_key": "cache",
                        "status": "open",
                        "priority": "high",
                        "highlight": "Redis consistency tradeoff",
                    }
                ],
                retrieved_evidence=[
                    {"content": "Candidate previously discussed Redis double delete."}
                ],
            )
        )

        self.assertEqual(result.final_action, "continue_current_topic")
        self.assertEqual(
            result.conflict_resolution,
            "open_thread_overrode_move_next_section",
        )

    def test_policy_requires_recent_answer_context_before_unrequested_transition(self):
        result = self.policy.decide(
            DecisionPolicyInput(
                topic_judge_result=None,
                execution_state={},
                current_section={"section_key": "cache", "uncovered_probe_points": []},
                current_section_index=0,
                section_count=2,
                completed_rounds=1,
                target_rounds=3,
                open_threads=[],
                recent_history=[],
            )
        )

        self.assertEqual(result.final_action, "continue_current_topic")
        self.assertEqual(
            result.conflict_resolution,
            "policy_requires_recent_answer_before_transition",
        )


if __name__ == "__main__":
    unittest.main()

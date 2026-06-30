import unittest

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.prompt_contract import PromptContractValidator
from app.service.prompt_registry import PromptDefinition


def definition(
    required_context: tuple[str, ...],
    required_evidence: tuple[str, ...],
) -> PromptDefinition:
    return PromptDefinition(
        prompt_id="test_prompt",
        prompt_file="test_prompt.txt",
        version="3.0.0",
        owner_agent="TestAgent",
        task="test_task",
        input_schema="TestInput.v1",
        output_schema="TestOutput.v1",
        required_context=required_context,
        required_evidence=required_evidence,
    )


class PromptContractValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = PromptContractValidator()

    def test_validate_ok_when_required_context_aliases_and_evidence_exist(self):
        validation = self.validator.validate(
            definition=definition(
                required_context=("UserAnswer", "InterviewPlanExecution"),
                required_evidence=("interview_answer", "execution_probe"),
            ),
            input_snapshot={
                "answer_message_id": 101,
                "has_execution_context": True,
                "evidence_packet": {
                    "evidence_items": [
                        {"evidence_id": "interview_answer_101", "evidence_type": "interview_answer"},
                        {"evidence_id": "execution_probe_tech_1", "evidence_type": "execution_probe"},
                    ]
                },
            },
            context_refs={
                "execution_id": 30,
            },
            evidence_refs=["interview_answer_101", "execution_probe_tech_1"],
        )

        self.assertTrue(validation["ok"])
        self.assertEqual(validation["missing_context"], [])
        self.assertEqual(validation["missing_evidence"], [])
        self.assertEqual(
            validation["present_evidence_types"],
            ["execution_probe", "interview_answer"],
        )
        self.assertIn("answer_message_id", validation["present_context_keys"])
        self.assertIn("execution_id", validation["present_context_keys"])
        self.assertEqual(
            validation["evidence_refs"],
            ["interview_answer_101", "execution_probe_tech_1"],
        )

    def test_validate_reports_missing_required_context_and_evidence(self):
        validation = self.validator.validate(
            definition=definition(
                required_context=("ResumeDocument", "ResumeProfile"),
                required_evidence=("resume_claim", "authenticity_check"),
            ),
            input_snapshot={
                "resume_id": 7,
                "has_resume_profile": False,
                "evidence_packet": {
                    "evidence_items": [
                        {"evidence_id": "resume_claim_project_1", "evidence_type": "resume_claim"},
                    ]
                },
            },
            context_refs={},
            evidence_refs=["resume_claim_project_1"],
        )

        self.assertFalse(validation["ok"])
        self.assertEqual(validation["missing_context"], ["ResumeProfile"])
        self.assertEqual(validation["missing_evidence"], ["authenticity_check"])
        self.assertEqual(validation["present_evidence_types"], ["resume_claim"])
        self.assertIn("resume_id", validation["present_context_keys"])
        self.assertNotIn("has_resume_profile", validation["present_context_keys"])


if __name__ == "__main__":
    unittest.main()

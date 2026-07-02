import re
import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.evidence_service import EvidenceItem, EvidencePacketBuilder
from app.service.evidence_contract import EvidenceType


def message(
    message_id: int,
    content: str,
    role_type: str = "user",
    session_id: int = 10,
    round_no: int = 1,
):
    return SimpleNamespace(
        id=message_id,
        session_id=session_id,
        role_type=role_type,
        round_no=round_no,
        content=content,
    )


class EvidencePacketBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = EvidencePacketBuilder()

    def test_evidence_item_to_dict_has_stable_shape(self):
        item = EvidenceItem(
            evidence_id="interview_answer_1",
            evidence_type="interview_answer",
            source_type="interview_message",
            source_id=1,
            project_id=2,
            session_id=3,
            round_no=4,
            content_excerpt="Explained retry and idempotency.",
            tags=("interview", "reliability"),
            confidence="high",
        )

        self.assertEqual(
            item.to_dict(),
            {
                "evidence_id": "interview_answer_1",
                "evidence_type": "interview_answer",
                "source_type": "interview_message",
                "source_id": 1,
                "project_id": 2,
                "session_id": 3,
                "round_no": 4,
                "content_excerpt": "Explained retry and idempotency.",
                "tags": ["interview", "reliability"],
                "confidence": "high",
                "metadata": {},
            },
        )

    def test_jd_analysis_packet_marks_empty_source_text_as_missing(self):
        packet = self.builder.build_jd_analysis_packet(
            project_id=1,
            jd_id=7,
            jd_content="",
        )

        self.assertRegex(packet["packet_id"], r"^jd_analysis_1_\d{14}$")
        self.assertEqual(packet["task"], "jd_analysis")
        self.assertEqual(packet["project_id"], 1)
        self.assertEqual(packet["missing_evidence"], ["job_description_source_text"])
        self.assertEqual(packet["evidence_items"][0]["evidence_id"], "jd_requirement_7")
        self.assertEqual(packet["evidence_items"][0]["evidence_type"], "jd_requirement")
        self.assertEqual(packet["evidence_items"][0]["confidence"], "source_document")

    def test_resume_packet_collects_claim_answers_execution_and_authenticity_evidence(self):
        packet = self.builder.build_resume_packet(
            task="resume_rewrite",
            project_id=2,
            resume_profile={
                "projects": [
                    {
                        "name": "Order Platform",
                        "summary": "Owned order service with QPS 5000.",
                        "highlights": ["Added retry protection"],
                    }
                ],
                "skills": [{"name": "Kafka", "evidence": "Built retry pipeline"}],
            },
            transcript_messages=[
                message(101, "I handled QPS 5000 and idempotency.", round_no=3),
                message(102, "Please explain the design.", role_type="assistant", round_no=3),
            ],
            execution_state={
                "sections": [
                    {
                        "section_key": "tech_foundation",
                        "evidence": [
                            {
                                "round_no": 3,
                                "answer_excerpt": "QPS 5000 with idempotency.",
                                "covered_probe_points": ["idempotency"],
                                "confidence": "high",
                                "probe_point": "reliability",
                            }
                        ],
                    }
                ]
            },
            authenticity_report={
                "claim_checks": [
                    {
                        "resume_claim": "Owned order service",
                        "status": "supported",
                        "evidence": "Interview answer covered QPS 5000.",
                    }
                ]
            },
        )

        evidence_by_id = {
            item["evidence_id"]: item
            for item in packet["evidence_items"]
        }
        self.assertRegex(packet["packet_id"], r"^resume_rewrite_2_\d{14}$")
        self.assertEqual(packet["task"], "resume_rewrite")
        self.assertEqual(packet["missing_evidence"], [])
        self.assertIn("resume_claim_project_1", evidence_by_id)
        self.assertIn("resume_claim_project_1_highlight_1", evidence_by_id)
        self.assertIn("resume_claim_skill_1", evidence_by_id)
        self.assertIn("interview_answer_101", evidence_by_id)
        self.assertNotIn("interview_answer_102", evidence_by_id)
        self.assertIn("execution_probe_tech_foundation_1", evidence_by_id)
        self.assertIn("authenticity_check_1", evidence_by_id)
        self.assertEqual(evidence_by_id["authenticity_check_1"]["confidence"], "high")

    def test_question_generation_packet_reports_missing_followup_answer(self):
        packet = self.builder.build_question_generation_packet(
            task="followup_generation",
            session_id=10,
            project_id=1,
        )

        self.assertRegex(packet["packet_id"], r"^followup_generation_10_\d{14}$")
        self.assertEqual(packet["task"], "followup_generation")
        self.assertEqual(packet["missing_evidence"], ["interview_answer"])
        self.assertEqual(packet["evidence_items"], [])

    def test_refs_deduplicates_evidence_ids_in_order(self):
        refs = self.builder.refs(
            {
                "evidence_items": [
                    {"evidence_id": "a"},
                    {"evidence_id": "b"},
                    {"evidence_id": "a"},
                    {"evidence_id": ""},
                    {},
                ]
            }
        )

        self.assertEqual(refs, ["a", "b"])

    def test_validate_packet_delegates_to_evidence_contract_validator(self):
        packet = self.builder.build_resume_analysis_packet(
            project_id=1,
            resume_id=8,
            resume_content="Built backend service.",
        )

        result = self.builder.validate_packet(packet)

        self.assertTrue(result.ok)
        self.assertEqual(result.metadata["task"], "resume_analysis")
        self.assertEqual(result.metadata["evidence_types"], [EvidenceType.RESUME_CLAIM])


if __name__ == "__main__":
    unittest.main()

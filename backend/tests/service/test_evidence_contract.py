import unittest

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.evidence_contract import (
    ALLOWED_EVIDENCE_TYPES,
    EvidencePacketValidationResult,
    EvidencePacketValidator,
    EvidenceSourceType,
    EvidenceType,
)


def valid_packet() -> dict:
    return {
        "packet_id": "resume_rewrite_1_20260701000000",
        "task": "resume_rewrite",
        "project_id": 1,
        "evidence_items": [
            {
                "evidence_id": "resume_claim_1",
                "evidence_type": EvidenceType.RESUME_CLAIM,
                "source_type": EvidenceSourceType.RESUME_PROFILE,
                "source_id": 10,
                "content_excerpt": "Built order platform.",
                "tags": ["project"],
                "metadata": {},
            },
            {
                "evidence_id": "authenticity_check_1",
                "evidence_type": EvidenceType.AUTHENTICITY_CHECK,
                "source_type": EvidenceSourceType.RESUME_AUTHENTICITY_REPORT,
                "source_id": 20,
                "content_excerpt": "Claim supported by interview answer.",
                "tags": ["authenticity"],
                "metadata": {},
            },
        ],
        "missing_evidence": [],
    }


class EvidencePacketValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = EvidencePacketValidator()

    def test_valid_packet_passes_and_returns_metadata(self):
        result = self.validator.validate(valid_packet())

        self.assertTrue(result.ok)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.warnings, ())
        self.assertEqual(result.metadata["packet_id"], "resume_rewrite_1_20260701000000")
        self.assertEqual(result.metadata["task"], "resume_rewrite")
        self.assertEqual(result.metadata["evidence_count"], 2)
        self.assertEqual(
            result.metadata["evidence_types"],
            [EvidenceType.AUTHENTICITY_CHECK, EvidenceType.RESUME_CLAIM],
        )
        self.assertEqual(
            result.metadata["source_types"],
            [EvidenceSourceType.RESUME_AUTHENTICITY_REPORT, EvidenceSourceType.RESUME_PROFILE],
        )

    def test_result_can_be_serialized_to_dict(self):
        result = EvidencePacketValidationResult(
            ok=False,
            errors=("broken",),
            warnings=("empty excerpt",),
            metadata={"evidence_count": 1},
        )

        self.assertEqual(
            result.to_dict(),
            {
                "ok": False,
                "errors": ["broken"],
                "warnings": ["empty excerpt"],
                "metadata": {"evidence_count": 1},
            },
        )

    def test_none_packet_is_invalid(self):
        result = self.validator.validate(None)

        self.assertFalse(result.ok)
        self.assertEqual(result.errors, ("Evidence packet must be a dict",))
        self.assertEqual(result.metadata["evidence_count"], 0)

    def test_packet_shape_errors_are_reported(self):
        result = self.validator.validate(
            {
                "packet_id": "",
                "task": "",
                "evidence_items": {},
                "missing_evidence": {},
            }
        )

        self.assertFalse(result.ok)
        self.assertIn("Evidence packet evidence_items must be a list", result.errors)
        self.assertIn("Evidence packet missing_evidence must be a list", result.errors)
        self.assertIn("Evidence packet packet_id must not be empty", result.errors)
        self.assertIn("Evidence packet task must not be empty", result.errors)

    def test_item_errors_and_warnings_are_reported(self):
        packet = valid_packet()
        packet["evidence_items"] = [
            {
                "evidence_id": "dup",
                "evidence_type": EvidenceType.RESUME_CLAIM,
                "source_type": EvidenceSourceType.RESUME_PROFILE,
                "content_excerpt": "",
                "tags": (),
                "metadata": [],
            },
            {
                "evidence_id": "dup",
                "evidence_type": "unknown_type",
                "source_type": "unknown_source",
                "content_excerpt": "Some content",
            },
            "not a dict",
            {
                "evidence_id": "",
                "evidence_type": "",
                "source_type": "",
                "content_excerpt": "",
            },
        ]

        result = self.validator.validate(packet)

        self.assertFalse(result.ok)
        self.assertIn("Duplicate evidence_id: dup", result.errors)
        self.assertIn("Evidence item #2 has unknown evidence_type: unknown_type", result.errors)
        self.assertIn("Evidence item #2 has unknown source_type: unknown_source", result.errors)
        self.assertIn("Evidence item #3 must be a dict", result.errors)
        self.assertIn("Evidence item #4 evidence_id must not be empty", result.errors)
        self.assertIn("Evidence item #4 evidence_type must not be empty", result.errors)
        self.assertIn("Evidence item #4 source_type must not be empty", result.errors)
        self.assertIn("Evidence item #1 content_excerpt is empty", result.warnings)
        self.assertIn("Evidence item #1 tags should be a list", result.warnings)
        self.assertIn("Evidence item #1 metadata should be a dict", result.warnings)

    def test_allowed_evidence_types_are_centralized(self):
        self.assertIn(EvidenceType.RESUME_CLAIM, ALLOWED_EVIDENCE_TYPES)
        self.assertIn(EvidenceType.AUTHENTICITY_CHECK, ALLOWED_EVIDENCE_TYPES)


if __name__ == "__main__":
    unittest.main()

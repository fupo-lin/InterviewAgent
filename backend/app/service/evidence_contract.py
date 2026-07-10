from dataclasses import dataclass, field
from typing import Any


class EvidenceType:
    RESUME_CLAIM = "resume_claim"
    JD_REQUIREMENT = "jd_requirement"
    INTERVIEW_ANSWER = "interview_answer"
    EXECUTION_PROBE = "execution_probe"
    TOPIC_JUDGE = "topic_judge"
    EVALUATION_FINDING = "evaluation_finding"
    AUTHENTICITY_CHECK = "authenticity_check"
    GAP_POINT = "gap_point"
    MATCHED_POINT = "matched_point"
    RETRIEVED_KNOWLEDGE = "retrieved_knowledge"


class EvidenceSourceType:
    RESUME_DOCUMENT = "resume_document"
    JOB_DESCRIPTION = "job_description"
    JD_ANALYSIS = "jd_analysis"
    RESUME_PROFILE = "resume_profile"
    GAP_ANALYSIS = "gap_analysis"
    INTERVIEW_MESSAGE = "interview_message"
    INTERVIEW_PLAN_EXECUTION = "interview_plan_execution"
    INTERVIEW_EVALUATION = "interview_evaluation"
    RESUME_AUTHENTICITY_REPORT = "resume_authenticity_report"
    KNOWLEDGE_SOURCE = "knowledge_source"


ALLOWED_EVIDENCE_TYPES = frozenset(
    {
        EvidenceType.RESUME_CLAIM,
        EvidenceType.JD_REQUIREMENT,
        EvidenceType.INTERVIEW_ANSWER,
        EvidenceType.EXECUTION_PROBE,
        EvidenceType.TOPIC_JUDGE,
        EvidenceType.EVALUATION_FINDING,
        EvidenceType.AUTHENTICITY_CHECK,
        EvidenceType.GAP_POINT,
        EvidenceType.MATCHED_POINT,
        EvidenceType.RETRIEVED_KNOWLEDGE,
    }
)


ALLOWED_EVIDENCE_SOURCE_TYPES = frozenset(
    {
        EvidenceSourceType.RESUME_DOCUMENT,
        EvidenceSourceType.JOB_DESCRIPTION,
        EvidenceSourceType.JD_ANALYSIS,
        EvidenceSourceType.RESUME_PROFILE,
        EvidenceSourceType.GAP_ANALYSIS,
        EvidenceSourceType.INTERVIEW_MESSAGE,
        EvidenceSourceType.INTERVIEW_PLAN_EXECUTION,
        EvidenceSourceType.INTERVIEW_EVALUATION,
        EvidenceSourceType.RESUME_AUTHENTICITY_REPORT,
        EvidenceSourceType.KNOWLEDGE_SOURCE,
    }
)


@dataclass(frozen=True)
class EvidencePacketValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metadata": self.metadata,
        }


class EvidencePacketValidator:
    REQUIRED_PACKET_FIELDS = ("packet_id", "task", "evidence_items", "missing_evidence")
    REQUIRED_ITEM_FIELDS = ("evidence_id", "evidence_type", "source_type", "content_excerpt")

    def __init__(
        self,
        allowed_evidence_types: frozenset[str] = ALLOWED_EVIDENCE_TYPES,
        allowed_source_types: frozenset[str] = ALLOWED_EVIDENCE_SOURCE_TYPES,
    ) -> None:
        self.allowed_evidence_types = allowed_evidence_types
        self.allowed_source_types = allowed_source_types

    def validate(self, packet: dict[str, Any] | None) -> EvidencePacketValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(packet, dict):
            return EvidencePacketValidationResult(
                ok=False,
                errors=("Evidence packet must be a dict",),
                metadata=self._metadata(None),
            )

        self._validate_packet_shape(packet, errors)
        evidence_items = packet.get("evidence_items") or []
        if not isinstance(evidence_items, list):
            evidence_items = []
        self._validate_items(evidence_items, errors, warnings)

        return EvidencePacketValidationResult(
            ok=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            metadata=self._metadata(packet),
        )

    def _validate_packet_shape(self, packet: dict[str, Any], errors: list[str]) -> None:
        for field_name in self.REQUIRED_PACKET_FIELDS:
            if field_name not in packet:
                errors.append(f"Evidence packet missing {field_name}")
        if "evidence_items" in packet and not isinstance(packet.get("evidence_items"), list):
            errors.append("Evidence packet evidence_items must be a list")
        if "missing_evidence" in packet and not isinstance(packet.get("missing_evidence"), list):
            errors.append("Evidence packet missing_evidence must be a list")
        if packet.get("packet_id") is not None and not str(packet.get("packet_id")).strip():
            errors.append("Evidence packet packet_id must not be empty")
        if packet.get("task") is not None and not str(packet.get("task")).strip():
            errors.append("Evidence packet task must not be empty")

    def _validate_items(
        self,
        evidence_items: list[Any],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        seen_ids = set()
        for index, item in enumerate(evidence_items, start=1):
            prefix = f"Evidence item #{index}"
            if not isinstance(item, dict):
                errors.append(f"{prefix} must be a dict")
                continue

            for field_name in self.REQUIRED_ITEM_FIELDS:
                if field_name not in item:
                    errors.append(f"{prefix} missing {field_name}")

            evidence_id = item.get("evidence_id")
            if evidence_id:
                if evidence_id in seen_ids:
                    errors.append(f"Duplicate evidence_id: {evidence_id}")
                seen_ids.add(evidence_id)
            elif "evidence_id" in item:
                errors.append(f"{prefix} evidence_id must not be empty")

            evidence_type = item.get("evidence_type")
            if evidence_type and evidence_type not in self.allowed_evidence_types:
                errors.append(f"{prefix} has unknown evidence_type: {evidence_type}")
            elif "evidence_type" in item and not evidence_type:
                errors.append(f"{prefix} evidence_type must not be empty")

            source_type = item.get("source_type")
            if source_type and source_type not in self.allowed_source_types:
                errors.append(f"{prefix} has unknown source_type: {source_type}")
            elif "source_type" in item and not source_type:
                errors.append(f"{prefix} source_type must not be empty")

            if "content_excerpt" in item and not str(item.get("content_excerpt") or "").strip():
                warnings.append(f"{prefix} content_excerpt is empty")
            if "tags" in item and not isinstance(item.get("tags"), list):
                warnings.append(f"{prefix} tags should be a list")
            if "metadata" in item and not isinstance(item.get("metadata"), dict):
                warnings.append(f"{prefix} metadata should be a dict")

    def _metadata(self, packet: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(packet, dict):
            return {
                "packet_id": None,
                "task": None,
                "evidence_count": 0,
                "evidence_types": [],
                "source_types": [],
            }
        evidence_items = packet.get("evidence_items") or []
        if not isinstance(evidence_items, list):
            evidence_items = []
        evidence_types = sorted(
            {
                item.get("evidence_type")
                for item in evidence_items
                if isinstance(item, dict) and item.get("evidence_type")
            }
        )
        source_types = sorted(
            {
                item.get("source_type")
                for item in evidence_items
                if isinstance(item, dict) and item.get("source_type")
            }
        )
        return {
            "packet_id": packet.get("packet_id"),
            "task": packet.get("task"),
            "evidence_count": len(evidence_items),
            "evidence_types": evidence_types,
            "source_types": source_types,
        }

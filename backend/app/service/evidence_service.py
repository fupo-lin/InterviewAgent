from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.interview import InterviewMessage


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    evidence_type: str
    source_type: str
    source_id: int | None
    content_excerpt: str
    project_id: int | None = None
    session_id: int | None = None
    round_no: int | None = None
    tags: tuple[str, ...] = ()
    confidence: str = "medium"
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "round_no": self.round_no,
            "content_excerpt": self.content_excerpt,
            "tags": list(self.tags),
            "confidence": self.confidence,
            "metadata": self.metadata or {},
        }


class EvidencePacketBuilder:
    def build_evaluation_packet(
        self,
        session_id: int,
        project_id: int | None = None,
        execution_state: dict | None = None,
        transcript_messages: list[InterviewMessage] | None = None,
    ) -> dict[str, Any]:
        items: list[EvidenceItem] = []
        items.extend(self._interview_answers(project_id, transcript_messages or []))
        items.extend(self._execution_probes(project_id, execution_state or {}))
        return {
            "packet_id": f"evaluation_{session_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "task": "evaluation_generation",
            "project_id": project_id,
            "session_id": session_id,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": self._missing_evaluation_evidence(items),
        }

    def build_resume_packet(
        self,
        task: str,
        project_id: int,
        resume_profile: dict | None = None,
        execution_state: dict | None = None,
        transcript_messages: list[InterviewMessage] | None = None,
        authenticity_report: dict | None = None,
    ) -> dict[str, Any]:
        items: list[EvidenceItem] = []
        items.extend(self._resume_claims(project_id, resume_profile))
        items.extend(self._interview_answers(project_id, transcript_messages or []))
        items.extend(self._execution_probes(project_id, execution_state or {}))
        items.extend(self._authenticity_checks(project_id, authenticity_report or {}))
        return {
            "packet_id": f"{task}_{project_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "task": task,
            "project_id": project_id,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": self._missing_evidence(items, resume_profile, authenticity_report),
        }

    def refs(self, packet: dict[str, Any] | None) -> list[str]:
        if not packet:
            return []
        return [item.get("evidence_id", "") for item in packet.get("evidence_items", []) if item.get("evidence_id")]

    def _resume_claims(self, project_id: int, resume_profile: dict | None) -> list[EvidenceItem]:
        if not resume_profile:
            return []
        items: list[EvidenceItem] = []
        for index, project in enumerate(resume_profile.get("projects") or [], start=1):
            summary = project.get("summary") or project.get("background") or project.get("name") or ""
            items.append(
                EvidenceItem(
                    evidence_id=f"resume_claim_project_{index}",
                    evidence_type="resume_claim",
                    source_type="resume_profile",
                    source_id=None,
                    project_id=project_id,
                    content_excerpt=self._excerpt(summary),
                    tags=("project",),
                    confidence="claim_only",
                    metadata={"project_name": project.get("name", "")},
                )
            )
            for highlight_index, highlight in enumerate(project.get("highlights") or [], start=1):
                items.append(
                    EvidenceItem(
                        evidence_id=f"resume_claim_project_{index}_highlight_{highlight_index}",
                        evidence_type="resume_claim",
                        source_type="resume_profile",
                        source_id=None,
                        project_id=project_id,
                        content_excerpt=self._excerpt(str(highlight)),
                        tags=("project", "highlight"),
                        confidence="claim_only",
                        metadata={"project_name": project.get("name", "")},
                    )
                )
        for index, skill in enumerate(resume_profile.get("skills") or [], start=1):
            if isinstance(skill, dict):
                name = skill.get("name") or ""
                evidence = skill.get("evidence") or skill.get("level_inferred") or ""
                excerpt = f"{name}: {evidence}".strip(": ")
            else:
                excerpt = str(skill)
            items.append(
                EvidenceItem(
                    evidence_id=f"resume_claim_skill_{index}",
                    evidence_type="resume_claim",
                    source_type="resume_profile",
                    source_id=None,
                    project_id=project_id,
                    content_excerpt=self._excerpt(excerpt),
                    tags=("skill",),
                    confidence="claim_only",
                )
            )
        return items

    def _interview_answers(self, project_id: int | None, messages: list[InterviewMessage]) -> list[EvidenceItem]:
        return [
            EvidenceItem(
                evidence_id=f"interview_answer_{message.id}",
                evidence_type="interview_answer",
                source_type="interview_message",
                source_id=message.id,
                project_id=project_id,
                session_id=message.session_id,
                round_no=message.round_no,
                content_excerpt=self._excerpt(message.content),
                tags=("interview", "answer"),
                confidence="medium",
            )
            for message in messages
            if message.role_type == "user"
        ]

    def _execution_probes(self, project_id: int | None, execution_state: dict) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for section_index, section in enumerate(execution_state.get("sections") or [], start=1):
            section_key = section.get("section_key") or f"section_{section_index}"
            for evidence_index, evidence in enumerate(section.get("evidence") or [], start=1):
                covered = evidence.get("covered_probe_points") or []
                items.append(
                    EvidenceItem(
                        evidence_id=f"execution_probe_{section_key}_{evidence_index}",
                        evidence_type="execution_probe",
                        source_type="interview_plan_execution",
                        source_id=None,
                        project_id=project_id,
                        round_no=evidence.get("round_no"),
                        content_excerpt=self._excerpt(evidence.get("answer_excerpt") or ""),
                        tags=tuple(str(item) for item in covered),
                        confidence=evidence.get("confidence") or "medium",
                        metadata={
                            "section_key": section_key,
                            "probe_point": evidence.get("probe_point", ""),
                            "answer_quality": evidence.get("answer_quality", ""),
                            "judge_reason": evidence.get("judge_reason", ""),
                        },
                    )
                )
        return items

    def _authenticity_checks(self, project_id: int, authenticity_report: dict) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for index, claim in enumerate(authenticity_report.get("claim_checks") or [], start=1):
            excerpt = f"{claim.get('resume_claim', '')}: {claim.get('status', '')}. {claim.get('evidence', '')}"
            items.append(
                EvidenceItem(
                    evidence_id=f"authenticity_check_{index}",
                    evidence_type="authenticity_check",
                    source_type="resume_authenticity_report",
                    source_id=None,
                    project_id=project_id,
                    content_excerpt=self._excerpt(excerpt),
                    tags=("authenticity", claim.get("status", "")),
                    confidence="high" if claim.get("status") in {"supported", "strongly_supported"} else "medium",
                    metadata={
                        "risk_level": claim.get("risk_level", ""),
                        "suggestion": claim.get("suggestion", ""),
                    },
                )
            )
        return items

    def _missing_evidence(
        self,
        items: list[EvidenceItem],
        resume_profile: dict | None,
        authenticity_report: dict | None,
    ) -> list[str]:
        missing = list((authenticity_report or {}).get("missing_evidence_to_collect") or [])
        if resume_profile and not any(item.evidence_type == "interview_answer" for item in items):
            missing.append("面试回答证据")
        if not any("指标" in item.content_excerpt or "QPS" in item.content_excerpt for item in items):
            missing.append("量化指标")
        return list(dict.fromkeys(item for item in missing if item))

    def _missing_evaluation_evidence(self, items: list[EvidenceItem]) -> list[str]:
        missing = []
        if not any(item.evidence_type == "interview_answer" for item in items):
            missing.append("面试回答证据")
        if not any(item.evidence_type == "execution_probe" for item in items):
            missing.append("面试计划执行证据")
        return missing

    def _excerpt(self, content: str, limit: int = 300) -> str:
        text = " ".join(str(content).split())
        return text[:limit]

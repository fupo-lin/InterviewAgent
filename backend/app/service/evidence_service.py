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

    def build_jd_analysis_packet(
        self,
        project_id: int,
        jd_id: int,
        jd_content: str,
    ) -> dict[str, Any]:
        items = [
            EvidenceItem(
                evidence_id=f"jd_requirement_{jd_id}",
                evidence_type="jd_requirement",
                source_type="job_description",
                source_id=jd_id,
                project_id=project_id,
                content_excerpt=self._excerpt(jd_content),
                tags=("jd", "requirement"),
                confidence="source_document",
            )
        ]
        return {
            "packet_id": f"jd_analysis_{project_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "task": "jd_analysis",
            "project_id": project_id,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": [] if jd_content.strip() else ["job_description_source_text"],
        }

    def build_resume_analysis_packet(
        self,
        project_id: int,
        resume_id: int,
        resume_content: str,
    ) -> dict[str, Any]:
        items = [
            EvidenceItem(
                evidence_id=f"resume_claim_{resume_id}",
                evidence_type="resume_claim",
                source_type="resume_document",
                source_id=resume_id,
                project_id=project_id,
                content_excerpt=self._excerpt(resume_content),
                tags=("resume", "claim"),
                confidence="source_document",
            )
        ]
        return {
            "packet_id": f"resume_analysis_{project_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "task": "resume_analysis",
            "project_id": project_id,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": [] if resume_content.strip() else ["resume_source_text"],
        }

    def build_gap_analysis_packet(
        self,
        project_id: int,
        jd_analysis_id: int,
        resume_profile_id: int,
        jd_analysis: dict,
        resume_profile: dict,
    ) -> dict[str, Any]:
        items: list[EvidenceItem] = []
        items.extend(self._jd_requirements(project_id, jd_analysis_id, jd_analysis))
        items.extend(self._resume_claims_from_profile(project_id, resume_profile_id, resume_profile))
        return {
            "packet_id": f"gap_analysis_{project_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "task": "gap_analysis",
            "project_id": project_id,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": self._missing_gap_evidence(items),
        }

    def build_interview_plan_packet(
        self,
        project_id: int,
        plan_mode: str,
        jd_analysis_id: int | None = None,
        resume_profile_id: int | None = None,
        gap_analysis_id: int | None = None,
        jd_analysis: dict | None = None,
        resume_profile: dict | None = None,
        gap_analysis: dict | None = None,
    ) -> dict[str, Any]:
        items: list[EvidenceItem] = []
        if jd_analysis_id and jd_analysis:
            items.extend(self._jd_requirements(project_id, jd_analysis_id, jd_analysis))
        if resume_profile_id and resume_profile:
            items.extend(self._resume_claims_from_profile(project_id, resume_profile_id, resume_profile))
        if gap_analysis_id and gap_analysis:
            items.extend(self._gap_findings(project_id, gap_analysis_id, gap_analysis))
        return {
            "packet_id": f"interview_plan_{project_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "task": "interview_plan_generation",
            "project_id": project_id,
            "plan_mode": plan_mode,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": self._missing_interview_plan_evidence(items, plan_mode),
        }

    def refs(self, packet: dict[str, Any] | None) -> list[str]:
        if not packet:
            return []
        return [item.get("evidence_id", "") for item in packet.get("evidence_items", []) if item.get("evidence_id")]

    def _jd_requirements(self, project_id: int, jd_analysis_id: int, jd_analysis: dict) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        requirement_sources = (
            ("core_responsibilities", "responsibility"),
            ("required_skills", "required_skill"),
            ("preferred_skills", "preferred_skill"),
            ("interview_focus", "interview_focus"),
        )
        for field_name, tag in requirement_sources:
            for index, value in enumerate(jd_analysis.get(field_name) or [], start=1):
                items.append(
                    EvidenceItem(
                        evidence_id=f"jd_analysis_{jd_analysis_id}_{field_name}_{index}",
                        evidence_type="jd_requirement",
                        source_type="jd_analysis",
                        source_id=jd_analysis_id,
                        project_id=project_id,
                        content_excerpt=self._excerpt(str(value)),
                        tags=("jd", tag),
                        confidence="medium",
                    )
                )
        return items

    def _resume_claims_from_profile(
        self,
        project_id: int,
        resume_profile_id: int,
        resume_profile: dict,
    ) -> list[EvidenceItem]:
        items = self._resume_claims(project_id, resume_profile)
        return [
            EvidenceItem(
                evidence_id=f"resume_profile_{resume_profile_id}_{item.evidence_id}",
                evidence_type=item.evidence_type,
                source_type="resume_profile",
                source_id=resume_profile_id,
                project_id=item.project_id,
                session_id=item.session_id,
                round_no=item.round_no,
                content_excerpt=item.content_excerpt,
                tags=item.tags,
                confidence=item.confidence,
                metadata=item.metadata,
            )
            for item in items
        ]

    def _gap_findings(self, project_id: int, gap_analysis_id: int, gap_analysis: dict) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for index, point in enumerate(gap_analysis.get("gap_points") or [], start=1):
            excerpt = (
                f"{point.get('jd_requirement', '')}: "
                f"{point.get('resume_current_evidence', '')}. "
                f"{point.get('interview_probe', '')}"
            )
            items.append(
                EvidenceItem(
                    evidence_id=f"gap_analysis_{gap_analysis_id}_gap_point_{index}",
                    evidence_type="gap_point",
                    source_type="gap_analysis",
                    source_id=gap_analysis_id,
                    project_id=project_id,
                    content_excerpt=self._excerpt(excerpt),
                    tags=("gap", point.get("gap_level", "")),
                    confidence="medium",
                    metadata={
                        "gap_level": point.get("gap_level", ""),
                        "resume_suggestion": point.get("resume_suggestion", ""),
                    },
                )
            )
        for index, point in enumerate(gap_analysis.get("matched_points") or [], start=1):
            excerpt = f"{point.get('jd_requirement', '')}: {point.get('resume_evidence', '')}"
            items.append(
                EvidenceItem(
                    evidence_id=f"gap_analysis_{gap_analysis_id}_matched_point_{index}",
                    evidence_type="matched_point",
                    source_type="gap_analysis",
                    source_id=gap_analysis_id,
                    project_id=project_id,
                    content_excerpt=self._excerpt(excerpt),
                    tags=("match",),
                    confidence=point.get("confidence") or "medium",
                )
            )
        return items

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

    def _missing_gap_evidence(self, items: list[EvidenceItem]) -> list[str]:
        missing = []
        if not any(item.evidence_type == "jd_requirement" for item in items):
            missing.append("jd_requirement")
        if not any(item.evidence_type == "resume_claim" for item in items):
            missing.append("resume_claim")
        return missing

    def _missing_interview_plan_evidence(self, items: list[EvidenceItem], plan_mode: str) -> list[str]:
        missing = []
        if plan_mode in {"jd_only", "jd_resume"} and not any(item.evidence_type == "jd_requirement" for item in items):
            missing.append("jd_requirement")
        if plan_mode in {"resume_only", "jd_resume"} and not any(item.evidence_type == "resume_claim" for item in items):
            missing.append("resume_claim")
        if plan_mode == "jd_resume" and not any(item.evidence_type == "gap_point" for item in items):
            missing.append("gap_point")
        return missing

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

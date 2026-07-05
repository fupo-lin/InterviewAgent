from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.models.interview import InterviewMessage
from app.service.evidence_contract import EvidencePacketValidator, EvidenceSourceType, EvidenceType


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
            "packet_id": self._packet_id("evaluation", session_id),
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
            "packet_id": self._packet_id(task, project_id),
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
                evidence_type=EvidenceType.JD_REQUIREMENT,
                source_type=EvidenceSourceType.JOB_DESCRIPTION,
                source_id=jd_id,
                project_id=project_id,
                content_excerpt=self._excerpt(jd_content),
                tags=("jd", "requirement"),
                confidence="source_document",
            )
        ]
        return {
            "packet_id": self._packet_id("jd_analysis", project_id),
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
                evidence_type=EvidenceType.RESUME_CLAIM,
                source_type=EvidenceSourceType.RESUME_DOCUMENT,
                source_id=resume_id,
                project_id=project_id,
                content_excerpt=self._excerpt(resume_content),
                tags=("resume", "claim"),
                confidence="source_document",
            )
        ]
        return {
            "packet_id": self._packet_id("resume_analysis", project_id),
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
            "packet_id": self._packet_id("gap_analysis", project_id),
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
            "packet_id": self._packet_id("interview_plan", project_id),
            "task": "interview_plan_generation",
            "project_id": project_id,
            "plan_mode": plan_mode,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": self._missing_interview_plan_evidence(items, plan_mode),
        }

    def build_topic_judge_packet(
        self,
        session_id: int,
        project_id: int | None,
        answer_message_id: int | None,
        round_no: int,
        user_answer: str,
        current_section: dict,
        execution_state: dict,
    ) -> dict[str, Any]:
        items = [
            EvidenceItem(
                evidence_id=f"interview_answer_{answer_message_id or round_no}",
                evidence_type=EvidenceType.INTERVIEW_ANSWER,
                source_type=EvidenceSourceType.INTERVIEW_MESSAGE,
                source_id=answer_message_id,
                project_id=project_id,
                session_id=session_id,
                round_no=round_no,
                content_excerpt=self._excerpt(user_answer),
                tags=("topic_judge", "answer"),
                confidence="source_message" if answer_message_id else "medium",
                metadata={
                    "section_key": current_section.get("section_key", ""),
                    "current_section_round_no": current_section.get("completed_rounds", 0),
                },
            )
        ]
        probe_point = self._first_uncovered_probe_point(current_section)
        if probe_point:
            items.append(
                EvidenceItem(
                    evidence_id=f"topic_probe_{current_section.get('section_key') or 'section'}_{round_no}",
                    evidence_type=EvidenceType.EXECUTION_PROBE,
                    source_type=EvidenceSourceType.INTERVIEW_PLAN_EXECUTION,
                    source_id=None,
                    project_id=project_id,
                    session_id=session_id,
                    round_no=round_no,
                    content_excerpt=self._excerpt(probe_point),
                    tags=("topic_judge", "probe"),
                    confidence="medium",
                    metadata={
                        "section_key": current_section.get("section_key", ""),
                        "execution_next_action": (execution_state.get("next_action") or {}).get("type", ""),
                    },
                )
            )
        return {
            "packet_id": self._packet_id("topic_judge", session_id, round_no),
            "task": "topic_completion_judge",
            "project_id": project_id,
            "session_id": session_id,
            "round_no": round_no,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": self._missing_topic_judge_evidence(items),
        }

    def build_growth_report_packet(
        self,
        session_id: int,
        project_id: int | None = None,
        transcript_messages: list[InterviewMessage] | None = None,
        execution_state: dict | None = None,
        evaluation_id: int | None = None,
        evaluation: dict | None = None,
        jd_analysis_id: int | None = None,
        jd_analysis: dict | None = None,
        resume_profile_id: int | None = None,
        resume_profile: dict | None = None,
        gap_analysis_id: int | None = None,
        gap_analysis: dict | None = None,
        authenticity_report: dict | None = None,
    ) -> dict[str, Any]:
        items: list[EvidenceItem] = []
        if project_id and jd_analysis_id and jd_analysis:
            items.extend(self._jd_requirements(project_id, jd_analysis_id, jd_analysis))
        if project_id and resume_profile_id and resume_profile:
            items.extend(self._resume_claims_from_profile(project_id, resume_profile_id, resume_profile))
        if project_id and gap_analysis_id and gap_analysis:
            items.extend(self._gap_findings(project_id, gap_analysis_id, gap_analysis))
        items.extend(self._interview_answers(project_id, transcript_messages or []))
        items.extend(self._execution_probes(project_id, execution_state or {}))
        items.extend(self._evaluation_findings(project_id, session_id, evaluation_id, evaluation or {}))
        if project_id:
            items.extend(self._authenticity_checks(project_id, authenticity_report or {}))
        return {
            "packet_id": self._packet_id("candidate_growth_report", session_id),
            "task": "candidate_growth_report_generation",
            "project_id": project_id,
            "session_id": session_id,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": self._missing_growth_report_evidence(
                items=items,
                evaluation=evaluation,
                jd_analysis=jd_analysis,
                resume_profile=resume_profile,
            ),
        }

    def build_question_generation_packet(
        self,
        task: str,
        session_id: int,
        project_id: int | None = None,
        user_answer_message_id: int | None = None,
        user_answer: str | None = None,
        round_no: int | None = None,
        recent_history: list[InterviewMessage] | None = None,
        execution_state: dict | None = None,
    ) -> dict[str, Any]:
        items: list[EvidenceItem] = []
        if user_answer:
            items.append(
                EvidenceItem(
                    evidence_id=f"interview_answer_{user_answer_message_id or round_no or 'latest'}",
                    evidence_type=EvidenceType.INTERVIEW_ANSWER,
                    source_type=EvidenceSourceType.INTERVIEW_MESSAGE,
                    source_id=user_answer_message_id,
                    project_id=project_id,
                    session_id=session_id,
                    round_no=round_no,
                    content_excerpt=self._excerpt(user_answer),
                    tags=("question_generation", "answer"),
                    confidence="source_message" if user_answer_message_id else "medium",
                )
            )
        items.extend(self._interview_answers(project_id, recent_history or []))
        items.extend(self._execution_probes(project_id, execution_state or {}))
        return {
            "packet_id": self._packet_id(task, session_id),
            "task": task,
            "project_id": project_id,
            "session_id": session_id,
            "round_no": round_no,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": self._missing_question_generation_evidence(items, task),
        }

    def build_memory_packet(
        self,
        task: str,
        session_id: int,
        project_id: int | None,
        messages: list[InterviewMessage],
    ) -> dict[str, Any]:
        items = self._interview_answers(project_id, messages)
        return {
            "packet_id": self._packet_id(task, session_id),
            "task": task,
            "project_id": project_id,
            "session_id": session_id,
            "evidence_items": [item.to_dict() for item in items],
            "missing_evidence": [] if items else ["interview_answer"],
        }

    def refs(self, packet: dict[str, Any] | None) -> list[str]:
        if not packet:
            return []
        refs = []
        for item in packet.get("evidence_items", []):
            evidence_id = item.get("evidence_id", "")
            if evidence_id and evidence_id not in refs:
                refs.append(evidence_id)
        return refs

    def validate_packet(self, packet: dict[str, Any] | None):
        return EvidencePacketValidator().validate(packet)

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
                        evidence_type=EvidenceType.JD_REQUIREMENT,
                        source_type=EvidenceSourceType.JD_ANALYSIS,
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
                source_type=EvidenceSourceType.RESUME_PROFILE,
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
                    evidence_type=EvidenceType.GAP_POINT,
                    source_type=EvidenceSourceType.GAP_ANALYSIS,
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
                    evidence_type=EvidenceType.MATCHED_POINT,
                    source_type=EvidenceSourceType.GAP_ANALYSIS,
                    source_id=gap_analysis_id,
                    project_id=project_id,
                    content_excerpt=self._excerpt(excerpt),
                    tags=("match",),
                    confidence=point.get("confidence") or "medium",
                )
            )
        return items

    def _first_uncovered_probe_point(self, current_section: dict) -> str:
        uncovered = current_section.get("uncovered_probe_points") or []
        if uncovered:
            return str(uncovered[0])
        probe_points = current_section.get("probe_points") or []
        return str(probe_points[-1]) if probe_points else ""

    def _resume_claims(self, project_id: int, resume_profile: dict | None) -> list[EvidenceItem]:
        if not resume_profile:
            return []
        items: list[EvidenceItem] = []
        for index, project in enumerate(resume_profile.get("projects") or [], start=1):
            summary = project.get("summary") or project.get("background") or project.get("name") or ""
            items.append(
                EvidenceItem(
                    evidence_id=f"resume_claim_project_{index}",
                    evidence_type=EvidenceType.RESUME_CLAIM,
                    source_type=EvidenceSourceType.RESUME_PROFILE,
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
                        evidence_type=EvidenceType.RESUME_CLAIM,
                        source_type=EvidenceSourceType.RESUME_PROFILE,
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
                    evidence_type=EvidenceType.RESUME_CLAIM,
                    source_type=EvidenceSourceType.RESUME_PROFILE,
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
                evidence_type=EvidenceType.INTERVIEW_ANSWER,
                source_type=EvidenceSourceType.INTERVIEW_MESSAGE,
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
                        evidence_type=EvidenceType.EXECUTION_PROBE,
                        source_type=EvidenceSourceType.INTERVIEW_PLAN_EXECUTION,
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
                    evidence_type=EvidenceType.AUTHENTICITY_CHECK,
                    source_type=EvidenceSourceType.RESUME_AUTHENTICITY_REPORT,
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

    def _evaluation_findings(
        self,
        project_id: int | None,
        session_id: int,
        evaluation_id: int | None,
        evaluation: dict,
    ) -> list[EvidenceItem]:
        if not evaluation:
            return []
        items: list[EvidenceItem] = []
        for field_name in (
            "summary",
            "strengths",
            "weaknesses",
            "suggestions",
            "technical_ability",
            "project_experience",
            "communication",
            "improvement_suggestions",
        ):
            value = evaluation.get(field_name)
            if not value:
                continue
            items.append(
                EvidenceItem(
                    evidence_id=f"evaluation_{evaluation_id or session_id}_{field_name}",
                    evidence_type=EvidenceType.EVALUATION_FINDING,
                    source_type=EvidenceSourceType.INTERVIEW_EVALUATION,
                    source_id=evaluation_id,
                    project_id=project_id,
                    session_id=session_id,
                    content_excerpt=self._excerpt(str(value)),
                    tags=("evaluation", field_name),
                    confidence="medium",
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
        if resume_profile and not any(item.evidence_type == EvidenceType.INTERVIEW_ANSWER for item in items):
            missing.append("面试回答证据")
        if not any("指标" in item.content_excerpt or "QPS" in item.content_excerpt for item in items):
            missing.append("量化指标")
        return list(dict.fromkeys(item for item in missing if item))

    def _missing_gap_evidence(self, items: list[EvidenceItem]) -> list[str]:
        missing = []
        if not any(item.evidence_type == EvidenceType.JD_REQUIREMENT for item in items):
            missing.append("jd_requirement")
        if not any(item.evidence_type == EvidenceType.RESUME_CLAIM for item in items):
            missing.append("resume_claim")
        return missing

    def _missing_interview_plan_evidence(self, items: list[EvidenceItem], plan_mode: str) -> list[str]:
        missing = []
        if plan_mode in {"jd_only", "jd_resume"} and not any(
            item.evidence_type == EvidenceType.JD_REQUIREMENT for item in items
        ):
            missing.append("jd_requirement")
        if plan_mode in {"resume_only", "jd_resume"} and not any(
            item.evidence_type == EvidenceType.RESUME_CLAIM for item in items
        ):
            missing.append("resume_claim")
        if plan_mode == "jd_resume" and not any(item.evidence_type == EvidenceType.GAP_POINT for item in items):
            missing.append("gap_point")
        return missing

    def _missing_topic_judge_evidence(self, items: list[EvidenceItem]) -> list[str]:
        missing = []
        if not any(item.evidence_type == EvidenceType.INTERVIEW_ANSWER for item in items):
            missing.append("interview_answer")
        if not any(item.evidence_type == EvidenceType.EXECUTION_PROBE for item in items):
            missing.append("execution_probe")
        return missing

    def _missing_question_generation_evidence(self, items: list[EvidenceItem], task: str) -> list[str]:
        missing = []
        if task == "followup_generation" and not any(
            item.evidence_type == EvidenceType.INTERVIEW_ANSWER for item in items
        ):
            missing.append("interview_answer")
        return missing

    def _missing_evaluation_evidence(self, items: list[EvidenceItem]) -> list[str]:
        missing = []
        if not any(item.evidence_type == EvidenceType.INTERVIEW_ANSWER for item in items):
            missing.append("面试回答证据")
        if not any(item.evidence_type == EvidenceType.EXECUTION_PROBE for item in items):
            missing.append("面试计划执行证据")
        return missing

    def _missing_growth_report_evidence(
        self,
        items: list[EvidenceItem],
        evaluation: dict | None,
        jd_analysis: dict | None,
        resume_profile: dict | None,
    ) -> list[str]:
        missing = []
        if not any(item.evidence_type == EvidenceType.INTERVIEW_ANSWER for item in items):
            missing.append("interview_answer")
        if not evaluation:
            missing.append("evaluation")
        if not jd_analysis:
            missing.append("jd_analysis")
        if not resume_profile:
            missing.append("resume_profile")
        return missing

    def _excerpt(self, content: str, limit: int = 300) -> str:
        text = " ".join(str(content).split())
        return text[:limit]

    def _packet_id(self, *parts: object) -> str:
        prefix = "_".join(str(part) for part in parts if part is not None)
        return f"{prefix}_{self._timestamp()}"

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

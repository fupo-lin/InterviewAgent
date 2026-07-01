from typing import Any

from app.service.prompt_registry import PromptDefinition


class PromptContractValidator:
    CONTEXT_ALIASES = {
        "RoleName": ("role_name",),
        "UserAnswer": ("user_answer", "answer_message_id"),
        "InterviewTranscriptDelta": ("message_count", "message_ids", "from_round_no", "to_round_no"),
        "JobDescription": ("jd_id", "job_description_id", "content_length"),
        "ResumeDocument": ("resume_id", "resume_document_id", "content_length"),
        "JDAnalysis": ("jd_analysis_id", "has_jd_analysis"),
        "ResumeProfile": ("resume_profile_id", "has_resume_profile"),
        "GapAnalysis": ("gap_analysis_id", "has_gap_analysis"),
        "InterviewPlan": ("interview_plan_id", "has_interview_plan", "has_plan_context"),
        "InterviewPlanExecution": ("execution_id", "has_execution_context"),
        "InterviewPlanSection": ("current_section_key",),
        "RecentHistory": ("recent_history_count",),
        "Evaluation": ("evaluation_id", "has_evaluation"),
        "ProjectCandidateProfile": ("project_candidate_profile_id", "has_project_candidate_profile"),
        "ConversationSummary": ("conversation_summary_id", "conversation_summary_summary_id"),
        "CandidateProfile": ("candidate_profile_summary_id",),
        "PreviousCandidateMemory": ("previous_summary_id", "has_previous_content"),
        "PreviousConversationSummary": ("previous_summary_id", "has_previous_content"),
    }

    def validate(
        self,
        definition: PromptDefinition,
        input_snapshot: dict[str, Any] | None,
        context_refs: dict[str, Any] | None,
        evidence_refs: list[str] | None,
    ) -> dict[str, Any]:
        input_snapshot = input_snapshot or {}
        context_refs = context_refs or {}
        evidence_packet = input_snapshot.get("evidence_packet") or {}
        evidence_items = evidence_packet.get("evidence_items") or []
        evidence_types = sorted(
            {
                item.get("evidence_type")
                for item in evidence_items
                if isinstance(item, dict) and item.get("evidence_type")
            }
        )

        present_context_keys = self._present_context_keys(input_snapshot, context_refs)
        missing_context = [
            item
            for item in definition.required_context
            if not self._context_satisfied(item, input_snapshot, context_refs)
        ]
        missing_evidence = [
            item
            for item in definition.required_evidence
            if item not in evidence_types
        ]
        return {
            "schema_version": "PromptContractValidation.v1",
            "mode": "warn_only",
            "ok": not missing_context and not missing_evidence,
            "required_context": list(definition.required_context),
            "missing_context": missing_context,
            "required_evidence": list(definition.required_evidence),
            "missing_evidence": missing_evidence,
            "present_context_keys": present_context_keys,
            "present_evidence_types": evidence_types,
            "evidence_refs": evidence_refs or [],
        }

    def _context_satisfied(
        self,
        required_context: str,
        input_snapshot: dict[str, Any],
        context_refs: dict[str, Any],
    ) -> bool:
        aliases = self.CONTEXT_ALIASES.get(required_context, ())
        candidates = (required_context, self._snake_case(required_context), *aliases)
        return any(
            self._has_value(input_snapshot.get(candidate)) or self._has_value(context_refs.get(candidate))
            for candidate in candidates
        )

    def _present_context_keys(self, input_snapshot: dict[str, Any], context_refs: dict[str, Any]) -> list[str]:
        keys = set()
        for source in (input_snapshot, context_refs):
            for key, value in source.items():
                if key == "evidence_packet":
                    continue
                if self._has_value(value):
                    keys.add(key)
        return sorted(keys)

    def _has_value(self, value: Any) -> bool:
        if value is None or value is False:
            return False
        if isinstance(value, (str, list, tuple, dict, set)):
            return bool(value)
        return True

    def _snake_case(self, value: str) -> str:
        result = []
        for index, char in enumerate(value):
            if char.isupper() and index > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

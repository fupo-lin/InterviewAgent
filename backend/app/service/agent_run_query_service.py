from typing import Any

from fastapi import HTTPException

from app.models.agent import AgentRun
from app.repository.agent_run_repository import AgentRunRepository
from app.schemas.agent_run import (
    AgentRunDetailResponse,
    AgentRunListItem,
    AgentRunListResponse,
    AgentRunValidationSummary,
)


class AgentRunQueryService:
    def __init__(self, db: Any):
        self.repo = AgentRunRepository(db)

    def list_runs(
        self,
        project_id: int | None = None,
        session_id: int | None = None,
        status: str | None = None,
        agent_name: str | None = None,
        prompt_id: str | None = None,
        only_issues: bool = False,
        limit: int = 50,
    ) -> AgentRunListResponse:
        runs = self.repo.list(
            project_id=project_id,
            session_id=session_id,
            status=status,
            agent_name=agent_name,
            prompt_id=prompt_id,
            limit=self._limit(limit),
        )
        items = [self._list_item(run) for run in runs]
        if only_issues:
            items = [item for item in items if self._has_issue(item)]
        return AgentRunListResponse(items=items, total=len(items))

    def failed_runs(
        self,
        project_id: int | None = None,
        session_id: int | None = None,
        limit: int = 50,
    ) -> AgentRunListResponse:
        runs = self.repo.list_failed(
            project_id=project_id,
            session_id=session_id,
            limit=self._limit(limit),
        )
        items = [self._list_item(run) for run in runs]
        return AgentRunListResponse(items=items, total=len(items))

    def get_detail(self, agent_run_id: int) -> AgentRunDetailResponse:
        run = self.repo.get_by_id(agent_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Agent run not found")
        item = self._list_item(run)
        return AgentRunDetailResponse(
            **item.model_dump(),
            agentVersion=run.agent_version,
            inputSchemaVersion=run.input_schema_version,
            outputSchemaVersion=run.output_schema_version,
            inputSnapshot=run.input_snapshot,
            contextRefs=run.context_refs or {},
            outputSnapshot=run.output_snapshot,
            rawResponse=run.raw_response,
        )

    def _list_item(self, run: AgentRun) -> AgentRunListItem:
        return AgentRunListItem(
            id=run.id,
            agentName=run.agent_name,
            taskName=run.task_name,
            promptId=run.prompt_id,
            promptVersion=run.prompt_version,
            modelName=run.model_name,
            projectId=run.project_id,
            sessionId=run.session_id,
            status=run.status,
            evidenceRefs=run.evidence_refs or [],
            validation=self._validation_summary(run.input_snapshot or {}),
            errorMessage=run.error_message,
            createTime=run.create_time,
        )

    def _validation_summary(self, input_snapshot: dict) -> AgentRunValidationSummary:
        prompt_validation = input_snapshot.get("prompt_contract_validation") or {}
        evidence_validation = input_snapshot.get("evidence_packet_validation") or {}
        return AgentRunValidationSummary(
            promptContractOk=prompt_validation.get("ok"),
            evidencePacketOk=evidence_validation.get("ok"),
            promptMissingContext=prompt_validation.get("missing_context") or [],
            promptMissingEvidence=prompt_validation.get("missing_evidence") or [],
            evidenceErrors=evidence_validation.get("errors") or [],
            evidenceWarnings=evidence_validation.get("warnings") or [],
        )

    def _has_issue(self, item: AgentRunListItem) -> bool:
        validation = item.validation
        return (
            item.status != "success"
            or validation.prompt_contract_ok is False
            or validation.evidence_packet_ok is False
            or bool(validation.prompt_missing_context)
            or bool(validation.prompt_missing_evidence)
            or bool(validation.evidence_errors)
        )

    def _limit(self, limit: int) -> int:
        return max(1, min(limit, 200))

from typing import Any

from fastapi import HTTPException

from app.models.agent import AgentRun
from app.repository.agent_run_repository import AgentRunRepository
from app.schemas.agent_run import (
    AgentRunDetailResponse,
    AgentRunListItem,
    AgentRunListResponse,
    AgentRunValidationSummary,
    AgentRunWorkflowSummary,
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
        workflow_id: str | None = None,
        workflow_run_id: str | None = None,
        workflow_step_id: str | None = None,
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
        items = self._filter_workflow(
            items=items,
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
            workflow_step_id=workflow_step_id,
        )
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
            workflow=self._workflow_summary(run.input_snapshot or {}),
            validation=self._validation_summary(run.input_snapshot or {}),
            errorMessage=run.error_message,
            createTime=run.create_time,
        )

    def _workflow_summary(self, input_snapshot: dict) -> AgentRunWorkflowSummary:
        workflow_context = input_snapshot.get("workflow_context") or {}
        return AgentRunWorkflowSummary(
            workflowId=workflow_context.get("workflow_id"),
            workflowRunId=workflow_context.get("workflow_run_id"),
            stepId=workflow_context.get("step_id"),
        )

    def _filter_workflow(
        self,
        items: list[AgentRunListItem],
        workflow_id: str | None,
        workflow_run_id: str | None,
        workflow_step_id: str | None,
    ) -> list[AgentRunListItem]:
        if not any((workflow_id, workflow_run_id, workflow_step_id)):
            return items
        return [
            item
            for item in items
            if self._matches_workflow(item, workflow_id, workflow_run_id, workflow_step_id)
        ]

    def _matches_workflow(
        self,
        item: AgentRunListItem,
        workflow_id: str | None,
        workflow_run_id: str | None,
        workflow_step_id: str | None,
    ) -> bool:
        workflow = item.workflow
        return (
            (workflow_id is None or workflow.workflow_id == workflow_id)
            and (workflow_run_id is None or workflow.workflow_run_id == workflow_run_id)
            and (workflow_step_id is None or workflow.step_id == workflow_step_id)
        )

    def _validation_summary(self, input_snapshot: dict) -> AgentRunValidationSummary:
        agent_validation = input_snapshot.get("agent_definition_validation") or {}
        workflow_validation = input_snapshot.get("workflow_context_validation") or {}
        prompt_validation = input_snapshot.get("prompt_contract_validation") or {}
        evidence_validation = input_snapshot.get("evidence_packet_validation") or {}
        return AgentRunValidationSummary(
            agentDefinitionOk=agent_validation.get("ok"),
            workflowContextOk=workflow_validation.get("ok"),
            promptContractOk=prompt_validation.get("ok"),
            evidencePacketOk=evidence_validation.get("ok"),
            agentDefinitionErrors=agent_validation.get("errors") or [],
            agentDefinitionWarnings=agent_validation.get("warnings") or [],
            workflowContextErrors=workflow_validation.get("errors") or [],
            workflowContextWarnings=workflow_validation.get("warnings") or [],
            promptMissingContext=prompt_validation.get("missing_context") or [],
            promptMissingEvidence=prompt_validation.get("missing_evidence") or [],
            promptContextBoundaries=self._prompt_context_boundaries(prompt_validation),
            evidenceErrors=evidence_validation.get("errors") or [],
            evidenceWarnings=evidence_validation.get("warnings") or [],
        )

    def _prompt_context_boundaries(self, prompt_validation: dict) -> list[dict[str, str]]:
        boundaries = []
        seen = set()
        for key in ("required_context_boundaries", "optional_context_boundaries"):
            for boundary in prompt_validation.get(key) or []:
                identity = (
                    boundary.get("context_name"),
                    boundary.get("artifact_kind"),
                    boundary.get("scope"),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                boundaries.append(boundary)
        return boundaries

    def _has_issue(self, item: AgentRunListItem) -> bool:
        validation = item.validation
        return (
            item.status != "success"
            or validation.agent_definition_ok is False
            or validation.workflow_context_ok is False
            or validation.prompt_contract_ok is False
            or validation.evidence_packet_ok is False
            or bool(validation.agent_definition_errors)
            or bool(validation.workflow_context_errors)
            or bool(validation.prompt_missing_context)
            or bool(validation.prompt_missing_evidence)
            or bool(validation.evidence_errors)
        )

    def _limit(self, limit: int) -> int:
        return max(1, min(limit, 200))

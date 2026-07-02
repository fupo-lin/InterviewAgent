from collections import defaultdict
from typing import Any

from fastapi import HTTPException

from app.repository.agent_run_repository import AgentRunRepository
from app.schemas.agent_run import AgentRunListItem
from app.schemas.workflow_run import (
    WorkflowRunDetailResponse,
    WorkflowRunListItem,
    WorkflowRunListResponse,
    WorkflowRunStepSummary,
)
from app.service.agent_run_query_service import AgentRunQueryService
from app.service.workflow_registry import WorkflowDefinition, WorkflowRegistry, workflow_registry


class WorkflowRunQueryService:
    def __init__(
        self,
        db: Any,
        registry: WorkflowRegistry = workflow_registry,
    ) -> None:
        self.repo = AgentRunRepository(db)
        self.agent_runs = AgentRunQueryService(db)
        self.registry = registry

    def list_runs(
        self,
        workflow_id: str | None = None,
        project_id: int | None = None,
        session_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> WorkflowRunListResponse:
        items = [
            self._summary_from_group(workflow_run_id, runs)
            for workflow_run_id, runs in self._groups(
                workflow_id=workflow_id,
                project_id=project_id,
                session_id=session_id,
                limit=self._scan_limit(limit),
            ).items()
        ]
        if status:
            items = [item for item in items if item.status == status]
        items = sorted(items, key=lambda item: item.update_time or item.create_time, reverse=True)
        items = items[: self._limit(limit)]
        return WorkflowRunListResponse(items=items, total=len(items))

    def get_detail(self, workflow_run_id: str) -> WorkflowRunDetailResponse:
        groups = self._groups(workflow_run_id=workflow_run_id, limit=1000)
        runs = groups.get(workflow_run_id)
        if not runs:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        summary = self._summary_from_group(workflow_run_id, runs)
        definition = self._definition(summary.workflow_id)
        agent_run_items = [self.agent_runs._list_item(run) for run in runs]
        agent_run_items = sorted(agent_run_items, key=lambda item: item.id)
        return WorkflowRunDetailResponse(
            **summary.model_dump(),
            steps=self._step_summaries(definition, agent_run_items),
            agentRuns=agent_run_items,
        )

    def _groups(
        self,
        workflow_id: str | None = None,
        workflow_run_id: str | None = None,
        project_id: int | None = None,
        session_id: int | None = None,
        limit: int = 1000,
    ) -> dict[str, list]:
        runs = self.repo.list(
            project_id=project_id,
            session_id=session_id,
            limit=limit,
        )
        grouped = defaultdict(list)
        for run in runs:
            workflow_context = self._workflow_context(run)
            run_workflow_id = workflow_context.get("workflow_id")
            run_workflow_run_id = workflow_context.get("workflow_run_id")
            if not run_workflow_id or not run_workflow_run_id:
                continue
            if workflow_id and run_workflow_id != workflow_id:
                continue
            if workflow_run_id and run_workflow_run_id != workflow_run_id:
                continue
            grouped[run_workflow_run_id].append(run)
        return dict(grouped)

    def _summary_from_group(self, workflow_run_id: str, runs: list) -> WorkflowRunListItem:
        agent_run_items = [self.agent_runs._list_item(run) for run in runs]
        workflow_id = self._first_workflow_id(agent_run_items)
        definition = self._definition(workflow_id)
        step_summaries = self._step_summaries(definition, agent_run_items)
        failed_steps = [step.step_id for step in step_summaries if step.status == "failed"]
        missing_required_steps = [
            step.step_id
            for step in step_summaries
            if step.required and step.missing
        ]
        completed_steps = [
            step.step_id
            for step in step_summaries
            if step.run_count > 0 and step.status != "failed"
        ]
        latest = max(agent_run_items, key=lambda item: item.id)
        earliest_time = min((item.create_time for item in agent_run_items), default=None)
        latest_time = max((item.create_time for item in agent_run_items), default=None)
        return WorkflowRunListItem(
            workflowRunId=workflow_run_id,
            workflowId=workflow_id,
            projectId=latest.project_id,
            sessionId=latest.session_id,
            status=self._status(failed_steps, missing_required_steps),
            completedSteps=completed_steps,
            failedSteps=failed_steps,
            missingRequiredSteps=missing_required_steps,
            stepCount=len(step_summaries),
            agentRunCount=len(agent_run_items),
            latestAgentRunId=latest.id,
            createTime=earliest_time,
            updateTime=latest_time,
        )

    def _step_summaries(
        self,
        definition: WorkflowDefinition,
        agent_run_items: list[AgentRunListItem],
    ) -> list[WorkflowRunStepSummary]:
        runs_by_step = defaultdict(list)
        for item in agent_run_items:
            if item.workflow.step_id:
                runs_by_step[item.workflow.step_id].append(item)
        summaries = []
        for step in definition.steps:
            step_runs = sorted(runs_by_step.get(step.step_id, []), key=lambda item: item.id)
            latest = step_runs[-1] if step_runs else None
            status = self._step_status(step_runs)
            summaries.append(
                WorkflowRunStepSummary(
                    stepId=step.step_id,
                    required=step.required,
                    status=status,
                    agentRunIds=[item.id for item in step_runs],
                    latestAgentRunId=latest.id if latest else None,
                    latestStatus=latest.status if latest else None,
                    runCount=len(step_runs),
                    missing=not step_runs,
                )
            )
        return summaries

    def _step_status(self, step_runs: list[AgentRunListItem]) -> str:
        if not step_runs:
            return "missing"
        if any(item.status != "success" for item in step_runs):
            return "failed"
        return "success"

    def _status(self, failed_steps: list[str], missing_required_steps: list[str]) -> str:
        if failed_steps:
            return "failed"
        if missing_required_steps:
            return "partial"
        return "success"

    def _definition(self, workflow_id: str) -> WorkflowDefinition:
        try:
            return self.registry.get(workflow_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow definition not found") from exc

    def _first_workflow_id(self, items: list[AgentRunListItem]) -> str:
        for item in items:
            if item.workflow.workflow_id:
                return item.workflow.workflow_id
        return ""

    def _workflow_context(self, run) -> dict:
        return (run.input_snapshot or {}).get("workflow_context") or {}

    def _limit(self, limit: int) -> int:
        return max(1, min(limit, 200))

    def _scan_limit(self, limit: int) -> int:
        return max(self._limit(limit), 1000)

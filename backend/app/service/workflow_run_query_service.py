from collections import defaultdict
from typing import Any

from fastapi import HTTPException

from app.repository.agent_run_repository import AgentRunRepository
from app.repository.workflow_run_repository import WorkflowRunRepository
from app.schemas.agent_run import AgentRunListItem
from app.schemas.workflow_run import (
    WorkflowRunDetailResponse,
    WorkflowRunListItem,
    WorkflowRunListQuery,
    WorkflowRunListResponse,
    WorkflowRunStepSummary,
)
from app.service.agent_run_query_service import AgentRunQueryService
from app.service.workflow_registry import WorkflowDefinition, WorkflowRegistry, workflow_registry
from app.service.workflow_step_metrics import step_metrics_summary


class WorkflowRunQueryService:
    def __init__(
        self,
        db: Any,
        registry: WorkflowRegistry = workflow_registry,
    ) -> None:
        self.repo = AgentRunRepository(db)
        self.workflow_repo = WorkflowRunRepository(db)
        self.agent_runs = AgentRunQueryService(db)
        self.registry = registry

    def list_runs(
        self,
        query: WorkflowRunListQuery | None = None,
        workflow_id: str | None = None,
        project_id: int | None = None,
        session_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> WorkflowRunListResponse:
        query = query or WorkflowRunListQuery(
            workflow_id=workflow_id,
            project_id=project_id,
            session_id=session_id,
            status=status,
            limit=limit,
        )
        workflow_runs = self.workflow_repo.list(
            workflow_id=query.workflow_id,
            project_id=query.project_id,
            session_id=query.session_id,
            status=query.status,
            limit=query.limit,
        )
        if workflow_runs:
            items = [
                self._summary_from_workflow_run(item)
                for item in workflow_runs
            ]
        else:
            items = [
                self._summary_from_group(workflow_run_id, runs)
                for workflow_run_id, runs in self._groups(
                    workflow_id=query.workflow_id,
                    project_id=query.project_id,
                    session_id=query.session_id,
                    limit=self._scan_limit(query.limit),
                ).items()
            ]
            if query.status:
                items = [item for item in items if item.status == query.status]
        # 列表按更新时间倒序；没有 update_time 时用 create_time 兜底。
        items = sorted(items, key=lambda item: item.update_time or item.create_time, reverse=True)
        items = items[: query.limit]
        return WorkflowRunListResponse(items=items, total=len(items))

    def get_detail(self, workflow_run_id: str) -> WorkflowRunDetailResponse:
        workflow_run = self.workflow_repo.get_by_workflow_run_id(workflow_run_id)
        if workflow_run:
            summary = self._summary_from_workflow_run(workflow_run)
            state = workflow_run.state or {}
            runs = self._groups(workflow_run_id=workflow_run_id, limit=1000).get(
                workflow_run_id,
                [],
            )
            agent_run_items = [self.agent_runs._list_item(run) for run in runs]
            agent_run_items = sorted(agent_run_items, key=lambda item: item.id)
            definition = self._definition(summary.workflow_id)
            return WorkflowRunDetailResponse(
                **summary.model_dump(),
                steps=self._step_summaries(definition, agent_run_items, workflow_run),
                agentRuns=agent_run_items,
                stepMetricsSummary=step_metrics_summary(state),
                stepMetrics=self._step_metrics(state),
                state=state,
                lastError=workflow_run.last_error,
            )

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
            stepMetricsSummary=step_metrics_summary({}),
            stepMetrics=[],
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
            threadId=None,
            projectId=latest.project_id,
            sessionId=latest.session_id,
            status=self._status(failed_steps, missing_required_steps),
            currentStep=None,
            activeStep=None,
            resumeReason=None,
            resumeFromStep=None,
            completedSteps=completed_steps,
            failedSteps=failed_steps,
            missingRequiredSteps=missing_required_steps,
            errorMessage=None,
            stepCount=len(step_summaries),
            agentRunCount=len(agent_run_items),
            latestAgentRunId=latest.id,
            createTime=earliest_time,
            updateTime=latest_time,
        )

    def _summary_from_workflow_run(self, workflow_run) -> WorkflowRunListItem:
        state = workflow_run.state or {}
        agent_runs = self._groups(
            workflow_run_id=workflow_run.workflow_run_id,
            project_id=workflow_run.project_id,
            session_id=workflow_run.session_id,
            limit=1000,
        ).get(workflow_run.workflow_run_id, [])
        latest_agent_run = max(agent_runs, key=lambda run: run.id) if agent_runs else None
        definition = self._definition(workflow_run.workflow_id)
        step_count = len(definition.steps)
        return WorkflowRunListItem(
            workflowRunId=workflow_run.workflow_run_id,
            workflowId=workflow_run.workflow_id,
            threadId=workflow_run.thread_id,
            projectId=workflow_run.project_id,
            sessionId=workflow_run.session_id,
            status=workflow_run.status,
            currentStep=workflow_run.current_step,
            activeStep=state.get("active_step"),
            resumeReason=state.get("resume_reason"),
            resumeFromStep=state.get("resume_from_step"),
            completedSteps=state.get("completed_steps") or [],
            failedSteps=state.get("failed_steps") or [],
            missingRequiredSteps=[],
            errorMessage=self._error_message(workflow_run),
            stepCount=step_count,
            agentRunCount=len(agent_runs),
            latestAgentRunId=latest_agent_run.id if latest_agent_run else None,
            createTime=workflow_run.create_time,
            updateTime=workflow_run.update_time,
        )

    def _step_summaries(
        self,
        definition: WorkflowDefinition,
        agent_run_items: list[AgentRunListItem],
        workflow_run=None,
    ) -> list[WorkflowRunStepSummary]:
        runs_by_step = defaultdict(list)
        for item in agent_run_items:
            if item.workflow.step_id:
                runs_by_step[item.workflow.step_id].append(item)
        summaries = []
        state = (workflow_run.state or {}) if workflow_run else {}
        completed_steps = set(state.get("completed_steps") or [])
        failed_steps = set(state.get("failed_steps") or [])
        skipped_steps = set(state.get("skipped_steps") or [])
        current_step = workflow_run.current_step if workflow_run else None
        for step in definition.steps:
            step_runs = sorted(runs_by_step.get(step.step_id, []), key=lambda item: item.id)
            latest = step_runs[-1] if step_runs else None
            status = self._step_status(step_runs)
            if step.step_id in failed_steps:
                status = "failed"
            elif step.step_id in skipped_steps:
                status = "skipped"
            elif step.step_id in completed_steps:
                status = "success"
            elif step.step_id == current_step:
                status = workflow_run.status if workflow_run else status
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

    def _step_metrics(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            item
            for item in state.get("step_metrics") or []
            if isinstance(item, dict)
        ]

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

    def _error_message(self, workflow_run) -> str | None:
        error_message = getattr(workflow_run, "error_message", None)
        if error_message:
            return error_message
        last_error = getattr(workflow_run, "last_error", None) or {}
        return last_error.get("message")

    def _limit(self, limit: int) -> int:
        return max(1, min(limit, 200))

    def _scan_limit(self, limit: int) -> int:
        return max(self._limit(limit), 1000)

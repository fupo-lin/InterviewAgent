from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.agent_run import AgentRunListItem


WorkflowRunStatus = Literal["queued", "running", "waiting_user", "failed", "success", "partial", "finished"]
WorkflowRunResumeReason = Literal[
    "new_user_input",
    "unfinished_turn",
    "failed_retry",
    "new_trigger",
    "unfinished_run",
    "already_completed",
]
WorkflowRunStepStatus = Literal[
    "missing",
    "running",
    "waiting_user",
    "failed",
    "success",
    "skipped",
]


class WorkflowRunListQuery(BaseModel):
    workflow_id: str | None = Field(default=None, alias="workflowId")
    project_id: int | None = Field(default=None, alias="projectId")
    session_id: int | None = Field(default=None, alias="sessionId")
    status: WorkflowRunStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)

    class Config:
        populate_by_name = True


class WorkflowRunStepSummary(BaseModel):
    step_id: str = Field(alias="stepId")
    required: bool
    status: WorkflowRunStepStatus
    agent_run_ids: list[int] = Field(default_factory=list, alias="agentRunIds")
    latest_agent_run_id: int | None = Field(default=None, alias="latestAgentRunId")
    latest_status: str | None = Field(default=None, alias="latestStatus")
    run_count: int = Field(default=0, alias="runCount")
    missing: bool = False

    class Config:
        populate_by_name = True


class WorkflowStepMetric(BaseModel):
    step_id: str = Field(alias="stepId")
    status: str
    latency_ms: int = Field(default=0, alias="latencyMs")
    current_step: str | None = Field(default=None, alias="currentStep")
    recorded_at: str | None = Field(default=None, alias="recordedAt")
    error_type: str | None = Field(default=None, alias="errorType")
    error_message: str | None = Field(default=None, alias="errorMessage")

    class Config:
        populate_by_name = True


class WorkflowStepMetricsSummary(BaseModel):
    step_count: int = Field(default=0, alias="stepCount")
    failed_step_count: int = Field(default=0, alias="failedStepCount")
    total_latency_ms: int = Field(default=0, alias="totalLatencyMs")
    last_step_id: str | None = Field(default=None, alias="lastStepId")

    class Config:
        populate_by_name = True


class WorkflowRunListItem(BaseModel):
    workflow_run_id: str = Field(alias="workflowRunId")
    workflow_id: str = Field(alias="workflowId")
    thread_id: str | None = Field(default=None, alias="threadId")
    project_id: int | None = Field(default=None, alias="projectId")
    session_id: int | None = Field(default=None, alias="sessionId")
    status: WorkflowRunStatus
    current_step: str | None = Field(default=None, alias="currentStep")
    active_step: str | None = Field(default=None, alias="activeStep")
    resume_reason: WorkflowRunResumeReason | None = Field(default=None, alias="resumeReason")
    resume_from_step: str | None = Field(default=None, alias="resumeFromStep")
    completed_steps: list[str] = Field(default_factory=list, alias="completedSteps")
    failed_steps: list[str] = Field(default_factory=list, alias="failedSteps")
    missing_required_steps: list[str] = Field(default_factory=list, alias="missingRequiredSteps")
    error_message: str | None = Field(default=None, alias="errorMessage")
    step_count: int = Field(default=0, alias="stepCount")
    agent_run_count: int = Field(default=0, alias="agentRunCount")
    latest_agent_run_id: int | None = Field(default=None, alias="latestAgentRunId")
    create_time: datetime | None = Field(default=None, alias="createTime")
    update_time: datetime | None = Field(default=None, alias="updateTime")

    class Config:
        populate_by_name = True


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunListItem]
    total: int


class WorkflowRunDetailResponse(WorkflowRunListItem):
    steps: list[WorkflowRunStepSummary] = Field(default_factory=list)
    agent_runs: list[AgentRunListItem] = Field(default_factory=list, alias="agentRuns")
    step_metrics_summary: WorkflowStepMetricsSummary = Field(
        default_factory=WorkflowStepMetricsSummary,
        alias="stepMetricsSummary",
    )
    step_metrics: list[WorkflowStepMetric] = Field(default_factory=list, alias="stepMetrics")
    state: dict | None = None
    last_error: dict | None = Field(default=None, alias="lastError")

    class Config:
        populate_by_name = True


class WorkflowRunReconciliationCheck(BaseModel):
    name: str
    ok: bool
    level: str
    detail: str


class WorkflowRunReconciliationResponse(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: list[WorkflowRunReconciliationCheck] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

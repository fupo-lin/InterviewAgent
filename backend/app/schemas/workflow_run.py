from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.agent_run import AgentRunListItem


class WorkflowRunStepSummary(BaseModel):
    step_id: str = Field(alias="stepId")
    required: bool
    status: str
    agent_run_ids: list[int] = Field(default_factory=list, alias="agentRunIds")
    latest_agent_run_id: int | None = Field(default=None, alias="latestAgentRunId")
    latest_status: str | None = Field(default=None, alias="latestStatus")
    run_count: int = Field(default=0, alias="runCount")
    missing: bool = False

    class Config:
        populate_by_name = True


class WorkflowRunListItem(BaseModel):
    workflow_run_id: str = Field(alias="workflowRunId")
    workflow_id: str = Field(alias="workflowId")
    project_id: int | None = Field(default=None, alias="projectId")
    session_id: int | None = Field(default=None, alias="sessionId")
    status: str
    completed_steps: list[str] = Field(default_factory=list, alias="completedSteps")
    failed_steps: list[str] = Field(default_factory=list, alias="failedSteps")
    missing_required_steps: list[str] = Field(default_factory=list, alias="missingRequiredSteps")
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

    class Config:
        populate_by_name = True

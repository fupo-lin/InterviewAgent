from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator


WorkflowStatus = Literal["queued", "running", "waiting_user", "failed", "success", "partial", "finished"]


class WorkflowStateContractError(ValueError):
    def __init__(self, workflow_id: str, errors: list[str]) -> None:
        self.workflow_id = workflow_id
        self.errors = errors
        super().__init__(f"Invalid workflow state for {workflow_id}: {'; '.join(errors)}")


class WorkflowStateBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    workflow_id: str = Field(min_length=1)
    workflow_run_id: str | None = None
    thread_id: str = Field(min_length=1)
    status: WorkflowStatus
    active_step: str | None = None
    project_id: StrictInt | None = Field(default=None, gt=0)
    session_id: StrictInt = Field(gt=0)
    session_uid: str = Field(min_length=1)
    completed_steps: list[str] = Field(default_factory=list)
    failed_steps: list[str] = Field(default_factory=list)
    last_error: dict[str, Any] | None = None
    resume_reason: str | None = None
    resume_from_step: str | None = None

    @model_validator(mode="after")
    def failed_state_has_error(self):
        if self.status == "failed" and not self.last_error:
            raise ValueError("failed state requires last_error")
        return self


class InterviewRuntimeStateContract(WorkflowStateBase):
    workflow_id: Literal["interview_runtime"]
    role_name: str = Field(min_length=1)
    interview_plan_id: StrictInt | None = Field(default=None, gt=0)
    current_section_index: StrictInt = Field(ge=0)
    current_section_round_no: StrictInt = Field(ge=0)
    total_completed_round_no: StrictInt = Field(ge=0)
    route_after_advance: str | None = None
    route_after_advance_reason: str | None = None
    incoming_user_input: str | None = None
    expected_user_round_no: StrictInt | None = Field(default=None, ge=0)
    last_memory_agent_run_ids: list[StrictInt] = Field(default_factory=list)

    @model_validator(mode="after")
    def waiting_user_has_assistant_message(self):
        if self.status == "waiting_user" and self.model_extra.get("last_assistant_message_id") is None:
            raise ValueError("waiting_user state requires last_assistant_message_id")
        return self


class AssessmentOutputsContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    contract_version: str = Field(min_length=1)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)


class PostInterviewAssessmentStateContract(WorkflowStateBase):
    workflow_id: Literal["post_interview_assessment"]
    incoming_trigger: str = Field(min_length=1)
    skipped_steps: list[str] = Field(default_factory=list)
    partial_reason: str | None = None
    branch: str | None = None
    branch_reason: str | None = None
    branch_decisions: list[dict[str, Any]] = Field(default_factory=list)
    output_contract_version: str = Field(min_length=1)
    outputs: AssessmentOutputsContract
    next_actions: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def partial_state_has_reason(self):
        if self.status == "partial" and not self.partial_reason:
            raise ValueError("partial assessment state requires partial_reason")
        return self


class CandidateGrowthReportStateContract(WorkflowStateBase):
    workflow_id: Literal["candidate_growth_report"]
    incoming_trigger: str = Field(min_length=1)
    skipped_steps: list[str] = Field(default_factory=list)
    partial_reason: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    branch: str | None = None
    branch_reason: str | None = None
    branch_decisions: list[dict[str, Any]] = Field(default_factory=list)
    outputs: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def partial_state_has_missing_inputs(self):
        if self.status == "partial" and not self.missing_inputs:
            raise ValueError("partial growth report state requires missing_inputs")
        return self


_STATE_CONTRACTS: dict[str, type[WorkflowStateBase]] = {
    "interview_runtime": InterviewRuntimeStateContract,
    "post_interview_assessment": PostInterviewAssessmentStateContract,
    "candidate_growth_report": CandidateGrowthReportStateContract,
}


class WorkflowStateValidator:
    def validate(self, state: dict[str, Any]) -> dict[str, Any]:
        workflow_id = str((state or {}).get("workflow_id") or "")
        contract = _STATE_CONTRACTS.get(workflow_id)
        if not contract:
            return dict(state or {})
        try:
            return contract.model_validate(state).model_dump(mode="json", exclude_none=False)
        except ValidationError as exc:
            errors = []
            for error in exc.errors():
                location = ".".join(str(item) for item in error.get("loc", ())) or "__root__"
                errors.append(f"{location}: {error.get('msg', 'invalid value')}")
            raise WorkflowStateContractError(workflow_id, errors) from exc

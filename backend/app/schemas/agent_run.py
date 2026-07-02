from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentRunValidationSummary(BaseModel):
    agent_definition_ok: bool | None = Field(default=None, alias="agentDefinitionOk")
    prompt_contract_ok: bool | None = Field(default=None, alias="promptContractOk")
    evidence_packet_ok: bool | None = Field(default=None, alias="evidencePacketOk")
    agent_definition_errors: list[str] = Field(default_factory=list, alias="agentDefinitionErrors")
    agent_definition_warnings: list[str] = Field(default_factory=list, alias="agentDefinitionWarnings")
    prompt_missing_context: list[str] = Field(default_factory=list, alias="promptMissingContext")
    prompt_missing_evidence: list[str] = Field(default_factory=list, alias="promptMissingEvidence")
    evidence_errors: list[str] = Field(default_factory=list, alias="evidenceErrors")
    evidence_warnings: list[str] = Field(default_factory=list, alias="evidenceWarnings")

    class Config:
        populate_by_name = True


class AgentRunWorkflowSummary(BaseModel):
    workflow_id: str | None = Field(default=None, alias="workflowId")
    workflow_run_id: str | None = Field(default=None, alias="workflowRunId")
    step_id: str | None = Field(default=None, alias="stepId")

    class Config:
        populate_by_name = True


class AgentRunListItem(BaseModel):
    id: int
    agent_name: str = Field(alias="agentName")
    task_name: str = Field(alias="taskName")
    prompt_id: str = Field(alias="promptId")
    prompt_version: str = Field(alias="promptVersion")
    model_name: str | None = Field(default=None, alias="modelName")
    project_id: int | None = Field(default=None, alias="projectId")
    session_id: int | None = Field(default=None, alias="sessionId")
    status: str
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    workflow: AgentRunWorkflowSummary = Field(default_factory=AgentRunWorkflowSummary)
    validation: AgentRunValidationSummary
    error_message: str | None = Field(default=None, alias="errorMessage")
    create_time: datetime = Field(alias="createTime")

    class Config:
        populate_by_name = True


class AgentRunListResponse(BaseModel):
    items: list[AgentRunListItem]
    total: int


class AgentRunDetailResponse(AgentRunListItem):
    agent_version: str | None = Field(default=None, alias="agentVersion")
    input_schema_version: str | None = Field(default=None, alias="inputSchemaVersion")
    output_schema_version: str | None = Field(default=None, alias="outputSchemaVersion")
    input_snapshot: dict[str, Any] | None = Field(default=None, alias="inputSnapshot")
    context_refs: dict[str, Any] = Field(default_factory=dict, alias="contextRefs")
    output_snapshot: dict[str, Any] | None = Field(default=None, alias="outputSnapshot")
    raw_response: dict[str, Any] | None = Field(default=None, alias="rawResponse")

    class Config:
        populate_by_name = True

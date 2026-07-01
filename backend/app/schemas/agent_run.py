from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentRunValidationSummary(BaseModel):
    prompt_contract_ok: bool | None = Field(default=None, alias="promptContractOk")
    evidence_packet_ok: bool | None = Field(default=None, alias="evidencePacketOk")
    prompt_missing_context: list[str] = Field(default_factory=list, alias="promptMissingContext")
    prompt_missing_evidence: list[str] = Field(default_factory=list, alias="promptMissingEvidence")
    evidence_errors: list[str] = Field(default_factory=list, alias="evidenceErrors")
    evidence_warnings: list[str] = Field(default_factory=list, alias="evidenceWarnings")

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

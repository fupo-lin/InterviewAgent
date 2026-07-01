from typing import Any

from pydantic import BaseModel, Field


class AgentPromptBindingResponse(BaseModel):
    prompt_id: str = Field(alias="promptId")
    prompt_version: str = Field(alias="promptVersion")
    task: str
    input_schema: str = Field(alias="inputSchema")
    output_schema: str = Field(alias="outputSchema")
    required_context: list[str] = Field(default_factory=list, alias="requiredContext")
    optional_context: list[str] = Field(default_factory=list, alias="optionalContext")
    required_evidence: list[str] = Field(default_factory=list, alias="requiredEvidence")

    class Config:
        populate_by_name = True


class AgentDefinitionResponse(BaseModel):
    agent_name: str = Field(alias="agentName")
    prompt_ids: list[str] = Field(default_factory=list, alias="promptIds")
    tasks: list[str] = Field(default_factory=list)
    input_schemas: list[str] = Field(default_factory=list, alias="inputSchemas")
    output_schemas: list[str] = Field(default_factory=list, alias="outputSchemas")
    required_context: list[str] = Field(default_factory=list, alias="requiredContext")
    optional_context: list[str] = Field(default_factory=list, alias="optionalContext")
    required_evidence: list[str] = Field(default_factory=list, alias="requiredEvidence")
    prompts: list[AgentPromptBindingResponse] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class AgentRegistryResponse(BaseModel):
    items: list[AgentDefinitionResponse]
    total: int


class AgentRegistryValidationResponse(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

from typing import Any

from pydantic import BaseModel, Field


class ArtifactBoundaryResponse(BaseModel):
    artifact_kind: str = Field(alias="artifactKind")
    owner_agent: str = Field(alias="ownerAgent")
    agent_category: str = Field(alias="agentCategory")
    scope: str
    lifecycle: str
    storage_model: str = Field(alias="storageModel")
    output_schemas: list[str] = Field(default_factory=list, alias="outputSchemas")
    allowed_workflows: list[str] = Field(default_factory=list, alias="allowedWorkflows")
    allowed_downstream_usage: list[str] = Field(default_factory=list, alias="allowedDownstreamUsage")
    not_allowed_usage: list[str] = Field(default_factory=list, alias="notAllowedUsage")
    description: str

    class Config:
        populate_by_name = True


class ContextBoundaryResponse(BaseModel):
    context_name: str = Field(alias="contextName")
    artifact_kind: str = Field(alias="artifactKind")
    scope: str
    description: str

    class Config:
        populate_by_name = True


class ArtifactBoundaryRegistryResponse(BaseModel):
    items: list[ArtifactBoundaryResponse]
    total: int


class ContextBoundaryRegistryResponse(BaseModel):
    items: list[ContextBoundaryResponse]
    total: int


class ArtifactBoundaryValidationResponse(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

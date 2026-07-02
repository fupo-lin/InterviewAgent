from typing import Any

from pydantic import BaseModel, Field


class WorkflowStepResponse(BaseModel):
    step_id: str = Field(alias="stepId")
    agent_name: str = Field(alias="agentName")
    prompt_id: str = Field(alias="promptId")
    task: str
    required: bool
    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")

    class Config:
        populate_by_name = True


class WorkflowDefinitionResponse(BaseModel):
    workflow_id: str = Field(alias="workflowId")
    name: str
    description: str
    step_ids: list[str] = Field(default_factory=list, alias="stepIds")
    agent_names: list[str] = Field(default_factory=list, alias="agentNames")
    prompt_ids: list[str] = Field(default_factory=list, alias="promptIds")
    tasks: list[str] = Field(default_factory=list)
    steps: list[WorkflowStepResponse] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class WorkflowRegistryResponse(BaseModel):
    items: list[WorkflowDefinitionResponse]
    total: int


class WorkflowRegistryValidationResponse(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

from fastapi import APIRouter, HTTPException

from app.schemas.workflow import (
    WorkflowDefinitionResponse,
    WorkflowRegistryResponse,
    WorkflowRegistryValidationResponse,
    WorkflowStepResponse,
)
from app.service.workflow_registry import WorkflowDefinition, workflow_registry

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=WorkflowRegistryResponse, response_model_by_alias=True)
def list_workflows():
    items = [_definition_response(definition) for definition in workflow_registry.all()]
    return WorkflowRegistryResponse(items=items, total=len(items))


@router.get("/validation", response_model=WorkflowRegistryValidationResponse)
def validate_workflow_registry():
    result = workflow_registry.validate()
    return WorkflowRegistryValidationResponse(**result.to_dict())


@router.get("/{workflow_id}", response_model=WorkflowDefinitionResponse, response_model_by_alias=True)
def get_workflow(workflow_id: str):
    try:
        definition = workflow_registry.get(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow definition not found") from exc
    return _definition_response(definition)


def _definition_response(definition: WorkflowDefinition) -> WorkflowDefinitionResponse:
    return WorkflowDefinitionResponse(
        workflowId=definition.workflow_id,
        name=definition.name,
        description=definition.description,
        stepIds=list(definition.step_ids),
        agentNames=list(definition.agent_names),
        promptIds=list(definition.prompt_ids),
        tasks=list(definition.tasks),
        steps=[
            WorkflowStepResponse(
                stepId=step.step_id,
                agentName=step.agent_name,
                promptId=step.prompt_id,
                task=step.task,
                required=step.required,
                dependsOn=list(step.depends_on),
            )
            for step in definition.steps
        ],
    )

from fastapi import APIRouter, HTTPException

from app.schemas.agent import (
    AgentDefinitionResponse,
    AgentPromptBindingResponse,
    AgentRegistryResponse,
    AgentRegistryValidationResponse,
)
from app.service.agent_registry import AgentDefinition, AgentRegistry, agent_registry

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentRegistryResponse, response_model_by_alias=True)
def list_agents():
    items = [_definition_response(definition) for definition in agent_registry.all()]
    return AgentRegistryResponse(items=items, total=len(items))


@router.get("/validation", response_model=AgentRegistryValidationResponse)
def validate_agent_registry():
    result = agent_registry.validate()
    return AgentRegistryValidationResponse(**result.to_dict())


@router.get("/{agent_name}", response_model=AgentDefinitionResponse, response_model_by_alias=True)
def get_agent(agent_name: str):
    try:
        definition = agent_registry.get(agent_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent definition not found") from exc
    return _definition_response(definition)


def _definition_response(definition: AgentDefinition) -> AgentDefinitionResponse:
    return AgentDefinitionResponse(
        agentName=definition.agent_name,
        promptIds=list(definition.prompt_ids),
        tasks=list(definition.tasks),
        inputSchemas=list(definition.input_schemas),
        outputSchemas=list(definition.output_schemas),
        requiredContext=list(definition.required_context),
        optionalContext=list(definition.optional_context),
        requiredEvidence=list(definition.required_evidence),
        prompts=[
            AgentPromptBindingResponse(
                promptId=binding.prompt_id,
                promptVersion=binding.prompt_version,
                task=binding.task,
                inputSchema=binding.input_schema,
                outputSchema=binding.output_schema,
                requiredContext=list(binding.required_context),
                optionalContext=list(binding.optional_context),
                requiredEvidence=list(binding.required_evidence),
            )
            for binding in definition.prompts
        ],
    )

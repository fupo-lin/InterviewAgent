from fastapi import APIRouter, HTTPException

from app.schemas.artifact_boundary import (
    ArtifactBoundaryRegistryResponse,
    ArtifactBoundaryResponse,
    ArtifactBoundaryValidationResponse,
    ContextBoundaryRegistryResponse,
    ContextBoundaryResponse,
)
from app.service.artifact_boundary import (
    ArtifactBoundaryDefinition,
    ContextBoundaryDefinition,
    ArtifactBoundaryValidator,
    artifact_boundary_registry,
)

router = APIRouter(prefix="/artifact-boundaries", tags=["artifact-boundaries"])


@router.get("", response_model=ArtifactBoundaryRegistryResponse, response_model_by_alias=True)
def list_artifact_boundaries():
    items = [_boundary_response(definition) for definition in artifact_boundary_registry.all()]
    return ArtifactBoundaryRegistryResponse(items=items, total=len(items))


@router.get("/validation", response_model=ArtifactBoundaryValidationResponse)
def validate_artifact_boundaries():
    result = ArtifactBoundaryValidator().validate()
    return ArtifactBoundaryValidationResponse(**result.to_dict())


@router.get("/contexts", response_model=ContextBoundaryRegistryResponse, response_model_by_alias=True)
def list_context_boundaries():
    items = [_context_response(definition) for definition in artifact_boundary_registry.all_contexts()]
    return ContextBoundaryRegistryResponse(items=items, total=len(items))


@router.get("/{artifact_kind}", response_model=ArtifactBoundaryResponse, response_model_by_alias=True)
def get_artifact_boundary(artifact_kind: str):
    try:
        definition = artifact_boundary_registry.get(artifact_kind)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Artifact boundary not found") from exc
    return _boundary_response(definition)


def _boundary_response(definition: ArtifactBoundaryDefinition) -> ArtifactBoundaryResponse:
    return ArtifactBoundaryResponse(
        artifactKind=definition.artifact_kind,
        ownerAgent=definition.owner_agent,
        agentCategory=definition.agent_category,
        scope=definition.scope,
        lifecycle=definition.lifecycle,
        storageModel=definition.storage_model,
        outputSchemas=list(definition.output_schemas),
        allowedWorkflows=list(definition.allowed_workflows),
        allowedDownstreamUsage=list(definition.allowed_downstream_usage),
        notAllowedUsage=list(definition.not_allowed_usage),
        description=definition.description,
    )


def _context_response(definition: ContextBoundaryDefinition) -> ContextBoundaryResponse:
    return ContextBoundaryResponse(
        contextName=definition.context_name,
        artifactKind=definition.artifact_kind,
        scope=definition.scope,
        description=definition.description,
    )

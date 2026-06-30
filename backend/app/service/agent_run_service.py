from typing import Any

from app.models.agent import AgentRun
from app.service.prompt_registry import PromptDefinition


class AgentRunRecorder:
    def __init__(self, db):
        self.db = db

    def record_success(
        self,
        definition: PromptDefinition,
        project_id: int | None,
        session_id: int | None,
        input_snapshot: dict[str, Any],
        output_snapshot: dict[str, Any],
        raw_response: dict | None,
        model_name: str,
        evidence_refs: list[str] | None = None,
        context_refs: dict[str, Any] | None = None,
    ) -> AgentRun:
        item = AgentRun(
            agent_name=definition.owner_agent,
            agent_version="1.0.0",
            task_name=definition.task,
            project_id=project_id,
            session_id=session_id,
            input_schema_version=definition.input_schema,
            output_schema_version=definition.output_schema,
            prompt_id=definition.prompt_id,
            prompt_version=definition.version,
            model_name=model_name,
            input_snapshot=input_snapshot,
            context_refs=context_refs or {},
            evidence_refs=evidence_refs or [],
            output_snapshot=output_snapshot,
            raw_response=raw_response,
            status="success",
        )
        self.db.add(item)
        self.db.flush()
        return item

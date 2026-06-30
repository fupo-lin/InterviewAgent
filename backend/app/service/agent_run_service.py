from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.agent import AgentRun
from app.service.prompt_contract import PromptContractValidator
from app.service.prompt_registry import PromptDefinition, prompt_registry


@dataclass(frozen=True)
class AgentRunContext:
    definition: PromptDefinition
    project_id: int | None
    session_id: int | None
    input_snapshot: dict[str, Any]
    context_refs: dict[str, Any]
    evidence_refs: list[str] = field(default_factory=list)


class AgentRunRecorder:
    def __init__(self, db):
        self.db = db
        self.contract_validator = PromptContractValidator()

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
        input_snapshot = self._with_contract_validation(
            definition=definition,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=evidence_refs,
        )
        return self._create(
            definition=definition,
            project_id=project_id,
            session_id=session_id,
            input_snapshot=input_snapshot,
            output_snapshot=output_snapshot,
            raw_response=raw_response,
            model_name=model_name,
            evidence_refs=evidence_refs,
            context_refs=context_refs,
            status="success",
        )

    def record_failure(
        self,
        definition: PromptDefinition,
        project_id: int | None,
        session_id: int | None,
        input_snapshot: dict[str, Any],
        error: Exception,
        model_name: str,
        evidence_refs: list[str] | None = None,
        context_refs: dict[str, Any] | None = None,
    ) -> AgentRun:
        input_snapshot = self._with_contract_validation(
            definition=definition,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=evidence_refs,
        )
        return self._create(
            definition=definition,
            project_id=project_id,
            session_id=session_id,
            input_snapshot=input_snapshot,
            output_snapshot={},
            raw_response=None,
            model_name=model_name,
            evidence_refs=evidence_refs,
            context_refs=context_refs,
            status="failed",
            error_message=str(error),
        )

    def _create(
        self,
        definition: PromptDefinition,
        project_id: int | None,
        session_id: int | None,
        input_snapshot: dict[str, Any],
        output_snapshot: dict[str, Any],
        raw_response: dict | None,
        model_name: str,
        evidence_refs: list[str] | None,
        context_refs: dict[str, Any] | None,
        status: str,
        error_message: str | None = None,
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
            output_snapshot={},
            raw_response=raw_response,
            status=status,
            error_message=error_message,
        )
        item.output_snapshot = output_snapshot
        self.db.add(item)
        self.db.flush()
        return item

    def _with_contract_validation(
        self,
        definition: PromptDefinition,
        input_snapshot: dict[str, Any],
        context_refs: dict[str, Any] | None,
        evidence_refs: list[str] | None,
    ) -> dict[str, Any]:
        validation = self.contract_validator.validate(
            definition=definition,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=evidence_refs,
        )
        return {
            **(input_snapshot or {}),
            "prompt_contract_validation": validation,
        }


class AgentRunExecutor:
    def __init__(self, db, recorder: AgentRunRecorder | None = None):
        self.db = db
        self.recorder = recorder or AgentRunRecorder(db)

    def definition(self, prompt_id: str) -> PromptDefinition:
        return prompt_registry.get(prompt_id)

    def context(
        self,
        prompt_id: str,
        project_id: int | None,
        session_id: int | None,
        input_snapshot: dict[str, Any],
        context_refs: dict[str, Any] | None = None,
        evidence_packet: dict[str, Any] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> AgentRunContext:
        definition = self.definition(prompt_id)
        resolved_evidence_refs = evidence_refs
        if resolved_evidence_refs is None:
            resolved_evidence_refs = self._evidence_refs(evidence_packet)
        resolved_input_snapshot = dict(input_snapshot or {})
        if evidence_packet is not None and "evidence_packet" not in resolved_input_snapshot:
            resolved_input_snapshot["evidence_packet"] = evidence_packet
        return AgentRunContext(
            definition=definition,
            project_id=project_id,
            session_id=session_id,
            input_snapshot=resolved_input_snapshot,
            context_refs=context_refs or {},
            evidence_refs=resolved_evidence_refs,
        )

    async def run(
        self,
        definition: PromptDefinition,
        project_id: int | None,
        session_id: int | None,
        input_snapshot: dict[str, Any],
        context_refs: dict[str, Any],
        evidence_refs: list[str],
        model_name: str,
        call: Callable[[], Awaitable[tuple[Any, dict | None]]],
        output_snapshot: Callable[[Any], dict[str, Any]] | dict[str, Any] | None = None,
        commit_on_failure: bool = True,
    ) -> tuple[Any, dict | None, AgentRun]:
        context = AgentRunContext(
            definition=definition,
            project_id=project_id,
            session_id=session_id,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=evidence_refs,
        )
        return await self.run_context(
            context=context,
            model_name=model_name,
            call=call,
            output_snapshot=output_snapshot,
            commit_on_failure=commit_on_failure,
        )

    async def run_context(
        self,
        context: AgentRunContext,
        model_name: str,
        call: Callable[[], Awaitable[tuple[Any, dict | None]]],
        output_snapshot: Callable[[Any], dict[str, Any]] | dict[str, Any] | None = None,
        commit_on_failure: bool = True,
    ) -> tuple[Any, dict | None, AgentRun]:
        try:
            output, raw_response = await call()
        except Exception as exc:
            self.recorder.record_failure(
                definition=context.definition,
                project_id=context.project_id,
                session_id=context.session_id,
                input_snapshot=context.input_snapshot,
                context_refs=context.context_refs,
                evidence_refs=context.evidence_refs,
                error=exc,
                model_name=model_name,
            )
            if commit_on_failure:
                self.db.commit()
            raise

        agent_run = self.recorder.record_success(
            definition=context.definition,
            project_id=context.project_id,
            session_id=context.session_id,
            input_snapshot=context.input_snapshot,
            context_refs=context.context_refs,
            evidence_refs=context.evidence_refs,
            output_snapshot=self._output_snapshot(output, output_snapshot),
            raw_response=raw_response,
            model_name=model_name,
        )
        return output, raw_response, agent_run

    def _output_snapshot(
        self,
        output: Any,
        output_snapshot: Callable[[Any], dict[str, Any]] | dict[str, Any] | None,
    ) -> dict[str, Any]:
        if callable(output_snapshot):
            return output_snapshot(output)
        if output_snapshot is not None:
            return output_snapshot
        return output if isinstance(output, dict) else {"result": output}

    def _evidence_refs(self, packet: dict[str, Any] | None) -> list[str]:
        if not packet:
            return []
        refs = []
        for item in packet.get("evidence_items", []):
            evidence_id = item.get("evidence_id", "")
            if evidence_id and evidence_id not in refs:
                refs.append(evidence_id)
        return refs

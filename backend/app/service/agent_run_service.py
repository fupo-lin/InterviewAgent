from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.agent import AgentEvidenceItem, AgentRun
from app.service.agent_registry import AgentDefinitionValidator
from app.service.evidence_contract import EvidencePacketValidator
from app.service.prompt_contract import PromptContractValidator
from app.service.prompt_registry import PromptDefinition, prompt_registry
from app.service.workflow_registry import WorkflowContextValidator


@dataclass(frozen=True)
class AgentSpec:
    prompt_id: str
    project_id: int | None
    session_id: int | None
    input_snapshot: dict[str, Any]
    context_refs: dict[str, Any] = field(default_factory=dict)
    evidence_packet: dict[str, Any] | None = None
    evidence_refs: list[str] | None = None
    workflow_context: dict[str, Any] | None = None
    output_snapshot: Callable[[Any], dict[str, Any]] | dict[str, Any] | None = None
    commit_on_failure: bool = True


@dataclass(frozen=True)
class AgentRunContext:
    definition: PromptDefinition
    project_id: int | None
    session_id: int | None
    input_snapshot: dict[str, Any]
    context_refs: dict[str, Any]
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRunResult:
    output: Any
    raw_response: dict | None
    agent_run: AgentRun
    context: AgentRunContext

    @property
    def definition(self) -> PromptDefinition:
        return self.context.definition

    @property
    def output_schema(self) -> str:
        return self.context.definition.output_schema

    @property
    def evidence_refs(self) -> list[str]:
        return self.context.evidence_refs

    def artifact_fields(self) -> dict[str, Any]:
        return {
            "content": self.output,
            "raw_response": self.raw_response,
            "agent_run_id": self.agent_run.id,
            "schema_version": self.output_schema,
            "evidence_refs": self.evidence_refs,
        }

    def message_fields(self) -> dict[str, Any]:
        return {
            "content": self.output,
            "raw_response": self.raw_response,
            "agent_run_id": self.agent_run.id,
            "schema_version": self.output_schema,
            "evidence_refs": self.evidence_refs,
        }


class AgentRunRecorder:
    def __init__(self, db):
        self.db = db
        self.contract_validator = PromptContractValidator()
        self.agent_definition_validator = AgentDefinitionValidator()
        self.workflow_context_validator = WorkflowContextValidator()

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
        self._persist_evidence_items(
            agent_run=item,
            input_snapshot=input_snapshot,
            evidence_refs=evidence_refs,
        )
        return item

    def _with_contract_validation(
        self,
        definition: PromptDefinition,
        input_snapshot: dict[str, Any],
        context_refs: dict[str, Any] | None,
        evidence_refs: list[str] | None,
    ) -> dict[str, Any]:
        prompt_validation = self.contract_validator.validate(
            definition=definition,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=evidence_refs,
        )
        agent_definition_validation = self.agent_definition_validator.validate_prompt_definition(
            definition=definition,
        )
        workflow_context_validation = self.workflow_context_validator.validate(
            workflow_context=(input_snapshot or {}).get("workflow_context"),
            prompt_definition=definition,
        )
        return {
            **(input_snapshot or {}),
            "prompt_contract_validation": prompt_validation,
            "agent_definition_validation": agent_definition_validation.to_dict(),
            "workflow_context_validation": workflow_context_validation.to_dict(),
        }

    def _persist_evidence_items(
        self,
        agent_run: AgentRun,
        input_snapshot: dict[str, Any],
        evidence_refs: list[str] | None,
    ) -> None:
        evidence_packet = (input_snapshot or {}).get("evidence_packet") or {}
        evidence_items = evidence_packet.get("evidence_items") or []
        if not isinstance(evidence_items, list):
            return

        workflow_context = (input_snapshot or {}).get("workflow_context") or {}
        allowed_refs = set(evidence_refs or [])
        seen: set[str] = set()
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("evidence_id") or "").strip()
            if not evidence_id:
                continue
            if allowed_refs and evidence_id not in allowed_refs:
                continue
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            self.db.add(
                AgentEvidenceItem(
                    evidence_id=evidence_id,
                    evidence_type=item.get("evidence_type"),
                    source_type=item.get("source_type"),
                    source_id=item.get("source_id"),
                    project_id=item.get("project_id", agent_run.project_id),
                    session_id=item.get("session_id", agent_run.session_id),
                    agent_run_id=agent_run.id,
                    prompt_id=agent_run.prompt_id,
                    workflow_id=workflow_context.get("workflow_id"),
                    workflow_run_id=workflow_context.get("workflow_run_id"),
                    step_id=workflow_context.get("step_id"),
                    round_no=item.get("round_no"),
                    content_excerpt=item.get("content_excerpt"),
                    tags=item.get("tags") or [],
                    confidence=item.get("confidence"),
                    item_metadata=item.get("metadata") or {},
                )
            )


class AgentRunExecutor:
    def __init__(self, db, recorder: AgentRunRecorder | None = None):
        self.db = db
        self.recorder = recorder or AgentRunRecorder(db)

    def definition(self, prompt_id: str) -> PromptDefinition:
        return prompt_registry.get(prompt_id)

    def spec(
        self,
        prompt_id: str,
        project_id: int | None,
        session_id: int | None,
        input_snapshot: dict[str, Any],
        context_refs: dict[str, Any] | None = None,
        evidence_packet: dict[str, Any] | None = None,
        evidence_refs: list[str] | None = None,
        workflow_context: dict[str, Any] | None = None,
        output_snapshot: Callable[[Any], dict[str, Any]] | dict[str, Any] | None = None,
        commit_on_failure: bool = True,
    ) -> AgentSpec:
        return AgentSpec(
            prompt_id=prompt_id,
            project_id=project_id,
            session_id=session_id,
            input_snapshot=input_snapshot,
            context_refs=context_refs or {},
            evidence_packet=evidence_packet,
            evidence_refs=evidence_refs,
            workflow_context=workflow_context,
            output_snapshot=output_snapshot,
            commit_on_failure=commit_on_failure,
        )

    def context(
        self,
        prompt_id: str,
        project_id: int | None,
        session_id: int | None,
        input_snapshot: dict[str, Any],
        context_refs: dict[str, Any] | None = None,
        evidence_packet: dict[str, Any] | None = None,
        evidence_refs: list[str] | None = None,
        workflow_context: dict[str, Any] | None = None,
    ) -> AgentRunContext:
        definition = self.definition(prompt_id)
        resolved_evidence_refs = evidence_refs
        if resolved_evidence_refs is None:
            resolved_evidence_refs = self._evidence_refs(evidence_packet)
        resolved_input_snapshot = dict(input_snapshot or {})
        if evidence_packet is not None and "evidence_packet" not in resolved_input_snapshot:
            resolved_input_snapshot["evidence_packet"] = evidence_packet
        if evidence_packet is not None and "evidence_packet_validation" not in resolved_input_snapshot:
            resolved_input_snapshot["evidence_packet_validation"] = (
                EvidencePacketValidator().validate(evidence_packet).to_dict()
            )
        if workflow_context is not None and "workflow_context" not in resolved_input_snapshot:
            resolved_input_snapshot["workflow_context"] = workflow_context
        return AgentRunContext(
            definition=definition,
            project_id=project_id,
            session_id=session_id,
            input_snapshot=resolved_input_snapshot,
            context_refs=context_refs or {},
            evidence_refs=resolved_evidence_refs,
        )

    def context_from_spec(self, spec: AgentSpec) -> AgentRunContext:
        return self.context(
            prompt_id=spec.prompt_id,
            project_id=spec.project_id,
            session_id=spec.session_id,
            input_snapshot=spec.input_snapshot,
            context_refs=spec.context_refs,
            evidence_packet=spec.evidence_packet,
            evidence_refs=spec.evidence_refs,
            workflow_context=spec.workflow_context,
        )

    async def execute(
        self,
        prompt_id: str,
        project_id: int | None,
        session_id: int | None,
        input_snapshot: dict[str, Any],
        model_name: str,
        call: Callable[[], Awaitable[tuple[Any, dict | None]]],
        context_refs: dict[str, Any] | None = None,
        evidence_packet: dict[str, Any] | None = None,
        evidence_refs: list[str] | None = None,
        workflow_context: dict[str, Any] | None = None,
        output_snapshot: Callable[[Any], dict[str, Any]] | dict[str, Any] | None = None,
        commit_on_failure: bool = True,
    ) -> AgentRunResult:
        spec = self.spec(
            prompt_id=prompt_id,
            project_id=project_id,
            session_id=session_id,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_packet=evidence_packet,
            evidence_refs=evidence_refs,
            workflow_context=workflow_context,
            output_snapshot=output_snapshot,
            commit_on_failure=commit_on_failure,
        )
        return await self.execute_spec(
            spec=spec,
            model_name=model_name,
            call=call,
        )

    async def execute_spec(
        self,
        spec: AgentSpec,
        model_name: str,
        call: Callable[[], Awaitable[tuple[Any, dict | None]]],
    ) -> AgentRunResult:
        context = self.context_from_spec(spec)
        output, raw_response, agent_run = await self.run_context(
            context=context,
            model_name=model_name,
            call=call,
            output_snapshot=spec.output_snapshot,
            commit_on_failure=spec.commit_on_failure,
        )
        return AgentRunResult(
            output=output,
            raw_response=raw_response,
            agent_run=agent_run,
            context=context,
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

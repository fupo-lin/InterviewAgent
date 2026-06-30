from collections.abc import Awaitable, Callable
from typing import Any

from app.models.agent import AgentRun
from app.service.prompt_contract import PromptContractValidator
from app.service.prompt_registry import PromptDefinition


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
        try:
            output, raw_response = await call()
        except Exception as exc:
            self.recorder.record_failure(
                definition=definition,
                project_id=project_id,
                session_id=session_id,
                input_snapshot=input_snapshot,
                context_refs=context_refs,
                evidence_refs=evidence_refs,
                error=exc,
                model_name=model_name,
            )
            if commit_on_failure:
                self.db.commit()
            raise

        agent_run = self.recorder.record_success(
            definition=definition,
            project_id=project_id,
            session_id=session_id,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=evidence_refs,
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

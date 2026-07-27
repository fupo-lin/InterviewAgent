from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.agent_contract import AgentContractValidation
from app.service.agent_run_service import AgentRunExecutor, AgentRunResult, AgentSpec


InputT = TypeVar("InputT")

# 轻量Agent生命周期

@dataclass(frozen=True)
class AgentRuntimeConfig:
    model_name: str
    max_output_repair_attempts: int = 1


class AgentOutputValidationError(RuntimeError):
    def __init__(self, validation: AgentContractValidation) -> None:
        self.validation = validation
        message = "agent output validation failed"
        if validation.errors:
            message = f"{message}: {'; '.join(validation.errors)}"
        super().__init__(message)


class BaseAgent(ABC, Generic[InputT]):
    prompt_id: str
    input_model: type[BaseModel] | None = None
    output_model: type[BaseModel] | None = None

    def __init__(
        self,
        agent_run_executor: AgentRunExecutor,
        config: AgentRuntimeConfig,
    ) -> None:
        self.agent_run_executor = agent_run_executor
        self.config = config

    async def run(self, agent_input: InputT) -> AgentRunResult:
        input_validation = self.validate_input(agent_input)
        spec = self.build_spec(agent_input)
        self.add_contract_validation(spec, input_validation)
        return await self.agent_run_executor.execute_spec(
            spec=spec,
            model_name=self.config.model_name,
            call=lambda: self.call_model_with_output_validation(agent_input, spec),
        )

    def validate_input(self, agent_input: InputT) -> AgentContractValidation:
        validation = self._empty_validation()
        if not self.input_model:
            return validation
        try:
            self.input_model.model_validate(self.input_contract_payload(agent_input))
        except ValidationError as exc:
            validation.input_ok = False
            validation.errors.extend(self._validation_errors("input", exc))
        return validation

    async def call_model_with_output_validation(
        self,
        agent_input: InputT,
        spec: AgentSpec,
    ) -> tuple[Any, dict | None]:
        output, raw_response = await self.call_model(agent_input, spec)
        output_validation = self.validate_output(output)
        if output_validation.output_ok:
            self.merge_output_validation(spec, output_validation)
            return output, raw_response

        repaired = await self.repair_output(
            agent_input=agent_input,
            spec=spec,
            output=output,
            raw_response=raw_response,
            validation=output_validation,
        )
        if repaired is not None:
            repaired_output, repaired_raw_response = repaired
            repaired_validation = self.validate_output(repaired_output)
            self.add_output_repair_snapshot(
                spec=spec,
                initial_validation=output_validation,
                repaired_validation=repaired_validation,
            )
            self.merge_output_validation(spec, repaired_validation)
            if repaired_validation.output_ok:
                return repaired_output, self.repaired_raw_response(
                    original=raw_response,
                    repair=repaired_raw_response,
                )
            output_validation = repaired_validation

        self.merge_output_validation(spec, output_validation)
        raise AgentOutputValidationError(output_validation)

    def validate_output(self, output: Any) -> AgentContractValidation:
        validation = self._empty_validation()
        if not self.output_model:
            return validation
        try:
            self.output_model.model_validate(output)
        except ValidationError as exc:
            validation.output_ok = False
            validation.errors.extend(self._validation_errors("output", exc))
        return validation

    def input_contract_payload(self, agent_input: InputT) -> Any:
        return agent_input

    def add_contract_validation(
        self,
        spec: AgentSpec,
        validation: AgentContractValidation,
    ) -> None:
        spec.input_snapshot["agent_contract_validation"] = validation.model_dump()

    def merge_output_validation(
        self,
        spec: AgentSpec,
        validation: AgentContractValidation,
    ) -> None:
        current = spec.input_snapshot.get("agent_contract_validation") or {}
        if not isinstance(current, dict):
            current = {}
            spec.input_snapshot["agent_contract_validation"] = current
        current_errors = current.get("errors") or []
        current.update(
            {
                "output_schema": validation.output_schema,
                "output_ok": validation.output_ok,
                "errors": [*current_errors, *validation.errors],
            }
        )

    async def repair_output(
        self,
        agent_input: InputT,
        spec: AgentSpec,
        output: Any,
        raw_response: dict | None,
        validation: AgentContractValidation,
    ) -> tuple[Any, dict | None] | None:
        if self.config.max_output_repair_attempts <= 0 or not self.output_model:
            return None
        llm = getattr(self, "llm", None)
        repair = getattr(llm, "repair_structured_output", None)
        if not callable(repair):
            return None
        return await repair(
            prompt_id=spec.prompt_id,
            output=output,
            output_schema=self.output_model.model_json_schema(),
            validation_errors=validation.errors,
        )

    def add_output_repair_snapshot(
        self,
        spec: AgentSpec,
        initial_validation: AgentContractValidation,
        repaired_validation: AgentContractValidation,
    ) -> None:
        current = spec.input_snapshot.get("agent_contract_validation") or {}
        if not isinstance(current, dict):
            current = {}
            spec.input_snapshot["agent_contract_validation"] = current
        current["output_repair"] = {
            "attempted": True,
            "initial_errors": initial_validation.errors,
            "repaired_ok": repaired_validation.output_ok,
            "repaired_errors": repaired_validation.errors,
        }

    def repaired_raw_response(
        self,
        original: dict | None,
        repair: dict | None,
    ) -> dict | None:
        if original is None and repair is None:
            return None
        return {
            "output_repaired": True,
            "original": original,
            "repair": repair,
        }

    def _empty_validation(self) -> AgentContractValidation:
        return AgentContractValidation(
            input_schema=self.input_model.__name__ if self.input_model else None,
            output_schema=self.output_model.__name__ if self.output_model else None,
        )

    def _validation_errors(self, prefix: str, exc: ValidationError) -> list[str]:
        messages = []
        for error in exc.errors():
            location = ".".join(str(item) for item in error.get("loc", ())) or "__root__"
            messages.append(f"{prefix}.{location}: {error.get('msg', 'invalid value')}")
        return messages

    @abstractmethod
    def build_spec(self, agent_input: InputT) -> AgentSpec:
        raise NotImplementedError

    @abstractmethod
    async def call_model(
        self,
        agent_input: InputT,
        spec: AgentSpec,
    ) -> tuple[Any, dict | None]:
        raise NotImplementedError

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.agent_contract import AgentContractValidation
from app.service.agent_run_service import AgentRunExecutor, AgentRunResult, AgentSpec


InputT = TypeVar("InputT")


@dataclass(frozen=True)
class AgentRuntimeConfig:
    model_name: str


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
        self.merge_output_validation(spec, output_validation)
        return output, raw_response

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
        current_errors = current.get("errors") or []
        spec.input_snapshot["agent_contract_validation"] = {
            **current,
            "output_schema": validation.output_schema,
            "output_ok": validation.output_ok,
            "errors": [*current_errors, *validation.errors],
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

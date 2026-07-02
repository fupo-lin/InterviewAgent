from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from app.service.agent_run_service import AgentRunExecutor, AgentRunResult, AgentSpec


InputT = TypeVar("InputT")


@dataclass(frozen=True)
class AgentRuntimeConfig:
    model_name: str

# ABC表示这是一个抽象基类，不能直接实例化。Generic[InputT]表示这个类是一个泛型类，可以接受不同类型的输入参数。
class BaseAgent(ABC, Generic[InputT]):
    prompt_id: str

    def __init__(
        self,
        agent_run_executor: AgentRunExecutor,
        config: AgentRuntimeConfig,
    ) -> None:
        self.agent_run_executor = agent_run_executor
        self.config = config

    async def run(self, agent_input: InputT) -> AgentRunResult:
        spec = self.build_spec(agent_input)
        return await self.agent_run_executor.execute_spec(
            spec=spec,
            model_name=self.config.model_name,
            call=lambda: self.call_model(agent_input, spec),
        )

# 抽象方法(强制子类实现)
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

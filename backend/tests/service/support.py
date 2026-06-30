import sys
from pathlib import Path
from types import ModuleType


def configure_backend_imports() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    backend_root_text = str(backend_root)
    if backend_root_text not in sys.path:
        sys.path.insert(0, backend_root_text)
    _install_model_stubs()


def _install_model_stubs() -> None:
    if "app.models" not in sys.modules:
        models_module = ModuleType("app.models")
        models_module.__path__ = []
        sys.modules["app.models"] = models_module

    agent_module = ModuleType("app.models.agent")

    class AgentRun:
        pass

    agent_module.AgentRun = AgentRun
    sys.modules["app.models.agent"] = agent_module
    setattr(sys.modules["app.models"], "AgentRun", AgentRun)

    interview_module = ModuleType("app.models.interview")

    class InterviewMessage:
        pass

    interview_module.InterviewMessage = InterviewMessage
    sys.modules["app.models.interview"] = interview_module
    setattr(sys.modules["app.models"], "InterviewMessage", InterviewMessage)

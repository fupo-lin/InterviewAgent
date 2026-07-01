import sys
from pathlib import Path
from types import ModuleType


def configure_backend_imports() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    backend_root_text = str(backend_root)
    if backend_root_text not in sys.path:
        sys.path.insert(0, backend_root_text)
    _install_fastapi_stub()
    _install_model_stubs()


def _install_fastapi_stub() -> None:
    if "fastapi" in sys.modules:
        return
    fastapi_module = ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi_module.HTTPException = HTTPException
    sys.modules["fastapi"] = fastapi_module


def _install_model_stubs() -> None:
    if "app.models" not in sys.modules:
        models_module = ModuleType("app.models")
        models_module.__path__ = []
        sys.modules["app.models"] = models_module

    agent_module = ModuleType("app.models.agent")

    class AgentRun:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    agent_module.AgentRun = AgentRun
    sys.modules["app.models.agent"] = agent_module
    setattr(sys.modules["app.models"], "AgentRun", AgentRun)

    interview_module = ModuleType("app.models.interview")

    class InterviewMessage:
        pass

    interview_module.InterviewMessage = InterviewMessage
    sys.modules["app.models.interview"] = interview_module
    setattr(sys.modules["app.models"], "InterviewMessage", InterviewMessage)

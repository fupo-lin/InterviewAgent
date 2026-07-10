from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievedKnowledge:
    source_name: str
    source_type: str
    source_id: int | None
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

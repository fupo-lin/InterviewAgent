from __future__ import annotations


class LangGraphCheckpointNotAvailable(RuntimeError):
    pass


def create_memory_checkpointer():
    """Create the Phase 6 development checkpointer for interview runtime graphs."""
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    except ImportError as exc:
        raise LangGraphCheckpointNotAvailable(
            "langgraph checkpoint support is not installed."
        ) from exc

    return MemorySaver(serde=JsonPlusSerializer(pickle_fallback=True))

from __future__ import annotations

from app.service.interview_runtime_state import InterviewRuntimeState


def resume_interview_runtime_state(
    *, # 强制关键字参数，要求*后面的所有参数在调用的时候必须要明确写出参数名，以 workflow_run=some_run类似的格式
    workflow_run,
    initial_state: InterviewRuntimeState,
    session,
    incoming_user_input: str,
) -> InterviewRuntimeState:
    """Build the per-turn runtime state from persisted workflow state."""
    stored_state = dict(getattr(workflow_run, "state", None) or {}) # getattr表示安全的获取对象属性 -- getattr(对象, "属性名", 默认值)
    state: InterviewRuntimeState = {
        **dict(initial_state),
        **stored_state,
    } # 先创建一个新的字典，把initial_state和stored_state的内容都放进去，如果有重复的键，后面的会覆盖前面的
    # ** 是字典的解包操作符。它的作用是把一个字典里的所有键值对“展开”，然后合并到一个新的字典里

    state.update(
        {
            "workflow_id": initial_state["workflow_id"],
            "thread_id": initial_state["thread_id"],
            "project_id": session.project_id,
            "session_id": session.id,
            "session_uid": session.session_uid,
            "role_name": session.role_name,
            "interview_plan_id": session.interview_plan_id,
            "incoming_user_input": incoming_user_input,
            "status": "running",
            "completed_steps": [],
            "failed_steps": [],
            "last_memory_agent_run_ids": [],
            "last_error": None,
        }
    )

    if workflow_run:
        state["workflow_run_id"] = workflow_run.workflow_run_id
    else:
        state.pop("workflow_run_id", None)

    return state

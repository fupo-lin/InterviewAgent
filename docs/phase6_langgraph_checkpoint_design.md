# Phase 6 设计文档：LangGraph Checkpointer 与状态对账

本文档描述第六阶段要做什么、为什么做、怎么分步做，以及怎样判断这一阶段完成。

第五阶段已经完成了 workflow 可观测化：`workflow_runs` 可以记录状态，前端可以查看 Workflow Runs 列表和详情，LangGraph normal path 与 failed retry 已经通过测试和手动验收。

第六阶段的目标不是简单“接上 LangGraph checkpointer”，而是让 LangGraph checkpointer 成为执行层 checkpoint，同时继续保留 `workflow_runs.state` 作为业务恢复依据，并建立两者与 DB artifact 的对账关系。

---

## 1. 阶段背景

当前系统已经有三类状态和记录：

```text
workflow_runs
  业务运行记录。
  保存 status / current_step / state / last_error / error_message。
  面向业务恢复、前端调试和开发者观测。

AgentRun / message / execution / summary
  DB artifact。
  代表真实副作用是否已经发生。
  是判断 node 能否幂等跳过或重跑的依据。

LangGraph runtime state
  图执行时的内存状态。
  当前只在一次请求内流转。
```

Phase 6 要新增第四类状态：

```text
LangGraph checkpoint
  图执行层 checkpoint。
  保存 LangGraph graph state。
  支持图执行恢复、interrupt / resume 和更细粒度的执行观测。
```

关键问题是：

```text
checkpoint 说某个 node 执行过，不等于 DB 副作用一定完成。
```

例如：

```text
save_user_answer node:
  checkpoint 可能已经保存了 answer_message_obj。
  但如果 DB transaction 没有 commit，message 可能不存在。

generate_followup node:
  checkpoint 可能记录 message_fields_obj。
  但 AgentRun 是否成功落库、assistant message 是否保存，需要查 DB。
```

所以 Phase 6 的核心不是“信任 checkpoint”，而是：

```text
checkpoint + workflow_runs.state + DB artifact reconciliation
```

---

## 2. 第六阶段目标

### 2.1 目标一：引入 LangGraph checkpointer

让 `InterviewRuntimeLangGraph` 在启用 LangGraph path 时可以写入 checkpoint。

最小目标：

```text
1. 为 interview_runtime graph 配置 checkpointer。
2. 使用稳定 thread_id。
3. 每次 graph.ainvoke 都带 configurable.thread_id。
4. 可以查询或验证 checkpoint 已产生。
```

建议 thread_id：

```text
thread_id = workflow_runs.thread_id
          = interview:{session_uid}
```

原因：

```text
1. 已经是当前 workflow_run 的稳定业务线程 ID。
2. 同一个面试会话天然对应同一个 runtime thread。
3. 可以把 workflow_runs 和 LangGraph checkpoint 对齐。
```

### 2.2 目标二：明确状态职责边界

Phase 6 后，状态职责应该明确：

```text
workflow_runs.state:
  业务恢复游标。
  面向前端观测和 DB artifact 对账。
  保存 resume_reason / completed_steps / failed_steps / last IDs。

LangGraph checkpoint:
  图执行层快照。
  面向 LangGraph resume / interrupt / execution recovery。
  不直接替代业务状态。

DB artifact:
  真实副作用来源。
  message / AgentRun / execution / summary 等必须以 DB 为准。
```

判断原则：

```text
如果一个字段用于判断业务副作用是否发生，不能只信 checkpoint。
如果一个字段只是图执行中间变量，可以由 checkpoint 保存。
```

### 2.3 目标三：建立 checkpoint 对账机制

Phase 6 应该新增一个轻量对账能力，用于回答：

```text
checkpoint state
workflow_runs.state
DB artifact

三者是否一致？
```

最小对账字段：

```text
workflow_run_id
thread_id
status
current_step
incoming_user_input
last_user_message_id
last_assistant_message_id
last_topic_judge_agent_run_id
last_followup_agent_run_id
completed_steps
failed_steps
last_error
```

最小对账规则：

```text
last_user_message_id:
  如果 state 中存在，则 DB 中应存在对应 user answer message。

last_assistant_message_id:
  如果 state 中存在，则 DB 中应存在对应 assistant followup message。

last_topic_judge_agent_run_id:
  如果 state 中存在，则 DB 中应存在对应 AgentRun。

last_followup_agent_run_id:
  如果 state 中存在，则 DB 中应存在对应 AgentRun。

completed_steps 包含 advance_execution:
  execution.state 中应能找到 answer_message_id marker。

status = failed:
  last_error 应存在。
  current_step 应等于失败边界。
```

### 2.4 目标四：定义恢复策略升级路径

当前 Phase 5 的恢复策略是保守但可靠的：

```text
从 start 重新跑。
依赖 node 幂等逻辑跳过已完成副作用。
```

Phase 6 不应该一上来完全改成“从 checkpoint 中间节点恢复”。

建议采用分级策略：

```text
Level 1:
  接入 checkpointer，只记录 checkpoint。
  业务恢复仍使用 workflow_runs.state + start retry。

Level 2:
  增加 checkpoint / workflow_runs.state 对账接口或测试。
  仍不改变生产恢复路径。

Level 3:
  只在无 DB 副作用或已完成对账的安全节点尝试 checkpoint resume。

Level 4:
  引入 interrupt / resume，为 human review 做准备。
```

第六阶段建议完成 Level 1 + Level 2，谨慎探索 Level 3。

---

## 3. 不同状态来源的职责表

| 内容 | workflow_runs.state | LangGraph checkpoint | DB artifact |
| --- | --- | --- | --- |
| workflow_run_id | 必须 | 可保存 | workflow_runs 主记录 |
| thread_id | 必须 | configurable.thread_id | workflow_runs 主记录 |
| incoming_user_input | 必须 | 可保存 | message 可间接证明 |
| active_step | 必须 | 可保存 | 无 |
| current_step | workflow_runs column | 可保存 | 无 |
| completed_steps | 必须 | 可保存 | 需要 DB 对账 |
| failed_steps | 必须 | 可保存 | workflow_runs.last_error |
| last_error | 必须 | 可保存 | workflow_runs.last_error |
| answer_message_obj | 不保存 | 可临时保存但不依赖 | messages 表 |
| runtime_context_obj | 不保存 | 可临时保存但不依赖 | 多表查询重建 |
| message_fields_obj | 不保存 | 可临时保存但不依赖 | AgentRun / message |
| assistant_message_obj | 不保存 | 可临时保存但不依赖 | messages 表 |

重要结论：

```text
Python 对象不进入 workflow_runs.state。
checkpoint 可以保存图状态，但业务恢复不能依赖未对账的对象快照。
```

---

## 4. 推荐实现顺序

### 4.1 第一步：选择 checkpointer 实现

先选择最小可用实现。

建议顺序：

```text
1. 测试中使用 MemorySaver。
2. 开发环境先使用 MemorySaver 或 SQLite checkpointer。
3. 后续再评估 MySQL / production checkpointer。
```

原因：

```text
1. 当前目标是验证语义，不是先上生产级 checkpoint 存储。
2. MemorySaver 最容易覆盖测试。
3. 持久化 checkpointer 会引入迁移、清理和运维问题，可以后置。
```

### 4.2 第二步：让 InterviewRuntimeLangGraph 接收 checkpointer

目标改造：

```text
InterviewRuntimeLangGraph(
  nodes=...,
  runtime=...,
  checkpointer=...
)
```

构建图时：

```text
builder.compile(checkpointer=checkpointer)
```

调用图时：

```text
await graph.ainvoke(
  state,
  config={"configurable": {"thread_id": state["thread_id"]}},
)
```

注意：

```text
thread_id 必须和 workflow_runs.thread_id 一致。
```

### 4.3 第三步：新增 checkpoint smoke test

测试目标：

```text
1. LangGraph normal path 可以写 checkpoint。
2. checkpoint 使用 interview:{session_uid} 作为 thread_id。
3. workflow_runs.state 仍正常保存 waiting_user。
4. AgentRun workflow_run_id 不受 checkpointer 影响。
```

测试文件建议：

```text
backend/tests/service/test_interview_runtime_langgraph_checkpoint.py
```

### 4.4 第四步：新增 reconciliation service

新增轻量服务：

```text
backend/app/service/workflow_checkpoint_reconciliation.py
```

职责：

```text
输入 workflow_run。
读取 workflow_runs.state。
读取相关 DB artifact。
可选读取 checkpoint state。
输出 ok / warnings / errors / metadata。
```

第一版可以不接真实 checkpoint 存储，只对 `workflow_runs.state` 与 DB artifact 做对账。

因为这一步本身就能发现很多业务恢复问题。

### 4.5 第五步：前端或 API 暴露对账结果

可选新增 API：

```text
GET /api/workflow-runs/{workflowRunId}/reconciliation
```

返回：

```json
{
  "ok": true,
  "errors": [],
  "warnings": [],
  "checks": [
    {
      "name": "last_user_message_exists",
      "ok": true,
      "detail": "message 123 exists"
    }
  ]
}
```

前端 Workflow Run 详情页可以增加一个 Reconciliation 区域。

但 Phase 6 第一轮可以先只写 service + tests，不急着做前端。

### 4.6 第六步：探索安全 checkpoint resume

只允许在安全条件下探索：

```text
1. checkpoint state 存在。
2. workflow_runs.state 存在。
3. reconciliation ok。
4. 要恢复的 node 没有未确认 DB 副作用。
```

初期不要改变默认生产路径。

默认仍然：

```text
start retry + idempotent node
```

---

## 5. 需要补充的测试

### 5.1 checkpointer smoke tests

```text
1. LangGraph path with checkpointer can finish normal chat.
2. checkpointer receives stable thread_id.
3. workflow_runs.state remains persisted.
4. final workflow status is waiting_user.
```

### 5.2 failed checkpoint tests

```text
1. generate_followup failure still writes workflow_runs.status = failed.
2. failed transaction is committed by InterviewService.chat().
3. checkpoint presence does not hide workflow_runs.last_error.
```

### 5.3 reconciliation tests

```text
1. last_user_message_id exists -> ok.
2. last_user_message_id missing in DB -> error.
3. last_followup_agent_run_id exists -> ok.
4. completed_steps includes advance_execution but execution marker missing -> warning/error.
5. failed workflow without last_error -> error.
```

### 5.4 retry tests

```text
1. failed retry still uses old incoming_user_input.
2. waiting_user uses new input.
3. unfinished_turn uses old input.
4. checkpointer does not change these semantics.
```

---

## 6. 验收标准

Phase 6 完成时，应该满足：

```text
1. LangGraph runtime 可以配置 checkpointer。
2. checkpointer 使用稳定 thread_id。
3. normal path 下 checkpoint 和 workflow_runs 都能写入。
4. failed path 下 workflow_runs.status = failed 仍能被前端看到。
5. failed retry 语义不被 checkpointer 改变。
6. 至少有 workflow_runs.state 与 DB artifact 的 reconciliation service。
7. 至少有 reconciliation 单元测试。
8. 文档能说清楚 checkpoint、workflow_runs.state、DB artifact 三者职责。
```

如果探索了 checkpoint resume，还必须额外满足：

```text
1. 只在 reconciliation ok 的情况下启用。
2. 有测试证明不会重复创建 message。
3. 有测试证明不会重复推进 execution。
4. 有测试证明不会重复创建 AgentRun，或能复用已有 AgentRun。
```

---

## 7. 本阶段不做什么

为了避免阶段失控，Phase 6 暂不做：

```text
1. 不把 workflow_runs.state 删除。
2. 不把 LangGraph checkpoint 当成唯一恢复来源。
3. 不默认从任意 checkpoint node 恢复。
4. 不迁移 start_with_project 到 LangGraph。
5. 不迁移 end/evaluation 到 LangGraph。
6. 不做复杂 human review。
7. 不做多 workflow 编排。
8. 不做生产级 checkpoint 清理策略。
```

这些能力可以后续做，但必须建立在状态对账可靠的基础上。

---

## 8. 推荐第一轮任务

Phase 6 第一轮建议只做：

```text
1. 阅读 LangGraph checkpointer API。
2. 给 InterviewRuntimeLangGraph 增加可注入 checkpointer。
3. 在测试中使用 MemorySaver。
4. graph.ainvoke 增加 configurable.thread_id。
5. 补 normal path checkpoint smoke test。
6. 确认 workflow_runs.state 不受影响。
```

第一轮完成后，再做：

```text
1. workflow_runs.state 与 DB artifact reconciliation service。
2. reconciliation tests。
3. 可选 API 暴露对账结果。
```

---

## 9. 核心原则

```text
checkpoint 是执行层能力，不是业务事实来源。
workflow_runs.state 是业务恢复游标，不是完整上下文。
DB artifact 是副作用事实来源，不是图执行状态。
```

第六阶段最重要的工程判断是：

```text
什么时候可以相信 checkpoint？
什么时候必须回到 DB artifact 对账？
什么时候宁可从 start 幂等重跑，也不要从中间节点冒险恢复？
```

这个问题想清楚，Phase 7 的条件分支、多 workflow 编排和 human review 才能稳。

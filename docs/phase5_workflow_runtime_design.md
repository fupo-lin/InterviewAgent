# Phase 5 设计文档：Workflow 可观测化与 LangGraph 接入加固

本文档描述第五阶段要实现的内容、进入下一阶段的标准，以及这一阶段在最终目标中的位置。

第五阶段不是“继续堆功能”，而是把前面已经抽出来的 `State / Node / Workflow / workflow_runs` 变成一个真正可观察、可恢复、可验证的运行时基础设施。只有这一层足够稳定，后续接入 LangGraph checkpointer、条件分支、多 workflow 编排和更复杂的 Agent 工具链才不会变成黑盒。

---

## 1. 最终目标回顾

当前项目最终要实现的不是一个简单问答接口，而是一个可持续演进的面试 Agent 系统：

```text
候选人输入
-> Interview Runtime Workflow
-> 多个业务 Node
-> Agent 调用 / Tool 调用 / DB artifact
-> 可恢复状态
-> 可观测运行记录
-> 面试继续、结束评估、简历优化、学习建议等后续 workflow
```

最终形态应该具备：

```text
1. 面试过程可以拆成清晰的 workflow。
2. 每个 workflow 有可持久化 state。
3. 每个业务步骤有清晰 node 边界。
4. AgentRun、message、summary、execution 等 artifact 可以和 workflow_run 对齐。
5. 程序中断后可以恢复，不需要人工猜测停在哪里。
6. 后端和前端都能看到 workflow 当前状态、错误、重试原因和运行历史。
7. LangGraph 可以作为编排引擎，而不是侵入业务逻辑。
8. 未来可以加入 checkpointer、interrupt、human review、tool calling、RAG 和多 workflow 协作。
```

---

## 2. 第五阶段的位置

前面阶段已经完成了几件关键事情：

```text
Phase 1:
  跑通基础 Interview Agent 对话。

Phase 2:
  引入项目、面试计划、面试执行状态等业务结构。

Phase 3:
  建立 Agent / Prompt / Evidence / AgentRun 的治理边界。

Phase 4:
  把 InterviewService.chat() 拆成 Runtime State、Node、Workflow，并引入 workflow_runs 持久化。
```

第五阶段要做的是：

```text
把 Phase 4 的后端运行时能力变成可被使用、观察、调试和验证的系统能力。
```

也就是说，Phase 4 的重点是“拆出来并能跑”，Phase 5 的重点是“看得见、查得清、能重试、能放心打开 LangGraph path”。

---

## 3. 第五阶段核心目标

### 3.1 目标一：让 workflow_runs 成为运行时观测入口

当前后端已经保存了 `workflow_runs.state`、`status`、`current_step`、`last_error` 等信息。

第五阶段要让这些信息不仅存在数据库里，还能被前端、调试页面和开发者直接理解。

目标效果：

```text
开发者打开 Workflow Runs 页面，可以看到：

1. 当前有哪些 workflow run。
2. 每个 workflow run 属于哪个 thread / session。
3. 当前状态是 running、waiting_user 还是 failed。
4. 当前停在哪个 step。
5. 是新用户输入、未完成恢复，还是失败重试。
6. 如果失败，失败节点和错误摘要是什么。
7. 这一轮关联了哪些 AgentRun。
8. 已完成步骤和失败步骤是什么。
```

这一步的价值：

```text
以前 chat() 出错时，我们只能看日志和猜测。
Phase 5 之后，我们可以直接从 workflow_run 反推运行轨迹。
```

### 3.2 目标二：让前端具备 Workflow 调试能力

第五阶段建议开始修改前端，但不是做复杂的产品页面，而是先做一个开发期可用的 workflow observability 页面。

页面可以先简单，但信息要准确。

建议页面：

```text
/workflow-runs
  Workflow Run 列表

/workflow-runs/:workflowRunId
  Workflow Run 详情
```

列表页展示：

```text
workflowRunId
workflowId
threadId
status
currentStep
activeStep
resumeReason
errorMessage
agentRunCount
updatedAt
```

详情页展示：

```text
基础信息
状态信息
completedSteps
failedSteps
lastError
state JSON
关联 AgentRuns
```

这一阶段不要把 UI 做得过度复杂。重点是帮助你理解系统，而不是先做面向最终用户的精致工作台。

### 3.3 目标三：加固 sequential runtime 和 LangGraph runtime 的一致性

当前架构中：

```text
USE_LANGGRAPH_INTERVIEW_RUNTIME=false
  使用 sequential runtime

USE_LANGGRAPH_INTERVIEW_RUNTIME=true
  使用 LangGraph runtime
```

第五阶段应该验证两条路径对业务结果的一致性。

需要确认：

```text
1. 两条路径调用同一套 InterviewRuntimeNodes。
2. 两条路径保存相同结构的 workflow_runs.state。
3. 两条路径都能进入 waiting_user。
4. 两条路径遇到 blocking failure 时都会进入 failed。
5. 两条路径都能带上真实 workflow_run_id 创建 AgentRun。
6. 两条路径的 retry 行为一致。
```

这里的重点不是 LangGraph 用了多少高级特性，而是：

```text
LangGraph path 不应该改变业务语义。
```

第五阶段完成后，我们才能更放心地在第六阶段引入 checkpointer。

### 3.4 目标四：明确恢复语义和重试体验

当前恢复策略是保守但可靠的：

```text
不直接从中间 node 跳转恢复。
从本轮 start 重跑。
依赖每个 node 的幂等逻辑跳过已经完成的副作用。
```

第五阶段要把这个策略做得更可见、更可测。

需要覆盖的状态：

```text
waiting_user:
  上一轮已经完成，下一次输入是新一轮用户回答。

running:
  上一轮执行中断，下一次请求应该恢复旧 incoming_user_input。

failed:
  上一轮 blocking node 失败，下一次请求应该重试旧 incoming_user_input。
```

开发者在前端应该能看到：

```text
resumeReason = new_user_input
resumeReason = unfinished_turn
resumeReason = failed_retry
```

这可以帮助你判断：

```text
这次请求到底是新一轮面试，还是在修复上一轮没有完成的 workflow。
```

### 3.5 目标五：准备接入 LangGraph checkpointer，但暂不完全依赖它

第五阶段不要急着把恢复完全交给 LangGraph checkpointer。

原因：

```text
1. 当前系统的真实副作用不只在 LangGraph state 中。
2. message、AgentRun、execution、summary 都是数据库 artifact。
3. 如果只信 checkpoint，可能不知道 DB 副作用是否已经发生。
4. 业务恢复需要 state + DB artifact 对账，而不是只恢复内存快照。
```

第五阶段应该产出一个明确结论：

```text
workflow_runs.state 是当前业务恢复依据。
LangGraph checkpointer 是下一阶段要引入的执行层 checkpoint。
两者需要并存一段时间，并做 reconciliation。
```

---

## 4. 第五阶段具体交付内容

### 4.1 后端 API 稳定化

需要确认已有查询接口可以稳定返回：

```text
Workflow Run 列表
Workflow Run 详情
关联 AgentRun
state
lastError
completedSteps
failedSteps
activeStep
resumeReason
resumeFromStep
errorMessage
```

如果字段命名已经稳定，前端可以直接依赖这些字段。

如果字段还不稳定，Phase 5 应该先固定 schema，避免前端改完后后端频繁变更。

验收标准：

```text
1. Workflow Run 列表接口字段稳定。
2. Workflow Run 详情接口字段稳定。
3. failed workflow 可以看到错误摘要。
4. AgentRun 可以通过 workflow_run_id 关联回来。
5. legacy AgentRun grouping fallback 不影响 persisted workflow_runs 的优先级。
```

### 4.2 前端 Workflow Runs 列表页

建议实现一个面向开发者的列表页面。

核心字段：

```text
workflowRunId
workflowId
threadId
status
currentStep
activeStep
resumeReason
agentRunCount
errorMessage
updatedAt
```

建议交互：

```text
1. 点击一行进入详情页。
2. 支持按 status 过滤。
3. failed 状态突出显示。
4. waiting_user 状态显示为正常等待。
5. running 状态显示为需要关注。
```

注意：

```text
这个页面是开发期 observability 页面，不需要做成业务用户页面。
```

### 4.3 前端 Workflow Run 详情页

详情页用于回答一个问题：

```text
这一轮 workflow 到底发生了什么？
```

建议展示区域：

```text
1. Summary 区域
   status
   currentStep
   activeStep
   resumeReason
   resumeFromStep
   errorMessage

2. Steps 区域
   completedSteps
   failedSteps

3. State 区域
   展示 state JSON

4. Error 区域
   lastError

5. AgentRuns 区域
   每个 AgentRun 的 id、agent、status、step_id、created_at
```

详情页最重要的是帮助你定位：

```text
是哪个 node 失败？
失败前哪些副作用已经完成？
下一次 retry 会从什么语义恢复？
是否重复调用了 LLM？
AgentRun 是否正确挂在 workflow_run_id 下？
```

### 4.4 LangGraph path 加固测试

第五阶段建议补充或确认这些测试：

```text
1. sequential runtime 可以完成正常 chat。
2. LangGraph runtime 可以完成正常 chat。
3. LangGraph runtime 下 generate_followup 失败会写 failed。
4. failed retry 使用旧 incoming_user_input。
5. waiting_user 下新输入会开启新一轮。
6. AgentRun workflow_context.workflow_run_id 等于 workflow_runs.workflow_run_id。
7. WorkflowRunQueryService 能查询到 persisted workflow_run 的观测字段。
```

测试重点不是数量，而是覆盖关键恢复语义。

### 4.5 文档更新

第五阶段应该补齐三类文档：

```text
1. Phase 5 当前设计文档。
2. 项目知识地图。
3. 前端 Workflow Runs 页面使用说明。
```

本文档覆盖第 1 类。

知识地图文档用于帮助你理解：

```text
每个阶段学到了什么。
为什么项目要这么演进。
这些知识点以后怎么复用。
```

---

## 5. 第五阶段不做什么

为了避免阶段失控，Phase 5 暂不建议做：

```text
1. 不把 start_with_project 全量迁移成 LangGraph workflow。
2. 不把 end/evaluation 全量迁移成 LangGraph workflow。
3. 不马上依赖 LangGraph checkpointer 作为唯一恢复来源。
4. 不做复杂 human review。
5. 不做多 Agent 自主规划。
6. 不做复杂 tool calling。
7. 不做 RAG 知识库闭环。
8. 不做面向最终用户的大型运营后台。
```

这些能力都可以做，但它们依赖稳定的 runtime 观测和恢复基础。

Phase 5 的核心克制是：

```text
先让当前 workflow 看得见、解释得清、重试得稳。
```

---

## 6. 达到什么目标可以进入 Phase 6

满足下面标准，就可以进入第六阶段。

### 6.1 后端标准

```text
1. InterviewService.chat() 默认仍可以稳定走 sequential runtime。
2. 打开 USE_LANGGRAPH_INTERVIEW_RUNTIME=true 后，基础 chat path 可以跑通。
3. sequential 和 LangGraph 共享同一套 InterviewRuntimeNodes。
4. workflow_runs.status 能准确表现 running / waiting_user / failed。
5. blocking failure 能写入 failed 和 errorMessage。
6. failed retry 使用旧 incoming_user_input，而不是误用新请求 message。
7. waiting_user 使用新用户输入开启下一轮。
8. workflow_run_id 能串起 workflow_runs 和 AgentRun。
```

### 6.2 前端标准

```text
1. 可以打开 Workflow Runs 列表页。
2. 可以查看单个 Workflow Run 详情。
3. 可以看到 status / currentStep / activeStep / resumeReason / errorMessage。
4. 可以看到 completedSteps / failedSteps。
5. 可以看到 state JSON。
6. 可以看到关联 AgentRun。
7. failed 状态能被开发者快速定位。
```

### 6.3 测试标准

```text
1. backend/tests 全量通过。
2. 至少有 LangGraph path 的正常路径测试。
3. 至少有 failed retry 的恢复测试。
4. 至少有 WorkflowRunQueryService 的列表 / 详情字段测试。
5. 如果前端有测试框架，至少覆盖列表和详情的基础渲染。
```

### 6.4 设计标准

```text
1. 明确 workflow_runs.state 和 LangGraph checkpoint 的职责差异。
2. 明确哪些 state 字段是恢复游标，哪些内容必须回 DB 查询。
3. 明确哪些 node 有副作用，哪些 node 可以随时重跑。
4. 明确下一阶段 checkpointer 接入时不能绕过 DB artifact 对账。
```

如果这些标准达成，就说明 Phase 5 完成。

---

## 7. 最终目标还需要几个阶段

以当前项目状态看，从 Phase 5 开始，到比较完整的 LangGraph Agent Workflow 系统，建议还需要 4 个阶段，其中 Phase 5 是当前阶段。

```text
Phase 5:
  Workflow 可观测化 + 前端调试页 + LangGraph path 加固

Phase 6:
  LangGraph checkpointer 接入 + checkpoint / workflow_runs.state 对账

Phase 7:
  多 workflow 编排 + 条件分支 + start/end/evaluation 逐步迁移

Phase 8:
  高级 Agent 能力：human review、tool calling、RAG、学习建议、岗位匹配等
```

也就是说：

```text
如果从现在算起，包含当前 Phase 5，大约还需要 4 个阶段。
如果 Phase 5 完成后再算，大约还需要 3 个阶段。
```

如果你的最终目标只是：

```text
稳定接入 LangGraph，并支持中断恢复。
```

那么 Phase 6 结束就可以认为核心目标完成。

如果你的最终目标是：

```text
构建完整的 Agent Workflow 产品能力。
```

那么建议继续做到 Phase 8。

---

## 8. Phase 6 预告：为什么 checkpointer 放在下一阶段

LangGraph checkpointer 的价值是：

```text
1. 保存图执行过程中的 checkpoint。
2. 支持从某个图状态恢复。
3. 支持 interrupt / resume。
4. 支持更自然的人机协作流程。
```

但在当前项目里，checkpointer 不能直接替代 `workflow_runs.state`。

原因：

```text
workflow_runs.state:
  代表业务恢复游标。
  需要和 message、AgentRun、execution、summary 等 DB artifact 对齐。

LangGraph checkpoint:
  代表图执行层的检查点。
  更适合恢复图的执行过程。
```

第六阶段要解决的问题是：

```text
当 checkpoint 说某个 node 已经执行过时，
我们如何确认对应的 DB 副作用也真的完成了？
```

因此第六阶段应该重点做：

```text
1. 引入 checkpointer。
2. 明确 thread_id / checkpoint_id 设计。
3. 对比 checkpoint state 和 workflow_runs.state。
4. 保留 DB artifact 对账。
5. 在安全场景下尝试从 checkpoint node 恢复。
6. 在不安全场景下继续使用 start retry + 幂等 node。
```

---

## 9. Phase 5 推荐实施顺序

建议按下面顺序做：

```text
1. 固定 WorkflowRun 查询 schema。
2. 新增前端 Workflow Runs 列表页。
3. 新增前端 Workflow Run 详情页。
4. 在详情页展示 state / steps / error / AgentRuns。
5. 补 LangGraph path 正常路径测试。
6. 补 failed retry 测试。
7. 手动制造一次失败，验证前端能看到 failed。
8. 打开 LangGraph flag，在开发环境跑一轮完整 chat。
9. 更新 README 或开发文档，记录如何调试 workflow。
```

推荐不要先做 checkpointer，因为那会让你同时面对三个问题：

```text
1. 前端还看不见 workflow。
2. 后端恢复语义还没完全验证。
3. checkpointer 又引入新的状态来源。
```

先完成 Phase 5，Phase 6 会顺很多。

---

## 10. Workflow 调试手册

开发期调试 workflow 时，优先从 `workflow_runs` 入口看状态，再回到关联的 `AgentRun` 和业务 artifact 对账。

### 10.1 打开调试入口

后端接口：

```text
GET /api/workflow-runs
GET /api/workflow-runs?workflowId=interview_runtime
GET /api/workflow-runs?status=failed
GET /api/workflow-runs/{workflowRunId}
```

列表页重点看：

```text
workflowRunId
workflowId
threadId
status
currentStep
activeStep
resumeReason
errorMessage
agentRunCount
updateTime
```

详情页重点看：

```text
state
lastError
steps
agentRuns
completedSteps
failedSteps
```

### 10.2 判断 workflow 当前状态

```text
status = waiting_user
  正常状态。
  上一轮已经完成，workflow 正在等待下一次用户输入。

status = running
  上一轮可能在执行中中断。
  下一次请求会进入 unfinished_turn，继续使用旧 incoming_user_input 做恢复。

status = failed
  blocking node 失败。
  下一次请求会进入 failed_retry，继续使用旧 incoming_user_input 重试失败轮次。
```

### 10.3 定位失败位置

定位顺序：

```text
1. 看 status 是否为 failed。
2. 看 currentStep，确认最后持久化的边界。
3. 看 activeStep，确认失败时正在执行的 node。
4. 看 errorMessage，快速判断异常摘要。
5. 看 lastError.step_id / lastError.message / lastError.error_type。
6. 看 failedSteps，确认是否只记录了预期失败节点。
7. 看 completedSteps，确认失败前哪些副作用已经完成。
8. 看 steps，确认每个 workflow step 是否有对应 AgentRun。
9. 看 agentRuns，确认 AgentRun.workflow.workflowRunId 是否等于当前 workflowRunId。
```

最常见的 blocking failure 是：

```text
generate_followup failed
  workflow_runs.status = failed
  workflow_runs.current_step = generate_followup
  workflow_runs.last_error.step_id = generate_followup
  state.failed_steps 包含 generate_followup
  state.last_assistant_message_id 不应出现
```

### 10.4 验证 retry 是否安全

failed retry 的关键判断：

```text
1. 新请求 message 不应覆盖旧 incoming_user_input。
2. save_user_answer 应复用旧 user message。
3. advance_execution 如果已经完成，应复用旧 evidence marker，不重复推进 execution。
4. generate_followup 可以重新跑，或复用已有 AgentRun。
5. 最终成功后 status 应回到 waiting_user。
```

调试时重点比较两次请求前后的字段：

```text
incoming_user_input
last_user_message_id
last_assistant_message_id
completedSteps
failedSteps
resumeReason
resumeFromStep
agentRunCount
```

### 10.5 验证 LangGraph path

打开 LangGraph runtime：

```text
USE_LANGGRAPH_INTERVIEW_RUNTIME=true
```

验证目标不是“用了 LangGraph 就行”，而是确认它和 sequential runtime 具备相同业务语义：

```text
1. 两条路径都进入 waiting_user。
2. 两条路径都写 workflow_runs.state。
3. 两条路径失败时都写 failed / currentStep / lastError。
4. 两条路径 failed retry 都使用旧 incoming_user_input。
5. 两条路径创建 AgentRun 时都带真实 workflow_run_id。
```

当前重点测试：

```text
cd backend/tests
python -m unittest service.test_interview_runtime_nodes
python -m unittest service.test_workflow_run_query_service
python -m unittest discover -s service -p "test_*.py"
```

`test_interview_runtime_nodes.py` 覆盖：

```text
sequential normal path
sequential failed retry
LangGraph normal path
LangGraph persisted state resume
LangGraph failed retry
blocking failure marks workflow_run failed
```

### 10.6 调试原则

```text
先看 workflow_runs，再看 AgentRun。
先看 state 游标，再看完整业务 artifact。
先确认副作用是否已发生，再决定 node 能否重跑。
先保证 retry 幂等，再考虑引入 checkpointer。
```

---

## 11. 本阶段你应该真正理解什么

Phase 5 完成后，你应该不只是“会用 LangGraph”，而是理解：

```text
1. Workflow 为什么需要可观测性。
2. State 为什么不能塞完整上下文。
3. Node 为什么要有副作用边界。
4. 幂等为什么比简单 retry 更重要。
5. workflow_runs.state 和 DB artifact 为什么要对账。
6. LangGraph 是执行编排层，不是业务语义本身。
7. checkpointer 解决的是执行恢复，但业务恢复仍需要系统设计。
8. 前端 observability 页面是开发复杂 Agent 系统的重要工具。
```

这也是本项目最重要的收益之一：

```text
你不是只接了一个库，而是在学习如何把一个普通 Agent API 演进成可维护的 Agent Workflow 系统。
```

# Phase 7 执行文档：多 Workflow 编排与条件分支

本文档描述第七阶段要做什么、为什么做、如何分步执行、哪些事情暂不做，以及怎样判断本阶段完成。

第六阶段已经完成了 LangGraph checkpointer 的安全接入：运行时可以写 checkpoint，`thread_id` 稳定，对账能力已经建立，前端也能观察 reconciliation 结果。第七阶段不应该急着把恢复完全交给 checkpoint，而应该在这个基础上继续扩大 workflow 的业务覆盖面，让系统从“单个可观测 chat runtime”升级为“多 workflow 协作系统”。

---

## 1. 阶段背景

当前系统已经具备这些基础能力：

```text
WorkflowRuntime:
  可以创建 workflow_runs。
  可以保存 status / current_step / state / last_error。
  可以支持失败重试和运行时观测。

InterviewRuntimeWorkflow:
  已经有顺序 runtime 和 LangGraph runtime 两条路径。
  LangGraph path 已支持 checkpointer。
  failed retry 仍然依赖 workflow_runs.state + 幂等节点。

WorkflowRun Observability:
  后端可以查询 workflow run 列表和详情。
  前端可以查看 Workflow Runs。
  reconciliation 可以展示 workflow_runs.state 与 DB artifact 是否一致。

AgentRun:
  各 Agent 调用已有 AgentRun 记录。
  AgentRun 中已有 workflow_context。
  可以把 AgentRun 归属到 workflow / step。
```

第七阶段要解决的问题是：

```text
如何把更多业务流程纳入 workflow 编排？
如何让 workflow 根据 state 做条件分支？
如何让多个 workflow 之间有清楚的输入输出边界？
如何在不破坏 Phase 6 状态可靠性的前提下，引入更复杂的流程？
```

---

## 2. 阶段目标

### 2.1 目标一：建立多 workflow 编排能力

当前系统里已经有一些业务流程具备 workflow 化的基础：

```text
interview_runtime:
  面试进行中每一轮问答。

preparation:
  JD 分析、简历分析、候选人画像、面试计划生成。

post_interview_assessment:
  面试结束后的评估、总结、真实性分析。

resume_optimization:
  简历真实性检查、简历改写、岗位匹配建议。
```

Phase 7 不要求一次迁移所有流程。

第一轮建议选择一个非 chat 流程作为试点：

```text
推荐试点：post_interview_assessment workflow
```

原因：

```text
1. 它天然发生在 interview_runtime 之后。
2. 它和面试 transcript、execution、evaluation、summary 关系明确。
3. 它适合验证 workflow 之间的输入输出边界。
4. 它不会直接干扰正在进行的 chat loop。
5. 它可以为后续 resume_optimization workflow 打基础。
```

### 2.2 目标二：引入条件分支

Phase 7 应该让 workflow 不再只是线性步骤，而是可以根据 state 或 artifact 决定下一步。

候选条件：

```text
interview_runtime:
  continue_current_topic
  advance_to_next_topic
  wrap_up_interview

post_interview_assessment:
  has_enough_transcript
  needs_conversation_summary
  trigger_evaluation
  trigger_resume_authenticity

resume_optimization:
  has_resume_profile
  has_authenticity_report
  rewrite_mode = jd_targeted / general_polish
```

第一轮不要把所有条件都做完。

建议先做：

```text
post_interview_assessment:
  if evaluation exists:
    reuse evaluation artifact
  else:
    run evaluation node

  if transcript round count is enough:
    run assessment node
  else:
    mark workflow partial / skipped with reason
```

### 2.3 目标三：明确 workflow 之间的边界

多 workflow 系统最容易失控的地方，是 workflow 之间互相偷读状态。

Phase 7 必须明确：

```text
workflow_runs.state:
  只保存本 workflow 的恢复游标。

DB artifact:
  是跨 workflow 共享事实来源。

AgentRun:
  是 Agent 调用事实和可观测记录。

Workflow output:
  是后续 workflow 可以消费的结构化结果。
```

原则：

```text
一个 workflow 不应该直接依赖另一个 workflow 的内部 state。
如果需要跨 workflow 传递信息，应该通过 DB artifact 或明确 output contract。
```

例子：

```text
interview_runtime workflow:
  输出 message / execution / summary / evaluation artifacts。

post_interview_assessment workflow:
  输入 session_id / project_id / transcript / execution / existing evaluation。
  输出 assessment artifact / AgentRun / optional resume optimization trigger。
```

### 2.4 目标四：保持 Phase 6 的状态安全边界

Phase 7 可以继续使用 Phase 6 的能力：

```text
workflow_runs.state
LangGraph checkpoint
reconciliation
frontend observability
```

但不能越过 Phase 6 已经定好的安全边界：

```text
checkpoint 仍然不是业务事实来源。
DB artifact 仍然是副作用事实来源。
默认恢复仍然优先 workflow_runs.state + 幂等 retry。
checkpoint resume 只能在安全节点和 reconciliation ok 的前提下探索。
```

---

## 3. 本阶段建议范围

### 3.1 第一轮建议只做

```text
1. 定义 post_interview_assessment workflow。
2. 建立 workflow definition 和 step 列表。
3. 抽出 assessment workflow state。
4. 把现有 end/evaluation 相关逻辑整理为 workflow nodes。
5. 接入 WorkflowRuntime。
6. 写 workflow_runs.state。
7. 写 AgentRun workflow_context。
8. 在 Workflow Runs 前端可观察。
9. 增加条件分支：evaluation exists -> reuse，否则 run。
10. 增加测试覆盖 normal / reuse / failed / retry。
```

### 3.2 第二轮再考虑

```text
1. resume_optimization workflow。
2. preparation workflow。
3. interview_runtime 的更多条件边。
4. workflow 之间自动触发。
5. 更完整的 workflow output contract。
```

### 3.3 暂不做

```text
1. 不默认从 checkpoint 中间节点恢复。
2. 不引入生产级 checkpointer 存储。
3. 不引入复杂 human review。
4. 不做多 workflow 并发调度器。
5. 不做任务队列。
6. 不做跨 workflow 的复杂 DAG 编排。
7. 不把所有 service 一次性迁移成 workflow。
8. 不删除现有 service API。
```

---

## 4. 推荐实现顺序

### 4.1 第一步：梳理现有 end/evaluation 流程

先阅读并梳理：

```text
backend/app/service/interview_service.py
backend/app/service/assessment_agents.py
backend/app/service/interview_execution_service.py
backend/app/repository/interview_repository.py
backend/tests/service/test_assessment_agents.py
```

需要回答：

```text
InterviewService.end() 当前做了什么？
evaluation artifact 存在哪里？
evaluation AgentRun 如何记录？
是否已有 session summary / transcript / execution 可复用？
失败时是否会留下部分 artifact？
```

输出一份内部结论：

```text
post_interview_assessment workflow 的输入：
  session_id
  project_id
  workflow_run_id
  transcript messages
  execution state
  existing evaluation

post_interview_assessment workflow 的输出：
  evaluation_id
  assessment_agent_run_id
  summary_id 可选
  next_action 可选
```

### 4.2 第二步：定义 workflow registry

在 workflow registry 中新增：

```text
workflow_id = post_interview_assessment
```

候选 steps：

```text
load_assessment_context
ensure_evaluation
run_assessment
persist_assessment_result
complete
```

第一轮可以简化为：

```text
load_assessment_context
ensure_evaluation
complete
```

条件分支：

```text
load_assessment_context -> ensure_evaluation

ensure_evaluation:
  if evaluation exists:
    complete
  else:
    generate_evaluation
```

如果暂时不接 LangGraph 条件边，也可以先在 workflow node 内显式判断，但需要把分支结果写进 state：

```json
{
  "branch": "reuse_existing_evaluation",
  "completed_steps": ["load_assessment_context", "ensure_evaluation_reused"]
}
```

### 4.3 第三步：定义 state

新增或整理 state 类型：

```text
PostInterviewAssessmentState
```

建议字段：

```text
workflow_id
workflow_run_id
thread_id
status
active_step
project_id
session_id
session_uid
incoming_trigger
evaluation_id
assessment_agent_run_id
conversation_summary_id
completed_steps
failed_steps
last_error
resume_reason
resume_from_step
branch
next_action
```

thread_id 建议：

```text
assessment:{session_uid}
```

原因：

```text
1. 与 interview_runtime 的 interview:{session_uid} 区分。
2. 同一 session 的 assessment workflow 稳定可复用。
3. 前端可以清楚区分 workflow_id + thread_id。
```

### 4.4 第四步：实现 workflow nodes

建议文件：

```text
backend/app/service/post_interview_assessment_state.py
backend/app/service/post_interview_assessment_nodes.py
backend/app/service/post_interview_assessment_workflow.py
```

第一轮 nodes：

```text
initial_state(session)
load_assessment_context_node(state, session)
ensure_evaluation_node(state, context)
complete_node(state)
```

每个 node 必须遵守：

```text
1. 写 completed_steps。
2. 失败时写 failed_steps / last_error。
3. 对已有 artifact 做幂等复用。
4. 不把 Python 对象写入 workflow_runs.state。
5. 需要对象时从 DB artifact 重建。
```

如果 node 内临时需要 Python 对象，可以使用私有 runtime state，但保存到 workflow_runs.state 时必须过滤掉。

### 4.5 第五步：接入 WorkflowRuntime

post_interview_assessment workflow 应该和 interview_runtime 一样写入：

```text
workflow_runs.workflow_id = post_interview_assessment
workflow_runs.thread_id = assessment:{session_uid}
workflow_runs.status
workflow_runs.current_step
workflow_runs.state
workflow_runs.last_error
```

第一轮恢复策略：

```text
failed retry:
  使用旧 state 的 trigger/context。
  从 start 重跑。
  依赖幂等 node 复用已有 artifact。

waiting / success:
  不重复生成 evaluation。
```

### 4.6 第六步：API 接入

可以选择两种方式：

方案 A：保守接入，保留现有接口语义。

```text
POST /api/interview/end
  内部调用 post_interview_assessment workflow。
  返回格式保持不变。
```

方案 B：新增显式 workflow API。

```text
POST /api/workflows/post-interview-assessment/start
GET /api/workflow-runs/{workflowRunId}
```

第一轮建议使用方案 A：

```text
用户体验不变。
后端内部开始 workflow 化。
Workflow Runs 页面自然能看到新 workflow。
```

### 4.7 第七步：前端观察

前端第一轮不需要新增复杂页面。

只需要确保：

```text
Workflow Runs 列表可以看到 workflow_id = post_interview_assessment。
详情页可以看到 state / steps / AgentRuns。
失败时可以看到 last_error。
```

如果需要增强，可以加 workflow_id filter，但不作为第一轮必须项。

---

## 5. 测试计划

### 5.1 workflow registry tests

```text
1. post_interview_assessment workflow 注册成功。
2. step_id 不重复。
3. required steps 合法。
4. workflow_context 校验可以识别 step。
```

### 5.2 state tests

```text
1. initial_state 使用 assessment:{session_uid}。
2. state 包含 workflow_id / thread_id / session_id。
3. public state 不包含 Python 对象。
```

### 5.3 normal path tests

```text
1. 没有 evaluation 时，workflow 生成 evaluation。
2. workflow_runs.status 最终为 success 或 waiting_user 以设计为准。
3. workflow_runs.current_step 最终为 complete。
4. workflow_runs.state 包含 evaluation_id。
5. AgentRun workflow_context 指向 post_interview_assessment。
```

### 5.4 reuse tests

```text
1. 已有 evaluation 时，不重复生成。
2. state.branch = reuse_existing_evaluation。
3. completed_steps 包含 ensure_evaluation_reused。
4. AgentRun 数量不增加。
```

### 5.5 failed path tests

```text
1. evaluation agent 失败时，workflow_runs.status = failed。
2. current_step 指向失败 node。
3. last_error 存在。
4. 已经生成的 artifact 不被删除。
```

### 5.6 retry tests

```text
1. failed retry 使用旧 trigger/context。
2. retry 不重复生成已有 evaluation。
3. retry 成功后 workflow_runs.status 更新。
4. failed_steps 清空或按设计重置。
```

### 5.7 observability tests

```text
1. WorkflowRunQueryService 可以列出 post_interview_assessment。
2. detail 可以看到 steps。
3. AgentRun 可以通过 workflow_run_id 关联。
4. 前端 build 通过。
```

---

## 6. checkpoint resume 是否进入 Phase 7

这是一个需要明确的边界。

结论：

```text
Phase 7 可以做 checkpoint resume 的设计准备和安全约束定义。
Phase 7 不应该默认启用从 checkpoint 中间节点恢复。
```

可以在 Phase 7 做：

```text
1. 定义 safe_resume_policy。
2. 定义哪些 node 是 checkpoint-resume-safe。
3. 让 reconciliation 结果成为 resume 前置条件。
4. 写少量实验性测试，证明不安全时 fallback 到 start retry。
```

不建议在 Phase 7 第一轮做：

```text
1. 从任意 checkpoint node resume。
2. 用 checkpoint state 判断 DB 副作用是否完成。
3. 跳过 workflow_runs.state。
4. 跳过 DB artifact 对账。
5. 生产环境默认开启 checkpoint resume。
```

推荐策略：

```text
Phase 7 主线:
  多 workflow 编排 + 条件分支。

Phase 7 支线:
  checkpoint resume policy 设计，不默认启用。

Phase 8 或单独 Phase 7.5:
  在少数安全节点上启用 checkpoint resume 实验。
```

---

## 7. 验收标准

Phase 7 第一轮完成时，应该满足：

```text
1. 至少一个非 chat 流程被迁移为 workflow。
2. 推荐目标 post_interview_assessment workflow 可运行。
3. workflow_runs 能记录该 workflow 的状态。
4. AgentRun workflow_context 能关联到该 workflow。
5. 至少一个条件分支可用，例如 evaluation exists -> reuse。
6. failed path 能写 workflow_runs.status = failed。
7. retry 不重复生成已有 artifact。
8. Workflow Runs 前端可观察该 workflow。
9. 测试覆盖 normal / reuse / failed / retry / observability。
10. 文档明确 checkpoint resume 暂不默认启用。
```

如果继续探索 checkpoint resume，还必须额外满足：

```text
1. resume 前必须 reconciliation ok。
2. resume node 必须声明 checkpoint-resume-safe。
3. 测试证明不会重复创建 message。
4. 测试证明不会重复推进 execution。
5. 测试证明不会重复创建 AgentRun，或能复用已有 AgentRun。
6. 不满足条件时必须 fallback 到 start retry。
```

---

## 8. 推荐第一轮任务清单

建议按这个顺序执行：

```text
1. 阅读 InterviewService.end() 和 assessment agent 相关代码。
2. 写 post_interview_assessment state 设计。
3. 在 workflow_registry 注册 post_interview_assessment。
4. 实现 post_interview_assessment_nodes。
5. 实现 post_interview_assessment_workflow。
6. 在 InterviewService.end() 内部接入 workflow。
7. 确保 API 返回保持兼容。
8. 补 normal path 测试。
9. 补 reuse existing evaluation 测试。
10. 补 failed path 测试。
11. 补 failed retry 测试。
12. 跑 service 测试和前端 build。
13. 手动在 Workflow Runs 页面确认新 workflow 可观察。
```

---

## 9. 核心原则

```text
多 workflow 编排不是把 service 方法机械搬进 graph。
它的核心是让业务流程拥有清晰的 state、step、artifact、retry 和 observability。
```

```text
条件分支不是让流程变得随意。
它的核心是让每一次分支都有 state 记录、有 artifact 证明、有测试覆盖。
```

```text
checkpoint resume 不是 Phase 7 的默认目标。
Phase 7 应该先让多个 workflow 可靠运行，再讨论更细粒度的恢复优化。
```

第七阶段的工程判断是：

```text
什么时候一个流程应该成为独立 workflow？
什么时候应该只是一个 node？
什么时候可以复用已有 artifact？
什么时候必须重新生成？
workflow 之间应该通过什么边界协作？
```

这些问题想清楚后，系统就会从“一个可恢复的面试 runtime”成长为“可扩展的 Agent Workflow 平台”。

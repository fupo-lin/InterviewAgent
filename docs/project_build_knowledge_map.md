# 项目构建知识地图：从 Interview Agent 到 Workflow / LangGraph

本文档按阶段整理本项目的学习收益、关键知识点和应用方式。

它的目的不是重复实现细节，而是帮助你回答三个问题：

```text
1. 这个阶段我到底学到了什么？
2. 这些知识点在当前项目里怎么应用？
3. 达到什么程度，说明我可以进入下一阶段？
```

---

## 总体学习路线

这个项目的演进路线可以理解为：

```text
Phase 1: 能对话
Phase 2: 有业务结构
Phase 3: 有 Agent 治理
Phase 4: 有 Workflow 运行时
Phase 5: 有可观测和可恢复体验
Phase 6: 有 LangGraph checkpoint 能力
Phase 7: 有多 Workflow 编排
Phase 8: 有高级 Agent 产品能力
```

从技术成长角度看，它对应的是：

```text
普通 API
-> 业务服务
-> Agent Service
-> Workflow Runtime
-> Observable Workflow
-> Checkpointed Graph
-> Multi-workflow System
-> Agent Product Platform
```

---

## Phase 1：Interview Agent MVP

### 阶段目标

跑通最基础的面试问答能力。

用户输入一段回答后，系统能够：

```text
1. 接收用户输入。
2. 保存消息。
3. 调用 LLM。
4. 返回下一轮问题。
```

### 需要掌握的知识点

```text
FastAPI:
  如何定义 API route。
  如何接收 request body。
  如何返回 response schema。

Service 层:
  为什么不要把所有逻辑写在 API route 里。
  如何用 service 承载业务流程。

Repository / DB:
  如何保存 interview session 和 message。
  为什么数据读写需要和业务逻辑分层。

LLM 调用:
  如何组织 prompt。
  如何把用户输入传给模型。
  如何解析模型输出。

基础错误处理:
  LLM 调用失败时如何返回错误。
  DB 写入失败时如何避免静默失败。
```

### 在项目中的应用

对应能力：

```text
InterviewService.chat()
interview_messages
session
基础 prompt
基础 assistant response
```

你在这个阶段学到的是：

```text
如何把一个“能回答问题的模型”包装成一个可被后端服务调用的应用能力。
```

### 本阶段收益

```text
1. 理解 API -> Service -> DB -> LLM 的基本链路。
2. 理解为什么 Agent 不是直接调用模型，而是业务系统的一部分。
3. 建立最小可运行闭环。
```

### 进入下一阶段的标志

```text
1. 用户可以完成多轮对话。
2. 每轮消息都能保存。
3. 后端可以稳定返回 assistant 问题。
4. 你能说清楚 API、Service、Repository 分别负责什么。
```

---

## Phase 2：业务结构与面试计划

### 阶段目标

让面试不再只是自由聊天，而是围绕项目、岗位、面试计划和执行状态进行。

系统需要理解：

```text
1. 候选人的项目是什么。
2. 面试目标岗位是什么。
3. 面试计划包含哪些 section / topic。
4. 当前执行到哪个 topic。
5. 用户回答后是否应该推进到下一步。
```

### 需要掌握的知识点

```text
领域建模:
  如何把真实业务概念建成 Project、Session、Plan、Execution。

状态建模:
  current_section、round_no、completed_rounds 等字段为什么重要。

CRUD 与业务动作:
  CRUD 负责基础增删改查。
  业务动作负责推进面试状态。

JSON 状态:
  如何在 DB 中保存可演进的 execution.state。
  JSON state 适合保存什么，不适合保存什么。

业务幂等:
  为什么同一轮回答不应该重复推进 execution。
```

### 在项目中的应用

对应能力：

```text
project
interview_plan
interview_plan_execution
start_with_project()
advance_after_answer()
current_section_key
current_section_round_no
```

你在这个阶段学到的是：

```text
如何把自由对话变成有业务目标、有进度、有结构的面试流程。
```

### 本阶段收益

```text
1. Agent 不再是随机追问，而是围绕计划追问。
2. 面试可以记录进度。
3. 后续可以基于执行状态做评估和总结。
4. 你开始理解“状态”在业务系统里的作用。
```

### 进入下一阶段的标志

```text
1. 面试计划可以生成或配置。
2. 每次回答后 execution 可以推进。
3. 系统知道当前 section / round。
4. 你能说清楚 plan 和 execution 的区别。
```

---

## Phase 3：Agent / Prompt / Evidence 治理

### 阶段目标

让 Agent 调用变得可记录、可追踪、可复用，而不是散落在业务代码里的 LLM 调用。

这一阶段的核心是：

```text
每一次 Agent 调用都应该有输入、输出、证据、上下文和运行记录。
```

### 需要掌握的知识点

```text
Agent Contract:
  Agent 应该接收什么输入。
  Agent 应该返回什么输出。
  Agent 的职责边界是什么。

Prompt Contract:
  prompt_id、prompt_version、prompt variables 为什么重要。
  为什么 prompt 应该可追踪。

Evidence Packet:
  Agent 判断应该基于哪些证据。
  如何避免模型凭空判断。

AgentRun:
  每次 Agent 调用都需要保存 input_snapshot、output_snapshot、status、error。

Output Schema:
  为什么模型输出最好结构化。
  如何降低解析失败风险。

可审计性:
  出问题时能查到模型当时看到了什么、输出了什么。
```

### 在项目中的应用

对应能力：

```text
TopicJudgeAgent
InterviewExecutorAgent
memory summary agent
AgentRun
agent_evidence_items
input_snapshot
output_snapshot
workflow_context
```

你在这个阶段学到的是：

```text
如何把 LLM 调用从“黑盒函数”变成可治理的 Agent 运行记录。
```

### 本阶段收益

```text
1. 可以追踪每一次 Agent 调用。
2. 可以知道 Agent 判断基于哪些证据。
3. prompt 变化可以被记录。
4. 后续 workflow 可以通过 AgentRun 做幂等复用。
5. 为 LangGraph / workflow_run 对齐打基础。
```

### 进入下一阶段的标志

```text
1. 关键 Agent 调用都有 AgentRun。
2. AgentRun 保存 input/output/error。
3. AgentRun 能关联 prompt 和 evidence。
4. 你能说清楚 AgentRun 和普通 message 的区别。
```

---

## Phase 4：Runtime 抽象与 Workflow 持久化

### 阶段目标

把原本顺序执行的 `InterviewService.chat()` 拆成可恢复的 workflow runtime。

核心变化：

```text
从一个大方法
-> 拆成 State + Node + Workflow
-> 每个节点边界保存 workflow_runs.state
```

### 需要掌握的知识点

```text
State:
  State 是 workflow 的运行游标。
  State 保存恢复需要的少量关键字段。
  State 不应该保存完整上下文。

Node:
  Node 是一个明确的业务步骤。
  每个 Node 应该有单一职责。
  有副作用的 Node 必须考虑幂等。

Workflow:
  Workflow 负责把多个 Node 组织成流程。
  Workflow 负责保存边界、处理失败、决定恢复策略。

Idempotency:
  同一个请求重试时，不应该重复写 message、重复推进 execution、重复调用 LLM。

Recovery:
  进程停了以后，系统应该知道从哪里恢复。
  当前策略是从 start 重跑，并通过幂等 Node 跳过已完成副作用。

workflow_runs:
  workflow_run 是一次 workflow 执行记录。
  它保存 status、current_step、state、last_error。
```

### 在项目中的应用

对应能力：

```text
InterviewRuntimeState
RuntimeContext
InterviewRuntimeNodes
InterviewRuntimeWorkflow
WorkflowRuntime
workflow_runs
resume_interview_runtime_state()
```

典型 Node：

```text
save_user_answer_node
load_runtime_context_node
topic_judge_node
advance_execution_node
refresh_memory_node
reload_followup_context_node
generate_followup_node
save_assistant_message_node
```

你在这个阶段学到的是：

```text
如何把一个复杂业务流程拆成可恢复、可测试、可观测的 runtime。
```

### 本阶段收益

```text
1. chat() 不再无限膨胀。
2. 每个步骤有明确职责。
3. 程序中断后可以根据 workflow_runs.state 恢复。
4. AgentRun 可以挂到 workflow_run_id 下。
5. LangGraph 可以接入但不侵入业务节点。
```

### 进入下一阶段的标志

```text
1. API -> InterviewService.chat() -> InterviewRuntimeWorkflow 链路跑通。
2. workflow_runs.state 能保存和恢复。
3. waiting_user / running / failed 语义清楚。
4. 关键 Node 具备幂等逻辑。
5. 后端测试通过。
```

---

## Phase 5：Workflow 可观测化与 LangGraph 接入加固

### 阶段目标

让 workflow 不只是后端内部机制，而是可以被开发者观察、理解、调试和验证的运行时系统。

核心目标：

```text
1. 前端可以查看 workflow_runs。
2. 开发者可以看到 workflow 当前状态。
3. failed / running / waiting_user 可以被清晰区分。
4. sequential runtime 和 LangGraph runtime 行为一致。
5. 为 Phase 6 的 checkpointer 做准备。
```

### 需要掌握的知识点

```text
Observability:
  为什么复杂 workflow 必须能被看见。
  status、currentStep、activeStep、resumeReason 有什么区别。

Frontend Debug UI:
  如何设计开发期调试页面。
  如何让 state、steps、error、AgentRuns 可读。

Runtime Parity:
  sequential runtime 和 LangGraph runtime 为什么必须共享业务 Node。
  如何验证两条执行路径结果一致。

Failure UX:
  failed 状态不是简单报错，而是可恢复状态。
  前端应该帮助开发者知道失败在哪里。

Schema Stability:
  前后端协作前，API response 字段需要稳定。
```

### 在项目中的应用

对应能力：

```text
WorkflowRunQueryService
workflow run list API
workflow run detail API
Workflow Runs 前端页面
activeStep
resumeReason
resumeFromStep
errorMessage
LangGraph path tests
```

你在这个阶段要真正理解：

```text
看得见 workflow，才有资格谈复杂恢复。
```

### 本阶段收益

```text
1. 出错时不再只能看日志。
2. 可以从 UI 看到 workflow 停在哪一步。
3. 可以看到每轮关联的 AgentRun。
4. 可以验证 LangGraph path 是否真的可用。
5. 为 checkpointer 接入降低风险。
```

### 调试 workflow 的固定流程

```text
1. 先打开 Workflow Runs 列表，看 workflowRunId / status / currentStep / activeStep。
2. 如果 status = failed，进入详情看 errorMessage / lastError / failedSteps。
3. 看 completedSteps，确认失败前哪些副作用已经完成。
4. 看 state.incoming_user_input，确认 retry 使用的是哪一次用户输入。
5. 看 agentRuns，确认 AgentRun.workflow.workflowRunId 能关联回当前 workflow_run。
6. 对比 sequential 和 LangGraph path，确认两条路径最终语义一致。
```

当前测试锚点：

```text
backend/tests/service/test_interview_runtime_nodes.py
  LangGraph normal path
  LangGraph failed retry
  sequential failed retry

backend/tests/service/test_workflow_run_query_service.py
  WorkflowRun list/detail schema
  persisted workflow_runs 优先
  AgentRun fallback grouping
```

### 进入下一阶段的标志

```text
1. Workflow Runs 列表页可用。
2. Workflow Run 详情页可用。
3. failed workflow 可以从前端定位错误。
4. sequential 和 LangGraph 基础 chat path 都可跑通。
5. failed retry 语义测试通过。
6. 你能说清楚 workflow_runs.state 和未来 checkpointer 的区别。
```

---

## Phase 6：LangGraph Checkpointer 与状态对账

### 阶段目标

引入 LangGraph checkpointer，让图执行过程具备 checkpoint / resume 能力，同时保持业务状态可靠。

这一阶段的关键不是“用了 checkpointer”，而是：

```text
明确 LangGraph checkpoint 和 workflow_runs.state 如何共同工作。
```

### 需要掌握的知识点

```text
LangGraph StateGraph:
  如何定义 graph state。
  如何注册 node。
  如何连接 edge。

Checkpointer:
  checkpointer 保存什么。
  thread_id / checkpoint_id 如何设计。
  什么时候可以从 checkpoint 恢复。

Interrupt / Resume:
  什么情况下 workflow 应该暂停等待用户。
  resume 时如何恢复上下文。

State Reconciliation:
  checkpoint state 说 node 完成了，不代表 DB 副作用一定完成。
  需要用 message、AgentRun、execution 等 artifact 对账。

恢复策略升级:
  哪些场景可以从 checkpoint node 恢复。
  哪些场景仍然应该从 start 重跑。
```

### 在项目中的应用

可能对应能力：

```text
InterviewRuntimeLangGraph checkpointer
thread_id = interview:{session_uid}
checkpoint metadata
workflow_runs.state 对账
checkpoint resume tests
```

你在这个阶段要理解：

```text
checkpointer 解决的是图执行恢复，业务恢复仍需要 DB artifact 证明。
```

### 本阶段收益

```text
1. LangGraph 不再只是可选 wrapper，而开始承担执行层 checkpoint。
2. 某些恢复场景可以更接近中断节点。
3. human-in-the-loop 的基础能力变得可行。
4. 你会理解复杂 Agent 系统中“状态来源不止一个”的设计难点。
```

### 进入下一阶段的标志

```text
1. checkpointer 在开发环境可用。
2. checkpoint 和 workflow_runs.state 的职责边界清楚。
3. 至少一个安全场景支持 checkpoint resume。
4. 不安全场景仍能 fallback 到 start retry。
5. 测试覆盖 checkpoint resume 和 DB artifact 对账。
```

---

## Phase 7：多 Workflow 编排与条件分支

### 阶段目标

把更多业务流程从普通 service 方法迁移成 workflow。

候选流程：

```text
1. start_with_project workflow
2. interview_runtime workflow
3. post_interview_assessment workflow
4. resume_optimization workflow
5. preparation workflow
```

同时引入更明确的条件分支：

```text
continue_current_topic
advance_to_next_topic
wrap_up_interview
trigger_evaluation
trigger_resume_optimization
```

### 需要掌握的知识点

```text
Conditional Edge:
  根据 state 决定下一步 node。

Subgraph / Multi Workflow:
  什么时候一个流程应该是独立 workflow。
  什么时候应该是同一个 graph 的子图。

Workflow Boundary:
  start、runtime、evaluation、resume optimization 的边界如何划分。

Event-driven Thinking:
  一个 workflow 完成后，如何触发下一个 workflow。

Cross-workflow Context:
  如何让 assessment 使用 interview runtime 的结果。
  如何让 resume optimization 使用 project 和 assessment。
```

### 在项目中的应用

可能对应能力：

```text
post_interview_assessment
resume_optimization
preparation
workflow_id 分类
workflow event
conditional routing
```

你在这个阶段要理解：

```text
不是所有逻辑都应该塞进一个 graph。
好的 workflow 设计来自清晰的业务边界。
```

### 本阶段收益

```text
1. 系统从单一 chat loop 变成多 workflow 系统。
2. 面试结束后的评估和优化可以自动衔接。
3. 每个 workflow 有自己的状态、节点和恢复策略。
4. LangGraph 的条件分支价值开始真正体现。
```

### 进入下一阶段的标志

```text
1. 至少一个非 chat 流程迁移成 workflow。
2. 条件分支可以根据 state 决策。
3. workflow 之间的输入输出边界清楚。
4. 前端可以区分不同 workflow_id 的运行记录。
```

---

## Phase 8：高级 Agent 产品能力

### 阶段目标

在稳定 workflow 基础上，加入更接近真实产品的 Agent 能力。

可能方向：

```text
1. Human review。
2. Tool calling。
3. RAG / 知识库。
4. 学习计划生成。
5. 岗位匹配。
6. 简历优化。
7. 多 Agent 协作。
```

### 需要掌握的知识点

```text
Human-in-the-loop:
  哪些节点需要人工确认。
  人工确认如何通过 interrupt / resume 接回 workflow。

Tool Calling:
  Tool 和 Node 的区别。
  Tool 执行结果如何保存。
  Tool 失败如何重试。

RAG:
  文档切分、embedding、检索、rerank、引用证据。
  RAG 结果如何进入 EvidencePacket。

Agent Planning:
  什么时候需要 planner。
  planner 的输出如何限制在可执行 action 内。

Product UX:
  如何把复杂 workflow 状态变成用户能理解的产品体验。
```

### 在项目中的应用

可能对应能力：

```text
resume rewrite tool
job description analysis tool
knowledge base retrieval
learning plan agent
human review node
candidate growth report
```

你在这个阶段要理解：

```text
高级 Agent 能力不是让模型自由发挥，而是让模型在 workflow、state、tool、evidence 的约束下工作。
```

### 本阶段收益

```text
1. 项目从面试工具升级为职业发展 Agent 系统。
2. Tool / RAG / human review 都能纳入统一 workflow。
3. 用户得到的不只是下一题，而是结构化反馈和行动建议。
4. 你掌握了 Agent 产品化的核心工程方法。
```

### 阶段完成标志

```text
1. 至少一个 Tool 被安全接入 workflow。
2. 至少一个 human review 或 interrupt/resume 场景可用。
3. RAG 或外部知识能以 evidence 形式进入 Agent。
4. 高级能力有可观测 AgentRun 和 workflow_run。
5. 用户可以看到最终结构化结果。
```

---

## 核心概念速查

### State

```text
State 是 workflow 的运行游标。
它回答：恢复时我需要知道什么？
```

适合进入 State：

```text
workflow_run_id
session_id
current_step
incoming_user_input
last_user_message_id
last_agent_run_id
resume_reason
failed_steps
```

不适合进入 State：

```text
完整 transcript
完整 prompt
完整 LLM response
完整 evidence packet
完整 candidate profile
```

### Node

```text
Node 是 workflow 中一个清晰的业务步骤。
它回答：这一步做什么？有没有副作用？失败能不能继续？
```

例如：

```text
save_user_answer_node
topic_judge_node
generate_followup_node
save_assistant_message_node
```

### Workflow

```text
Workflow 是多个 Node 的编排。
它回答：这些步骤按什么顺序执行？失败如何处理？状态如何保存？
```

### Middleware

```text
Middleware 是横切能力，不应该绑定具体业务步骤。
```

适合做 Middleware：

```text
request id
logging
auth
metrics
trace context
error normalization
```

不适合做 Middleware：

```text
保存用户回答
推进面试计划
调用 TopicJudge
生成下一问
```

### Tool

```text
Tool 是 Agent 可以调用的外部能力。
它回答：模型需要借助哪个确定性能力完成任务？
```

适合做 Tool：

```text
检索知识库
分析 JD
读取简历结构化信息
生成文件
调用外部 API
```

不适合做 Tool：

```text
workflow 状态保存
node 编排
API 鉴权
数据库事务控制
```

### Checkpointer

```text
Checkpointer 是图执行层的检查点机制。
它回答：Graph 执行到哪里了，能不能从某个图状态恢复？
```

但它不自动回答：

```text
DB 副作用是否完成？
AgentRun 是否已经成功？
message 是否已经保存？
execution 是否已经推进？
```

所以本项目需要：

```text
LangGraph checkpoint + workflow_runs.state + DB artifact 对账
```

---

## 你在这个项目中的长期收益

完成这个项目后，你掌握的不是单点技术，而是一套 Agent 系统工程能力：

```text
1. 能把业务流程拆成 State / Node / Workflow。
2. 能判断哪些内容应该持久化，哪些内容应该按需读取。
3. 能设计幂等节点，避免 retry 造成重复副作用。
4. 能让 LLM 调用具备 AgentRun 记录和证据链。
5. 能把 LangGraph 当作编排引擎，而不是盲目迁移目标。
6. 能设计可观测 workflow，让复杂 Agent 系统可调试。
7. 能理解 checkpoint、DB state、业务 artifact 的关系。
8. 能把 Tool、RAG、human review 接进稳定 workflow。
```

最重要的是：

```text
你会从“会调用模型”升级到“会设计 Agent Workflow 系统”。
```

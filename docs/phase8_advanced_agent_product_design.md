# Phase 8 执行文档：高级 Agent 产品能力与候选人成长报告

本文档描述第八阶段要做什么、为什么做、如何分步执行、哪些事情暂不做，以及如何判断本阶段完成。

第七阶段已经让系统从单一 interview runtime 扩展为多 workflow 协作系统，并完成了 `post_interview_assessment` 这类非 chat 流程的 workflow 化。第八阶段不应该继续只堆运行时能力，而应该把前七阶段积累的 AgentRun、Evidence、Workflow、Checkpoint、Assessment 能力转化为用户能直接感知的高级产品结果。

本阶段建议主线：

```text
基于已有面试过程、岗位要求、简历 / 项目画像、评价结果和证据链，
生成结构化 Candidate Growth Report，
让产品从“模拟面试工具”升级为“AI 求职成长系统”。
```

---

## 1. 产品形态回顾

### 1.1 最初的产品形态

项目最开始定下来的产品不是泛泛的聊天机器人，而是一个可实际使用的 AI 面试官系统。

用户能够：

```text
1. 选择目标岗位。
2. 开始模拟面试。
3. 与 AI 面试官进行多轮对话。
4. 获得面试评价。
5. 查看历史面试记录。
```

最初的核心闭环是：

```text
选择目标岗位
-> 创建面试 session
-> AI 生成首题
-> 用户回答
-> AI 追问
-> 多轮循环
-> 用户结束面试
-> 生成评价
-> 保存评价与历史记录
```

它的第一性目标是：

```text
完成一个可运行、可部署、可持续演进的 AI 面试训练产品。
```

### 1.2 当前已经演进到的产品形态

经过前七个阶段，系统已经不只是一个 chat loop。

当前系统已经具备：

```text
1. 结构化面试计划与执行状态。
2. AgentRun 调用记录。
3. Prompt / Evidence / Output Schema 治理。
4. workflow_runs 状态持久化。
5. sequential runtime 与 LangGraph runtime。
6. LangGraph checkpoint。
7. workflow_runs.state 与 DB artifact reconciliation。
8. 多 workflow 编排。
9. post_interview_assessment workflow。
10. 前端 Workflow Runs 可观测页面。
```

因此，当前产品形态已经从：

```text
AI 面试官
```

演进为：

```text
具备 AgentRun、Evidence、Workflow、Checkpoint、Observability 的 AI 面试工作流系统。
```

### 1.3 长期产品形态

从最早规划看，系统最终不应停留在“问答式模拟面试”，而应该成长为完整的 AI 求职辅助系统。

长期形态可以理解为：

```text
简历 / 项目经历
-> JD / 目标岗位
-> 候选人画像
-> 面试计划
-> 模拟面试
-> 面试评价
-> 候选人成长报告
-> 简历优化
-> 学习计划
-> 下一轮训练
```

一句话定义：

```text
这是一个面向求职者的 AI 面试与职业准备系统。
它通过 Resume / JD / Project / Interview / Assessment / Growth 多个 Agent 和 Workflow，
帮助用户完成从岗位准备、模拟面试、表现评估，到简历优化和能力提升的完整闭环。
```

第八阶段要推动的正是这个转变：

```text
从“系统能稳定运行复杂 workflow”
升级为
“用户能获得结构化、可信、可执行的成长建议”。
```

---

## 2. 阶段背景

第七阶段完成后，系统已经具备比较稳定的多 workflow 基础。

已有关键基础能力：

```text
WorkflowRuntime:
  可以创建 workflow_runs。
  可以保存 status / current_step / state / last_error。
  可以支持 failed retry。
  可以被前端观察。

AgentRun:
  关键 Agent 调用已有 input / output / error 记录。
  AgentRun 可以通过 workflow_context 归属到 workflow 和 step。
  后续高级 Agent 能力必须继续使用 AgentRun。

Evidence:
  Agent 判断不应该凭空生成。
  evaluation / assessment / resume analysis / JD analysis / transcript 都可以成为 evidence 来源。

post_interview_assessment:
  面试结束后的评估流程已经可以 workflow 化。
  这是第八阶段生成成长报告的天然上游。

Observability:
  Workflow Runs 页面可以查看 workflow list/detail。
  开发者可以定位失败 step、state、last_error 和关联 AgentRun。
```

第八阶段要解决的问题是：

```text
如何把已有面试和评估结果变成用户能直接理解的成长报告？
如何让高级 Agent 输出结构化、可追踪、可复用的产品结果？
如何在不破坏已有 workflow 边界的前提下，引入更强的产品闭环？
```

---

## 3. 阶段目标

### 3.1 目标一：建立 Candidate Growth Report 产品能力

第八阶段第一轮建议聚焦一个明确产品产物：

```text
Candidate Growth Report
```

它不是普通的面试评价，而是面试后的综合成长报告。

它应该回答用户真正关心的问题：

```text
1. 我这场面试整体表现如何？
2. 我的能力和目标岗位是否匹配？
3. 哪些回答体现了真实能力？
4. 哪些回答有表达风险或真实性风险？
5. 我的项目经历讲得够不够清楚？
6. 我有哪些高优先级能力缺口？
7. 我的简历应该优先优化哪里？
8. 下一轮模拟面试应该重点练什么？
9. 接下来 7 天 / 14 天应该怎么补强？
```

这会让产品从“问下一题”升级为“给出下一步行动建议”。

### 3.2 目标二：新增 candidate_growth_report workflow

成长报告不应该只是 `InterviewService.end()` 里的一个 prompt 调用。

它应该作为独立 workflow 存在：

```text
workflow_id = candidate_growth_report
```

原因：

```text
1. 它发生在 post_interview_assessment 之后，有独立业务边界。
2. 它会消费多个 artifact，包括 transcript、evaluation、assessment、resume profile、JD analysis。
3. 它会生成新的长期产品 artifact。
4. 它需要独立 retry。
5. 它需要在 Workflow Runs 页面里可观测。
6. 后续 resume_optimization / preparation workflow 可以消费它的输出。
```

### 3.3 目标三：让高级 Agent 输出依赖 EvidencePacket

成长报告必须基于证据，而不是让模型自由发挥。

GrowthReportAgent 的输入应该包含：

```text
1. interview session 基础信息。
2. interview transcript 摘要或关键消息。
3. interview evaluation。
4. post interview assessment。
5. resume analysis / candidate profile。
6. JD analysis。
7. project profile。
8. topic coverage / execution state。
9. authenticity / risk signals。
```

这些输入应该被整理为：

```text
GrowthReportEvidencePacket
```

原则：

```text
Agent 可以总结、归纳、排序、建议。
Agent 不应该编造不存在的经历、技能、评价或岗位要求。
```

### 3.4 目标四：形成可展示的结构化 artifact

第八阶段的产物必须能被前端直接展示，而不是一大段散文。

推荐新增 artifact：

```text
candidate_growth_reports
```

或者先在现有可扩展 artifact 表 / JSON 字段中保存，具体取决于当前数据模型演进成本。

核心要求：

```text
1. 有稳定 report_uid。
2. 能关联 session / project / workflow_run / agent_run。
3. 保存结构化 JSON 内容。
4. 保存生成状态和版本。
5. 可以被后续 workflow 复用。
```

### 3.5 目标五：前端提供成长报告视图

用户应该能在面试结束后看到清晰的成长报告。

第一轮前端不需要做复杂 dashboard，但至少要有：

```text
1. 总体表现摘要。
2. 岗位匹配分析。
3. 技术优势。
4. 技术缺口。
5. 项目表达问题。
6. 真实性 / 包装风险。
7. 简历优化建议。
8. 下一轮训练重点。
9. 学习行动计划。
```

前端重点不是炫技，而是让用户能快速知道：

```text
我哪里好？
我哪里弱？
我下一步该做什么？
```

---

## 4. 本阶段建议范围

### 4.1 第一轮建议只做

```text
1. 定义 CandidateGrowthReport 数据结构。
2. 定义 GrowthReportEvidencePacket。
3. 新增 GrowthReportAgent。
4. 新增 candidate_growth_report workflow。
5. 注册 workflow_id 和 step 列表。
6. 从 post_interview_assessment 或 interview end 后触发成长报告生成。
7. 将 GrowthReportAgent 调用写入 AgentRun。
8. 将 workflow_context 写入 AgentRun。
9. 持久化 growth report artifact。
10. 增加 API 查询成长报告。
11. 前端展示成长报告。
12. Workflow Runs 页面可以观察该 workflow。
13. 增加 normal / reuse / failed / retry / schema 测试。
```

### 4.2 第二轮再考虑

```text
1. resume_optimization workflow 消费 growth report。
2. preparation workflow 根据 growth report 生成下一轮面试计划。
3. RAG 知识库接入学习建议。
4. 用户选择目标改进方向后触发后续 workflow。
5. 多份 growth report 的历史对比。
6. 分数趋势、能力雷达图等更强前端表达。
```

### 4.3 暂不做

```text
1. 不做完整 RAG 知识库。
2. 不做外部招聘平台 API。
3. 不做自动投递。
4. 不做完整 Human Review 后台。
5. 不做多 Agent 自主规划器。
6. 不做生产级任务队列。
7. 不做复杂权限系统。
8. 不做跨用户报告对比。
9. 不做自动生成 Word / PDF 简历。
10. 不把所有后续流程一次性串成复杂 DAG。
```

第八阶段第一轮的核心不是“让模型能做更多事”，而是：

```text
让高级 Agent 能力以 workflow、state、evidence、artifact、AgentRun 的形式稳定进入产品。
```

---

## 5. 产品输出设计

### 5.1 Candidate Growth Report 应包含的模块

建议第一版报告包含：

```text
overall_summary:
  总体表现摘要。

job_match:
  与目标岗位的匹配度分析。

technical_strengths:
  技术优势。

technical_gaps:
  技术短板。

project_storytelling:
  项目表达能力分析。

authenticity_risks:
  回答真实性或包装风险。

resume_suggestions:
  简历优化建议。

next_interview_focus:
  下一轮模拟面试重点。

learning_plan:
  短期学习行动计划。

evidence_references:
  关键判断对应的证据引用。
```

### 5.2 推荐 JSON Schema 草案

第一版可以使用如下结构：

```json
{
  "report_version": "v1",
  "overall_summary": {
    "level": "medium",
    "summary": "...",
    "top_strength": "...",
    "top_risk": "...",
    "next_priority": "..."
  },
  "job_match": {
    "level": "medium",
    "matched_points": [
      {
        "title": "...",
        "reason": "...",
        "evidence_ids": ["..."]
      }
    ],
    "missing_points": [
      {
        "title": "...",
        "impact": "...",
        "suggestion": "...",
        "evidence_ids": ["..."]
      }
    ]
  },
  "technical_strengths": [
    {
      "skill": "...",
      "description": "...",
      "evidence_ids": ["..."]
    }
  ],
  "technical_gaps": [
    {
      "skill": "...",
      "gap": "...",
      "priority": "high",
      "improvement_action": "...",
      "evidence_ids": ["..."]
    }
  ],
  "project_storytelling": {
    "strengths": [],
    "risks": [],
    "suggestions": []
  },
  "authenticity_risks": [
    {
      "risk": "...",
      "severity": "medium",
      "reason": "...",
      "suggested_fix": "...",
      "evidence_ids": ["..."]
    }
  ],
  "resume_suggestions": [
    {
      "section": "project_experience",
      "problem": "...",
      "suggestion": "...",
      "priority": "high"
    }
  ],
  "next_interview_focus": [
    {
      "topic": "...",
      "reason": "...",
      "sample_question": "..."
    }
  ],
  "learning_plan": [
    {
      "day_range": "day_1_3",
      "goal": "...",
      "tasks": ["..."],
      "expected_output": "..."
    }
  ],
  "evidence_references": [
    {
      "evidence_id": "...",
      "source_type": "interview_message",
      "summary": "..."
    }
  ]
}
```

### 5.3 结构化输出原则

GrowthReportAgent 输出必须满足：

```text
1. 不输出纯 Markdown 长文作为唯一结果。
2. 每个重要判断尽量带 evidence_ids。
3. priority / severity / level 使用枚举值。
4. 不直接给出无法验证的分数。
5. 不凭空添加候选人没有提过的项目经历。
6. 不凭空声称候选人掌握某项技术。
7. 建议必须可行动。
```

推荐枚举：

```text
level:
  strong
  medium
  weak
  unknown

priority:
  high
  medium
  low

severity:
  high
  medium
  low
```

---

## 6. Workflow 设计

### 6.1 workflow_id

```text
candidate_growth_report
```

### 6.2 推荐 steps

第一轮推荐：

```text
load_growth_context
build_growth_evidence
ensure_growth_report
generate_growth_report
persist_growth_report
complete
```

如果想更简化，第一轮可以合并为：

```text
load_growth_context
ensure_growth_report
generate_growth_report
complete
```

但建议保留 `build_growth_evidence`，因为第八阶段的关键就是 evidence-driven。

### 6.3 条件分支

第一轮至少需要一个复用分支：

```text
if growth report exists:
  branch = reuse_existing_growth_report
  next = complete
else:
  branch = generate_new_growth_report
  next = generate_growth_report
```

可选分支：

```text
if assessment missing:
  branch = missing_assessment
  next = failed 或 skipped

if transcript too short:
  branch = insufficient_transcript
  next = partial_report 或 skipped

if JD missing:
  branch = missing_jd
  next = generate_report_without_job_match
```

第一轮建议：

```text
assessment missing:
  failed

transcript too short:
  success with partial report

JD missing:
  success，但 job_match.level = unknown
```

### 6.4 workflow 触发方式

建议第一轮采用保守触发：

```text
POST /api/interview/end
  -> 内部完成 post_interview_assessment
  -> 再触发 candidate_growth_report
  -> 返回 evaluation + growth_report 简要结果
```

或者：

```text
POST /api/interview/end
  -> 只触发 post_interview_assessment

GET /api/interview/{session_uid}/growth-report
  -> 如果没有报告，则显式触发生成
```

第一轮推荐第二种更安全：

```text
面试结束仍保持稳定。
成长报告可以作为独立产品视图按需生成。
失败不会影响 interview end 主链路。
```

但如果产品上希望结束后立即看到报告，也可以在 `end` 内部串行触发。需要注意失败隔离。

### 6.5 推荐触发策略

建议采用：

```text
方案 A：按需生成
```

流程：

```text
用户结束面试
-> post_interview_assessment workflow 生成 evaluation / assessment
-> 用户进入成长报告页
-> 后端检查是否已有 growth report
-> 没有则启动 candidate_growth_report workflow
-> 前端展示报告或生成中状态
```

优点：

```text
1. 不阻塞面试结束接口。
2. workflow 边界更清晰。
3. 报告失败不会破坏 evaluation。
4. 适合后续改成异步任务。
```

---

## 7. State 设计

### 7.1 新增 state 类型

建议新增：

```text
CandidateGrowthReportState
```

建议文件：

```text
backend/app/service/candidate_growth_report_state.py
```

### 7.2 state 字段

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
assessment_id
growth_report_id
growth_report_uid
growth_agent_run_id
evidence_packet_id
completed_steps
failed_steps
last_error
resume_reason
resume_from_step
branch
next_action
is_partial
missing_inputs
```

### 7.3 thread_id 设计

推荐：

```text
growth:{session_uid}
```

原因：

```text
1. 与 interview:{session_uid} 区分。
2. 与 assessment:{session_uid} 区分。
3. 同一场面试的成长报告 workflow 有稳定 thread_id。
4. Workflow Runs 页面可以清楚区分 workflow_id + thread_id。
```

### 7.4 state 保存原则

可以进入 state 的内容：

```text
workflow_run_id
session_id
session_uid
project_id
evaluation_id
assessment_id
growth_report_id
growth_agent_run_id
completed_steps
failed_steps
branch
missing_inputs
last_error
```

不应该进入 state 的内容：

```text
完整 transcript
完整 prompt
完整 LLM response
完整 EvidencePacket
完整 GrowthReport JSON
Python ORM 对象
不可 JSON 序列化对象
```

这些内容应该通过 DB artifact 或 AgentRun 重建。

---

## 8. Artifact 设计

### 8.1 CandidateGrowthReport

建议新增持久化 artifact：

```text
candidate_growth_reports
```

建议字段：

```text
id
report_uid
session_id
session_uid
project_id
workflow_run_id
agent_run_id
status
report_version
content_json
source_snapshot
create_time
update_time
```

如果当前阶段不想新增表，可以先复用已有 JSON artifact 模式，但需要保证：

```text
1. 可以按 session 查询。
2. 可以关联 workflow_run。
3. 可以关联 AgentRun。
4. 可以判断是否已有报告。
5. 可以复用已有报告而不重复生成。
```

### 8.2 source_snapshot

`source_snapshot` 不保存完整大文本，只保存输入来源索引：

```json
{
  "session_uid": "...",
  "evaluation_id": 1,
  "assessment_id": 2,
  "resume_analysis_id": 3,
  "jd_analysis_id": 4,
  "message_count": 12,
  "report_version": "v1"
}
```

作用：

```text
1. 方便判断报告基于哪些上游结果生成。
2. 后续可用于报告失效判断。
3. 避免把大段 transcript 重复塞进 artifact。
```

### 8.3 artifact 复用原则

如果已有成功报告：

```text
1. 默认复用。
2. 不重复调用 GrowthReportAgent。
3. workflow state 写 branch = reuse_existing_growth_report。
4. completed_steps 记录 ensure_growth_report_reused。
```

如果上游输入发生变化，后续阶段可以引入：

```text
regenerate = true
```

第一轮暂不做复杂失效判断。

---

## 9. Evidence 设计

### 9.1 GrowthReportEvidencePacket

建议新增：

```text
GrowthReportEvidencePacket
```

它可以由 service 构建，不一定第一轮就持久化为独立表，但必须能进入 AgentRun input_snapshot。

推荐包含：

```text
session:
  session_uid
  role_name
  status

job:
  JD analysis
  target role
  key requirements

candidate:
  resume analysis
  project profile
  candidate profile

interview:
  transcript summary
  key answer excerpts
  topic coverage
  execution state

assessment:
  evaluation result
  post interview assessment
  authenticity signals

evidence_items:
  evidence_id
  source_type
  source_id
  summary
```

### 9.2 evidence_id 规则

推荐格式：

```text
msg:{message_id}
evaluation:{evaluation_id}
assessment:{assessment_id}
resume:{resume_analysis_id}
jd:{jd_analysis_id}
project:{project_id}
execution:{execution_id}
```

报告中的关键判断应引用这些 id。

### 9.3 EvidencePacket 构建原则

```text
1. 只放和成长报告有关的内容。
2. 大文本要摘要化。
3. 保留关键原话时要控制长度。
4. 每个 evidence item 要有 source_type。
5. 不把 workflow_runs.state 当成跨 workflow 事实来源。
6. 跨 workflow 事实来自 DB artifact。
```

---

## 10. Agent 设计

### 10.1 GrowthReportAgent

建议新增：

```text
GrowthReportAgent
```

职责：

```text
基于 GrowthReportEvidencePacket 生成结构化 Candidate Growth Report。
```

不负责：

```text
1. 查询数据库。
2. 推进 workflow。
3. 保存 report。
4. 判断是否复用已有 report。
5. 触发 resume optimization。
```

这些由 workflow node / service 负责。

### 10.2 Prompt

建议新增 prompt：

```text
backend/app/prompts/candidate_growth_report.txt
```

Prompt 要求：

```text
1. 明确输出 JSON。
2. 明确必须基于 evidence。
3. 明确不能编造经历或技能。
4. 明确 priority / severity / level 枚举。
5. 明确缺少证据时使用 unknown。
6. 明确建议必须可执行。
```

### 10.3 AgentRun 记录

GrowthReportAgent 每次调用必须写 AgentRun：

```text
agent_id = growth_report_agent
workflow_context.workflow_id = candidate_growth_report
workflow_context.workflow_run_id = 当前 workflow_run_id
workflow_context.step_id = generate_growth_report
input_snapshot = GrowthReportEvidencePacket + prompt variables 摘要
output_snapshot = structured report
status = success / failed
```

失败时必须记录：

```text
error_type
error_message
raw_response 可选
```

### 10.4 输出校验

第一轮至少需要做基础校验：

```text
1. 是否为合法 JSON。
2. 是否包含 report_version。
3. 是否包含 overall_summary。
4. 数组字段类型是否正确。
5. level / priority / severity 是否在允许枚举中。
```

如果已有 prompt contract / manifest validator，可以把该 prompt 纳入 manifest。

---

## 11. Node 设计

建议新增文件：

```text
backend/app/service/candidate_growth_report_nodes.py
backend/app/service/candidate_growth_report_workflow.py
backend/app/service/candidate_growth_report_state.py
```

### 11.1 initial_state

输入：

```text
session_uid 或 session_id
trigger
```

输出：

```text
CandidateGrowthReportState
```

职责：

```text
1. 设置 workflow_id。
2. 设置 thread_id = growth:{session_uid}。
3. 设置 incoming_trigger。
4. 初始化 completed_steps / failed_steps。
```

### 11.2 load_growth_context_node

职责：

```text
1. 加载 interview session。
2. 加载 project / resume / JD 相关 artifact。
3. 加载 evaluation / assessment。
4. 检查生成报告所需的最小输入。
5. 将 artifact id 写入 state。
```

最小输入建议：

```text
session 存在。
transcript 存在。
evaluation 或 assessment 至少一个存在。
```

如果缺少关键输入：

```text
state.missing_inputs 写入缺失项。
可根据策略 failed 或 partial。
```

### 11.3 build_growth_evidence_node

职责：

```text
1. 从 DB artifact 构建 GrowthReportEvidencePacket。
2. 生成 evidence_items。
3. 控制输入大小。
4. 写入 evidence_packet_id 或 evidence summary。
```

第一轮如果不持久化 evidence packet：

```text
可以只在内存中传给下一步，
但 AgentRun input_snapshot 必须保存足够的证据摘要。
```

### 11.4 ensure_growth_report_node

职责：

```text
1. 查询当前 session 是否已有成功 growth report。
2. 如果有，写入 state.growth_report_id。
3. 设置 branch = reuse_existing_growth_report。
4. 跳过 generate_growth_report。
```

如果没有：

```text
branch = generate_new_growth_report
```

### 11.5 generate_growth_report_node

职责：

```text
1. 调用 GrowthReportAgent。
2. 写 AgentRun。
3. 校验输出结构。
4. 将 agent_run_id 写入 state。
5. 将结构化结果交给 persist node。
```

注意：

```text
不要在该 node 里直接把 workflow 标记为 complete。
不要在 Agent 内部保存 DB artifact。
```

### 11.6 persist_growth_report_node

职责：

```text
1. 保存 CandidateGrowthReport artifact。
2. 关联 session / project / workflow_run / agent_run。
3. 写入 growth_report_id / growth_report_uid。
4. 保证幂等。
```

幂等要求：

```text
同一个 session_uid + report_version 默认只保留一个成功报告。
retry 时如果已有成功报告，直接复用。
```

### 11.7 complete_node

职责：

```text
1. 设置 status = success。
2. 设置 active_step = complete。
3. 设置 next_action。
4. 清理 last_error。
```

next_action 可选：

```text
view_report
start_resume_optimization
start_next_interview_practice
```

第一轮建议只写：

```text
view_report
```

---

## 12. API 设计

### 12.1 推荐新增 API

建议新增：

```text
GET /api/interview/{session_uid}/growth-report
```

语义：

```text
查询当前 session 的成长报告。
如果已存在，直接返回。
如果不存在，可根据 query 参数决定是否自动生成。
```

建议支持：

```text
GET /api/interview/{session_uid}/growth-report?generate=true
```

响应：

```json
{
  "sessionUid": "...",
  "status": "success",
  "workflowRunId": 123,
  "report": {},
  "errorMessage": null
}
```

### 12.2 可选显式生成 API

也可以新增：

```text
POST /api/interview/{session_uid}/growth-report/generate
```

优点：

```text
1. 查询和生成语义更清晰。
2. 前端可以明确控制生成动作。
3. 后续异步化更自然。
```

第一轮推荐：

```text
GET 查询已有报告。
POST 触发生成或复用。
```

### 12.3 API 返回状态

建议状态：

```text
not_found
generating
success
failed
partial
```

第一轮如果是同步生成，可以只使用：

```text
success
failed
not_found
```

---

## 13. 前端设计

### 13.1 新增视图

建议在面试结束结果区域新增：

```text
成长报告 / Growth Report
```

或者新增一个 session detail 子区域：

```text
Evaluation
Growth Report
Workflow Runs
```

### 13.2 展示模块

第一轮前端展示：

```text
1. 总体摘要。
2. 最强优势。
3. 最大风险。
4. 岗位匹配点。
5. 岗位缺口。
6. 技术优势。
7. 技术短板。
8. 项目表达建议。
9. 简历优化建议。
10. 下一轮训练重点。
11. 学习计划。
```

### 13.3 UI 原则

```text
1. 不要只展示一大段 Markdown。
2. 用分区展示结构化内容。
3. priority high 的内容要更突出。
4. evidence 可以第一轮不完全展开，但要保留数据结构。
5. 如果报告生成失败，要能提示用户重试。
6. 如果报告不存在，要提供生成入口。
```

### 13.4 Workflow Runs 页面

需要确认：

```text
1. 列表能看到 workflow_id = candidate_growth_report。
2. 详情能看到 state.branch。
3. 详情能看到 current_step。
4. failed 时能看到 last_error。
5. AgentRuns 能关联到 generate_growth_report step。
```

如果当前 Workflow Runs 页面已经通用，第一轮不需要额外改很多 UI。

---

## 14. 推荐实现顺序

### 14.1 第一步：梳理现有上游 artifact

先阅读：

```text
backend/app/service/post_interview_assessment_workflow.py
backend/app/service/post_interview_assessment_nodes.py
backend/app/service/post_interview_assessment_state.py
backend/app/service/assessment_agents.py
backend/app/service/preparation_agents.py
backend/app/service/resume_agents.py
backend/app/service/interview_service.py
backend/app/repository/interview_repository.py
backend/app/repository/workflow_run_repository.py
```

需要回答：

```text
1. evaluation 现在保存在哪里？
2. post_interview_assessment 的最终输出是什么？
3. resume analysis / JD analysis / candidate profile 保存在哪里？
4. transcript 如何读取？
5. 当前是否已有通用 artifact 表可复用？
6. AgentRun workflow_context 如何写？
```

### 14.2 第二步：定义数据结构

实现：

```text
CandidateGrowthReportState
CandidateGrowthReport schema
GrowthReportEvidencePacket
GrowthReportOutput schema
```

### 14.3 第三步：注册 workflow

在 workflow registry 中注册：

```text
workflow_id = candidate_growth_report
steps:
  load_growth_context
  build_growth_evidence
  ensure_growth_report
  generate_growth_report
  persist_growth_report
  complete
```

### 14.4 第四步：实现 Agent

实现：

```text
GrowthReportAgent
candidate_growth_report.txt
prompt manifest 更新
output schema validation
```

### 14.5 第五步：实现 workflow nodes

实现：

```text
initial_state
load_growth_context_node
build_growth_evidence_node
ensure_growth_report_node
generate_growth_report_node
persist_growth_report_node
complete_node
```

### 14.6 第六步：接入 API

建议新增：

```text
GET /api/interview/{session_uid}/growth-report
POST /api/interview/{session_uid}/growth-report/generate
```

### 14.7 第七步：前端展示

实现：

```text
1. 成长报告查询。
2. 成长报告生成入口。
3. 成功态展示。
4. 失败态重试。
5. 空态展示。
```

### 14.8 第八步：测试和验收

补齐后端测试和前端 build。

---

## 15. 测试计划

### 15.1 workflow registry tests

```text
1. candidate_growth_report workflow 注册成功。
2. step_id 不重复。
3. required steps 合法。
4. workflow_context 可以识别 generate_growth_report step。
```

### 15.2 state tests

```text
1. initial_state 使用 growth:{session_uid}。
2. state 包含 workflow_id / thread_id / session_uid。
3. public state 不包含 ORM 对象。
4. state 可以 JSON 序列化。
```

### 15.3 evidence tests

```text
1. 可以从 session / transcript / evaluation / assessment 构建 evidence packet。
2. 缺少 JD 时 job_match 可以降级为 unknown。
3. 缺少 assessment 时按策略 failed。
4. evidence item 包含 evidence_id / source_type / summary。
```

### 15.4 normal path tests

```text
1. 没有 growth report 时，workflow 生成新报告。
2. workflow_runs.status 最终为 success。
3. workflow_runs.current_step 最终为 complete。
4. workflow_runs.state 包含 growth_report_id。
5. AgentRun workflow_context 指向 candidate_growth_report。
6. report content_json 符合 schema。
```

### 15.5 reuse tests

```text
1. 已有成功 growth report 时不重复调用 GrowthReportAgent。
2. state.branch = reuse_existing_growth_report。
3. completed_steps 包含 ensure_growth_report_reused。
4. AgentRun 数量不增加。
5. API 返回已有报告。
```

### 15.6 failed path tests

```text
1. GrowthReportAgent 失败时 workflow_runs.status = failed。
2. current_step 指向 generate_growth_report。
3. last_error 存在。
4. 不保存半成品 success report。
5. AgentRun 记录 failed 状态。
```

### 15.7 retry tests

```text
1. failed retry 使用旧 state 的 session/context。
2. retry 成功后 workflow_runs.status = success。
3. retry 不重复保存多个 success report。
4. 如果 retry 前已经存在成功 report，则复用。
```

### 15.8 API tests

```text
1. GET 无报告时返回 not_found。
2. POST generate 可以生成报告。
3. GET 有报告时返回 success。
4. 生成失败时返回 failed 和 errorMessage。
```

### 15.9 frontend tests / build

```text
1. 前端 build 通过。
2. 空态显示生成入口。
3. 成功态显示结构化报告。
4. 失败态显示重试入口。
5. Workflow Runs 页面仍可查看新 workflow。
```

---

## 16. 验收标准

Phase 8 第一轮完成时，应满足：

```text
1. candidate_growth_report workflow 已注册。
2. GrowthReportAgent 已接入。
3. GrowthReportAgent 调用有 AgentRun。
4. AgentRun 带 workflow_context。
5. 成长报告基于 GrowthReportEvidencePacket 生成。
6. 成长报告被持久化为 artifact。
7. 已有报告可以复用，不重复生成。
8. 失败时 workflow_runs.status = failed。
9. retry 可以成功恢复。
10. 前端可以查看成长报告。
11. Workflow Runs 可以观察 candidate_growth_report。
12. 测试覆盖 normal / reuse / failed / retry / API / schema。
```

更产品化的验收标准：

```text
用户完成一场模拟面试后，
不仅能看到面试评价，
还能看到一份结构化成长报告，
知道自己的优势、短板、岗位差距、简历优化方向和下一轮训练重点。
```

---

## 17. 与后续阶段的关系

第八阶段第一轮完成后，后续可以自然演进：

```text
Phase 8.2:
  resume_optimization workflow 消费 growth report，生成简历改写建议。

Phase 8.3:
  preparation workflow 消费 growth report，生成下一轮面试训练计划。

Phase 9:
  引入 RAG 知识库，给 learning_plan 提供学习材料和面试题证据。

Phase 10:
  引入 Human Review，让用户选择成长方向并确认简历改写策略。

Phase 11:
  多次面试报告对比，形成长期能力成长曲线。
```

因此，第八阶段第一轮不是终点，而是高级 Agent 产品能力的入口。

---

## 18. 核心原则

```text
高级 Agent 能力不是让模型自由发挥，
而是让模型在 workflow、state、tool、evidence、artifact、AgentRun 的约束下工作。
```

```text
成长报告不是评价的重复，
而是把评价转化为用户下一步可以执行的行动计划。
```

```text
workflow_runs.state 不是跨 workflow 的事实来源，
跨 workflow 协作必须通过 DB artifact 或明确 output contract。
```

```text
第八阶段的工程判断不是“还能接入哪个 Agent”，
而是“哪个 Agent 产物能让用户更清楚地知道下一步怎么变强”。
```

最终，本阶段要让系统从：

```text
可观测、可恢复的 AI 面试 workflow 系统
```

升级为：

```text
能够输出结构化成长报告和行动建议的 AI 求职成长产品。
```


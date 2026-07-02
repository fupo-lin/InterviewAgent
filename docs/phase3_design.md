# Phase 3 设计文档：Agent、Prompt、画像与证据体系治理

## 1. 背景

当前系统已经完成了从 V1 面试问答，到 Phase 2 求职准备项目，再到 Phase 2 优化链路的多轮演进。现有能力大致包括：

1. `PreparationProject`：求职准备项目。
2. `JDAnalysis`：JD 结构化解析。
3. `ResumeProfile`：简历结构化解析。
4. `GapAnalysis`：JD 与简历匹配差距分析。
5. `InterviewPlan`：面试计划生成。
6. `InterviewPlanExecution`：面试计划执行状态。
7. `TopicCompletionJudge`：话题是否继续或切换的判断。
8. `InterviewSummary`：面试过程中的 CandidateProfile 与 ConversationSummary。
9. `ProjectCandidateProfile`：项目级候选人画像。
10. `ResumeAuthenticityReport`：简历真实性验证报告。
11. `ResumeRewriteResult`：简历重写结果。

这说明系统已经不再是一个简单的“面试聊天机器人”，而是开始具备“求职准备工作流”的雏形。

但随着 Agent 和 Prompt 数量增加，当前架构正在出现新的复杂度问题：

1. Prompt 文件越来越多，但缺少统一的输入参数、输出结构、版本、依赖关系和质量约束。
2. Agent 目前主要表现为 `Service + Prompt + LLMService method`，缺少统一 Agent 抽象。
3. 候选人画像虽然已经有 session 级和 project 级两类产物，但没有明确版本化策略。
4. `Summary`、`Profile`、`Evaluation` 的边界仍然容易混淆。
5. 多数 Agent 仍直接读取 `summary + resume + JD + history`，缺少统一证据体系，导致输出难以追踪、复用和校验。

Phase 3 的重点不应该继续堆新功能，而是先治理“上下文、证据、Agent、Prompt、画像版本”这些底层结构。

## 2. Phase 3 总目标

Phase 3 的目标是把当前系统从：

```text
多个 Service 各自拼 Prompt、拼上下文、调用 LLM
```

升级为：

```text
统一 Agent Contract
+ 统一 Prompt Contract
+ 统一 Context Assembly
+ 统一 Evidence System
+ 版本化 Candidate Profile
```

最终希望达到：

```text
任意一个 Agent 在执行前都能声明：
  我是谁
  我的任务是什么
  我需要哪些输入
  我可以读取哪些上下文
  我必须基于哪些证据
  我输出什么结构
  我的输出版本是什么
  我的结果如何被后续 Agent 使用
```

这不是为了“架构漂亮”，而是为了解决后续扩展时的真实问题：

1. 新增 Agent 时不会重复发明输入格式。
2. 修改 Prompt 时能知道影响哪些输出和下游功能。
3. 候选人画像可追踪、可比较、可回滚。
4. Evaluation 不再混用 memory 或 profile 的职责。
5. ResumeRewrite、Coach、JobRecommendation 等 Agent 可以基于可解释证据输出，而不是基于一大坨上下文自由发挥。

## 3. Phase 3 不做什么

Phase 3 暂时不以新增业务功能为核心。

暂不建议做：

1. 不做岗位推荐 Agent 的完整实现。
2. 不做学习计划 Agent 的完整实现。
3. 不做复杂 LangGraph 多 Agent 编排。
4. 不做题库 RAG。
5. 不做 PDF / DOCX 简历解析。
6. 不做前端大型交互重构。
7. 不追求一次性替换所有已有服务。

Phase 3 的核心是“治理与规范”，优先让已有 Agent 变得可维护、可扩展、可追踪。

## 4. 当前问题分析

### 4.1 Prompt 爆炸与 Prompt Contract 缺失

当前已有多个 prompt：

```text
candidate_profile.txt
conversation_summary.txt
evaluation.txt
followup.txt
gap_analysis.txt
interviewer.txt
interview_plan.txt
jd_analysis.txt
project_candidate_profile.txt
resume_analysis.txt
resume_authenticity.txt
resume_rewrite.txt
topic_completion_judge.txt
```

它们的问题不是“文件多”，而是缺少统一规范。

当前 Prompt 层常见问题：

1. Prompt 文件只是一段模板文本，没有声明自己的用途、输入、输出和版本。
2. 输入参数通过字符串替换传入，缺少统一 schema。
3. 输出 JSON 结构写在 prompt 文本里，但没有独立 schema 管理。
4. `LLMService` 对每个 prompt 单独写一个 method，method 越来越多。
5. Prompt 之间存在隐性依赖，例如 `resume_rewrite` 依赖 `resume_authenticity`，但系统层没有显式描述。
6. Prompt 更新后，旧产物无法知道是由哪个 prompt 版本生成的。
7. 某些 prompt 的输出结构相似但字段命名不统一，例如 `snake_case`、`camelCase`、自由文本混用。

如果继续这样发展，后续每新增一个 Agent，就会多一套：

```text
prompt 文件
LLMService method
mock method
parse method
service orchestration
上下文拼接逻辑
输出 JSON 约定
```

这会造成提示词爆炸和服务层膨胀。

### 4.2 Agent 缺少统一抽象

当前系统中有很多“事实上的 Agent”：

```text
JDAnalysisAgent
ResumeAnalysisAgent
GapAnalysisAgent
InterviewPlanAgent
InterviewExecutorAgent
TopicCompletionJudgeAgent
ProjectCandidateProfileAgent
ResumeAuthenticityAgent
ResumeRewriteAgent
EvaluationAgent
```

但代码层目前主要还是：

```text
PreparationService / InterviewService
  -> LLMService.generate_xxx()
  -> prompt_xxx.txt
```

这带来几个问题：

1. 每个 Agent 的输入输出没有统一生命周期。
2. 每个 Agent 如何取上下文由调用方临时决定。
3. 每个 Agent 的错误处理、mock、重试、JSON 解析逻辑分散。
4. 每个 Agent 的产物保存策略不统一。
5. 无法统一记录一次 Agent Run 的输入、输出、模型、prompt 版本和证据引用。

Phase 3 需要引入“轻量 Agent 基类”，但不必一开始就上复杂多 Agent 框架。

### 4.3 候选人画像没有版本化

当前存在三类容易混淆的画像或记忆：

```text
ResumeProfile
  来自简历解析，是简历视角下的静态候选人画像。

InterviewSummary(summary_type = candidate_profile)
  来自单场面试滚动总结，是 session 级动态画像。

ProjectCandidateProfile
  来自项目上下文、简历、面试证据和评价，是 project 级综合画像。
```

但当前 `ProjectCandidateProfile` 更像是“最新画像快照”，还没有完整表达：

1. 这是第几版画像。
2. 相比上一版新增、修正、删除了什么。
3. 由哪些输入生成。
4. 引用了哪些证据。
5. 是否已经被真实性报告或简历重写使用。
6. 哪些字段是高置信度，哪些是低置信度。
7. 当 Resume/JD/Interview/Evaluation 变化后，画像是否过期。

候选人画像后续会成为多个功能的底座。如果没有版本化，后续会出现：

1. 简历重写不知道用了哪版画像。
2. 学习计划不知道基于哪场面试表现生成。
3. 多次训练后无法对比能力成长。
4. 用户修改简历后，旧画像和新画像混在一起。
5. 画像错误时无法回滚或排查来源。

### 4.4 Summary、Profile、Evaluation 边界不清

这三者的边界必须在 Phase 3 明确下来。

当前容易混淆的原因是：

1. CandidateProfile 目前作为 `InterviewSummary` 的一种类型保存。
2. ConversationSummary 也是 `InterviewSummary` 的一种类型保存。
3. Evaluation 会读取 Summary 和 Profile，又会产生新的能力判断。
4. ProjectCandidateProfile 又融合了 ResumeProfile、InterviewSummary、Evaluation。

如果边界不清，会导致：

1. Summary 里混入能力结论。
2. Profile 里混入面试建议。
3. Evaluation 里承担记忆职责。
4. ResumeRewrite 不知道应该相信 Summary、Profile 还是 Evaluation。

Phase 3 必须定义：

```text
Summary 是记忆。
Profile 是能力模型。
Evaluation 是评价结论。
Evidence 是事实依据。
```

### 4.5 缺少证据体系

当前 Agent 多数直接读取：

```text
summary
resume
JD
history
plan
execution
evaluation
```

然后让模型自行判断哪些内容重要。

这种方式早期可用，但后续风险很大：

1. 模型可能把 summary 中的压缩表达当成事实。
2. 模型可能引用简历声明，却没有面试证据支撑。
3. 模型可能把 evaluation 的主观结论当成原始事实。
4. ResumeRewrite 可能强化证据不足的内容。
5. 用户质疑某个建议时，系统无法回答“依据是哪一轮回答”。

Phase 3 需要引入 Evidence System，让 Agent 的输入不只是上下文文本，而是结构化证据包。

## 5. Phase 3 核心设计原则

### 5.1 Prompt 是可版本化资产，不是普通文本

每个 prompt 都应该有：

```text
prompt_id
version
owner_agent
task
input_schema
output_schema
required_context
required_evidence
```

Prompt 文件可以继续是 `.txt`，但必须配套元数据。

### 5.2 Agent 是稳定接口，Prompt 是可替换实现

Agent 不应该等同于某个 prompt。

推荐理解：

```text
Agent:
  对外稳定的任务执行单元。

Prompt:
  Agent 当前使用的一种 LLM 指令实现。
```

例如：

```text
ResumeRewriteAgent
  可以从 prompt v1 升级到 prompt v2
  但对调用方仍然是 rewrite_resume(input) -> ResumeRewriteResult
```

### 5.3 Context 和 Evidence 分离

上下文不是证据。

```text
Context:
  帮助模型理解任务背景的信息。

Evidence:
  可以支撑判断、评价、重写、建议的事实依据。
```

例如：

```text
JDAnalysis 是 context。
ResumeProfile 是 context + resume claim source。
InterviewMessage 用户回答是 evidence。
InterviewPlanExecution.evidence 是 evidence index。
Evaluation 是 conclusion，不是原始 evidence。
ConversationSummary 是 memory，不是强 evidence。
```

### 5.4 产物必须能追踪来源

所有关键 LLM 产物应能追踪：

```text
由哪个 Agent 生成
使用哪个 prompt 版本
使用哪个模型
输入了哪些上下文
引用了哪些证据
输出 schema 版本
生成时间
```

这能支撑调试、回滚、版本迁移和质量评估。

### 5.5 画像是可演进模型，不是一次性总结

候选人画像应该支持：

```text
版本
来源
置信度
证据引用
变更记录
过期判断
```

画像不能只是一段“最新 JSON”。

## 6. 核心概念边界

### 6.1 Summary：记忆

Summary 的职责是压缩对话历史，服务于后续上下文注入。

它回答：

```text
前面聊过什么？
已经问过哪些点？
候选人最近怎么回答？
后续追问应避免重复什么？
```

Summary 不应该承担：

```text
最终能力评级
简历真实性判断
是否录用建议
长期候选人能力模型
```

建议 Summary 类型：

```text
conversation_summary
  面试对话摘要，快变记忆。

session_candidate_memory
  单场面试中候选人稳定信息摘要，慢变记忆。

evaluation_context
  可选，用于最终评价的证据摘要。
```

注意：`session_candidate_memory` 可以继续短期放在 `interview_summaries.summary_type = candidate_profile`，但概念上应从 Profile 中剥离，避免命名误导。

### 6.2 Profile：能力模型

Profile 的职责是表达候选人的能力、经验、风险和发展方向。

它回答：

```text
候选人是什么类型的人？
有哪些技能和项目经验？
哪些能力被验证？
哪些声明未验证？
哪些风险需要关注？
适合什么岗位方向？
```

Profile 应该是结构化模型，包含证据和置信度。

系统中建议保留多层 Profile：

```text
ResumeProfile
  简历解析得到的静态画像。
  来源：ResumeDocument。
  置信度：只代表“简历声称”，不代表已验证。

SessionCandidateProfile
  单场面试过程画像。
  来源：InterviewMessage + InterviewPlanExecution。
  置信度：基于本场面试证据。

ProjectCandidateProfile
  项目级综合画像。
  来源：ResumeProfile + JDAnalysis + GapAnalysis + one/many SessionCandidateProfile + Evaluation + Evidence。
  置信度：综合判断。
```

### 6.3 Evaluation：评价

Evaluation 的职责是对一次面试表现或一次项目准备状态做评价。

它回答：

```text
这场面试表现如何？
技术能力如何？
项目经验如何？
沟通表达如何？
是否建议进入下一轮？
下一步如何改进？
```

Evaluation 是结论，不是记忆，也不是画像底座。

它可以读取 Summary、Profile、Evidence，但不应该取代它们。

### 6.4 Evidence：事实依据

Evidence 的职责是支撑判断。

它回答：

```text
这个结论来自哪里？
是哪一轮回答？
原文是什么？
对应哪个简历声明？
对应哪个 JD 要求？
对应哪个 InterviewPlan probe point？
证据强度如何？
```

Evidence 应该尽可能结构化和可引用。

## 7. Prompt Contract 设计

### 7.1 Prompt 元数据

建议为每个 prompt 增加一份元数据定义。第一阶段可以使用文件头注释或单独 YAML/JSON 文件。推荐长期使用：

```text
backend/app/prompts/manifest.json
```

示例：

```json
{
  "resume_rewrite": {
    "prompt_file": "resume_rewrite.txt",
    "version": "3.0.0",
    "owner_agent": "ResumeRewriteAgent",
    "task": "rewrite_resume",
    "input_schema": "ResumeRewriteInput.v1",
    "output_schema": "ResumeRewriteResult.v1",
    "required_context": [
      "ResumeDocument",
      "ResumeProfile"
    ],
    "optional_context": [
      "JDAnalysis",
      "GapAnalysis",
      "ProjectCandidateProfile",
      "Evaluation"
    ],
    "required_evidence": [
      "ResumeClaimEvidence",
      "InterviewEvidence"
    ],
    "output_contract": {
      "format": "json_object",
      "strict": true
    }
  }
}
```

### 7.2 Prompt 输入规范

每个 Prompt 不再直接面对散乱字符串参数，而是面对一个统一输入对象。

推荐输入结构：

```json
{
  "task": {
    "task_id": "resume_rewrite",
    "mode": "jd_targeted",
    "locale": "zh-CN"
  },
  "context": {
    "jd_analysis": {},
    "resume_profile": {},
    "gap_analysis": {},
    "project_candidate_profile": {},
    "evaluation": {}
  },
  "evidence_packet": {
    "evidence_items": []
  },
  "constraints": {
    "must_not_fabricate": true,
    "output_language": "zh-CN"
  }
}
```

好处是：

1. Agent 不再临时拼一堆 prompt 参数。
2. Prompt 输入可以被记录、测试、回放。
3. 输入可以做 schema 校验。
4. 新增字段不容易破坏旧逻辑。

### 7.3 Prompt 输出规范

每个 Agent 输出都应该有统一外壳：

```json
{
  "schema_version": "ResumeRewriteResult.v1",
  "result": {},
  "evidence_refs": [],
  "confidence": "high|medium|low",
  "warnings": [],
  "missing_inputs": []
}
```

其中：

```text
result
  业务结果。

evidence_refs
  本次输出引用了哪些证据。

confidence
  输出整体置信度。

warnings
  风险提示，例如证据不足、输入缺失、只能生成草稿。

missing_inputs
  明确告诉上游还缺哪些信息。
```

业务层可以先兼容旧格式，但新 Agent 应逐步采用这个统一外壳。

### 7.4 Prompt 命名规范

建议 prompt_id 使用任务名，而不是随意文件名：

```text
jd_analysis
resume_analysis
gap_analysis
interview_plan_generation
topic_completion_judge
project_candidate_profile_generation
resume_authenticity_check
resume_rewrite
evaluation_generation
```

文件命名可以保持：

```text
{prompt_id}.txt
{prompt_id}.schema.json
```

### 7.5 Prompt 版本规范

版本建议采用：

```text
major.minor.patch
```

规则：

```text
patch:
  文案优化，不改变输入输出结构。

minor:
  增加可选字段，兼容旧调用方。

major:
  改变输入或输出 schema，旧调用方需要适配。
```

所有 LLM 产物保存时，应记录：

```text
prompt_id
prompt_version
output_schema_version
```

## 8. Agent 基类设计

### 8.1 为什么需要 Agent 基类

Agent 基类不是为了复杂化系统，而是统一以下行为：

1. 输入校验。
2. 上下文装配。
3. 证据包装配。
4. Prompt 渲染。
5. LLM 调用。
6. JSON 解析。
7. 输出校验。
8. 运行日志。
9. 产物保存。
10. mock / fallback。

### 8.2 Agent 抽象职责

建议定义轻量基类：

```python
class BaseAgent:
    agent_name: str
    task_name: str
    prompt_id: str
    input_schema: type
    output_schema: type

    async def run(self, input_data, runtime_context):
        ...

    def build_context(self, input_data, runtime_context):
        ...

    def build_evidence_packet(self, input_data, runtime_context):
        ...

    def render_prompt(self, agent_input):
        ...

    def parse_output(self, model_output):
        ...

    def validate_output(self, parsed_output):
        ...
```

Phase 3 不一定马上写代码，但设计上应明确这个方向。

### 8.3 Agent 输入输出

统一 Agent 输入：

```json
{
  "request_id": "",
  "project_id": null,
  "session_id": null,
  "task_params": {},
  "context_refs": {},
  "evidence_policy": {
    "required": [],
    "optional": [],
    "min_confidence": "medium"
  }
}
```

统一 Agent 输出：

```json
{
  "agent_name": "",
  "agent_version": "",
  "prompt_id": "",
  "prompt_version": "",
  "output_schema_version": "",
  "result": {},
  "evidence_refs": [],
  "confidence": "medium",
  "warnings": [],
  "raw_response": {}
}
```

### 8.4 Agent Run 记录

建议新增统一运行记录概念：

```text
agent_runs
```

字段建议：

```text
id
agent_name
agent_version
task_name
project_id
session_id
input_schema_version
output_schema_version
prompt_id
prompt_version
model_name
input_snapshot JSON
context_refs JSON
evidence_refs JSON
output_snapshot JSON
raw_response JSON
status
error_message
create_time
```

这张表可以先不立即实现，但 Phase 3 设计上应作为目标。

它解决：

1. 为什么这次输出是这样？
2. 哪个 prompt 版本生成的？
3. 使用了哪些证据？
4. 失败时怎么排查？
5. prompt 升级后如何对比新旧输出？

### 8.5 Agent 列表与职责

Phase 3 建议明确已有 Agent 边界：

```text
JDAnalysisAgent
  输入：JobDescription。
  输出：JDAnalysis。
  证据：JD 原文。

ResumeAnalysisAgent
  输入：ResumeDocument。
  输出：ResumeProfile。
  证据：Resume 原文。

GapAnalysisAgent
  输入：JDAnalysis + ResumeProfile。
  输出：GapAnalysis。
  证据：JD requirement refs + resume claim refs。

InterviewPlanAgent
  输入：JDAnalysis / ResumeProfile / GapAnalysis。
  输出：InterviewPlan。
  证据：GapAnalysis、JDAnalysis、ResumeProfile。

InterviewExecutorAgent
  输入：InterviewPlan + InterviewPlanExecution + recent messages。
  输出：next question。
  证据：current section evidence + recent answer。

TopicJudgeAgent
  输入：current section + user answer + recent messages。
  输出：TopicJudgeResult。
  证据：当前轮回答。

SessionMemoryAgent
  输入：InterviewMessage delta。
  输出：ConversationSummary / SessionCandidateMemory。
  证据：对话原文。

ProjectProfileAgent
  输入：ResumeProfile + InterviewEvidence + Evaluation。
  输出：ProjectCandidateProfileVersion。
  证据：面试回答、执行证据、简历声明。

EvaluationAgent
  输入：InterviewEvidence + Summary + Profile。
  输出：InterviewEvaluation。
  证据：面试回答和证据索引。

ResumeAuthenticityAgent
  输入：ResumeClaim + InterviewEvidence + ProjectCandidateProfile。
  输出：ResumeAuthenticityReport。
  证据：简历 claim 与面试回答对齐。

ResumeRewriteAgent
  输入：ResumeDocument + ResumeProfile + JDAnalysis + AuthenticityReport + Evidence。
  输出：ResumeRewriteResult。
  证据：已验证 claim、真实性约束。
```

## 9. Candidate Profile 版本化设计

### 9.1 为什么画像需要版本

候选人画像会随着以下事件变化：

1. 用户上传新简历。
2. 用户修改目标 JD。
3. 生成新的 GapAnalysis。
4. 完成一场新的模拟面试。
5. 生成新的 Evaluation。
6. 生成新的 ResumeAuthenticityReport。
7. 用户手动修正某些画像内容。

因此画像不是一个固定字段，而是一条演进链。

### 9.2 ProjectCandidateProfileVersion

建议将项目级画像理解为版本化产物：

```text
ProjectCandidateProfile
  逻辑上的当前项目候选人画像。

ProjectCandidateProfileVersion
  某一次生成的画像版本。
```

如果不想马上拆表，也可以先在现有 `project_candidate_profiles` 中增加版本字段。长期推荐概念如下：

```text
project_candidate_profiles
  id
  project_id
  current_version_id
  status

project_candidate_profile_versions
  id
  profile_id
  version_no
  source_session_id
  source_resume_profile_id
  source_jd_analysis_id
  source_gap_analysis_id
  source_evaluation_id
  source_authenticity_report_id
  content JSON
  evidence_refs JSON
  change_summary JSON
  confidence
  status
  create_time
```

### 9.3 画像内容结构

建议画像内容包含：

```json
{
  "schema_version": "ProjectCandidateProfile.v1",
  "profile_meta": {
    "version_no": 3,
    "source_type": "interview_completed",
    "confidence": "medium",
    "generated_at": ""
  },
  "basic_profile": {},
  "skill_profile": [],
  "project_experience": [],
  "capability_profile": {},
  "risk_profile": [],
  "evidence_map": {},
  "open_questions": [],
  "learning_needs": [],
  "resume_optimization_focus": []
}
```

### 9.4 画像字段必须带来源

能力画像不能只写：

```json
{
  "technical_depth": {
    "level": "medium"
  }
}
```

应该写：

```json
{
  "technical_depth": {
    "level": "medium",
    "confidence": "medium",
    "evidence_refs": ["ev_12", "ev_18"],
    "reason": "能说明消息可靠性方案，但缺少压测和容量规划细节"
  }
}
```

### 9.5 画像版本生成时机

建议：

```text
创建项目后：
  无画像。

生成 ResumeProfile 后：
  可生成 profile v1，标记 source_type = resume_only。

完成第一场面试后：
  生成 profile v2，标记 source_type = interview_completed。

生成 ResumeAuthenticityReport 后：
  可生成 profile v3，补充真实性风险。

用户上传新简历后：
  旧 profile 标记 stale，新 ResumeProfile 触发新画像版本。

用户更换 JD 后：
  不必重写所有能力结论，但 JD 匹配相关字段应标记 stale。
```

### 9.6 画像过期判断

Profile 需要 stale 判断。

示例规则：

```text
如果 latest_resume_profile_id != profile.source_resume_profile_id:
  profile 对简历相关字段过期。

如果 latest_jd_analysis_id != profile.source_jd_analysis_id:
  profile 对岗位匹配字段过期。

如果 latest_evaluation_id 比 profile.source_evaluation_id 更新:
  profile 对面试表现字段过期。

如果最新 InterviewSession finished 且没有生成新 profile:
  profile 对面试证据字段过期。
```

## 10. Evidence System 设计

### 10.1 Evidence 的来源

Evidence 可以来自：

```text
ResumeDocument
  简历原文中的声明。

JobDescription
  JD 原文中的要求。

InterviewMessage
  候选人面试回答。

InterviewPlanExecution
  当前回答覆盖的 probe point、answer_quality、judge_reason。

Evaluation
  评价结论，注意它是 conclusion evidence，不是原始事实。

ResumeAuthenticityReport
  claim check 结论。
```

### 10.2 Evidence 类型

建议统一证据类型：

```text
resume_claim
  简历声明。

jd_requirement
  JD 要求。

interview_answer
  面试回答原文。

execution_probe
  面试计划中的 probe point 覆盖结果。

topic_judge
  话题判断结果。

evaluation_finding
  评价发现。

authenticity_check
  简历真实性检查结果。
```

### 10.3 EvidenceItem 结构

建议结构：

```json
{
  "evidence_id": "ev_001",
  "evidence_type": "interview_answer",
  "source_type": "interview_message",
  "source_id": 123,
  "project_id": 1,
  "session_id": 10,
  "round_no": 4,
  "content_excerpt": "候选人说明了消息重试和幂等处理...",
  "raw_ref": {
    "table": "interview_messages",
    "id": 123
  },
  "tags": ["message_reliability", "idempotency"],
  "confidence": "medium",
  "created_at": ""
}
```

### 10.4 EvidencePacket

Agent 不应直接读取一堆对象，而应读取按任务整理好的证据包。

示例：

```json
{
  "packet_id": "ep_resume_rewrite_001",
  "task": "resume_rewrite",
  "project_id": 1,
  "evidence_items": [
    {
      "evidence_id": "ev_resume_claim_1",
      "evidence_type": "resume_claim",
      "content_excerpt": "负责订单系统高并发架构设计",
      "confidence": "claim_only"
    },
    {
      "evidence_id": "ev_answer_4",
      "evidence_type": "interview_answer",
      "content_excerpt": "候选人能讲清 MQ 重试，但没有给出 QPS 和压测数据",
      "confidence": "medium"
    },
    {
      "evidence_id": "ev_auth_2",
      "evidence_type": "authenticity_check",
      "content_excerpt": "高并发架构主导权仅部分支持",
      "confidence": "high"
    }
  ],
  "missing_evidence": [
    "QPS",
    "压测结果",
    "个人主导边界"
  ]
}
```

### 10.5 Evidence 与 Context 的输入分层

推荐 Agent 输入分成三层：

```text
Task Params:
  本次要做什么。

Context:
  背景材料，例如 JDAnalysis、ResumeProfile、GapAnalysis。

EvidencePacket:
  可引用、可追踪、可约束输出的事实依据。
```

对于 ResumeRewriteAgent：

```text
Task Params:
  rewrite_mode = jd_targeted

Context:
  JDAnalysis
  ResumeProfile
  GapAnalysis
  ProjectCandidateProfile

EvidencePacket:
  resume_claim evidence
  interview_answer evidence
  authenticity_check evidence
```

这样可以明确告诉模型：

```text
Context 用来理解背景。
Evidence 用来支撑可写入简历的事实。
没有 Evidence 的内容只能作为待补充建议，不能写成强事实。
```

## 11. 各 Agent 的证据需求

### 11.1 JDAnalysisAgent

```text
必需 context:
  JobDescription.raw_content

必需 evidence:
  JD 原文段落

输出:
  JDAnalysis

注意:
  JDAnalysis 是对 JD 的解释，不是候选人能力判断。
```

### 11.2 ResumeAnalysisAgent

```text
必需 context:
  ResumeDocument.raw_content

必需 evidence:
  简历原文段落

输出:
  ResumeProfile

注意:
  ResumeProfile 表达的是“简历声称”，不是已验证事实。
```

### 11.3 GapAnalysisAgent

```text
必需 context:
  JDAnalysis
  ResumeProfile

必需 evidence:
  jd_requirement
  resume_claim

输出:
  GapAnalysis

注意:
  GapAnalysis 只能判断 JD 与简历文本的匹配差距，不能判断候选人实际能力。
```

### 11.4 InterviewExecutorAgent

```text
必需 context:
  InterviewPlan
  InterviewPlanExecution
  ConversationSummary
  SessionCandidateMemory

必需 evidence:
  recent interview_answer
  current section evidence

输出:
  next_question

注意:
  追问必须服务于 current_section 和 next_action。
```

### 11.5 EvaluationAgent

```text
必需 context:
  InterviewPlan，可选
  JDAnalysis，可选
  ResumeProfile，可选
  ConversationSummary，可选
  ProjectCandidateProfile，可选

必需 evidence:
  interview_answer
  execution_probe

输出:
  InterviewEvaluation

注意:
  所有评价结论必须引用具体面试表现，不应只基于简历或 summary。
```

### 11.6 ProjectProfileAgent

```text
必需 context:
  ResumeProfile，可选
  JDAnalysis，可选
  GapAnalysis，可选
  Evaluation，可选

必需 evidence:
  interview_answer
  execution_probe
  resume_claim

输出:
  ProjectCandidateProfileVersion

注意:
  每个能力结论应有 evidence_refs 和 confidence。
```

### 11.7 ResumeAuthenticityAgent

```text
必需 context:
  ResumeDocument
  ResumeProfile
  ProjectCandidateProfile，可选

必需 evidence:
  resume_claim
  interview_answer
  execution_probe

输出:
  ResumeAuthenticityReport

注意:
  它不是判断候选人是否撒谎，而是判断简历声明是否有足够证据支撑。
```

### 11.8 ResumeRewriteAgent

```text
必需 context:
  ResumeDocument
  ResumeProfile

可选 context:
  JDAnalysis
  GapAnalysis
  ProjectCandidateProfile
  Evaluation

必需 evidence:
  resume_claim
  authenticity_check

推荐 evidence:
  interview_answer
  execution_probe

输出:
  ResumeRewriteResult

注意:
  没有证据支撑的内容只能进入 missing_info_to_collect 或 risk_warnings，不能写入 rewritten 强事实。
```

## 12. 数据结构调整建议

Phase 3 可以分成“文档规范先行”和“代码逐步落地”两层。

### 12.1 建议新增概念表

长期建议新增：

```text
agent_runs
evidence_items
evidence_packets
project_candidate_profile_versions
prompt_registry
```

但不建议一次性全部实现。

### 12.2 现有表的渐进增强

如果希望低成本演进，可以先在现有 LLM 产物表增加：

```text
schema_version
prompt_id
prompt_version
agent_name
agent_run_id
evidence_refs JSON
```

涉及表：

```text
jd_analyses
resume_profiles
gap_analyses
interview_plans
interview_evaluations
project_candidate_profiles
resume_authenticity_reports
resume_rewrite_results
```

### 12.3 Evidence 可以先不落库

第一步可以先不新增 `evidence_items` 表，而是在 Agent 执行时动态构造 EvidencePacket：

```text
InterviewMessage -> interview_answer evidence
ResumeProfile.projects / skills -> resume_claim evidence
JDAnalysis.required_skills -> jd_requirement evidence
InterviewPlanExecution.state.sections[].evidence -> execution_probe evidence
```

当 EvidencePacket 结构稳定后，再考虑落库。

## 13. 推荐实施路线

### Step 1：写清 Prompt Contract

目标：

```text
为现有 prompt 建立统一 manifest。
明确每个 prompt 的 input_schema、output_schema、owner_agent、version。
```

交付：

```text
docs 或 backend/app/prompts/manifest.json
每个 prompt 的 schema 草案
Prompt 命名和版本规范
```

收益：

```text
先止住 prompt 爆炸。
后续新增 prompt 必须按规范登记。
```

### Step 2：定义 Agent Contract

目标：

```text
不急着重写所有服务，先定义 BaseAgent 接口和 AgentRun 结构。
```

交付：

```text
BaseAgent 设计文档
AgentInput / AgentOutput 结构
AgentRun 记录结构
已有 Agent 职责表
```

收益：

```text
后续逐个迁移 Agent，不需要一次性推翻现有代码。
```

### Step 3：统一 Summary / Profile / Evaluation 边界

目标：

```text
把 summary_type = candidate_profile 的概念从“画像”修正为“session memory”。
明确 ResumeProfile、SessionCandidateProfile、ProjectCandidateProfile 的层级。
```

交付：

```text
概念命名规范
上下游使用规则
Evaluation 输入规则
```

收益：

```text
避免后续 Agent 混用记忆、能力模型和评价结论。
```

### Step 4：引入 EvidencePacket

目标：

```text
先动态构造证据包，不急着落库。
让 Evaluation、ProjectProfile、ResumeAuthenticity、ResumeRewrite 优先使用 EvidencePacket。
```

交付：

```text
EvidenceItem schema
EvidencePacket schema
EvidenceBuilder 设计
各 Agent evidence_policy
```

收益：

```text
所有关键输出开始能追踪依据。
ResumeRewrite 不再只靠 summary + resume + JD 自由发挥。
```

### Step 5：ProjectCandidateProfile 版本化

目标：

```text
让项目级画像从“最新快照”升级为“可追踪版本链”。
```

交付：

```text
profile version schema
profile stale rules
profile change summary
profile evidence_refs
```

收益：

```text
支持多次面试对比、简历修改后重算、学习计划和岗位推荐。
```

### Step 6：逐步迁移 Agent

推荐迁移顺序：

```text
P0:
  ResumeRewriteAgent
  ResumeAuthenticityAgent

P1:
  ProjectProfileAgent
  EvaluationAgent

P2:
  InterviewExecutorAgent
  TopicJudgeAgent

P3:
  JDAnalysisAgent
  ResumeAnalysisAgent
  GapAnalysisAgent
  InterviewPlanAgent
```

原因：

1. ResumeRewrite 风险最高，最需要证据约束。
2. ResumeAuthenticity 是证据系统最直接的消费者。
3. ProjectProfile 是后续能力模型底座。
4. Evaluation 对证据引用质量要求高。
5. 前置分析类 Agent 相对简单，可以后迁移。

## 14. Phase 3 MVP 范围

建议 Phase 3 MVP 不做大改，只完成以下内容：

```text
1. 建立 Prompt Contract 文档和 manifest 草案。
2. 建立 Agent Contract 文档。
3. 定义 Summary / Profile / Evaluation / Evidence 边界。
4. 定义 EvidenceItem / EvidencePacket schema。
5. 定义 ProjectCandidateProfile 版本化 schema 和 stale 规则。
6. 选择 ResumeRewriteAgent 作为第一个证据化 Agent 的迁移目标。
```

Phase 3 MVP 的验收标准：

```text
新增 Agent 时，必须能回答：
  输入 schema 是什么？
  输出 schema 是什么？
  用哪个 prompt 版本？
  需要哪些 context？
  需要哪些 evidence？
  输出如何引用 evidence？

简历重写时，必须能回答：
  哪些内容来自简历声明？
  哪些内容被面试证据支持？
  哪些内容证据不足，只能作为补充建议？
  使用了哪版 ProjectCandidateProfile？
```

## 15. 推荐最终架构

Phase 3 完成后，系统核心链路应从：

```text
Service
  -> load_prompt
  -> LLMService.generate_xxx
  -> parse JSON
  -> save result
```

升级为：

```text
Service
  -> Agent.run(input)
      -> validate input
      -> ContextBuilder build context
      -> EvidenceBuilder build evidence packet
      -> PromptRegistry resolve prompt version
      -> render prompt
      -> LLMClient call model
      -> parse and validate output
      -> record AgentRun
      -> save business artifact
  -> return result
```

其中：

```text
PromptRegistry
  管理 prompt 元数据和版本。

ContextBuilder
  负责装配背景信息。

EvidenceBuilder
  负责装配可引用证据。

BaseAgent
  负责统一执行生命周期。

AgentRun
  负责追踪每次执行。

ProfileVersion
  负责候选人画像演进。
```

## 16. 最终建议

第三阶段不要急着继续加 Agent。当前更重要的是把系统从“能跑”推进到“可治理”。

推荐优先级：

```text
P0:
  Prompt Contract
  Summary / Profile / Evaluation / Evidence 边界
  EvidencePacket schema

P1:
  Agent Contract
  AgentRun 记录设计
  ResumeRewriteAgent 证据化

P2:
  ProjectCandidateProfile 版本化
  ResumeAuthenticityAgent 证据化
  EvaluationAgent 证据化

P3:
  全量 Agent 迁移
  PromptRegistry 工具化
  Evidence 落库
```

这样 Phase 3 的价值会非常明确：

```text
不是增加更多功能，
而是让之后每一个功能都不会继续放大混乱。
```

当 Prompt、Agent、Profile、Evidence 四个底座稳定后，后续再做学习计划、岗位推荐、多轮训练复盘、题库 RAG，都会顺很多。

# Phase 2 优化点详细设计

## 1. 背景

当前 Phase 2 已经补上了求职准备项目、JD 解析、简历解析、Gap 分析、InterviewPlan 和基于项目启动面试的基础链路。

但从产品目标看，当前实现仍然更接近“能基于计划开场的问答系统”，还没有完全变成“计划驱动的面试 Agent”。你提出的 4 类问题都是真实存在的优化点：

1. 面试计划只在第一题时被强使用，后续追问仍主要依赖 followup prompt。
2. 系统没有判断当前话题是否应该结束，可能围绕一个点无限深挖。
3. 缺少跨功能复用的面试者画像，后续简历优化、学习规划、岗位推荐都会缺少统一候选人上下文。
4. 缺少简历重写 Agent 和简历真实性验证 Agent。

因此 Phase 2 的下一轮优化目标应该是：

```text
从“InterviewPlan 生成器”
升级为
“InterviewPlan 执行器 + 候选人画像沉淀 + 简历验证与优化”
```

## 2. 当前问题分析

### 2.1 InterviewPlan 没有贯穿整个面试过程

当前逻辑：

```text
start_with_project()
  优先取 InterviewPlan.sections[0].seed_questions[0] 作为第一题

chat()
  保存用户回答
  读取 CandidateProfile + ConversationSummary + recent_history
  调用 generate_followup()
```

虽然 `chat()` 会把 plan_context 传给 LLM，但这只是“把计划作为上下文提示”，并没有真正执行计划。

缺少的能力：

1. 当前处于哪个 section。
2. 当前 section 已问了几轮。
3. 当前 section 的目标是否已经完成。
4. 是否应该进入下一个 section。
5. 是否已经覆盖 InterviewPlan 中要求验证的 probe_points。
6. 每轮追问应服务于哪个计划目标。

所以当前是：

```text
计划只参与第一题 + 后续作为弱上下文
```

目标应该是：

```text
每一轮追问都由 InterviewPlanExecutionState 驱动
```

### 2.2 没有话题收束机制

当前追问逻辑默认会继续深挖最新回答。

风险：

1. 候选人一直答同一个项目，模型可能持续追问同一技术点。
2. 即使当前 section 已经达到目标，也不会主动切换。
3. 面试计划中的其他 section 无法保证被覆盖。
4. 最终评价会偏向被深挖的话题，缺少完整证据。

需要新增：

```text
TopicState
TopicCompletionJudge
SectionTransitionPolicy
```

### 2.3 面试者画像不应只依赖 interview_summaries

当前已有：

```text
ResumeProfile
  来自简历解析，面试前静态画像。

CandidateProfile
  当前存在于 interview_summaries，来自面试过程中的滚动总结。
```

但后续完整产品需要一个更稳定、更可复用的候选人画像：

```text
面试
简历优化
学习规划
岗位推荐
多次模拟面试对比
```

这些功能都需要同一个候选人画像，而不是只在某个 interview_session 下有一份 summary。

因此需要引入项目级候选人画像：

```text
ProjectCandidateProfile
```

它应该融合：

```text
ResumeProfile
面试过程 CandidateProfile
GapAnalysis
Evaluation
简历真实性验证结果
```

### 2.4 缺少简历真实性验证

简历优化不能只把文字写漂亮。更重要的是判断：

```text
简历写的内容，候选人是否真的讲得出来？
简历里的项目贡献是否经过面试验证？
哪些内容可信，哪些内容存疑？
哪些内容建议保留、弱化、删除或补证据？
```

如果没有真实性验证，简历重写 Agent 可能会把不真实或证据不足的内容写得更夸张，反而增加面试风险。

### 2.5 缺少简历重写 Agent

当前只做了解析和 Gap，不会输出可直接使用的简历优化结果。

后续需要：

```text
ResumeRewriteAgent
```

但它必须依赖：

```text
ResumeProfile
JDAnalysis，可选
GapAnalysis，可选
InterviewEvidence
ResumeAuthenticityReport
CandidateProfile
```

否则只能做泛泛改写。

## 3. 优化目标

本轮优化建议拆成 5 个能力模块：

```text
1. InterviewPlanExecution
   让面试计划贯穿整个面试过程。

2. TopicCompletionJudge
   判断当前话题是否应该继续深挖或切换。

3. ProjectCandidateProfile
   形成项目级、跨功能复用的候选人画像。

4. ResumeAuthenticityAgent
   判断简历内容是否被面试证据支撑。

5. ResumeRewriteAgent
   基于 JD、简历、面试证据和真实性报告进行简历优化重写。
```

## 4. 推荐整体架构

### 4.1 优化后的主流程

```text
创建 PreparationProject
  ↓
上传 JD，可选
  ↓
上传简历，可选
  ↓
解析 JD / 简历
  ↓
生成 GapAnalysis，可选
  ↓
生成 InterviewPlan
  ↓
开始面试
  ↓
初始化 InterviewPlanExecution
  ↓
每轮 chat:
    保存用户回答
    更新当前 section 证据
    判断当前话题是否完成
    判断是否切换 section
    基于当前 section 目标生成追问
    更新 ConversationSummary / CandidateProfile
  ↓
结束面试
  ↓
生成 Evaluation
  ↓
生成 / 更新 ProjectCandidateProfile
  ↓
如果有简历:
    生成 ResumeAuthenticityReport
  ↓
如果用户请求简历优化:
    生成 ResumeRewriteResult
```

### 4.2 模块关系

```text
InterviewPlan
  ↓
InterviewPlanExecution
  ↓
TopicCompletionJudge
  ↓
InterviewService.chat()
  ↓
InterviewEvidence
  ↓
ProjectCandidateProfile
  ↓
ResumeAuthenticityReport
  ↓
ResumeRewriteResult
```

## 5. InterviewPlanExecution 设计

### 5.1 为什么需要执行状态

InterviewPlan 是“计划”，但不是“执行记录”。

例如计划中有：

```json
{
  "sections": [
    {
      "section_key": "project_depth",
      "target_rounds": 4,
      "goals": ["验证项目真实性", "确认个人贡献"],
      "probe_points": ["项目背景", "技术方案", "上线结果"]
    },
    {
      "section_key": "technical_depth",
      "target_rounds": 3,
      "goals": ["验证底层理解"],
      "probe_points": ["底层原理", "边界条件"]
    }
  ]
}
```

面试过程中必须记录：

```text
当前 section 是哪个？
这个 section 已经问了几轮？
哪些 probe_points 已覆盖？
哪些证据已经采集？
当前 section 是否完成？
下一轮应该追问还是切换？
```

这些不应该写回 InterviewPlan，而应该写入执行状态。

### 5.2 新增表：interview_plan_executions

建议新增：

```sql
CREATE TABLE IF NOT EXISTS interview_plan_executions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id BIGINT NOT NULL,
  interview_plan_id BIGINT NOT NULL,
  current_section_key VARCHAR(80) NULL,
  current_section_index INT NOT NULL DEFAULT 0,
  current_section_round_no INT NOT NULL DEFAULT 0,
  total_completed_round_no INT NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  state JSON NOT NULL,
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_plan_executions_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_plan_executions_plan
    FOREIGN KEY (interview_plan_id) REFERENCES interview_plans(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 5.3 state JSON 建议结构

```json
{
  "sections": [
    {
      "section_key": "project_depth",
      "status": "active",
      "target_rounds": 4,
      "completed_rounds": 2,
      "covered_probe_points": ["项目背景", "个人职责"],
      "uncovered_probe_points": ["上线结果"],
      "evidence": [
        {
          "round_no": 1,
          "probe_point": "项目背景",
          "evidence_summary": "候选人介绍了订单履约系统背景",
          "confidence": "medium"
        }
      ],
      "completion_reason": ""
    }
  ],
  "current_topic": {
    "topic_key": "message_reliability",
    "topic_summary": "消息可靠性设计",
    "started_round_no": 2,
    "depth": 2,
    "status": "active"
  },
  "next_action": {
    "type": "continue_current_section",
    "reason": "还缺少上线结果和异常场景证据"
  }
}
```

### 5.4 下一轮动作类型

建议定义：

```text
continue_current_topic
  继续深挖当前话题。

switch_topic_in_section
  当前话题够了，但当前 section 还有其他 probe point。

move_next_section
  当前 section 已完成，切到下一个 section。

wrap_up_interview
  所有 section 基本完成，可以提示用户结束或进入总结问题。
```

## 6. TopicCompletionJudge 设计

### 6.1 目标

判断当前话题是否应该继续深挖。

它不是最终评价，而是一个轻量的“面试控制器”。

### 6.2 输入

```text
当前 InterviewPlan section
当前 topic 状态
最近 2-4 轮对话
CandidateProfile
ConversationSummary
当前 section 已覆盖证据
```

### 6.3 输出

建议返回 JSON：

```json
{
  "topic_status": "continue|complete|stuck|insufficient",
  "should_continue_topic": true,
  "should_switch_section": false,
  "covered_probe_points": ["技术方案"],
  "missing_probe_points": ["上线效果", "失败场景"],
  "next_action": "continue_current_topic",
  "next_question_intent": "追问失败场景下的补偿机制",
  "reason": "候选人讲清了正常链路，但缺少异常场景证据"
}
```

### 6.4 判断规则

可以先用规则 + LLM 混合。

规则层：

```text
如果当前 topic 深挖轮数 >= 3，倾向切换。
如果当前 section completed_rounds >= target_rounds，倾向切换 section。
如果回答明显空泛，允许继续追问 1 轮要求举例。
如果连续 2 轮仍无有效信息，标记 stuck 并切换。
```

LLM 层：

```text
判断是否已覆盖当前 probe point。
判断回答是否提供具体证据。
判断下一问应该继续追问还是切换。
```

### 6.5 为什么不能只靠规则

因为“是否讲清楚”不是简单轮数能判断。

例如：

```text
一轮回答可能已经非常完整，可以切换。
三轮回答可能都很空，继续追问也没意义。
```

所以建议：

```text
规则控制上限
LLM 判断质量
```

## 7. 面试追问生成改造

### 7.1 当前追问输入

当前大致是：

```text
interviewer prompt
CandidateProfile
ConversationSummary
InterviewPlan context
recent history
followup prompt
```

### 7.2 优化后追问输入

建议改为：

```text
interviewer prompt
InterviewPlan 当前 section
InterviewPlanExecution 当前状态
TopicCompletionJudge 输出
CandidateProfile
ConversationSummary
recent history
followup prompt
```

### 7.3 followup prompt 应该变化

当前 followup prompt 主要要求“基于候选人上一轮回答追问”。

优化后应该改成：

```text
请根据 next_action 生成下一问：

continue_current_topic:
  基于 next_question_intent 继续深挖。

switch_topic_in_section:
  切到当前 section 中尚未覆盖的 probe point。

move_next_section:
  自然过渡到下一个 section 的 seed question 或 probe point。

wrap_up_interview:
  生成收尾问题或提示可以结束面试。
```

这样追问才会被计划状态驱动。

## 8. ProjectCandidateProfile 设计

### 8.1 为什么需要项目级画像

当前 `ResumeProfile` 和 `CandidateProfile` 各自解决一部分问题：

```text
ResumeProfile:
  简历解析出的静态画像。

CandidateProfile:
  面试过程中总结出的动态画像。
```

但后续功能需要统一画像：

```text
简历优化
学习规划
岗位推荐
多次面试表现对比
```

所以建议新增项目级画像：

```text
ProjectCandidateProfile
```

### 8.2 新增表：project_candidate_profiles

```sql
CREATE TABLE IF NOT EXISTS project_candidate_profiles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  source_session_id BIGINT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_project_candidate_profiles_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_project_candidate_profiles_session
    FOREIGN KEY (source_session_id) REFERENCES interview_sessions(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 8.3 content JSON 建议结构

```json
{
  "basic_profile": {
    "target_role": "",
    "years_of_experience": "",
    "main_domains": [],
    "main_tech_stack": []
  },
  "project_experience": [
    {
      "project_name": "",
      "verified_level": "high|medium|low|unknown",
      "candidate_role": "",
      "verified_contributions": [],
      "unverified_claims": [],
      "evidence_rounds": []
    }
  ],
  "capability_profile": {
    "technical_depth": {
      "level": "high|medium|low|unknown",
      "evidence": []
    },
    "system_design": {
      "level": "high|medium|low|unknown",
      "evidence": []
    },
    "troubleshooting": {
      "level": "high|medium|low|unknown",
      "evidence": []
    },
    "communication": {
      "level": "high|medium|low|unknown",
      "evidence": []
    }
  },
  "risk_profile": [
    {
      "risk": "",
      "severity": "high|medium|low",
      "evidence": ""
    }
  ],
  "learning_needs": [],
  "resume_optimization_focus": []
}
```

### 8.4 更新时机

建议：

```text
面试结束时必须生成 / 更新一次。
长面试中每 10 轮可选更新一次。
用户重新生成简历优化前，如果画像过旧，先更新画像。
```

## 9. ResumeAuthenticityAgent 设计

### 9.1 目标

判断简历中的声明是否被面试证据支撑。

它不是判断候选人是否“撒谎”，而是判断：

```text
简历内容是否有足够证据支撑？
面试中是否能讲清楚？
是否存在夸大、模糊、证据不足的点？
```

### 9.2 输入

```text
ResumeDocument 原文
ResumeProfile
Interview transcript
InterviewPlanExecution evidence
Evaluation
ProjectCandidateProfile
JDAnalysis，可选
GapAnalysis，可选
```

### 9.3 输出：ResumeAuthenticityReport

新增表：

```sql
CREATE TABLE IF NOT EXISTS resume_authenticity_reports (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  resume_id BIGINT NOT NULL,
  session_id BIGINT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_resume_auth_reports_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_resume_auth_reports_resume
    FOREIGN KEY (resume_id) REFERENCES resume_documents(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_resume_auth_reports_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

content 示例：

```json
{
  "overall_authenticity": "medium",
  "claim_checks": [
    {
      "resume_claim": "负责订单系统高并发架构设计",
      "status": "partially_supported",
      "evidence": "候选人能讲清缓存和 MQ，但缺少 QPS、压测和容量规划细节",
      "risk_level": "medium",
      "suggestion": "改成参与订单链路性能优化，并补充可量化指标"
    }
  ],
  "unsupported_claims": [],
  "strongly_supported_claims": [],
  "rewrite_constraints": [
    "不要强化高并发架构主导权",
    "可以突出消息可靠性改造经验"
  ]
}
```

### 9.4 使用场景

```text
面试结束后生成真实性报告。
简历重写前读取真实性报告。
评价报告中引用真实性结论。
岗位推荐时避开证据不足的方向。
```

## 10. ResumeRewriteAgent 设计

### 10.1 目标

基于证据优化简历，而不是泛泛润色。

它应该做到：

```text
更贴合目标 JD
突出真实强项
弱化证据不足的夸大表达
补充建议用户提供的数据点
生成可复制到简历里的项目描述
```

### 10.2 输入

```text
ResumeDocument 原文
ResumeProfile
JDAnalysis，可选
GapAnalysis，可选
ProjectCandidateProfile
ResumeAuthenticityReport
Evaluation
用户选择的优化目标：
  jd_targeted
  general_backend
  project_depth
  ats_keywords
```

### 10.3 输出：ResumeRewriteResult

新增表：

```sql
CREATE TABLE IF NOT EXISTS resume_rewrite_results (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  resume_id BIGINT NOT NULL,
  authenticity_report_id BIGINT NULL,
  rewrite_mode VARCHAR(30) NOT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_resume_rewrite_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_resume_rewrite_resume
    FOREIGN KEY (resume_id) REFERENCES resume_documents(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_resume_rewrite_auth_report
    FOREIGN KEY (authenticity_report_id) REFERENCES resume_authenticity_reports(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

content 示例：

```json
{
  "rewrite_mode": "jd_targeted",
  "summary": "本次优化重点突出 Java 后端、消息可靠性、订单链路经验",
  "rewritten_sections": [
    {
      "section": "project",
      "original": "负责订单系统开发...",
      "rewritten": "参与订单履约链路后端开发，负责消息可靠性改造...",
      "reason": "原描述过泛，改写后突出个人贡献和可验证技术点",
      "evidence_basis": ["面试第 2-4 轮消息可靠性回答"]
    }
  ],
  "missing_info_to_collect": [
    "订单峰值 QPS",
    "消息堆积最大量",
    "改造前后失败率变化"
  ],
  "risk_warnings": [
    "不要写主导高并发架构，当前面试证据不足"
  ]
}
```

### 10.4 简历重写原则

必须遵守：

```text
不能编造经历。
不能把未验证内容写成强事实。
可以把模糊经历改写得更清晰。
可以提示用户补充指标。
可以根据 JD 调整表达顺序和关键词。
```

## 11. 推荐服务与 Agent 划分

第一版不一定要引入复杂多 Agent 框架，可以先按 Service + Prompt 落地。

建议新增：

```text
InterviewExecutionService
  管理 InterviewPlanExecution，判断当前 section 和下一步动作。

TopicJudgeService
  调用 TopicCompletionJudge prompt，判断是否继续深挖。

ProjectCandidateProfileService
  生成和更新项目级候选人画像。

ResumeAuthenticityService
  生成简历真实性报告。

ResumeRewriteService
  生成简历优化重写结果。
```

对应 prompt：

```text
interview_execution_judge.txt
topic_completion_judge.txt
project_candidate_profile.txt
resume_authenticity.txt
resume_rewrite.txt
```

后续如果引入 Agent 框架，可以映射为：

```text
InterviewExecutorAgent
ProfileAgent
ResumeVerifierAgent
ResumeRewriteAgent
CoachAgent
```

## 12. API 设计建议

### 12.1 查询面试执行状态

```text
GET /api/interview/{sessionId}/execution
```

返回：

```json
{
  "currentSectionKey": "project_depth",
  "currentSectionRoundNo": 2,
  "nextAction": "continue_current_topic",
  "coveredProbePoints": [],
  "missingProbePoints": []
}
```

### 12.2 手动生成项目级候选人画像

```text
POST /api/preparation/projects/{projectId}/candidate-profile/generate
```

### 12.3 生成简历真实性报告

```text
POST /api/preparation/projects/{projectId}/resume/authenticity
```

### 12.4 生成简历重写结果

```text
POST /api/preparation/projects/{projectId}/resume/rewrite
```

Request:

```json
{
  "rewriteMode": "jd_targeted"
}
```

## 13. 面试 chat 改造后的链路

当前：

```text
user answer
  ↓
保存 answer
  ↓
summary refresh
  ↓
generate_followup
  ↓
保存 followup
```

优化后：

```text
user answer
  ↓
保存 answer
  ↓
读取 InterviewPlanExecution
  ↓
读取当前 section
  ↓
TopicCompletionJudge 判断当前话题状态
  ↓
更新 execution state
  ↓
根据 next_action 构造 followup prompt
  ↓
generate_followup
  ↓
保存 followup
  ↓
必要时更新 CandidateProfile / ConversationSummary
```

## 14. 分阶段实施建议

### Step 1：让 InterviewPlan 真正驱动面试

实现：

```text
interview_plan_executions 表
InterviewExecutionService
start_with_project 初始化 execution
chat 中读取 execution
根据 current_section 注入 prompt
按 target_rounds 简单切 section
```

先不用 LLM 判断话题结束，只用规则：

```text
current_section_round_no >= target_rounds
  -> move_next_section
```

### Step 2：增加 TopicCompletionJudge

实现：

```text
topic_completion_judge.txt
TopicJudgeService
chat 中每轮调用 judge
根据 judge.next_action 控制追问
```

先限制：

```text
单个 topic 最多深挖 3 轮
连续 2 轮回答空泛则切换
```

### Step 3：新增 ProjectCandidateProfile

实现：

```text
project_candidate_profiles 表
project_candidate_profile.txt
面试结束时生成项目级画像
overview 中返回 latest ProjectCandidateProfile
```

### Step 4：新增 ResumeAuthenticityReport

实现：

```text
resume_authenticity_reports 表
resume_authenticity.txt
面试结束后或手动接口生成真实性报告
```

前置条件：

```text
必须有 ResumeDocument / ResumeProfile
最好有至少一场 InterviewSession
```

### Step 5：新增 ResumeRewriteResult

实现：

```text
resume_rewrite_results 表
resume_rewrite.txt
POST /resume/rewrite
```

前置条件：

```text
ResumeDocument 必须存在
ResumeProfile 必须存在
ResumeAuthenticityReport 推荐存在
```

## 15. 优先级建议

推荐优先级：

```text
P0:
  InterviewPlanExecution
  简单 section 切换规则

P1:
  TopicCompletionJudge
  ProjectCandidateProfile

P2:
  ResumeAuthenticityAgent

P3:
  ResumeRewriteAgent
```

原因：

1. 如果 InterviewPlan 不能贯穿面试，后续画像和真实性验证的证据会不完整。
2. 如果没有话题收束，面试覆盖面会失控。
3. 如果没有项目级画像，简历优化和学习计划缺少统一基础。
4. 简历重写必须排在真实性验证之后，否则容易生成“漂亮但危险”的简历。

## 16. 最终推荐方案

你的 4 个问题都应该优化，但不建议一次性全部实现。

推荐下一步先做：

```text
InterviewPlanExecution + TopicCompletionJudge
```

它们是面试 Agent 的控制层，能解决：

```text
面试计划不贯穿
话题无限深挖
计划 section 覆盖不足
面试证据不完整
```

随后做：

```text
ProjectCandidateProfile
```

它是后续所有求职功能的统一画像底座。

最后再做：

```text
ResumeAuthenticityAgent
ResumeRewriteAgent
```

这样顺序更稳：

```text
先让面试采集到好证据
再沉淀候选人画像
再判断简历真伪
最后做简历重写
```


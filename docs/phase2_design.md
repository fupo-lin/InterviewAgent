# AI 求职陪练平台 Phase 2 详细设计

## 1. 背景与阶段定位

当前系统处在 Phase 1：已经具备一个基础的面试问答 Agent。

Phase 1 的能力边界是：

```text
选择岗位
  ↓
开始模拟面试
  ↓
AI 出第一题
  ↓
候选人回答
  ↓
AI 动态追问
  ↓
记录面试过程
  ↓
生成面试评价
```

也就是说，当前系统更像是一个“面试官问答 Agent”，核心能力是：

1. 出题。
2. 追问。
3. 保存面试记录。
4. 生成评价报告。
5. 通过 CandidateProfile 和 ConversationSummary 支撑较长轮次面试。

但完整的 AI 求职陪练平台目标更大：

```text
上传 JD
  +
上传简历
  ↓
JD 解析
  ↓
简历解析
  ↓
Gap 分析
  ↓
简历优化
  ↓
面试模拟
  ↓
能力评估
  ↓
学习建议
  ↓
岗位推荐
```

Phase 2 不建议一次性做完整闭环。更合理的阶段目标是：在现有面试问答 Agent 前面增加“JD 理解、简历理解、Gap 分析、面试计划”这几层，让面试从“泛岗位追问”升级为“围绕具体 JD 和候选人简历的定制化面试”。

## 2. Phase 2 总目标

Phase 2 的目标是构建一个“求职上下文驱动的定制化面试准备 Agent”。

这里的求职上下文不要求 JD 和简历同时存在。用户可以只提供 JD、只提供简历，也可以同时提供 JD 和简历。系统根据已有输入生成对应的面试计划和追问策略。

核心变化是：

```text
Phase 1:
role_name -> interview chat -> evaluation

Phase 2:
available context -> analysis -> interview plan -> interview chat -> context-aware evaluation
```

Phase 2 完成后，用户应该可以：

1. 创建一个求职准备项目。
2. 上传或粘贴目标 JD，可选。
3. 上传或粘贴候选人简历，可选。
4. 如果有 JD，系统解析 JD，提取岗位要求、技术栈、职责、软技能和隐含要求。
5. 如果有简历，系统解析简历，提取项目经历、技术栈、工作经历、亮点和风险点。
6. 如果 JD 和简历同时存在，系统生成 JD 与简历的匹配分析，也就是 Gap 分析。
7. 系统基于已有上下文生成一份面试计划。
8. 模拟面试根据面试计划推进，而不是只根据最近回答临场发挥。
9. 评价报告能结合已有上下文和面试表现，给出更有针对性的能力结论。

## 2.1 Phase 2 输入模式

Phase 2 必须支持三种输入模式。

### 2.1.1 JD-only 模式

用户只上传 JD，不上传简历。

适用场景：

```text
用户还没有整理简历，但想先针对某个岗位练习。
用户想了解这个岗位大概率会问什么。
用户想用 JD 生成一套面试训练计划。
```

系统流程：

```text
JD 原文
  ↓
JDAnalysis
  ↓
JD-driven InterviewPlan
  ↓
围绕岗位要求进行模拟面试
  ↓
JD-aware Evaluation
```

这个模式下不会生成 GapAnalysis，因为缺少简历侧证据。面试重点是验证候选人是否具备 JD 所要求的能力。

### 2.1.2 Resume-only 模式

用户只上传简历，不上传 JD。

适用场景：

```text
用户暂时没有目标岗位，但想围绕自己的简历做项目深挖。
用户想检查简历中的项目是否经得起追问。
用户想发现简历表达中的风险点和薄弱点。
```

系统流程：

```text
简历原文
  ↓
ResumeProfile
  ↓
Resume-driven InterviewPlan
  ↓
围绕简历项目和技术栈进行模拟面试
  ↓
Resume-aware Evaluation
```

这个模式下也不会生成 GapAnalysis，因为缺少 JD 侧要求。面试重点是验证简历真实性、项目深度、个人贡献和表达质量。

### 2.1.3 JD + Resume 模式

用户同时上传 JD 和简历。

适用场景：

```text
用户正在准备投递某个明确岗位。
用户想知道自己的简历和 JD 是否匹配。
用户想针对 Gap 做面试训练和简历优化。
```

系统流程：

```text
JD 原文 + 简历原文
  ↓
JDAnalysis + ResumeProfile
  ↓
GapAnalysis
  ↓
Gap-driven InterviewPlan
  ↓
围绕 JD 匹配度和简历证据进行模拟面试
  ↓
JD + Resume aware Evaluation
```

这个模式是 Phase 2 的最完整模式。系统不仅追问候选人能力，还会验证简历是否能支撑 JD 要求。

## 3. Phase 2 不做什么

为了避免范围过大，Phase 2 暂时不做以下能力：

1. 不做完整岗位推荐。
2. 不做多 JD 对比。
3. 不做自动投递。
4. 不做复杂简历排版导出。
5. 不做面试题知识库 RAG。
6. 不做多 Agent 编排框架的重构。
7. 不做企业级权限、组织、付费、审计。

这些能力可以放到后续 Phase 3、Phase 4。

Phase 2 的重点不是“更多功能”，而是把面试问答的输入从一个简单的 `role_name` 升级为结构化的求职上下文。这个上下文可以是不完整的：

```text
JobDescription       可选
ResumeProfile        可选
GapAnalysis          仅 JD + 简历同时存在时生成
InterviewPlan
```

## 4. Phase 2 核心业务流程

推荐 Phase 2 主流程如下：

```text
用户创建求职准备项目
  ↓
上传 / 粘贴 JD，可选
  ↓
如果有 JD，系统生成 JDAnalysis
  ↓
上传 / 粘贴简历，可选
  ↓
如果有简历，系统生成 ResumeProfile
  ↓
如果 JD 和简历都存在，系统生成 GapAnalysis
  ↓
系统基于已有上下文生成 InterviewPlan
  ↓
用户开始模拟面试
  ↓
Interview Agent 按 InterviewPlan 出题和追问
  ↓
记录面试过程
  ↓
生成 context-aware Evaluation
  ↓
输出学习建议和简历优化建议草稿
```

其中 Phase 2 的最小可用闭环是：

```text
至少上传 JD 或简历中的一个
  ↓
解析已有输入
  ↓
生成面试计划
  ↓
按计划模拟面试
  ↓
基于已有上下文的评价报告
```

## 5. 核心概念模型

### 5.1 PreparationProject

`PreparationProject` 是 Phase 2 建议新增的顶层业务对象。

这里的 `Project` 指的是“一次求职准备任务”或“一次训练工作台”，不是简历里写的项目经历。

例如：

```text
用户准备投递一个 Java 后端高级工程师岗位
```

一个 PreparationProject 下可以包含：

1. 一个目标 JD，可选。
2. 一份候选人简历，可选。
3. 一份 JD 解析结果，如果用户提供了 JD。
4. 一份简历解析结果，如果用户提供了简历。
5. 一份 Gap 分析，仅当 JD 和简历都存在时生成。
6. 一份面试计划，基于当前已有上下文生成。
7. 多场模拟面试 session。
8. 多份评价报告。

为什么需要项目层，而不是直接把 JD 和 resume 放在 interview_sessions 上？

原因是：

1. 同一个 JD、同一份简历，或者同一个 JD + 简历组合，都可能进行多次模拟面试。
2. 用户可能先分析 JD 或简历，不立刻开始面试。
3. 后续简历优化、学习建议、岗位推荐都应该挂在求职准备项目下。
4. 面试 session 只是项目中的一个执行环节。

为了避免和“简历里的项目经历”混淆，代码里也可以考虑使用更明确的命名：

```text
PreparationWorkspace
ApplicationProject
JobPreparation
```

如果继续使用 `PreparationProject`，文档和代码注释里要明确：它不是 resume project，而是 job preparation project。

### 5.2 JobDescription

`JobDescription` 保存用户上传或粘贴的原始 JD。

它的职责是保存原文和基础元信息，不负责复杂分析。

建议字段：

```text
id
project_id
title
company_name
source_url
raw_content
status
create_time
update_time
```

### 5.3 JDAnalysis

`JDAnalysis` 保存 LLM 对 JD 的结构化理解结果。

它不是原始 JD，而是面向后续 Gap、面试计划和评价使用的“岗位画像”。

建议结构：

```json
{
  "job_title": "Java 后端开发工程师",
  "seniority": "中高级",
  "core_responsibilities": [
    "负责核心业务系统后端开发",
    "参与高并发服务架构设计",
    "负责系统性能优化和稳定性建设"
  ],
  "required_skills": [
    {
      "name": "Java",
      "importance": "high",
      "evidence": "熟悉 Java 基础、多线程、JVM"
    },
    {
      "name": "Spring Boot",
      "importance": "high",
      "evidence": "熟悉 Spring Boot / Spring Cloud"
    }
  ],
  "preferred_skills": [
    "Kubernetes",
    "DDD",
    "消息队列治理"
  ],
  "domain_knowledge": [
    "电商交易",
    "支付",
    "供应链"
  ],
  "soft_skills": [
    "跨团队沟通",
    "项目推动",
    "问题定位"
  ],
  "hidden_requirements": [
    "需要有线上稳定性经验",
    "需要能独立负责模块设计"
  ],
  "interview_focus": [
    "项目复杂度",
    "高并发经验",
    "问题排查能力",
    "架构取舍能力"
  ],
  "risk_keywords": [
    "抗压",
    "快速迭代",
    "稳定性"
  ]
}
```

### 5.4 ResumeDocument

`ResumeDocument` 保存用户上传或粘贴的简历原文。

Phase 2 可以先支持纯文本输入，PDF / DOCX 解析可以后置。

它的职责是保存“用户原始输入”，不要在这张表里直接塞 LLM 总结后的结构化画像。

保留原始简历有几个好处：

1. 可以重新解析。Prompt 或模型升级后，可以基于同一份原文重新生成 ResumeProfile。
2. 可以调试。ResumeProfile 出错时，能回看原文判断是简历表达问题还是模型解析问题。
3. 可以做版本管理。用户修改简历后，可以新增一份 ResumeDocument，而不是覆盖历史。
4. 可以支持不同解析产物。同一份简历后续可能生成 ResumeProfile、ResumeOptimization、KeywordAnalysis 等多个结果。

建议字段：

```text
id
project_id
file_name
file_type
raw_content
status
create_time
update_time
```

### 5.5 ResumeProfile

`ResumeProfile` 保存 LLM 对候选人简历的结构化理解结果。

它的职责是保存“模型从简历中提取出的候选人画像”，供 GapAnalysis、InterviewPlan、追问和评价使用。

它和当前面试中滚动生成的 `candidate_profile` 不同：

```text
ResumeProfile:
来自用户上传简历，是面试前的候选人静态画像。

CandidateProfile:
来自模拟面试过程，是根据候选人真实回答逐步沉淀的动态画像。
```

`resume_documents` 和 `resume_profiles` 看起来都和简历有关，但职责不重复：

```text
resume_documents
  保存原始简历。它是输入、证据、可重新解析的源数据。

resume_profiles
  保存结构化解析结果。它是 LLM 产物，面向后续业务流程使用。
```

第一版如果想极简，也可以只建 `resume_documents`，把解析 JSON 放在同表的 `profile_content` 字段里。但不推荐，因为后续会遇到这些问题：

1. 原文和解析产物生命周期不同。用户改原文、模型重跑、解析失败都不好管理。
2. 无法保存多次解析结果。Prompt 变更后很难对比新旧解析质量。
3. 表职责会变混。后续简历优化、关键词分析、岗位匹配结果都可能继续往一张表里塞。
4. 调试不方便。原始输入和模型产物混在一起，排查链路会越来越乱。

所以 Phase 2 推荐保留两张表：

```text
ResumeDocument  原始简历
ResumeProfile   简历解析画像
```

建议结构：

```json
{
  "candidate_name": "可选",
  "target_role": "Java 后端开发",
  "years_of_experience": "3-5 年",
  "education": [
    {
      "school": "某大学",
      "degree": "本科",
      "major": "计算机科学与技术"
    }
  ],
  "work_experiences": [
    {
      "company": "某科技公司",
      "role": "后端开发工程师",
      "duration": "2022-2025",
      "responsibilities": [
        "负责订单系统开发",
        "参与消息队列治理"
      ]
    }
  ],
  "projects": [
    {
      "name": "订单履约系统",
      "background": "支撑电商订单履约链路",
      "candidate_role": "核心开发",
      "tech_stack": ["Java", "Spring Boot", "MySQL", "Kafka", "Redis"],
      "highlights": [
        "完成异步消息可靠投递改造",
        "将订单处理耗时降低 30%"
      ],
      "weak_evidence": [
        "缺少量化流量规模",
        "缺少故障处理案例"
      ]
    }
  ],
  "skills": [
    {
      "name": "Java",
      "level_inferred": "熟悉",
      "evidence": "多个项目中使用 Java / Spring Boot"
    }
  ],
  "strengths": [
    "有后端项目经验",
    "有消息队列和缓存使用经验"
  ],
  "risks": [
    "架构设计经验表达不足",
    "性能优化指标不够具体"
  ]
}
```

### 5.6 GapAnalysis

`GapAnalysis` 是 Phase 2 的关键中间产物。

但它不是所有模式都必须生成。只有 JDAnalysis 和 ResumeProfile 同时存在时，才生成 GapAnalysis。

它负责回答：

```text
这个候选人的简历和这个 JD 匹配吗？
哪些地方强？
哪些地方弱？
面试应该重点验证什么？
简历应该先补什么？
```

如果用户只上传 JD：

```text
没有简历证据，无法判断候选人与 JD 的匹配度。
系统应该跳过 GapAnalysis，直接基于 JDAnalysis 生成 JD-driven InterviewPlan。
```

如果用户只上传简历：

```text
没有 JD 要求，无法判断岗位匹配差距。
系统应该跳过 GapAnalysis，直接基于 ResumeProfile 生成 Resume-driven InterviewPlan。
```

建议结构：

```json
{
  "overall_match_level": "medium",
  "match_score": 72,
  "matched_points": [
    {
      "jd_requirement": "熟悉 Java / Spring Boot",
      "resume_evidence": "订单履约系统使用 Java、Spring Boot",
      "confidence": "high"
    }
  ],
  "gap_points": [
    {
      "jd_requirement": "具备高并发系统设计经验",
      "resume_current_evidence": "只提到订单系统，没有明确并发量和架构设计细节",
      "gap_level": "high",
      "interview_probe": "需要追问系统峰值 QPS、瓶颈、扩容方案和压测结果",
      "resume_suggestion": "补充系统规模、性能指标、候选人负责的架构设计部分"
    }
  ],
  "risk_points": [
    {
      "risk": "简历中项目贡献描述偏团队化",
      "verification_question": "你个人负责的核心模块是什么，哪些设计是你主导的？"
    }
  ],
  "interview_priorities": [
    "验证项目真实性和个人贡献",
    "验证 Java / Spring 底层能力",
    "验证高并发和稳定性经验",
    "验证问题排查能力"
  ],
  "resume_optimization_priorities": [
    "补充量化指标",
    "突出个人贡献",
    "补充技术选型和取舍"
  ]
}
```

### 5.7 InterviewPlan

`InterviewPlan` 是把 GapAnalysis 转换成面试执行策略。

Phase 1 的面试是动态追问驱动。Phase 2 应该变成：

```text
面试计划驱动 + 动态追问修正
```

建议结构：

```json
{
  "project_id": 1,
  "role_name": "Java 后端开发工程师",
  "total_round_target": 12,
  "sections": [
    {
      "section_key": "project_depth",
      "title": "项目深挖",
      "target_rounds": 4,
      "goals": [
        "验证项目真实性",
        "确认候选人个人贡献",
        "深挖核心模块设计"
      ],
      "seed_questions": [
        "你简历中订单履约系统最核心的技术难点是什么？你个人负责了哪一部分？"
      ],
      "probe_points": [
        "系统规模",
        "核心链路",
        "技术取舍",
        "上线结果"
      ]
    },
    {
      "section_key": "jd_gap_high_concurrency",
      "title": "JD Gap 验证：高并发与稳定性",
      "target_rounds": 3,
      "goals": [
        "验证是否具备 JD 要求的高并发经验",
        "验证线上稳定性治理能力"
      ],
      "seed_questions": [
        "这个系统在流量高峰时的处理链路是怎样的？你们如何发现和解决性能瓶颈？"
      ],
      "probe_points": [
        "QPS",
        "缓存策略",
        "消息堆积",
        "限流降级",
        "压测和监控"
      ]
    }
  ],
  "evaluation_rubric": [
    {
      "dimension": "technical_depth",
      "weight": 30,
      "evidence_to_collect": [
        "底层原理",
        "关键技术细节",
        "边界条件"
      ]
    },
    {
      "dimension": "jd_match",
      "weight": 30,
      "evidence_to_collect": [
        "与 JD 核心要求直接相关的项目证据",
        "Gap 点是否能通过回答补足"
      ]
    }
  ]
}
```

## 6. Phase 2 推荐数据表设计

### 6.1 preparation_projects

```sql
CREATE TABLE IF NOT EXISTS preparation_projects (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_uid VARCHAR(64) NOT NULL UNIQUE,
  user_id BIGINT NULL,
  title VARCHAR(100) NOT NULL,
  target_role VARCHAR(100) NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 6.2 job_descriptions

```sql
CREATE TABLE IF NOT EXISTS job_descriptions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  title VARCHAR(100) NULL,
  company_name VARCHAR(100) NULL,
  source_url VARCHAR(500) NULL,
  raw_content MEDIUMTEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_job_descriptions_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 6.3 jd_analyses

```sql
CREATE TABLE IF NOT EXISTS jd_analyses (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  jd_id BIGINT NOT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_jd_analyses_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_jd_analyses_jd
    FOREIGN KEY (jd_id) REFERENCES job_descriptions(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 6.4 resume_documents

```sql
CREATE TABLE IF NOT EXISTS resume_documents (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  file_name VARCHAR(255) NULL,
  file_type VARCHAR(30) NULL,
  raw_content MEDIUMTEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_resume_documents_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 6.5 resume_profiles

```sql
CREATE TABLE IF NOT EXISTS resume_profiles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  resume_id BIGINT NOT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_resume_profiles_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_resume_profiles_resume
    FOREIGN KEY (resume_id) REFERENCES resume_documents(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 6.6 gap_analyses

```sql
CREATE TABLE IF NOT EXISTS gap_analyses (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  jd_analysis_id BIGINT NOT NULL,
  resume_profile_id BIGINT NOT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_gap_analyses_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_gap_analyses_jd_analysis
    FOREIGN KEY (jd_analysis_id) REFERENCES jd_analyses(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_gap_analyses_resume_profile
    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 6.7 interview_plans

```sql
CREATE TABLE IF NOT EXISTS interview_plans (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  jd_analysis_id BIGINT NULL,
  resume_profile_id BIGINT NULL,
  gap_analysis_id BIGINT NULL,
  plan_mode VARCHAR(30) NOT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_interview_plans_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_interview_plans_jd_analysis
    FOREIGN KEY (jd_analysis_id) REFERENCES jd_analyses(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_interview_plans_resume_profile
    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_interview_plans_gap_analysis
    FOREIGN KEY (gap_analysis_id) REFERENCES gap_analyses(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

`plan_mode` 用于标记面试计划基于什么上下文生成：

```text
jd_only       只基于 JDAnalysis
resume_only   只基于 ResumeProfile
jd_resume     基于 JDAnalysis + ResumeProfile + GapAnalysis
```

这样用户只上传 JD 或只上传简历时，也可以生成 InterviewPlan。

### 6.8 interview_sessions 扩展

现有 `interview_sessions` 建议增加两个可空字段：

```sql
ALTER TABLE interview_sessions
  ADD COLUMN project_id BIGINT NULL AFTER id,
  ADD COLUMN interview_plan_id BIGINT NULL AFTER project_id;
```

这样 Phase 1 的纯岗位面试仍然可用，Phase 2 的 JD + 简历面试可以关联到项目和面试计划。

## 7. 后端模块设计

Phase 2 建议新增以下模块。

### 7.1 API 层

```text
backend/app/api/preparation.py
backend/app/api/jd.py
backend/app/api/resume.py
backend/app/api/gap.py
backend/app/api/interview_plan.py
```

为了初期简单，也可以先集中在一个文件：

```text
backend/app/api/preparation.py
```

推荐接口：

```text
POST /preparation/projects
GET  /preparation/projects/{projectId}

POST /preparation/projects/{projectId}/jd
POST /preparation/projects/{projectId}/jd/analyze

POST /preparation/projects/{projectId}/resume
POST /preparation/projects/{projectId}/resume/analyze

POST /preparation/projects/{projectId}/gap/analyze
POST /preparation/projects/{projectId}/interview-plan/generate

POST /preparation/projects/{projectId}/interview/start
GET  /preparation/projects/{projectId}/overview
```

### 7.2 Service 层

```text
PreparationProjectService
JDAnalysisService
ResumeAnalysisService
GapAnalysisService
InterviewPlanService
```

职责划分：

```text
PreparationProjectService
  创建项目、查询项目总览、管理项目状态

JDAnalysisService
  保存 JD 原文、调用 LLM 解析 JD、保存 JDAnalysis

ResumeAnalysisService
  保存简历原文、调用 LLM 解析简历、保存 ResumeProfile

GapAnalysisService
  仅在 JDAnalysis + ResumeProfile 都存在时生成 GapAnalysis

InterviewPlanService
  根据已有上下文生成 InterviewPlan：
  - jd_only：读取 JDAnalysis
  - resume_only：读取 ResumeProfile
  - jd_resume：读取 JDAnalysis + ResumeProfile + GapAnalysis
```

现有 `InterviewService` 在 Phase 2 中不需要重写，但需要扩展：

```text
start(role_name)
  保持 Phase 1 兼容

start_with_project(project_id, interview_plan_id)
  Phase 2 新增，根据 InterviewPlan 生成第一题
```

### 7.3 Repository 层

建议新增：

```text
PreparationProjectRepository
JobDescriptionRepository
JDAnalysisRepository
ResumeDocumentRepository
ResumeProfileRepository
GapAnalysisRepository
InterviewPlanRepository
```

每个 Repository 第一版只需要：

```text
create
get_by_id
get_latest_by_project_id
list_by_project_id
soft_delete
```

## 8. LLM 能力设计

Phase 2 需要新增 4 类 LLM 能力。

### 8.1 parse_jd

输入：

```text
JD 原文
```

输出：

```text
JDAnalysis JSON
```

目标：

1. 提取岗位名称、级别、职责。
2. 提取必须技能和加分技能。
3. 识别隐含要求。
4. 生成面试关注点。

### 8.2 parse_resume

输入：

```text
简历原文
```

输出：

```text
ResumeProfile JSON
```

目标：

1. 提取候选人经历。
2. 提取项目、技术栈、项目亮点。
3. 识别表达不足和证据不足点。
4. 形成静态候选人画像。

### 8.3 analyze_gap

输入：

```text
JDAnalysis
ResumeProfile
```

输出：

```text
GapAnalysis JSON
```

目标：

1. 判断匹配度。
2. 找到强匹配点。
3. 找到缺口和风险点。
4. 给出面试验证方向。
5. 给出简历优化优先级。

注意：`analyze_gap` 只在 JDAnalysis 和 ResumeProfile 同时存在时调用。

### 8.4 generate_interview_plan

输入：

```text
JD-only:
  JDAnalysis

Resume-only:
  ResumeProfile

JD + Resume:
  JDAnalysis
  ResumeProfile
  GapAnalysis
```

输出：

```text
InterviewPlan JSON
```

目标：

1. 决定面试分段。
2. 生成种子问题。
3. 设定每个分段的追问目标。
4. 设定评价维度和证据采集点。

不同模式下的面试计划重点不同：

```text
jd_only:
  围绕 JD 核心能力要求设计问题，重点验证候选人是否具备岗位要求。

resume_only:
  围绕简历项目经历、技术栈和风险点设计问题，重点验证简历真实性和项目深度。

jd_resume:
  围绕 JD 与简历的匹配和缺口设计问题，重点验证 GapAnalysis 中的风险点。
```

## 9. Prompt 文件设计

建议新增 prompt：

```text
backend/app/prompts/jd_analysis.txt
backend/app/prompts/resume_analysis.txt
backend/app/prompts/gap_analysis.txt
backend/app/prompts/interview_plan.txt
```

后续如果简历优化也进入 Phase 2，可以再新增：

```text
backend/app/prompts/resume_optimization.txt
```

但建议先不要把简历优化作为 Phase 2 第一批实现目标。先把分析链路跑通。

## 10. 面试 Agent 如何使用 InterviewPlan

Phase 2 不建议马上引入复杂 LangGraph。可以先让现有 `InterviewService` 持有计划上下文。

### 10.1 第一题生成

Phase 1：

```text
role_name -> generate_first_question
```

Phase 2：

```text
InterviewPlan.sections[0].seed_questions[0] -> 第一题
```

如果计划中没有 seed question，则退回：

```text
jd_only:
  JDAnalysis.interview_focus -> generate_first_question

resume_only:
  ResumeProfile.projects + ResumeProfile.skills -> generate_first_question

jd_resume:
  JDAnalysis.interview_focus + ResumeProfile.projects + GapAnalysis.gap_points -> generate_first_question
```

### 10.2 追问生成

Phase 2 的 `generate_followup` 上下文建议变为：

```text
system interviewer prompt
system JDAnalysis 摘要，如果存在
system ResumeProfile 摘要，如果存在
system GapAnalysis 摘要，如果存在
system InterviewPlan 当前 section
system CandidateProfile + ConversationSummary
最近 4 轮原文
user followup prompt
```

关键区别是：

```text
动态追问不再只是围绕最近回答，而是要服务于当前 InterviewPlan section 的目标。
```

### 10.3 面试计划进度

需要记录当前面试进行到哪个 section。

第一版有两种方式：

方案 A：存在 `interview_sessions` 上。

```text
current_section_key
current_section_round_no
```

方案 B：存在 summary 或 message metadata 里。

第一版推荐方案 A，更直观。

可选扩展 SQL：

```sql
ALTER TABLE interview_sessions
  ADD COLUMN current_section_key VARCHAR(50) NULL,
  ADD COLUMN current_section_round_no INT NOT NULL DEFAULT 0;
```

但也可以先不加字段，先由 `completed_round_no` 和 InterviewPlan 的 `target_rounds` 推算当前 section。

推荐第一版采用“推算”：

```text
project_depth target_rounds = 4
jd_gap_high_concurrency target_rounds = 3
...

completed_round_no = 1-4      -> project_depth
completed_round_no = 5-7      -> jd_gap_high_concurrency
completed_round_no = 8-10     -> troubleshooting
```

这样数据库改动更少。

## 11. Evaluation 如何升级

Phase 1 的评价主要根据面试记录输出：

```text
strengths
weaknesses
suggestions
technical_ability
project_experience
communication
improvement_suggestions
summary
```

Phase 2 的评价应该升级为 context-aware Evaluation：

```text
面试表现
  +
JD 要求
  +
简历声称
  +
Gap 分析
  +
面试计划证据点
```

建议扩展评价维度：

```json
{
  "summary": "整体评价",
  "jd_match": {
    "level": "medium",
    "evidence": "能覆盖 Java/Spring 项目经验，但高并发指标不足"
  },
  "resume_authenticity": {
    "level": "medium-high",
    "evidence": "能讲清订单履约系统核心链路，但个人贡献边界仍需补充"
  },
  "technical_ability": "...",
  "project_experience": "...",
  "communication": "...",
  "gap_verification": [
    {
      "gap": "高并发经验不足",
      "result": "partially_verified",
      "evidence": "候选人能讲缓存和 MQ，但缺少压测和峰值数据"
    }
  ],
  "resume_optimization_suggestions": [
    "补充订单系统 QPS、数据量、延迟指标",
    "突出本人主导的消息可靠性改造"
  ],
  "learning_suggestions": [
    "系统复习 JVM、线程池和锁优化",
    "准备一个完整的线上故障排查案例"
  ]
}
```

Phase 2 可以先不改 `interview_evaluations` 表结构，只把这些内容放进现有 `summary` 或新增字段中。但更推荐新增一张 `project_evaluations` 表，避免污染面试 session 层评价。

## 12. API 详细设计

### 12.1 创建项目

```text
POST /preparation/projects
```

Request:

```json
{
  "title": "Java 后端 - 某公司订单系统岗位",
  "targetRole": "Java 后端开发工程师"
}
```

Response:

```json
{
  "projectId": "p_abc123",
  "title": "Java 后端 - 某公司订单系统岗位",
  "targetRole": "Java 后端开发工程师"
}
```

### 12.2 上传 JD

```text
POST /preparation/projects/{projectId}/jd
```

Request:

```json
{
  "title": "Java 后端开发工程师",
  "companyName": "某科技公司",
  "sourceUrl": "https://example.com/job/123",
  "content": "岗位职责：..."
}
```

Response:

```json
{
  "jdId": 1,
  "status": "saved"
}
```

### 12.3 解析 JD

```text
POST /preparation/projects/{projectId}/jd/analyze
```

Response:

```json
{
  "analysisId": 1,
  "analysis": {
    "jobTitle": "Java 后端开发工程师",
    "requiredSkills": [],
    "interviewFocus": []
  }
}
```

### 12.4 上传简历

```text
POST /preparation/projects/{projectId}/resume
```

Request:

```json
{
  "fileName": "resume.txt",
  "fileType": "text",
  "content": "个人简历..."
}
```

Response:

```json
{
  "resumeId": 1,
  "status": "saved"
}
```

### 12.5 解析简历

```text
POST /preparation/projects/{projectId}/resume/analyze
```

Response:

```json
{
  "profileId": 1,
  "profile": {
    "projects": [],
    "skills": [],
    "risks": []
  }
}
```

### 12.6 生成 Gap 分析

```text
POST /preparation/projects/{projectId}/gap/analyze
```

前置条件：

```text
必须同时存在 JDAnalysis 和 ResumeProfile。
```

如果只上传了 JD 或只上传了简历，该接口应返回业务错误，例如：

```json
{
  "detail": "Gap analysis requires both JD analysis and resume profile."
}
```

Response:

```json
{
  "gapAnalysisId": 1,
  "gapAnalysis": {
    "overallMatchLevel": "medium",
    "matchScore": 72,
    "matchedPoints": [],
    "gapPoints": [],
    "interviewPriorities": []
  }
}
```

### 12.7 生成面试计划

```text
POST /preparation/projects/{projectId}/interview-plan/generate
```

前置条件：

```text
至少存在 JDAnalysis 或 ResumeProfile 中的一个。
```

生成规则：

```text
只有 JDAnalysis -> planMode = jd_only
只有 ResumeProfile -> planMode = resume_only
两者都有 -> 如果 GapAnalysis 已存在，planMode = jd_resume
两者都有但 GapAnalysis 不存在 -> 可以先自动生成 GapAnalysis，也可以提示用户先生成 GapAnalysis
```

Response:

```json
{
  "interviewPlanId": 1,
  "plan": {
    "planMode": "jd_resume",
    "totalRoundTarget": 12,
    "sections": []
  }
}
```

### 12.8 基于项目开始面试

```text
POST /preparation/projects/{projectId}/interview/start
```

Response:

```json
{
  "sessionId": "abc123",
  "reply": "你简历中订单履约系统最核心的技术难点是什么？你个人负责了哪一部分？"
}
```

### 12.9 项目总览

```text
GET /preparation/projects/{projectId}/overview
```

Response:

```json
{
  "project": {},
  "jd": {},
  "jdAnalysis": {},
  "resume": {},
  "resumeProfile": {},
  "gapAnalysis": {},
  "interviewPlan": {},
  "latestInterviewSession": {}
}
```

## 13. 前端页面设计

Phase 2 前端建议做成一个流程式工作台。

### 13.1 项目创建页

用户输入：

```text
项目名称
目标岗位
```

### 13.2 JD 输入页

支持：

```text
粘贴 JD 文本
填写公司名
填写岗位名
填写来源链接
点击“解析 JD”
```

展示：

```text
岗位职责
必须技能
加分技能
隐含要求
面试关注点
```

### 13.3 简历输入页

Phase 2 第一版支持：

```text
粘贴简历纯文本
点击“解析简历”
```

展示：

```text
工作经历
项目经历
技术栈
亮点
风险点
```

### 13.4 Gap 分析页

展示：

```text
整体匹配度
强匹配点
缺口点
风险点
简历优化优先级
面试验证重点
```

### 13.5 面试计划页

展示：

```text
预计轮数
面试分段
每段目标
种子问题
评价维度
```

用户可以：

```text
接受计划并开始面试
重新生成计划
```

第一版不建议做复杂手动编辑，避免前端复杂度过高。

### 13.6 模拟面试页

复用 Phase 1 的聊天页面，但增加项目上下文：

```text
当前面试 section
本 section 验证目标
当前轮次
```

这些信息可以在开发环境展示，正式用户界面不一定要全部展示。

## 14. 与当前 Phase 1 代码的关系

Phase 2 应该尽量复用当前代码。

当前已有：

```text
InterviewService
InterviewSessionRepository
InterviewMessageRepository
InterviewEvaluationRepository
InterviewSummaryRepository
LLMService
prompts/interviewer.txt
prompts/followup.txt
prompts/evaluation.txt
prompts/candidate_profile.txt
prompts/conversation_summary.txt
```

Phase 2 新增：

```text
PreparationProjectService
JDAnalysisService
ResumeAnalysisService
GapAnalysisService
InterviewPlanService

PreparationProjectRepository
JobDescriptionRepository
JDAnalysisRepository
ResumeDocumentRepository
ResumeProfileRepository
GapAnalysisRepository
InterviewPlanRepository

prompts/jd_analysis.txt
prompts/resume_analysis.txt
prompts/gap_analysis.txt
prompts/interview_plan.txt
```

Phase 2 修改：

```text
InterviewService.start()
  保持不变，用于 Phase 1 兼容。

InterviewService.start_with_project()
  新增，基于 InterviewPlan 开始面试。

LLMService.generate_followup()
  可选增加 JDAnalysis / ResumeProfile / GapAnalysis / InterviewPlan 当前 section 上下文。

LLMService.generate_evaluation()
  可选增加 JDAnalysis / ResumeProfile / GapAnalysis / InterviewPlan 上下文。
```

## 15. 推荐实施顺序

### Step 1：新增项目层和文档输入

目标：

```text
能创建 PreparationProject
能保存 JD 原文
能保存简历原文
```

涉及：

```text
SQL
ORM
Repository
Schema
API
Service
```

暂时不调用 LLM。

### Step 2：实现 JD 解析

目标：

```text
输入 JD 原文
输出 JDAnalysis JSON
保存到数据库
前端能展示解析结果
```

新增：

```text
prompts/jd_analysis.txt
LLMService.generate_jd_analysis()
JDAnalysisService.analyze()
```

### Step 3：实现简历解析

目标：

```text
输入简历原文
输出 ResumeProfile JSON
保存到数据库
前端能展示解析结果
```

新增：

```text
prompts/resume_analysis.txt
LLMService.generate_resume_profile()
ResumeAnalysisService.analyze()
```

### Step 4：实现 Gap 分析

目标：

```text
当 JDAnalysis + ResumeProfile 都存在时
  输出 GapAnalysis JSON

当只存在 JDAnalysis 或 ResumeProfile 时
  跳过 GapAnalysis
```

新增：

```text
prompts/gap_analysis.txt
LLMService.generate_gap_analysis()
GapAnalysisService.analyze()
```

### Step 5：实现 InterviewPlan

目标：

```text
读取已有上下文
输出 InterviewPlan JSON

支持三种 plan_mode：
  jd_only
  resume_only
  jd_resume
```

新增：

```text
prompts/interview_plan.txt
LLMService.generate_interview_plan()
InterviewPlanService.generate()
```

### Step 6：面试接入 InterviewPlan

目标：

```text
用户可以从项目中开始面试
第一题来自 InterviewPlan
追问时携带计划上下文
```

修改：

```text
interview_sessions 增加 project_id / interview_plan_id
InterviewService 新增 start_with_project()
generate_followup 增加计划上下文
```

### Step 7：评价接入已有上下文

目标：

```text
评价报告不只评价候选人表现，还要根据输入模式评价对应目标：JD-only 关注岗位能力匹配，Resume-only 关注简历真实性和项目深度，JD+Resume 关注 JD 匹配度和 Gap 验证。
```

修改：

```text
generate_evaluation 增加 JDAnalysis / ResumeProfile / GapAnalysis / InterviewPlan
evaluation prompt 增加 context-aware 评价维度
```

## 16. MVP 边界建议

Phase 2 MVP 建议做到：

```text
创建项目
粘贴 JD 或简历，至少一个
如果有 JD，解析 JD
如果有简历，解析简历
如果 JD 和简历都有，生成 Gap 分析
基于已有上下文生成面试计划
基于面试计划开始模拟面试
生成结合已有上下文的评价报告
```

暂不做：

```text
PDF / DOCX 解析
简历 Word/PDF 导出
岗位推荐
多 JD 对比
题库 RAG
复杂 Agent 编排
用户权限系统
```

## 17. 后续 Phase 3 展望

Phase 3 可以在 Phase 2 基础上继续扩展：

1. 简历优化 Agent：根据 GapAnalysis 改写简历项目描述。
2. 学习计划 Agent：根据面试评价生成 7 天 / 14 天学习计划。
3. 岗位推荐 Agent：根据 ResumeProfile 匹配岗位类型。
4. 面试题 RAG：基于技术栈和 JD 检索题库。
5. 多轮训练计划：根据多次模拟面试的结果追踪能力变化。
6. 多 Agent 编排：JD Agent、Resume Agent、Gap Agent、Interview Agent、Evaluation Agent、Coach Agent。

## 18. 最终推荐方案

Phase 2 推荐采用以下方案：

1. 新增 `PreparationProject` 作为顶层求职准备项目。这里的 Project 是求职准备任务，不是简历里的项目经历。
2. 用户可以只上传 JD、只上传简历，或者同时上传 JD 和简历。
3. 新增 JD 原文表和 JDAnalysis 表。
4. 新增简历原文表和 ResumeProfile 表。前者保存原始输入，后者保存模型解析结果，职责不同。
5. 新增 GapAnalysis 表，但仅在 JD 和简历同时存在时生成。
6. 新增 InterviewPlan 表，并通过 `plan_mode` 支持 `jd_only`、`resume_only`、`jd_resume` 三种计划模式。
7. 现有 `InterviewSession` 通过 `project_id` 和 `interview_plan_id` 关联 Phase 2 上下文。
8. 面试仍复用当前 InterviewService，不立刻重写成复杂 Agent 框架。
9. 第一题由 InterviewPlan 决定，追问由 InterviewPlan + 最近回答共同决定。
10. 评价报告根据输入模式动态调整：JD-only 看岗位能力匹配，Resume-only 看简历真实性和项目深度，JD+Resume 看 JD 匹配、Gap 验证、简历真实性和学习建议。
11. 简历优化、学习建议、岗位推荐先保留为后续能力，不进入 Phase 2 第一批实现。

这样设计的好处是：

1. 能明显提升产品价值，从“泛面试陪练”升级到“针对目标岗位的面试陪练”。
2. 改动路径清晰，不需要推翻 Phase 1。
3. 数据结构可以支撑后续简历优化和岗位推荐。
4. 每一步 LLM 产物都可保存、可调试、可复用。
5. 面试计划让动态追问更有目标，不容易变成随意聊天。

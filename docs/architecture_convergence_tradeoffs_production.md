# 架构收敛、Trade-off 与生产化部署说明

本文档用于回答三个问题：

```text
1. 当前系统的核心能力是什么？
2. 哪些能力应该保持可插拔，避免为了展示技术而堆复杂度？
3. 如果要生产化部署，应该按什么流程推进？
```

本文不是新的阶段计划，而是整个 InterviewAgent 项目的架构收敛文档。后续新增能力时，优先用本文判断：

```text
这个能力是产品骨架，还是插件？
它解决了真实业务问题，还是只是展示技术？
它是否能被 workflow_run / AgentRun / Evidence / artifact 观测和追踪？
```

---

## 1. 架构收敛结论

InterviewAgent 不应该被定义成一个简单的聊天接口，也不应该被定义成一个无限自治的 Agent demo。

更准确的定位是：

```text
面向求职面试场景的 AI Agent Workflow 系统。

它用 Workflow 管理业务流程，
用 Agent 做判断和生成，
用 Tool 获取确定性能力，
用 RAG 补充外部知识，
用 Evidence 约束模型判断，
用 AgentRun / workflow_runs 形成可观测、可恢复、可审计的运行闭环。
```

核心链路应该收敛为：

```text
User Request
  -> API
  -> workflow_task
  -> worker
  -> step execution
  -> Agent decision
  -> Tool / RAG / DB artifact
  -> EvidencePacket
  -> Agent output
  -> Persisted artifact
  -> Observable workflow_run
```

RAG 闭环应该收敛为：

```text
Knowledge Source
  -> Retrieval Pipeline
  -> Evidence Builder
  -> Agent Context
  -> AgentRun / Evidence references
  -> User-facing result
```

这意味着：`POST /chat` 不应该继续承载所有业务流程。它可以保留为兼容入口或同步调试入口，但产品主路径应该转向：

```text
POST /api/interview
  -> enqueue task
  -> worker 执行 workflow
  -> workflow_runs 记录状态
  -> 前端通过 workflow run / session 查询结果
```

---

## 2. 核心能力与可插拔能力

### 2.1 必须保留为核心能力

核心能力是系统成立的骨架，不应该被做成可有可无的装饰。

| 能力 | 为什么是核心 | 当前对应模块 |
| --- | --- | --- |
| 面试业务模型 | 产品不是通用聊天，必须理解 session、project、plan、execution、message | `interview_service.py`、`interview_execution_service.py`、repository / models |
| Workflow Runtime | 复杂 Agent 流程需要状态、步骤、失败、恢复和观测 | `workflow_runtime.py`、`interview_runtime_workflow.py`、`workflow_step_runner.py` |
| workflow_runs | 让每次流程执行有真实记录，是恢复、调试、审计的入口 | `workflow_run_query_service.py`、`workflow_run_repository.py` |
| Step retry / timeout | 生产系统必须处理 LLM、DB、Tool 的不稳定 | `workflow_step_runner.py`、`settings.py` |
| AgentRun | 每次 Agent 调用必须可追踪输入、输出、错误和 workflow context | `agent_run_service.py`、`agent_run_query_service.py` |
| EvidencePacket | Agent 判断必须有证据来源，不能只靠 prompt 自由发挥 | `evidence_contract.py`、`evidence_service.py` |
| Tool Runtime | Agent 需要调用确定性能力，而不是只生成文本 | `agent_tools.py` |
| RAG Evidence | 面对真实 AI 面试和技术问答，必须能从知识源检索并进入证据链 | `rag_pipeline.py`、`retrieval_tools.py`、`retrieval_contract.py` |
| Artifact Boundary | 跨 workflow 协作必须依赖明确 artifact，而不是偷读内存对象 | `artifact_boundary.py` |
| Observability API / UI | 复杂 Agent 系统必须能看到 workflow、AgentRun、错误和恢复状态 | `workflow_run.py`、`agent_run.py`、前端 Workflow Runs |

核心能力的判断标准：

```text
如果拿掉它，系统会重新退化成不可恢复、不可解释、不可产品化的 chat wrapper，
那么它就是核心能力。
```

### 2.2 应该保持可插拔的能力

可插拔能力是系统可以替换、扩展、升级的部分，不应该侵入核心业务语义。

| 能力 | 为什么可插拔 | 推荐边界 |
| --- | --- | --- |
| LLM Provider | OpenAI、DeepSeek、通义、Claude 等都只是模型供应商 | 保持在 `llm_service.py` / Agent runtime 后面 |
| Embedding Provider | 当前可用 hashing/simple embedding，后续可换真实 embedding | 保持在 `rag_pipeline.py` 的 embedder 抽象后面 |
| Vector Store | 本地表、MySQL、pgvector、Milvus、Qdrant 都只是检索存储实现 | Repository / retriever 接口隔离 |
| LangGraph Runtime | LangGraph 是执行编排能力，不是业务语义本身 | 与 sequential runtime 共用 Node |
| LangGraph Checkpointer | checkpoint 是执行层快照，不是业务事实来源 | 不替代 `workflow_runs.state` 和 DB artifact |
| Tool Catalog | 工具会越来越多，但调用协议应稳定 | `ToolRegistry` / `ToolRuntime` / `ToolPolicy` |
| Workflow 类型 | preparation、interview_runtime、assessment、growth_report 都可扩展 | 每个 workflow 有自己的 state / nodes / artifact |
| Report Agent | GrowthReport、ResumeOptimization、LearningPlan 都是产品插件 | 必须遵守 Evidence / AgentRun / artifact contract |
| 前端展示模块 | 面试页、Workflow Runs、Growth Report、知识库调试页可以渐进增加 | 不反向污染后端核心状态模型 |
| 部署形态 | 本地、单机 Docker、云服务器、K8s 都只是运行环境 | 通过 env、镜像、迁移、健康检查收敛 |

可插拔能力的判断标准：

```text
如果换一种实现，业务语义不应该改变，
那么它就是可插拔能力。
```

### 2.3 暂时不应该做重的能力

这些能力可以进入长期路线，但不应该在当前阶段为了展示技术而提前重做：

```text
1. 全自治多 Agent 规划器。
2. 大而全的 Human Review 后台。
3. 完整 RBAC / 多租户权限系统。
4. 自动投递招聘平台。
5. Word / PDF 简历生成流水线。
6. 复杂向量数据库集群和 reranker 服务。
7. 跨用户报告对比和增长曲线。
8. 实时语音面试。
9. 把所有流程一次性塞进一个巨大 DAG。
10. 让 LangGraph checkpoint 替代业务状态。
```

当前优先级应该是：

```text
先把核心闭环做稳，
再让可插拔能力逐个进入闭环。
```

---

## 3. 推荐的稳定架构分层

### 3.1 分层图

```text
Frontend
  Interview UI
  Workflow Runs UI
  Growth Report UI
  Knowledge Debug UI

API Layer
  /api/interview
  /api/workflow-runs
  /api/agent-runs
  /api/preparation

Application Service
  InterviewService
  PreparationService
  Workflow query services
  Growth report service

Workflow Layer
  workflow_task
  worker
  WorkflowRuntime
  WorkflowStepRunner
  Workflow state contract

Node Layer
  save_user_answer
  topic_judge
  retrieve_knowledge
  build_evidence
  generate_followup
  persist_artifact

Agent Layer
  Agent spec builder
  Agent runtime
  Prompt registry
  Output schema validation

Tool / RAG Layer
  ToolRegistry
  ToolRuntime
  RetrievalPipeline
  KnowledgeIndexer
  Evidence Builder

Persistence Layer
  workflow_runs
  step_executions
  AgentRun
  messages
  interview artifacts
  knowledge_documents / knowledge_chunks
```

### 3.2 每层职责边界

API 层：

```text
只负责接收请求、校验输入、返回响应。
不直接执行完整 Agent 流程。
不直接拼 prompt。
不直接处理 retry / timeout / failure recovery。
```

Application Service：

```text
负责编排业务入口。
可以创建 task、调用 workflow、查询 artifact。
不应该把所有 step 写成一个大方法。
```

Workflow 层：

```text
负责流程状态、步骤顺序、失败恢复、retry、timeout、workflow_run 持久化。
不负责具体业务判断。
```

Node 层：

```text
负责一个明确业务步骤。
有副作用的 Node 必须考虑幂等。
Node 可以调用 Agent / Tool / Repository，但要把结果写回 state 或 artifact。
```

Agent 层：

```text
负责判断、选择工具、生成结构化结果。
不直接控制 workflow 生命周期。
不直接隐藏 DB 副作用。
```

Tool / RAG 层：

```text
负责确定性能力和知识检索。
Tool 结果应该被记录，重要结果应该进入 EvidencePacket。
RAG 不直接等于最终回答，RAG 只是证据输入。
```

Persistence 层：

```text
保存业务事实、运行记录和可复用 artifact。
DB artifact 是判断副作用是否发生的事实来源。
```

---

## 4. 关键设计 Trade-off

### 4.1 Workflow：为什么不用 `POST /chat` 执行所有流程？

选择：

```text
POST /api/interview
  -> workflow_task
  -> worker
  -> step execution
```

而不是：

```text
POST /api/chat
  -> 保存消息
  -> 调 Agent
  -> 调 Tool
  -> RAG
  -> 保存结果
  -> 返回
```

原因：

```text
1. 面试流程不是一次文本生成，而是多个有副作用的业务步骤。
2. LLM、RAG、Tool 都可能慢、超时或失败，同步接口会越来越脆弱。
3. workflow_runs 只有在异步任务和步骤执行中才有真实意义。
4. retry / timeout / failure recovery 需要步骤边界，而不是一个大 try-catch。
5. 后续 growth report、resume optimization、assessment 都天然是 workflow，不是 chat。
```

放弃的东西：

```text
1. 同步接口实现简单。
2. 前端一次请求就拿到结果的体验简单。
3. 调试时链路更短。
```

接受的成本：

```text
1. 需要任务状态查询。
2. 需要 worker 生命周期管理。
3. 需要处理任务重复提交和幂等。
4. 前端需要展示 generating / failed / retry 等状态。
```

结论：

```text
保留 /chat 作为兼容或调试路径可以接受。
生产主路径应该是 workflow-first。
```

### 4.2 RAG：为什么要进入 Evidence，而不是只把检索结果塞进 prompt？

选择：

```text
Knowledge Source
  -> Retrieval Pipeline
  -> RetrievedKnowledge
  -> EvidencePacket
  -> Agent Context
  -> AgentRun input snapshot
```

而不是：

```text
search()
  -> 拼到 prompt
  -> 让模型自由回答
```

原因：

```text
1. AI 面试需要可信回答和可追溯依据，不能只靠模型记忆。
2. 面试评价、技术追问、学习建议都需要知道依据来自哪里。
3. 检索结果进入 Evidence 后，AgentRun 可以记录当时模型看到了什么。
4. 后续可以基于 evidence_ids 做报告引用、错误排查和质量评估。
5. RAG 和 Tool 统一进入 Evidence，架构更收敛。
```

放弃的东西：

```text
1. 直接 prompt stuffing 实现更快。
2. 不需要设计 evidence schema。
3. 不需要维护知识源元数据。
```

接受的成本：

```text
1. 需要知识文档、chunk、retrieval result 的结构。
2. 需要控制 evidence 数量和长度。
3. 需要处理召回质量、去重和过期问题。
```

结论：

```text
RAG 的产物不是最终答案，而是 Evidence。
Agent 基于 Evidence 做判断和生成。
```

### 4.3 Checkpoint：为什么不让 LangGraph checkpoint 成为唯一恢复来源？

选择：

```text
workflow_runs.state = 业务恢复游标
DB artifact = 副作用事实来源
LangGraph checkpoint = 执行层快照
```

而不是：

```text
LangGraph checkpoint = 全部状态来源
```

原因：

```text
1. checkpoint 只能说明图执行层看到了什么，不等于 DB transaction 已经提交。
2. message、AgentRun、execution、summary、report 都是业务 artifact。
3. 生产恢复必须判断副作用是否真实发生。
4. workflow_runs 是前端观测和业务调试入口，不能被隐藏在 checkpoint 内部。
5. 不同 runtime path 需要保持业务语义一致，不能绑定 LangGraph。
```

放弃的东西：

```text
1. 完全依赖 LangGraph resume 的简单叙事。
2. 从任意 graph node 恢复的表面灵活性。
```

接受的成本：

```text
1. 需要 reconciliation。
2. 需要设计哪些 state 字段是恢复游标。
3. Node 要具备幂等能力。
```

结论：

```text
Checkpoint 是执行层能力。
业务恢复必须看 workflow_runs.state 和 DB artifact。
```

### 4.4 Tool：为什么要设计 ToolRegistry / ToolRuntime，而不是直接在 Agent 里调用函数？

选择：

```text
Agent
  -> ToolPlanner
  -> ToolPolicy
  -> ToolRegistry
  -> ToolRuntime
  -> ToolResult
  -> EvidencePacket
```

而不是：

```text
Agent prompt 里写：
需要简历就调用 get_resume_profile()
需要公司信息就调用 search_company_info()
```

原因：

```text
1. Tool 是 Agent 可调用能力，必须有权限、输入、输出和错误边界。
2. 不同工具有不同副作用，必须有 policy。
3. Tool 调用结果应该可记录、可测试、可复用。
4. 后续工具会变多，直接函数调用会失控。
5. Tool 和 Evidence 结合后，Agent 输出更可解释。
```

放弃的东西：

```text
1. 直接写函数调用最简单。
2. Prompt 自由决定工具看起来更智能。
```

接受的成本：

```text
1. 需要维护工具定义和 registry。
2. 需要处理 tool timeout、错误和空结果。
3. 需要限制工具调用范围，避免 Agent 任意行动。
```

结论：

```text
Agent 不是只生成文本。
Agent 应该是决策 + 调工具 + 生成结果。
但工具调用必须被 Runtime 和 Policy 约束。
```

当前适合保留的基础工具：

```text
get_resume_profile()
get_previous_answer()
search_company_info()
search_technology()
```

后续新增工具时必须回答：

```text
1. 这个工具解决什么真实任务？
2. 输入输出 schema 是什么？
3. 是否有副作用？
4. 是否需要 retry / timeout？
5. 结果是否进入 Evidence？
6. AgentRun 是否能追踪这次工具调用？
```

### 4.5 Evidence：为什么要 EvidencePacket，而不是让模型自由判断？

选择：

```text
EvidencePacket
  - resume evidence
  - previous answer evidence
  - interview execution evidence
  - retrieved knowledge evidence
  - assessment evidence
```

而不是：

```text
把所有上下文直接拼成 prompt。
```

原因：

```text
1. 面试系统的核心价值不是说得流畅，而是判断可信。
2. Evidence 能减少模型编造候选人经历、技能和项目细节。
3. Evidence 让报告和评价可以引用来源。
4. Evidence 是跨 Agent / Tool / RAG 的统一上下文协议。
5. EvidencePacket 可以被 AgentRun 记录，便于复盘和调试。
```

放弃的东西：

```text
1. prompt 拼接更自由。
2. 不需要设计 source_type / evidence_id。
```

接受的成本：

```text
1. 需要 evidence schema。
2. 需要控制 evidence 颗粒度。
3. 需要处理 evidence 不足时的 unknown / partial 输出。
```

结论：

```text
Evidence 是 Agent 判断的边界。
没有证据时，Agent 应该说 unknown，而不是编造。
```

### 4.6 AgentRun：为什么每次 Agent 调用都要记录？

选择：

```text
每次 Agent 调用都保存：
input_snapshot
output_snapshot
status
error
prompt metadata
workflow_context
```

而不是：

```text
只保存最终 assistant message。
```

原因：

```text
1. assistant message 只告诉用户看到了什么，不告诉开发者模型为什么这么判断。
2. AgentRun 能追踪 prompt、evidence、tool result 和输出。
3. workflow retry 时可以判断是否复用已有 AgentRun。
4. 面试评价、成长报告、简历优化都需要审计。
```

放弃的东西：

```text
1. 数据库更轻。
2. 实现更简单。
```

接受的成本：

```text
1. 存储更多 JSON snapshot。
2. 需要敏感信息脱敏策略。
3. 需要清理和归档策略。
```

结论：

```text
没有 AgentRun，就没有可审计的 Agent 系统。
```

---

## 5. 复杂度控制原则

### 5.1 新能力进入系统的准入标准

任何新能力进入主链路前，必须满足至少 4 个条件：

```text
1. 有明确用户价值。
2. 有清楚 workflow 边界。
3. 有可观测运行记录。
4. 有失败恢复策略。
5. 有 Evidence 或 artifact 归属。
6. 有测试覆盖核心成功和失败路径。
```

如果一个能力只能展示“我们用了某技术”，但不能进入上述闭环，就不应该进入主链路。

### 5.2 不要把所有东西都做成 Agent

应该由确定性代码完成的事情：

```text
1. 数据库查询。
2. 状态推进。
3. workflow 分支。
4. schema 校验。
5. 权限判断。
6. retry / timeout。
7. artifact 复用判断。
```

适合 Agent 做的事情：

```text
1. 判断回答质量。
2. 归纳候选人能力。
3. 选择需要的工具。
4. 基于证据生成追问。
5. 基于证据生成成长报告。
6. 生成结构化建议。
```

### 5.3 不要把所有流程都塞进一个大图

推荐 workflow 边界：

```text
preparation:
  JD / 简历 / 项目分析，生成面试计划。

interview_runtime:
  面试进行中的每一轮问答。

post_interview_assessment:
  面试结束后的评价和风险分析。

candidate_growth_report:
  将评价转化为成长报告和行动建议。

resume_optimization:
  基于目标岗位和成长报告优化简历。
```

判断标准：

```text
如果一个流程有独立触发时机、独立 artifact、独立失败恢复和独立观测价值，
它就应该是独立 workflow。
```

---

## 6. 生产化部署流程

当前项目已经具备产品化雏形，但还不是完整生产部署形态。生产化不是把服务跑到云服务器上就结束，而是把配置、数据库、任务、观测、安全、回滚全部补齐。

### 6.1 生产化目标形态

推荐目标架构：

```text
Client Browser
  -> HTTPS / Domain
  -> Reverse Proxy
  -> Frontend static assets
  -> Backend API
  -> MySQL
  -> Worker process
  -> LLM Provider
  -> Optional Vector Store
  -> Logs / Metrics / Alerts
```

如果采用单机 Docker Compose，第一版可以是：

```text
nginx
  frontend static files
  reverse proxy /api

backend-api
  FastAPI + uvicorn/gunicorn

backend-worker
  workflow task worker

mysql
  business tables
  workflow_runs
  AgentRun
  knowledge_documents / chunks

optional-vector-store
  后续接入 pgvector / Qdrant / Milvus 时再加入
```

### 6.2 第一步：冻结生产入口

生产主入口建议收敛为：

```text
POST /api/interview
  创建或提交一轮面试 workflow task。

GET /api/workflow-runs/{workflowRunId}
  查询 workflow 状态。

GET /api/interview/{sessionId}/execution
  查询面试执行状态。

GET /api/interview/{sessionId}/growth-report
  查询成长报告。

POST /api/interview/{sessionId}/growth-report/generate
  显式触发成长报告生成。
```

生产中不建议把 `/chat` 作为主路径。可以保留：

```text
POST /api/interview/chat
  legacy / debug / fallback
```

但要在文档中明确：

```text
生产主链路是 workflow task。
```

### 6.3 第二步：环境变量和密钥管理

当前配置来自 `backend/app/config/settings.py`，生产需要补齐 `.env.production` 或部署平台 Secret。

必须配置：

```text
APP_ENV=production
CORS_ORIGINS=https://your-domain.com

DB_HOST=...
DB_PORT=3306
DB_USER=...
DB_PASSWORD=...
DB_NAME=interview_agent

LLM_API_KEY=...
LLM_API_BASE=...
LLM_MODEL=...
LLM_TIMEOUT_SECONDS=180

WORKFLOW_STEP_TIMEOUT_SECONDS=120
WORKFLOW_STEP_MAX_ATTEMPTS=2
USE_LANGGRAPH_INTERVIEW_RUNTIME=false 或 true
```

生产要求：

```text
1. 密钥不能提交到 git。
2. 前后端环境变量分离。
3. 不同环境使用不同数据库。
4. LLM key 必须能轮换。
5. CORS 不能使用任意来源。
```

建议新增：

```text
backend/.env.example
frontend/.env.example
```

### 6.4 第三步：数据库迁移流程

当前项目的 SQL 脚本在 `sql/` 目录，生产化需要有明确迁移流程。

最低要求：

```text
1. 新环境从 init 脚本初始化。
2. 按版本顺序执行 v*_*.sql。
3. 每次上线前记录当前 DB schema version。
4. 每个迁移脚本只能前进，不直接修改历史脚本。
5. 上线前备份数据库。
```

推荐增加：

```text
schema_migrations 表
```

字段：

```text
version
script_name
checksum
applied_at
applied_by
```

上线流程：

```text
1. 备份生产数据库。
2. 在 staging 数据库执行迁移。
3. 跑后端测试和关键手动验收。
4. 在生产低峰期执行迁移。
5. 启动新版本服务。
6. 验证 health check 和核心 API。
```

### 6.5 第四步：拆分 API 进程和 Worker 进程

当前已经有 `InterviewWorkflowTaskService` 和 `interview_workflow_worker` 的基础，但生产化需要明确进程模型。

推荐：

```text
backend-api:
  只处理 HTTP 请求。
  负责 enqueue task、查询状态、返回结果。

backend-worker:
  从任务表或队列中拉取任务。
  执行 workflow step。
  写 workflow_runs / AgentRun / artifact。
```

第一版可以使用数据库任务表轮询。后续再升级：

```text
Redis Queue / Celery / RQ / Dramatiq
```

但不要一开始为了“像生产”就引入复杂队列。判断标准：

```text
当任务并发、延迟、重试、死信和横向扩容成为真实问题时，再引入队列中间件。
```

### 6.6 第五步：容器化

当前 repo 没有 Dockerfile，生产化需要补齐。

建议新增：

```text
backend/Dockerfile
frontend/Dockerfile
docker-compose.prod.yml
nginx.conf
```

后端镜像职责：

```text
1. 安装 requirements.txt。
2. 启动 FastAPI。
3. 提供 health check。
4. 不在镜像里写死环境变量。
```

前端镜像职责：

```text
1. npm ci。
2. npm run build。
3. 用 nginx 托管 dist。
4. /api 反向代理到 backend-api。
```

Compose 第一版服务：

```text
mysql
backend-api
backend-worker
frontend-nginx
```

### 6.7 第六步：健康检查与启动顺序

后端建议新增：

```text
GET /api/health
```

返回：

```json
{
  "status": "ok",
  "appEnv": "production",
  "db": "ok",
  "version": "..."
}
```

生产启动顺序：

```text
1. MySQL 启动并通过 health check。
2. 执行数据库迁移。
3. backend-api 启动。
4. backend-worker 启动。
5. frontend-nginx 启动。
6. 外部负载均衡或域名切流。
```

### 6.8 第七步：日志、指标和告警

最低生产观测：

```text
1. API request log。
2. workflow_run status 统计。
3. failed workflow_run 告警。
4. LLM 调用耗时和失败率。
5. Tool 调用耗时和失败率。
6. RAG 检索结果数量和空召回率。
7. worker backlog。
8. 数据库连接错误。
```

建议关键指标：

```text
workflow_run_success_total
workflow_run_failed_total
workflow_step_duration_seconds
agent_run_failed_total
llm_request_duration_seconds
tool_call_failed_total
retrieval_empty_result_total
worker_pending_task_count
```

第一版可以先用结构化日志：

```text
request_id
session_id
workflow_run_id
workflow_id
step_id
agent_run_id
status
duration_ms
error_type
error_message
```

### 6.9 第八步：安全与数据保护

生产最小安全要求：

```text
1. HTTPS。
2. CORS 白名单。
3. LLM key / DB password 使用 Secret。
4. 用户输入长度限制。
5. API rate limit。
6. AgentRun input_snapshot 脱敏。
7. 简历、面试回答等个人信息加访问控制。
8. 删除数据时同步删除关联 message / artifact / AgentRun 或做逻辑删除策略。
```

注意：

```text
AgentRun 和 Evidence 会保存大量上下文，
上线前必须定义隐私边界和保留周期。
```

建议保留策略：

```text
开发环境：
  保留详细 snapshot，方便调试。

生产环境：
  默认保留必要摘要。
  对敏感字段脱敏。
  对原始 prompt / response 设置保留期限。
```

### 6.10 第九步：RAG 生产化

当前 RAG 更适合作为基础闭环，生产化需要补齐：

```text
1. 知识源管理 API。
2. 知识文档上传或导入。
3. chunk 重新生成机制。
4. embedding provider 配置。
5. 检索调试页面。
6. 知识版本和失效策略。
7. 空召回降级策略。
8. retrieval result 进入 Evidence 的长度控制。
```

推荐生产 RAG 路线：

```text
第一版：
  MySQL knowledge_documents / knowledge_chunks
  简单 embedding / hybrid retrieval
  EvidencePacket 引用 retrieved_knowledge

第二版：
  接入真实 embedding provider
  加入向量检索存储
  增加 rerank 抽象

第三版：
  知识源版本化
  后台管理和检索质量评估
```

### 6.11 第十步：发布流程

推荐发布流程：

```text
1. 本地测试
   backend: python -m unittest discover -s service
   frontend: npm run build

2. 构建镜像
   backend image
   frontend image

3. 部署到 staging
   执行 DB migration
   启动 api / worker / frontend

4. Staging 验收
   创建面试 session
   提交一轮 interview workflow
   查看 workflow_runs
   生成 growth report
   验证 AgentRun 和 Evidence

5. 生产备份
   备份 MySQL
   记录当前 image tag 和 schema version

6. 生产发布
   执行 migration
   滚动更新 backend-api
   更新 backend-worker
   更新 frontend

7. 发布后验证
   health check
   workflow_run 成功率
   worker backlog
   LLM 调用是否正常
   前端关键页面是否可用

8. 回滚预案
   回滚镜像 tag
   停止 worker
   保留 DB 备份
   对已执行 migration 的回滚策略提前评估
```

### 6.12 第十一点：生产化验收清单

上线前至少满足：

```text
1. 所有生产配置通过环境变量注入。
2. 数据库迁移流程可重复执行并有记录。
3. API 和 worker 分离。
4. workflow step 有 timeout 和 retry。
5. workflow_runs 可以查询成功、失败和当前步骤。
6. failed workflow 可以定位 last_error。
7. AgentRun 可以追踪关键 Agent 调用。
8. RAG 检索结果可以进入 Evidence。
9. 前端 build 通过。
10. 后端测试通过。
11. 有 health check。
12. 有结构化日志。
13. 有数据库备份和回滚方案。
14. LLM key 不在代码仓库中。
15. 用户敏感数据有脱敏或保留策略。
```

---

## 7. 推荐下一步实施顺序

如果现在继续推进工程实现，建议按这个顺序：

```text
1. 补 docs 本文，作为架构收敛依据。
2. 补 backend/.env.example 和 frontend/.env.example。
3. 新增 /api/health。
4. 新增 backend Dockerfile。
5. 新增 frontend Dockerfile + nginx 配置。
6. 新增 docker-compose.prod.yml。
7. 明确 backend-api / backend-worker 启动命令。
8. 增加 schema_migrations 或至少写迁移执行说明。
9. 增加知识库 search/index API，让 RAG 可运维。
10. 增加 workflow_run failed 告警或日志统计。
```

更靠后的增强：

```text
1. 引入真实任务队列。
2. 引入真实 embedding provider。
3. 引入向量数据库。
4. 引入 OpenTelemetry / Prometheus。
5. 引入对象存储保存上传文档。
6. 引入用户体系和权限。
```

---

## 8. 面试表达版本

如果在面试中介绍这个项目，可以这样收敛表达：

```text
这个项目不是简单把大模型接到 /chat 接口上，而是把 AI 面试拆成了可恢复、可观测的 Agent Workflow 系统。

我把核心链路从同步 chat 改造成 workflow task + worker + step execution，每个步骤都有 retry、timeout 和 failure recovery，并通过 workflow_runs 记录状态。

Agent 层不只是生成文本，而是可以基于 ToolRegistry 调用简历、历史回答、公司信息、技术知识等工具，再把工具和 RAG 检索结果统一整理为 EvidencePacket，最后生成结构化追问、评估或成长报告。

在状态恢复上，我没有简单依赖 LangGraph checkpoint，而是把 workflow_runs.state 作为业务恢复游标，把 DB artifact 作为副作用事实来源，把 checkpoint 作为执行层快照，并设计 reconciliation 来保证三者一致。

这套设计的重点不是堆技术，而是让 Agent 的每次判断都有证据，每次调用都有 AgentRun，每次 workflow 都能观测、失败、重试和恢复。
```

---

## 9. 最终原则

```text
Workflow 是业务流程骨架。
Tool 是 Agent 可调用的确定性能力。
RAG 是知识证据来源。
Evidence 是 Agent 判断边界。
AgentRun 是模型调用审计记录。
workflow_runs 是系统运行事实入口。
Checkpoint 是执行层恢复辅助。
Artifact 是跨 workflow 协作契约。
```

系统后续可以继续变强，但不应该变散。

每加一个能力，都要问：

```text
它进入 workflow 了吗？
它有 AgentRun 吗？
它有 Evidence 吗？
它有 artifact 吗？
它失败后能恢复吗？
它能被观察到吗？
```

如果答案是否定的，它还不应该进入生产主链路。

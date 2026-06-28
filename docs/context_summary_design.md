# CandidateProfile、ConversationSummary 与长面试评价优化方案

## 1. 背景问题

当前项目的上下文传递方式比较直接：

1. 面试追问时，将最近若干条历史消息发送给大模型。
2. 结束面试时，将完整历史记录发送给 evaluation 模型。
3. 轮次目前主要根据 user answer 增长，导致一轮内可能出现“AI 问题 + 用户回答 + AI 追问”三条消息。

当面试轮次较少时，这个方案简单可用；但当对话超过 10 轮后，会出现几个问题：

1. 上下文冗余：每次请求携带大量重复历史，增加 token 成本和响应延迟。
2. 关键信息丢失：如果只截取最近消息，模型可能忘记前面提到的项目背景、技术栈和候选人表现。
3. 评价质量不稳定：最终 evaluation 全量发送历史时，长对话可能接近上下文限制；只发送最近消息又会缺少证据。
4. 轮次语义不清：当前 followup 和 user answer 可能共用同一个 round_no，不利于统计“已完成第几轮”和触发 summary。
5. 摘要职责混杂：项目经验、技术栈、薄弱点、已问话题和下一步追问混在一份 summary 中，后续会越来越难维护。

因此建议将面试记忆拆成两类：

```text
CandidateProfile      慢变量，记录候选人的稳定画像
ConversationSummary   快变量，记录已经聊过什么和下一步怎么追问
```

CandidateProfile 变化慢，适合低频更新；ConversationSummary 变化快，适合较高频更新。

## 2. 是否应该直接新建 summary 表

推荐直接新建表。

虽然第一版可以把 `context_summary` 和 `summary_round_no` 直接放在 `interview_sessions` 表中，但当前代码量还比较少，直接创建独立表反而更利于后续演进。理由如下：

1. 可追溯：可以保留每次 summary 的版本，方便排查某次追问为什么重复或偏题。
2. 不污染 session 表：`interview_sessions` 继续只保存会话基本状态，summary 作为派生上下文单独管理。
3. 支持 evaluation 复用：最终评价可以选择最新 CandidateProfile 和 ConversationSummary，也可以读取 summary 历史。
4. 支持后续扩展：后续可以增加 summary 类型，例如 `evaluation_context`、`resume_context`。
5. 软删除一致：可以沿用当前 `status = normal/deleted` 的软删除模式。

结论：在当前项目阶段，直接加表更清晰，修改成本也不高。

## 3. 轮次语义建议

建议重新定义为：

```text
一轮 = 一个面试官问题 + 一个候选人回答
```

存储示例：

```text
round 1 assistant question
round 1 user answer
round 2 assistant followup
round 2 user answer
round 3 assistant followup
round 3 user answer
```

也就是说：

1. `/start` 创建第 1 轮问题。
2. 用户回答时，answer 使用当前待回答问题的 `round_no`。
3. AI 根据本轮回答生成下一轮问题，followup 使用 `round_no + 1`。
4. 已完成轮数可以通过 user answer 的最大 `round_no` 统计。

这样可以避免一轮中出现两个 assistant 消息，并且 summary 触发条件更容易判断。

## 4. 新增表设计

建议新增 `interview_summaries` 表。

```sql
CREATE TABLE IF NOT EXISTS interview_summaries (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id BIGINT NOT NULL,
  summary_type VARCHAR(30) NOT NULL DEFAULT 'conversation',
  from_round_no INT NOT NULL DEFAULT 1,
  to_round_no INT NOT NULL,
  content TEXT NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_interview_summaries_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_interview_summaries_session_type_round
  ON interview_summaries(session_id, summary_type, to_round_no);

CREATE INDEX idx_interview_summaries_session_status
  ON interview_summaries(session_id, status);
```

字段说明：

`summary_type`

用于区分摘要用途。第一版需要两个类型：

```text
candidate_profile    候选人的稳定画像，慢变量
conversation         面试对话摘要，快变量
evaluation_context   最终评价使用的压缩证据摘要，后续可选
```

`from_round_no` / `to_round_no`

表示本条 summary 覆盖的轮次范围。滚动摘要可以一直从第 1 轮覆盖到当前轮，例如：

```text
summary 1: from 1 to 10
summary 2: from 1 to 15
summary 3: from 1 to 20
```

也可以做增量摘要，例如：

```text
summary 1: from 1 to 10
summary 2: from 11 to 15
summary 3: from 16 to 20
```

第一版推荐使用滚动摘要，即每次生成的是“截至当前轮的完整压缩摘要”，读取时只需要拿最新一条。

`content`

保存摘要正文。

`raw_response`

保存大模型原始响应，便于调试。

`status`

支持软删除。删除 session 时，关联 summaries 也应该标记为 deleted。

## 5. Summary 生成时机

ConversationSummary 推荐规则：

```text
当 completed_round_no >= 10
并且 completed_round_no - latest_conversation_summary.to_round_no >= 5
时生成新的 conversation summary。
```

示例：

```text
第 1-9 轮：不生成 summary
完成第 10 轮：生成 conversation summary，覆盖 1-10 轮
完成第 11-14 轮：不更新 conversation summary
完成第 15 轮：生成 conversation summary，覆盖 1-15 轮
完成第 20 轮：生成 conversation summary，覆盖 1-20 轮
```

CandidateProfile 推荐规则：

```text
当 completed_round_no >= 10
并且没有 candidate_profile，或者 completed_round_no - latest_candidate_profile.to_round_no >= 10
时生成新的 candidate profile。
```

示例：

```text
完成第 10 轮：生成 candidate profile，覆盖 1-10 轮
完成第 15 轮：不更新 candidate profile
完成第 20 轮：生成 candidate profile，覆盖 1-20 轮
```

这样做的原因是：候选人的项目经历、技术栈和背景画像变化较慢，不需要像对话摘要一样频繁更新。

为什么不是每轮都 summary：

1. 每轮 summary 会增加额外模型调用成本。
2. 过于频繁更新，摘要质量可能变得不稳定。
3. 每 5 轮更新一次通常足够保持上下文新鲜。

## 6. Prompt 设计

建议新增两个 prompt：

```text
backend/app/prompts/candidate_profile.txt
backend/app/prompts/conversation_summary.txt
```

CandidateProfile 用于整理慢变量：

```text
候选人的主要项目经历、职责范围、业务领域
候选人长期使用或明确熟悉的技术栈
候选人反复体现出的能力倾向
候选人可确认的工作方式或表达习惯
```

ConversationSummary 用于整理快变量：

```text
已经覆盖的问题、项目模块、技术点和追问方向
最近几轮回答中的关键事实、设计取舍、结果数据或缺失信息
回答含糊、证据不足、值得继续深挖的薄弱点
后续追问建议，尤其是避免重复已经问过的问题
```

第一版建议都输出纯文本，不强制 JSON。原因是两类记忆主要给模型阅读，不需要前端展示，也不需要复杂结构化检索。后续如果要做可视化或分析，再改成 JSON。

## 7. Followup 上下文策略

当前策略：

```text
system interviewer prompt
最近 12 条消息
当前 followup prompt
```

建议改为：

```text
system interviewer prompt
最新 CandidateProfile，如果存在
最新 ConversationSummary，如果存在
最近 4 轮完整原文消息
当前 followup prompt
```

示例消息：

```text
system:
你是一位资深技术面试官...

system:
候选人稳定画像 CandidateProfile：
...

面试对话摘要 ConversationSummary：
...

assistant/user:
最近 4 轮完整对话

user:
请基于候选人最新回答生成下一轮追问...
```

好处：

1. 前面 10 轮以上的信息不会丢。
2. 最近几轮原文仍然保留，模型能看到真实表达和上下文细节。
3. token 成本可控。
4. 追问更容易连续，不会重复问已经覆盖的话题。

## 8. Evaluation 是否也要改

建议改，但分阶段。

### 8.1 当前 evaluation 的风险

当前最终评价如果直接使用完整历史，在长对话下会有两个风险：

1. token 过长：面试轮数越多，请求越大。
2. 证据密度低：模型要从很长的原文中提取证据，可能遗漏关键信号。

如果只使用 summary，又会有另一个风险：

1. summary 是压缩内容，可能丢掉原始证据。
2. evaluation prompt 要求“证据导向”，只看 summary 可能让评价变泛。

所以 evaluation 不建议简单地只用 summary。

### 8.2 推荐 evaluation 策略

采用混合上下文：

```text
如果 completed_round_no <= 15：
  使用完整 history

如果 completed_round_no > 15：
  使用 latest CandidateProfile + latest ConversationSummary + 最近 8 轮完整原文
```

也可以进一步生成专门的 evaluation summary：

```text
candidate profile        服务于稳定背景，强调项目经历、技术栈、长期能力倾向
conversation summary     服务于追问，强调已问内容和下一步追问点
evaluation summary       服务于最终评价，强调证据、表现、优势、不足
```

第一版建议不要新增 `evaluation_summary`，先复用 `CandidateProfile + ConversationSummary + 最近 8 轮原文`。原因是：

1. 改动少。
2. 能明显降低上下文长度。
3. 仍然保留最近原文证据。
4. 避免一次引入太多 LLM 调用链路。

### 8.3 更完整的 evaluation 方案

如果希望评价质量更稳，可以增加第二种 summary 类型：

```text
summary_type = 'evaluation_context'
```

它在结束面试时生成，输入为：

```text
latest CandidateProfile
latest ConversationSummary
全部 summary 历史或最近若干轮原文
```

输出为结构化评价证据：

```json
{
  "technical_evidence": "技术能力相关证据",
  "project_evidence": "项目经验相关证据",
  "communication_evidence": "沟通表达相关证据",
  "risk_points": "风险和不足证据",
  "recommendation_basis": "推荐或不推荐的依据"
}
```

然后最终 evaluation prompt 使用：

```text
evaluation_context
最近 5-8 轮原文
```

这个方案更强，但第一版实现成本更高。建议等 context summary 稳定后再做。

## 9. 代码改造范围

如果采用独立表方案，主要改这些文件：

```text
sql/init_v1.sql
sql/v1_update.sql

backend/app/models/interview.py
backend/app/repository/interview_repository.py
backend/app/service/llm_service.py
backend/app/service/interview_service.py
backend/app/prompts/summary.txt
```

可能涉及：

1. 新增 ORM：`InterviewSummary`
2. 新增 Repository：`InterviewSummaryRepository`
3. `InterviewService.chat()` 中加入 summary 触发逻辑
4. `LLMService` 新增 `generate_summary()`
5. `LLMService.generate_followup()` 参数增加 `candidate_profile` 和 `conversation_summary`
6. message repository 新增：

```text
latest_assistant_question_round_no(session_id)
completed_round_no(session_id)
list_recent_rounds(session_id, rounds)
list_between_rounds(session_id, from_round, to_round)
```

7. 删除 session 时，软删除 summaries

## 10. 推荐实施顺序

第一阶段：轮次语义修正

1. 新增 `latest_assistant_question_round_no()`
2. 用户 answer 使用当前问题轮次
3. AI followup 使用下一轮轮次
4. 前端显示自然变成“第 1 轮问答、第 2 轮问答”

第二阶段：新增 summary 表

1. SQL 增加 `interview_summaries`
2. ORM 增加 `InterviewSummary`
3. Repository 增加 latest/create/list/soft_delete

第三阶段：追问上下文压缩

1. 新增 `candidate_profile.txt` 和 `conversation_summary.txt`
2. 新增 `generate_candidate_profile()` 和 `generate_conversation_summary()`
3. chat 中完成第 10、15、20 轮后更新 ConversationSummary
4. chat 中完成第 10、20、30 轮后更新 CandidateProfile
5. followup 使用 latest CandidateProfile + latest ConversationSummary + 最近 4 轮原文

第四阶段：evaluation 长上下文优化

1. 15 轮以内继续全量 history
2. 超过 15 轮使用 latest CandidateProfile + latest ConversationSummary + 最近 8 轮原文
3. 观察评价质量

第五阶段：可选增强

1. 增加 `evaluation_context` 类型 summary
2. evaluation 输出引用证据点
3. 前端展示 summary 调试信息，仅开发环境可见

## 11. 推荐最终方案

推荐采用：

1. 直接新增 `interview_summaries` 表。
2. summary 第一版做 `summary_type = candidate_profile` 和 `summary_type = conversation`。
3. 轮次语义改成“一轮 = AI 问题 + 用户回答”。
4. 第 10 轮开始生成 ConversationSummary，之后每新增 5 轮更新一次。
5. 第 10 轮开始生成 CandidateProfile，之后每新增 10 轮更新一次。
6. followup 使用 `latest CandidateProfile + latest ConversationSummary + 最近 4 轮原文`。
7. evaluation 第一版改为：

```text
<= 15 轮：完整 history
> 15 轮：latest CandidateProfile + latest ConversationSummary + 最近 8 轮原文
```

这样方案的好处是：

1. 表结构清晰。
2. 后续容易调试和扩展。
3. 长面试 token 成本可控。
4. 不会牺牲最近几轮原始证据。
5. 对当前代码改动量仍然适中。

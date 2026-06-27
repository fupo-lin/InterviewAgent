# Interview Agent V1 系统设计文档

## 1. 项目目标

构建一个可实际使用的 AI 面试官系统。

用户能够：
* 选择目标岗位
* 开始模拟面试
* 与 AI 多轮对话
* 获取面试评价
* 查看历史记录
目标是先完成一个可运行、可部署、可持续演进的AI应用。

---
# 2. 技术架构
## 2.1 整体架构
            Browser
                ↓
            React
                ↓ HTTP
            FastAPI
                ↓
            Interview Service
                ↓
            LLM(GLM-4)
                ↓
            Response

同时：

            FastAPI
                ↓
            MySQL
            保存面试记录

---

## 2.2 技术选型
    前端：* React + * TypeScript + * Vite
    后端：* Python 3.12 + * FastAPI + * SQLAlchemy
    数据库： * MySQL 8.0
    大模型：* GLM-4
    Agent框架（V2启用）：  LangGraph +  LangChain



# 3. 项目目录结构

InterviewAgent/
├── backend/
│   ├── app/
│   │
│   ├── api/
│   ├── service/
│   ├── repository/
│   ├── models/
│   ├── prompts/
│   ├── agents/
│   ├── config/
│   └── main.py
│
├── frontend/
│
├── sql/
│
├── docs/
│
└── README.md

---

# 4. 后端目录设计
## api ---  负责HTTP接口
例如：
POST /api/interview/start

POST /api/interview/chat

POST /api/interview/end

GET /api/interview/history

---

## service --  业务逻辑层

例如：
InterviewService
负责：
* 创建面试
* 调用LLM
* 保存记录
* 生成评价

---

## repository--数据库访问层

例如：

InterviewSessionRepository
InterviewMessageRepository

---

## models
ORM实体
例如：
InterviewSession

InterviewMessage

InterviewEvaluation

---

## prompts

Prompt模板
例如：
interviewer.txt
followup.txt
evaluation.txt
避免Prompt写死在代码中

---

## agents

Agent逻辑
V1为空
V2开始启用：
interview_agent.py


# 5. 数据库设计

## interview_sessions

CREATE TABLE interview_sessions (
id BIGINT PRIMARY KEY AUTO_INCREMENT,
session_uid VARCHAR(64) UNIQUE,
role_name VARCHAR(50),
status VARCHAR(20),
create_time DATETIME,
update_time DATETIME
);

说明：

一场面试对应一条记录

---

## interview_messages

CREATE TABLE interview_messages (
id BIGINT PRIMARY KEY AUTO_INCREMENT,
session_id BIGINT,
role_type VARCHAR(20),
message_type VARCHAR(20),
round_no INT,
content TEXT,
raw_response JSON,
create_time DATETIME
);

role_type:

user
assistant

message_type:

question
answer
followup
summary

---

## interview_evaluations

CREATE TABLE interview_evaluations (
id BIGINT PRIMARY KEY AUTO_INCREMENT,
session_id BIGINT,
strengths TEXT,
weaknesses TEXT,
suggestions TEXT,
summary TEXT,
create_time DATETIME
);

V1不做数值评分
只保留文字评价

---

# 6. API设计

## 创建面试

POST

/api/interview/start

Request

{
"roleName": "Java后端"
}

Response

{
"sessionId": "abc123"
}

---

## 面试聊天

POST

/api/interview/chat

Request

{
"sessionId": "abc123",
"message": "我负责过Kafka消息治理系统"
}

Response

{
"reply": "Kafka如何保证消息不丢失？"
}

---

## 结束面试

POST

/api/interview/end

Request

{
"sessionId": "abc123"
}

Response

{
"evaluation": {
"strengths": "...",
"weaknesses": "...",
"suggestions": "..."
}
}

---

## 查询历史

GET

/api/interview/history/{sessionId}

---

# 7. Prompt设计

## interviewer.txt

你是一位经验丰富的技术面试官。

岗位：
{role_name}

请根据候选人的回答进行面试。

要求：

1. 一次只提一个问题
2. 优先深挖项目经验
3. 避免连续问八股文
4. 保持真实面试风格

---

## followup.txt

根据用户回答继续深挖。

回答：

{user_answer}

要求：

1. 深挖技术细节
2. 深挖设计原因
3. 深挖问题排查过程

---

## evaluation.txt

请根据完整面试记录生成：

1. 优势
2. 不足
3. 改进建议

---

# 8. V1业务流程

            用户进入系统
                ↓
            选择岗位
                ↓
            创建session
                ↓
            LLM生成首题
                ↓
            用户回答
                ↓
            LLM追问
                ↓
            循环
                ↓
            用户结束面试
                ↓
            生成评价
                ↓
            保存评价

---

# 9. V2规划（Agent）

引入：

LangGraph

新增：

agents/interview_agent.py

State:

class InterviewState:

```
role_name

history

round_no

evaluation
```

支持：

* Memory
* Checkpoint
* Human Review

---

# 10. V3规划（Tool）

新增工具：

QuestionTool

ProjectTool

EvaluationTool

Agent根据需要自动调用工具。

---

# 11. V4规划（RAG）

新增：

项目经验知识库

面试题知识库

技术文档知识库

技术：

Embedding

Vector Database

Retriever

Reranker

---

# 12. V5规划（Multi-Agent）

Resume Agent

JD Agent

Interview Agent

Evaluation Agent

Coordinator Agent

形成完整AI求职系统。

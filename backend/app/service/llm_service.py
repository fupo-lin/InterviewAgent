import json

import httpx

from app.config.settings import settings
from app.models.interview import InterviewMessage
from app.service.prompt_service import load_prompt


class LLMService:
    def __init__(self) -> None:
        self.api_key = settings.glm_api_key
        self.api_base = settings.glm_api_base.rstrip("/")
        self.model = settings.glm_model

    async def generate_first_question(self, role_name: str) -> tuple[str, dict | None]:
        prompt = load_prompt("interviewer.txt", role_name=role_name)
        if not self.api_key:
            return self._mock_first_question(role_name), {"mock": True}
        return await self._chat_completion(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "请开始本次模拟面试，提出第一道问题。"},
            ]
        )

    async def generate_followup(
        self,
        role_name: str,
        user_answer: str,
        history: list[InterviewMessage],
    ) -> tuple[str, dict | None]:
        prompt = load_prompt("interviewer.txt", role_name=role_name)
        followup_prompt = load_prompt("followup.txt", user_answer=user_answer)
        if not self.api_key:
            return self._mock_followup(user_answer), {"mock": True}

        messages = [{"role": "system", "content": prompt}]
        for item in history[-12:]:
            role = "assistant" if item.role_type == "assistant" else "user"
            messages.append({"role": role, "content": item.content})
        messages.append({"role": "user", "content": followup_prompt})
        return await self._chat_completion(messages)

    async def generate_evaluation(self, history: list[InterviewMessage]) -> tuple[dict[str, str], dict | None]:
        prompt = load_prompt("evaluation.txt")
        transcript = "\n".join(
            f"{item.role_type}({item.message_type}, round {item.round_no}): {item.content}"
            for item in history
        )
        if not self.api_key:
            return self._mock_evaluation(history), {"mock": True}

        content, raw_response = await self._chat_completion(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": transcript},
            ]
        )
        return self._parse_evaluation(content), raw_response

    async def _chat_completion(self, messages: list[dict[str, str]]) -> tuple[str, dict | None]:
        payload = {"model": self.model, "messages": messages, "temperature": 0.7}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return content, data

    def _parse_evaluation(self, content: str) -> dict[str, str]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {
                "strengths": "",
                "weaknesses": "",
                "suggestions": "",
                "summary": content,
            }

        return {
            "strengths": str(parsed.get("strengths", "")),
            "weaknesses": str(parsed.get("weaknesses", "")),
            "suggestions": str(parsed.get("suggestions", "")),
            "summary": str(parsed.get("summary", "")),
        }

    def _mock_first_question(self, role_name: str) -> str:
        return f"我们先从项目经验开始。请介绍一个你最能体现{role_name}能力的项目，以及你负责的核心模块。"

    def _mock_followup(self, user_answer: str) -> str:
        if "Kafka" in user_answer or "消息" in user_answer:
            return "你刚才提到了消息相关系统。请具体说明如何保证消息不丢失，以及失败重试怎么设计？"
        if "MySQL" in user_answer or "数据库" in user_answer:
            return "你刚才提到了数据库。请说明这个场景下表结构如何设计，以及如何处理性能瓶颈？"
        if "Spring" in user_answer or "接口" in user_answer:
            return "请进一步说明这个模块的接口边界、异常处理和上线后你关注过哪些指标？"
        return "请继续展开一个关键技术决策：当时为什么这样设计，有哪些替代方案，最终效果如何？"

    def _mock_evaluation(self, history: list[InterviewMessage]) -> dict[str, str]:
        answer_count = len([item for item in history if item.role_type == "user"])
        return {
            "strengths": f"候选人完成了 {answer_count} 轮回答，能够围绕项目经历展开说明。",
            "weaknesses": "部分回答还可以继续补充量化指标、故障处理细节和设计取舍。",
            "suggestions": "建议准备 1 到 2 个完整项目案例，重点补充架构图、核心难点、性能数据和复盘结果。",
            "summary": "整体具备继续面试评估的基础，后续可以加深技术细节和系统设计深度。",
        }

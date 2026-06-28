import json
import re

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
        candidate_profile: str | None = None,
        conversation_summary: str | None = None,
    ) -> tuple[str, dict | None]:
        prompt = load_prompt("interviewer.txt", role_name=role_name)
        followup_prompt = load_prompt("followup.txt", user_answer=user_answer)
        if not self.api_key:
            return self._mock_followup(user_answer), {"mock": True}

        messages = [{"role": "system", "content": prompt}]
        context = self._build_memory_context(candidate_profile, conversation_summary)
        if context:
            messages.append({"role": "system", "content": context})
        for item in history:
            role = "assistant" if item.role_type == "assistant" else "user"
            messages.append({"role": role, "content": item.content})
        messages.append({"role": "user", "content": followup_prompt})
        return await self._chat_completion(messages)

    async def generate_evaluation(
        self,
        history: list[InterviewMessage],
        candidate_profile: str | None = None,
        conversation_summary: str | None = None,
    ) -> tuple[dict[str, str], dict | None]:
        prompt = load_prompt("evaluation.txt")
        transcript = "\n".join(
            f"{item.role_type}({item.message_type}, round {item.round_no}): {item.content}"
            for item in history
        )
        if not self.api_key:
            return self._mock_evaluation(history), {"mock": True}

        messages = [{"role": "system", "content": prompt}]
        context = self._build_memory_context(candidate_profile, conversation_summary)
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": transcript})
        content, raw_response = await self._chat_completion(
            messages
        )
        return self._parse_evaluation(content), raw_response

    async def generate_candidate_profile(
        self,
        previous_profile: str | None,
        new_messages: list[InterviewMessage],
    ) -> tuple[str, dict | None]:
        transcript = self._format_transcript(new_messages)
        if not transcript:
            return previous_profile or "", {"mock": True}

        prompt = load_prompt(
            "candidate_profile.txt",
            previous_profile=previous_profile or "暂无",
            new_transcript=transcript,
        )
        if not self.api_key:
            return self._mock_candidate_profile(previous_profile, new_messages), {"mock": True}

        return await self._chat_completion([{"role": "user", "content": prompt}])

    async def generate_conversation_summary(
        self,
        previous_summary: str | None,
        new_messages: list[InterviewMessage],
    ) -> tuple[str, dict | None]:
        transcript = self._format_transcript(new_messages)
        if not transcript:
            return previous_summary or "", {"mock": True}

        prompt = load_prompt(
            "conversation_summary.txt",
            previous_summary=previous_summary or "暂无",
            new_transcript=transcript,
        )
        if not self.api_key:
            return self._mock_conversation_summary(previous_summary, new_messages), {"mock": True}

        return await self._chat_completion([{"role": "user", "content": prompt}])

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

    def _format_transcript(self, messages: list[InterviewMessage]) -> str:
        return "\n".join(
            f"{item.role_type}({item.message_type}, round {item.round_no}): {item.content}"
            for item in messages
        )

    def _build_memory_context(self, candidate_profile: str | None, conversation_summary: str | None) -> str:
        parts = []
        if candidate_profile:
            parts.append(f"候选人稳定画像 CandidateProfile：\n{candidate_profile}")
        if conversation_summary:
            parts.append(f"面试对话摘要 ConversationSummary：\n{conversation_summary}")
        if not parts:
            return ""
        return "\n\n".join(parts)

# 
    def _parse_evaluation(self, content: str) -> dict[str, str]:
        text = content.strip()  # 1. 去除首尾的空白字符或换行符
        try:
            parsed = json.loads(text) # 2. 尝试直接解析（最理想的情况：大模型返回了完美的纯 JSON）
        except json.JSONDecodeError:
            json_text = self._extract_json_text(text) 
            if json_text is None:
                return self._fallback_evaluation(content)

            try:
                parsed = json.loads(json_text)
            except json.JSONDecodeError:
                return self._fallback_evaluation(content)

        return {
            "strengths": str(parsed.get("strengths", "")),
            "weaknesses": str(parsed.get("weaknesses", "")),
            "suggestions": str(parsed.get("suggestions", "")),
            "summary": str(parsed.get("summary", "")),
            "technical_ability": str(parsed.get("technical_ability", parsed.get("technicalAbility", ""))),
            "project_experience": str(parsed.get("project_experience", parsed.get("projectExperience", ""))),
            "communication": str(parsed.get("communication", "")),
            "improvement_suggestions": str(
                parsed.get("improvement_suggestions", parsed.get("improvementSuggestions", ""))
            ),
        }

#
    def _extract_json_text(self, content: str) -> str | None:
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.IGNORECASE | re.DOTALL)
        #  优先使用正则表达式，匹配 Markdown 的代码块 (```json ... ``` 或 ``` ... ```) re.DOTALL 表示让 . 可以匹配换行符，确保跨行匹配
        if fenced:
            return fenced.group(1).strip()  # 提取代码块里的内容并去除空白

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return content[start : end + 1] # 把从第一个 { 到最后一个 } 之间的内容全切出来

        return None

# 兜底方案 --  把大模型的返回内容直接放到 summary 字段里，其他字段为空字符串
    def _fallback_evaluation(self, content: str) -> dict[str, str]:
        return {
            "strengths": "",
            "weaknesses": "",
            "suggestions": "",
            "summary": content,
            "technical_ability": "",
            "project_experience": "",
            "communication": "",
            "improvement_suggestions": "",
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
            "technical_ability": "已能围绕技术方案展开回答，但还需要补充底层原理、边界条件和性能数据来证明技术深度。",
            "project_experience": f"本次共有 {answer_count} 轮候选人回答，项目描述具备基础脉络，后续建议强化个人贡献、业务影响和复盘结果。",
            "communication": "表达能够覆盖项目背景和处理思路，建议进一步使用问题、行动、结果的结构提升信息密度。",
            "improvement_suggestions": "建议准备可量化项目案例，补充架构图、关键指标、故障复盘和技术取舍，并用 STAR 方式组织回答。",
        }

    def _mock_candidate_profile(self, previous_profile: str | None, messages: list[InterviewMessage]) -> str:
        user_messages = [item.content for item in messages if item.role_type == "user"]
        latest = user_messages[-1] if user_messages else "暂无新增候选人回答"
        prefix = previous_profile.strip() + "\n" if previous_profile else ""
        return f"{prefix}候选人近期提到的稳定经历或技术背景包括：{latest[:200]}"

    def _mock_conversation_summary(self, previous_summary: str | None, messages: list[InterviewMessage]) -> str:
        rounds = sorted({item.round_no for item in messages})
        prefix = previous_summary.strip() + "\n" if previous_summary else ""
        return f"{prefix}已覆盖第 {rounds[0]} 到第 {rounds[-1]} 轮对话，后续应避免重复已问内容，并继续深挖回答中的技术细节、项目贡献和结果数据。"

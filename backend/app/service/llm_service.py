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

    async def generate_first_question(
        self,
        role_name: str,
        plan_context: str | None = None,
    ) -> tuple[str, dict | None]:
        prompt = load_prompt("interviewer.txt", role_name=role_name)
        if not self.api_key:
            return self._mock_first_question(role_name), {"mock": True}

        messages = [{"role": "system", "content": prompt}]
        if plan_context:
            messages.append({"role": "system", "content": plan_context})
        messages.append({"role": "user", "content": "请开始本次模拟面试，提出第一道问题。"})
        return await self._chat_completion(messages)

    async def generate_followup(
        self,
        role_name: str,
        user_answer: str,
        history: list[InterviewMessage],
        candidate_profile: str | None = None,
        conversation_summary: str | None = None,
        plan_context: str | None = None,
    ) -> tuple[str, dict | None]:
        prompt = load_prompt("interviewer.txt", role_name=role_name)
        followup_prompt = load_prompt("followup.txt", user_answer=user_answer)
        if not self.api_key:
            return self._mock_followup(user_answer), {"mock": True}

        messages = [{"role": "system", "content": prompt}]
        context = self._build_memory_context(candidate_profile, conversation_summary)
        if context:
            messages.append({"role": "system", "content": context})
        if plan_context:
            messages.append({"role": "system", "content": plan_context})
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
        plan_context: str | None = None,
    ) -> tuple[dict[str, str], dict | None]:
        prompt = load_prompt("evaluation.txt")
        transcript = self._format_transcript(history)
        if not self.api_key:
            return self._mock_evaluation(history), {"mock": True}

        messages = [{"role": "system", "content": prompt}]
        context = self._build_memory_context(candidate_profile, conversation_summary)
        if context:
            messages.append({"role": "system", "content": context})
        if plan_context:
            messages.append({"role": "system", "content": plan_context})
        messages.append({"role": "user", "content": transcript})
        content, raw_response = await self._chat_completion(messages)
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

    async def generate_jd_analysis(self, jd_content: str) -> tuple[dict, dict | None]:
        prompt = load_prompt("jd_analysis.txt", jd_content=jd_content)
        if not self.api_key:
            return self._mock_jd_analysis(jd_content), {"mock": True}

        content, raw_response = await self._chat_completion([{"role": "user", "content": prompt}])
        return self._parse_json_object(content, {"raw_text": content}), raw_response

    async def generate_resume_profile(self, resume_content: str) -> tuple[dict, dict | None]:
        prompt = load_prompt("resume_analysis.txt", resume_content=resume_content)
        if not self.api_key:
            return self._mock_resume_profile(resume_content), {"mock": True}

        content, raw_response = await self._chat_completion([{"role": "user", "content": prompt}])
        return self._parse_json_object(content, {"raw_text": content}), raw_response

    async def generate_gap_analysis(self, jd_analysis: dict, resume_profile: dict) -> tuple[dict, dict | None]:
        prompt = load_prompt(
            "gap_analysis.txt",
            jd_analysis=json.dumps(jd_analysis, ensure_ascii=False),
            resume_profile=json.dumps(resume_profile, ensure_ascii=False),
        )
        if not self.api_key:
            return self._mock_gap_analysis(), {"mock": True}

        content, raw_response = await self._chat_completion([{"role": "user", "content": prompt}])
        return self._parse_json_object(content, {"raw_text": content}), raw_response

    async def generate_interview_plan(
        self,
        plan_mode: str,
        jd_analysis: dict | None = None,
        resume_profile: dict | None = None,
        gap_analysis: dict | None = None,
        target_role: str | None = None,
    ) -> tuple[dict, dict | None]:
        prompt = load_prompt(
            "interview_plan.txt",
            plan_mode=plan_mode,
            target_role=target_role or "目标岗位",
            jd_analysis=json.dumps(jd_analysis or {}, ensure_ascii=False),
            resume_profile=json.dumps(resume_profile or {}, ensure_ascii=False),
            gap_analysis=json.dumps(gap_analysis or {}, ensure_ascii=False),
        )
        if not self.api_key:
            return self._mock_interview_plan(plan_mode, target_role, jd_analysis, resume_profile), {"mock": True}

        content, raw_response = await self._chat_completion([{"role": "user", "content": prompt}])
        return self._parse_json_object(content, {"raw_text": content}), raw_response

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
            parts.append(f"候选人稳定画像 CandidateProfile:\n{candidate_profile}")
        if conversation_summary:
            parts.append(f"面试对话摘要 ConversationSummary:\n{conversation_summary}")
        return "\n\n".join(parts)

    def _parse_evaluation(self, content: str) -> dict[str, str]:
        parsed = self._parse_json_object(content, {})
        if not parsed:
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

    def _parse_json_object(self, content: str, fallback: dict) -> dict:
        text = content.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            json_text = self._extract_json_text(text)
            if json_text is None:
                return fallback
            try:
                parsed = json.loads(json_text)
            except json.JSONDecodeError:
                return fallback
        return parsed if isinstance(parsed, dict) else fallback

    def _extract_json_text(self, content: str) -> str | None:
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            return fenced.group(1).strip()

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return content[start : end + 1]
        return None

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
            "technical_ability": "已能围绕技术方案展开回答，但还需要补充底层原理、边界条件和性能数据。",
            "project_experience": f"本次共有 {answer_count} 轮候选人回答，项目描述具备基础脉络。",
            "communication": "表达能够覆盖项目背景和处理思路，建议进一步提升信息密度。",
            "improvement_suggestions": "建议准备可量化项目案例，并用 STAR 方式组织回答。",
        }

    def _mock_candidate_profile(self, previous_profile: str | None, messages: list[InterviewMessage]) -> str:
        user_messages = [item.content for item in messages if item.role_type == "user"]
        latest = user_messages[-1] if user_messages else "暂无新增候选人回答"
        prefix = previous_profile.strip() + "\n" if previous_profile else ""
        return f"{prefix}候选人近期提到的稳定经历或技术背景包括：{latest[:200]}"

    def _mock_conversation_summary(self, previous_summary: str | None, messages: list[InterviewMessage]) -> str:
        rounds = sorted({item.round_no for item in messages})
        prefix = previous_summary.strip() + "\n" if previous_summary else ""
        return f"{prefix}已覆盖第 {rounds[0]} 到第 {rounds[-1]} 轮对话，后续应避免重复已问内容。"

    def _mock_jd_analysis(self, jd_content: str) -> dict:
        return {
            "job_title": "目标岗位",
            "seniority": "unknown",
            "core_responsibilities": [jd_content[:120]],
            "required_skills": [],
            "preferred_skills": [],
            "interview_focus": ["岗位核心职责", "项目经验", "技术深度", "问题排查能力"],
        }

    def _mock_resume_profile(self, resume_content: str) -> dict:
        return {
            "target_role": "unknown",
            "projects": [{"name": "简历项目", "summary": resume_content[:160]}],
            "skills": [],
            "strengths": ["具备可继续深挖的项目经历"],
            "risks": ["需要补充量化指标、个人贡献和技术取舍"],
        }

    def _mock_gap_analysis(self) -> dict:
        return {
            "overall_match_level": "unknown",
            "match_score": 0,
            "matched_points": [],
            "gap_points": [
                {
                    "jd_requirement": "岗位核心要求",
                    "resume_current_evidence": "需要通过面试继续验证",
                    "gap_level": "medium",
                    "interview_probe": "围绕项目证据、技术深度和岗位要求进行追问",
                }
            ],
            "interview_priorities": ["验证 JD 要求和简历证据是否匹配"],
        }

    def _mock_interview_plan(
        self,
        plan_mode: str,
        target_role: str | None,
        jd_analysis: dict | None,
        resume_profile: dict | None,
    ) -> dict:
        role_name = target_role or (jd_analysis or {}).get("job_title") or (resume_profile or {}).get("target_role") or "目标岗位"
        if plan_mode == "jd_only":
            seed = f"针对{role_name}这个岗位，你认为自己最匹配的一段项目经历是什么？请先介绍背景和你的职责。"
        elif plan_mode == "resume_only":
            seed = "请从简历中选择一个最能体现你技术深度的项目，说明项目背景、你的职责和核心难点。"
        else:
            seed = f"结合目标岗位{role_name}，请介绍一个你简历中最能证明岗位匹配度的项目。"
        return {
            "plan_mode": plan_mode,
            "role_name": role_name,
            "total_round_target": 10,
            "sections": [
                {
                    "section_key": "project_depth",
                    "title": "项目深挖",
                    "target_rounds": 4,
                    "goals": ["验证项目真实性", "确认个人贡献", "深挖技术取舍"],
                    "seed_questions": [seed],
                    "probe_points": ["项目背景", "个人贡献", "技术方案", "结果指标"],
                },
                {
                    "section_key": "technical_depth",
                    "title": "技术深度",
                    "target_rounds": 3,
                    "goals": ["验证底层理解", "验证边界场景", "验证问题排查能力"],
                    "seed_questions": [],
                    "probe_points": ["底层原理", "性能瓶颈", "异常处理", "线上稳定性"],
                },
            ],
            "evaluation_rubric": [
                {"dimension": "technical_depth", "weight": 35},
                {"dimension": "project_experience", "weight": 35},
                {"dimension": "communication", "weight": 30},
            ],
        }

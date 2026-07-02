import json
import re

import httpx

from app.config.settings import settings
from app.models.interview import InterviewMessage
from app.service.prompt_service import load_prompt
from app.service.prompt_registry import prompt_registry


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
        prompt = load_prompt(prompt_registry.prompt_file("interviewer"), role_name=role_name)
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
        execution_context: str | None = None,
    ) -> tuple[str, dict | None]:
        prompt = load_prompt(prompt_registry.prompt_file("interviewer"), role_name=role_name)
        followup_prompt = load_prompt(prompt_registry.prompt_file("followup"), user_answer=user_answer)
        if not self.api_key:
            return self._mock_followup(user_answer, execution_context), {"mock": True}

        messages = [{"role": "system", "content": prompt}]
        context = self._build_memory_context(candidate_profile, conversation_summary)
        if context:
            messages.append({"role": "system", "content": context})
        if plan_context:
            messages.append({"role": "system", "content": plan_context})
        if execution_context:
            messages.append({"role": "system", "content": execution_context})
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
        evidence_packet: dict | None = None,
    ) -> tuple[dict[str, str], dict | None]:
        prompt = load_prompt(prompt_registry.prompt_file("evaluation"))
        transcript = self._format_transcript(history)
        if not self.api_key:
            return self._mock_evaluation(history), {"mock": True}

        messages = [{"role": "system", "content": prompt}]
        context = self._build_memory_context(candidate_profile, conversation_summary)
        if context:
            messages.append({"role": "system", "content": context})
        if plan_context:
            messages.append({"role": "system", "content": plan_context})
        if evidence_packet:
            messages.append(
                {
                    "role": "system",
                    "content": f"结构化证据包 EvidencePacket:\n{json.dumps(evidence_packet, ensure_ascii=False)}",
                }
            )
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
            prompt_registry.prompt_file("candidate_profile"),
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
            prompt_registry.prompt_file("conversation_summary"),
            previous_summary=previous_summary or "暂无",
            new_transcript=transcript,
        )
        if not self.api_key:
            return self._mock_conversation_summary(previous_summary, new_messages), {"mock": True}

        return await self._chat_completion([{"role": "user", "content": prompt}])

    async def generate_jd_analysis(self, jd_content: str) -> tuple[dict, dict | None]:
        prompt = load_prompt(prompt_registry.prompt_file("jd_analysis"), jd_content=jd_content)
        if not self.api_key:
            return self._mock_jd_analysis(jd_content), {"mock": True}

        content, raw_response = await self._chat_completion([{"role": "user", "content": prompt}])
        return self._parse_json_object(content, {"raw_text": content}), raw_response

    async def generate_resume_profile(self, resume_content: str) -> tuple[dict, dict | None]:
        prompt = load_prompt(prompt_registry.prompt_file("resume_analysis"), resume_content=resume_content)
        if not self.api_key:
            return self._mock_resume_profile(resume_content), {"mock": True}

        content, raw_response = await self._chat_completion([{"role": "user", "content": prompt}])
        return self._parse_json_object(content, {"raw_text": content}), raw_response

    async def generate_gap_analysis(self, jd_analysis: dict, resume_profile: dict) -> tuple[dict, dict | None]:
        prompt = load_prompt(
            prompt_registry.prompt_file("gap_analysis"),
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
            prompt_registry.prompt_file("interview_plan"),
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

    async def judge_topic_completion(
        self,
        current_section: dict,
        execution_state: dict,
        user_answer: str,
        recent_history: list[InterviewMessage],
    ) -> tuple[dict, dict | None]:
        prompt = load_prompt(
            prompt_registry.prompt_file("topic_completion_judge"),
            current_section=json.dumps(current_section or {}, ensure_ascii=False),
            execution_state=json.dumps(execution_state or {}, ensure_ascii=False),
            recent_history=self._format_transcript(recent_history),
            user_answer=user_answer,
        )
        if not self.api_key:
            return self._mock_topic_completion(current_section, execution_state, user_answer), {"mock": True}

        content, raw_response = await self._chat_completion([{"role": "user", "content": prompt}])
        return self._parse_json_object(content, self._mock_topic_completion(current_section, execution_state, user_answer)), raw_response

    async def generate_project_candidate_profile(
        self,
        target_role: str | None,
        jd_analysis: dict | None = None,
        resume_profile: dict | None = None,
        gap_analysis: dict | None = None,
        execution_state: dict | None = None,
        evaluation: dict | None = None,
        transcript_messages: list[InterviewMessage] | None = None,
        evidence_packet: dict | None = None,
    ) -> tuple[dict, dict | None]:
        prompt = load_prompt(
            prompt_registry.prompt_file("project_candidate_profile"),
            target_role=target_role or "目标岗位",
            jd_analysis=json.dumps(jd_analysis or {}, ensure_ascii=False),
            resume_profile=json.dumps(resume_profile or {}, ensure_ascii=False),
            gap_analysis=json.dumps(gap_analysis or {}, ensure_ascii=False),
            execution_state=json.dumps(execution_state or {}, ensure_ascii=False),
            evaluation=json.dumps(evaluation or {}, ensure_ascii=False),
            transcript=self._format_transcript(transcript_messages or []),
            evidence_packet=json.dumps(evidence_packet or {}, ensure_ascii=False),
        )
        if not self.api_key:
            return self._mock_project_candidate_profile(
                target_role,
                resume_profile,
                execution_state,
                evaluation,
                transcript_messages or [],
            ), {"mock": True}

        content, raw_response = await self._chat_completion([{"role": "user", "content": prompt}])
        return self._parse_json_object(
            content,
            self._mock_project_candidate_profile(
                target_role,
                resume_profile,
                execution_state,
                evaluation,
                transcript_messages or [],
            ),
        ), raw_response

    async def generate_resume_authenticity_report(
        self,
        resume_content: str,
        resume_profile: dict | None = None,
        jd_analysis: dict | None = None,
        gap_analysis: dict | None = None,
        project_candidate_profile: dict | None = None,
        execution_state: dict | None = None,
        evaluation: dict | None = None,
        transcript_messages: list[InterviewMessage] | None = None,
        evidence_packet: dict | None = None,
    ) -> tuple[dict, dict | None]:
        prompt = load_prompt(
            prompt_registry.prompt_file("resume_authenticity"),
            resume_content=resume_content,
            resume_profile=json.dumps(resume_profile or {}, ensure_ascii=False),
            jd_analysis=json.dumps(jd_analysis or {}, ensure_ascii=False),
            gap_analysis=json.dumps(gap_analysis or {}, ensure_ascii=False),
            project_candidate_profile=json.dumps(project_candidate_profile or {}, ensure_ascii=False),
            execution_state=json.dumps(execution_state or {}, ensure_ascii=False),
            evaluation=json.dumps(evaluation or {}, ensure_ascii=False),
            transcript=self._format_transcript(transcript_messages or []),
            evidence_packet=json.dumps(evidence_packet or {}, ensure_ascii=False),
        )
        if not self.api_key:
            return self._mock_resume_authenticity_report(
                resume_content,
                resume_profile,
                project_candidate_profile,
                evaluation,
                transcript_messages or [],
            ), {"mock": True}

        content, raw_response = await self._chat_completion([{"role": "user", "content": prompt}])
        return self._parse_json_object(
            content,
            self._mock_resume_authenticity_report(
                resume_content,
                resume_profile,
                project_candidate_profile,
                evaluation,
                transcript_messages or [],
            ),
        ), raw_response

    async def generate_resume_rewrite(
        self,
        rewrite_mode: str,
        resume_content: str,
        resume_profile: dict | None = None,
        jd_analysis: dict | None = None,
        gap_analysis: dict | None = None,
        project_candidate_profile: dict | None = None,
        resume_authenticity: dict | None = None,
        evaluation: dict | None = None,
        execution_state: dict | None = None,
        evidence_packet: dict | None = None,
    ) -> tuple[dict, dict | None]:
        prompt = load_prompt(
            prompt_registry.prompt_file("resume_rewrite"),
            rewrite_mode=rewrite_mode,
            resume_content=resume_content,
            resume_profile=json.dumps(resume_profile or {}, ensure_ascii=False),
            jd_analysis=json.dumps(jd_analysis or {}, ensure_ascii=False),
            gap_analysis=json.dumps(gap_analysis or {}, ensure_ascii=False),
            project_candidate_profile=json.dumps(project_candidate_profile or {}, ensure_ascii=False),
            resume_authenticity=json.dumps(resume_authenticity or {}, ensure_ascii=False),
            evaluation=json.dumps(evaluation or {}, ensure_ascii=False),
            execution_state=json.dumps(execution_state or {}, ensure_ascii=False),
            evidence_packet=json.dumps(evidence_packet or {}, ensure_ascii=False),
        )
        if not self.api_key:
            return self._mock_resume_rewrite(
                rewrite_mode,
                resume_content,
                resume_profile,
                resume_authenticity,
                project_candidate_profile,
            ), {"mock": True}

        content, raw_response = await self._chat_completion([{"role": "user", "content": prompt}])
        return self._parse_json_object(
            content,
            self._mock_resume_rewrite(
                rewrite_mode,
                resume_content,
                resume_profile,
                resume_authenticity,
                project_candidate_profile,
            ),
        ), raw_response

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

    def _mock_followup(self, user_answer: str, execution_context: str | None = None) -> str:
        if execution_context and "next_action: move_next_section" in execution_context:
            return "我们切到下一个考察点。请结合一个具体场景说明你在这个方向上遇到过的主要难点，以及你当时怎么处理？"
        if execution_context and "next_action: wrap_up_interview" in execution_context:
            return "最后请你总结一下：如果重新做刚才提到的项目，你认为最值得改进的一点是什么？"
        if execution_context and "suggested_probe_point:" in execution_context:
            probe_point = execution_context.split("suggested_probe_point:", 1)[1].splitlines()[0].strip()
            if probe_point:
                return f"我们聚焦到「{probe_point}」。请结合你刚才的项目，说明这个点当时是怎么落地的，以及你个人负责了哪一部分？"
        if "Kafka" in user_answer or "消息" in user_answer:
            return "你刚才提到了消息相关系统。请具体说明如何保证消息不丢失，以及失败重试怎么设计？"
        if "MySQL" in user_answer or "数据库" in user_answer:
            return "你刚才提到了数据库。请说明这个场景下表结构如何设计，以及如何处理性能瓶颈？"
        if "Spring" in user_answer or "接口" in user_answer:
            return "请进一步说明这个模块的接口边界、异常处理和上线后你关注过哪些指标？"
        return "请继续展开一个关键技术决策：当时为什么这样设计，有哪些替代方案，最终效果如何？"

    def _mock_topic_completion(self, current_section: dict, execution_state: dict, user_answer: str) -> dict:
        uncovered = list(current_section.get("uncovered_probe_points") or [])
        completed_rounds = int(current_section.get("completed_rounds") or 0)
        target_rounds = int(current_section.get("target_rounds") or 1)
        answer = user_answer.strip()
        answer_quality = "low" if len(answer) < 30 else "medium"
        if any(keyword in answer for keyword in ("QPS", "指标", "上线", "压测", "故障", "方案", "原因", "负责", "设计")):
            answer_quality = "high" if len(answer) >= 50 else "medium"

        covered = []
        if uncovered and answer_quality != "low":
            covered.append(uncovered[0])
        missing = [item for item in uncovered if item not in covered]

        next_action = "continue_current_topic"
        topic_status = "insufficient"
        reason = "回答还比较简略，需要继续围绕当前话题追问"
        if answer_quality == "low":
            next_action = "continue_current_topic"
        elif completed_rounds + 1 >= target_rounds or not missing:
            next_action = "move_next_section"
            topic_status = "complete"
            reason = "当前 section 已达到目标轮数或关键 probe point 已基本覆盖"
        elif missing:
            next_action = "switch_topic_in_section"
            topic_status = "complete"
            reason = "本轮回答已有有效信息，可以切到当前 section 的下一个 probe point"

        return {
            "topic_status": topic_status,
            "answer_quality": answer_quality,
            "covered_probe_points": covered,
            "missing_probe_points": missing,
            "next_action": next_action,
            "next_question_intent": f"围绕{missing[0]}继续提问" if missing else "进入下一个面试阶段",
            "reason": reason,
            "confidence": "medium",
        }

    def _mock_project_candidate_profile(
        self,
        target_role: str | None,
        resume_profile: dict | None,
        execution_state: dict | None,
        evaluation: dict | None,
        transcript_messages: list[InterviewMessage],
    ) -> dict:
        user_answers = [item.content for item in transcript_messages if item.role_type == "user"]
        sections = (execution_state or {}).get("sections") or []
        evidence = []
        for section in sections:
            for item in section.get("evidence") or []:
                evidence.append(f"第 {item.get('round_no')} 轮：{item.get('answer_excerpt', '')[:120]}")

        return {
            "basic_profile": {
                "target_role": target_role or (resume_profile or {}).get("target_role") or "unknown",
                "years_of_experience": "unknown",
                "main_domains": [],
                "main_tech_stack": (resume_profile or {}).get("skills", []),
            },
            "project_experience": [
                {
                    "project_name": ((resume_profile or {}).get("projects") or [{}])[0].get("name", "简历项目"),
                    "verified_level": "medium" if user_answers else "unknown",
                    "candidate_role": "需要结合后续面试继续确认",
                    "verified_contributions": evidence[:5],
                    "unverified_claims": (resume_profile or {}).get("risks", []),
                    "evidence_rounds": [item.round_no for item in transcript_messages if item.role_type == "user"],
                }
            ],
            "capability_profile": {
                "technical_depth": {
                    "level": "unknown",
                    "evidence": [],
                },
                "system_design": {
                    "level": "unknown",
                    "evidence": [],
                },
                "troubleshooting": {
                    "level": "unknown",
                    "evidence": [],
                },
                "communication": {
                    "level": "medium" if user_answers else "unknown",
                    "evidence": [f"已完成 {len(user_answers)} 轮面试回答"],
                },
            },
            "risk_profile": [
                {
                    "risk": "部分经历仍缺少量化指标或强证据",
                    "severity": "medium",
                    "evidence": (evaluation or {}).get("weaknesses", ""),
                }
            ],
            "learning_needs": ["补充项目量化指标", "准备关键技术方案的取舍说明"],
            "resume_optimization_focus": ["突出已验证的个人贡献", "弱化证据不足的夸大表述"],
            "summary": (evaluation or {}).get("summary", "已基于当前面试过程生成候选人项目画像。"),
        }

    def _mock_resume_authenticity_report(
        self,
        resume_content: str,
        resume_profile: dict | None,
        project_candidate_profile: dict | None,
        evaluation: dict | None,
        transcript_messages: list[InterviewMessage],
    ) -> dict:
        projects = (resume_profile or {}).get("projects") or []
        project_name = projects[0].get("name", "简历项目") if projects else "简历项目"
        user_answer_count = len([item for item in transcript_messages if item.role_type == "user"])
        verified_contributions = []
        for item in (project_candidate_profile or {}).get("project_experience", []):
            verified_contributions.extend(item.get("verified_contributions") or [])

        status = "partially_supported" if user_answer_count else "unclear"
        overall = "medium" if user_answer_count >= 3 else "unknown"
        return {
            "overall_authenticity": overall,
            "claim_checks": [
                {
                    "resume_claim": f"{project_name} 相关项目经历与技术贡献",
                    "status": status,
                    "evidence": "；".join(verified_contributions[:3]) or (evaluation or {}).get("summary", ""),
                    "risk_level": "medium",
                    "suggestion": "保留已能讲清的个人贡献，补充量化指标、上线效果和技术取舍；不要强化尚未被面试证据支撑的主导性表述。",
                }
            ],
            "unsupported_claims": [],
            "strongly_supported_claims": verified_contributions[:5],
            "rewrite_constraints": [
                "不要把未验证内容写成强事实",
                "不要强化缺少证据的主导权或高并发规模",
                "优先突出面试中已经讲清楚的个人贡献",
            ],
            "missing_evidence_to_collect": [
                "项目量化指标",
                "个人负责边界",
                "技术方案取舍",
                "上线后效果数据",
            ],
            "summary": "当前简历内容有一定面试证据支撑，但仍建议补充可量化结果和更清晰的个人贡献边界。",
        }

    def _mock_resume_rewrite(
        self,
        rewrite_mode: str,
        resume_content: str,
        resume_profile: dict | None,
        resume_authenticity: dict | None,
        project_candidate_profile: dict | None,
    ) -> dict:
        projects = (resume_profile or {}).get("projects") or []
        project_name = projects[0].get("name", "简历项目") if projects else "简历项目"
        constraints = (resume_authenticity or {}).get("rewrite_constraints") or []
        verified = []
        for item in (project_candidate_profile or {}).get("project_experience", []):
            verified.extend(item.get("verified_contributions") or [])

        rewritten = (
            f"参与{project_name}相关后端功能建设，围绕已验证的项目职责梳理业务流程、技术实现和异常处理，"
            "重点突出个人负责边界、方案取舍和上线效果。"
        )
        return {
            "rewrite_mode": rewrite_mode,
            "summary": "已基于当前面试证据和真实性约束生成安全版简历优化建议。",
            "rewritten_sections": [
                {
                    "section": "project",
                    "original": resume_content[:300],
                    "rewritten": rewritten,
                    "reason": "原始表述需要更突出个人贡献，并避免强化证据不足的内容。",
                    "evidence_basis": verified[:5],
                }
            ],
            "missing_info_to_collect": (resume_authenticity or {}).get("missing_evidence_to_collect")
            or ["项目量化指标", "个人负责边界", "上线后效果"],
            "risk_warnings": constraints
            or ["不要把未验证内容写成强事实", "不要补造项目规模或性能指标"],
            "ats_keywords": (resume_profile or {}).get("skills", []),
            "final_suggestions": [
                "补充可量化指标后再进一步强化项目结果",
                "把面试中能讲清楚的贡献放在项目描述前半部分",
            ],
        }

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

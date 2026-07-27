from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel

# 将输入输出定义为明确的 Pydantic 模型，建议一套强类型的数据契约
# 大模型本质上是一个黑盒，如果不加以约束，它返回的数据可能会随时漂移
# 模型默认返回的是自由文本。如果业务代码直接用 json.loads() 去解析，一旦大模型漏掉一个字段或拼错一个单词，整个程序就会抛出异常崩溃
#处理之后底层的 LLM 调用层会将这些 Pydantic 类转化为 JSON Schema 传给大模型，强制大模型按照这个模具返回数据。如果大模型返回的数据不符合这个类，Pydantic 会直接拦截并报错
class AgentContractValidation(BaseModel):
    schema_version: str = "AgentContractValidation.v1"
    input_schema: str | None = None
    output_schema: str | None = None
    input_ok: bool = True
    output_ok: bool = True
    errors: list[str] = Field(default_factory=list)


class ProjectAgentContextRefs(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    jd_analysis_id: int | None = None
    resume_profile_id: int | None = None
    gap_analysis_id: int | None = None
    project_candidate_profile_id: int | None = None


class JDAnalysisInputV1(BaseModel):
    project_id: int = Field(gt=0)
    jd_id: int = Field(gt=0)
    content_length: int = Field(gt=0)
    has_title: bool = False
    has_company_name: bool = False
    has_source_url: bool = False


class JDAnalysisV1(BaseModel):
    job_title: str = ""
    seniority: str = ""
    core_responsibilities: list[Any] = Field(default_factory=list)
    required_skills: list[Any] = Field(default_factory=list)
    preferred_skills: list[Any] = Field(default_factory=list)
    interview_focus: list[Any] = Field(default_factory=list)


class ResumeAnalysisInputV1(BaseModel):
    project_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    content_length: int = Field(gt=0)
    file_name: str | None = None
    file_type: str | None = None


class ResumeProfileV1(BaseModel):
    target_role: str = ""
    projects: list[Any] = Field(default_factory=list)
    skills: list[Any] = Field(default_factory=list)
    strengths: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)


class GapAnalysisInputV1(BaseModel):
    project_id: int = Field(gt=0)
    jd_analysis_id: int = Field(gt=0)
    resume_profile_id: int = Field(gt=0)
    jd_analysis_schema_version: str | None = None
    resume_profile_schema_version: str | None = None


class GapAnalysisV1(BaseModel):
    overall_match_level: str = ""
    match_score: int | float = 0
    matched_points: list[Any] = Field(default_factory=list)
    gap_points: list[Any] = Field(default_factory=list)
    interview_priorities: list[Any] = Field(default_factory=list)


class InterviewPlanInputV1(BaseModel):
    project_id: int = Field(gt=0)
    target_role: str | None = None
    plan_mode: str = Field(min_length=1, max_length=30)
    has_jd_analysis: bool = False
    has_resume_profile: bool = False
    has_gap_analysis: bool = False
    context_refs: ProjectAgentContextRefs = Field(default_factory=ProjectAgentContextRefs)


class InterviewPlanV1(BaseModel):
    plan_mode: str = ""
    role_name: str = ""
    total_round_target: int = 0
    sections: list[Any] = Field(default_factory=list)
    evaluation_rubric: list[Any] = Field(default_factory=list)


class InterviewExecutorInputV1(BaseModel):
    step_id: str = Field(min_length=1, max_length=40)
    session_id: int = Field(gt=0)
    project_id: int | None = Field(default=None, gt=0)
    role_name: str = Field(min_length=1)
    interview_plan_id: int | None = Field(default=None, gt=0)
    answer_message_id: int | None = Field(default=None, gt=0)
    answer_content_length: int | None = Field(default=None, gt=0)
    round_no: int | None = Field(default=None, ge=0)
    recent_history_count: int = Field(default=0, ge=0)
    has_candidate_profile: bool = False
    has_conversation_summary: bool = False
    has_plan_context: bool = False
    has_execution_context: bool = False
    candidate_profile_summary_id: int | None = Field(default=None, gt=0)
    conversation_summary_id: int | None = Field(default=None, gt=0)
    execution_id: int | None = Field(default=None, gt=0)


class InterviewQuestionOutputV1(RootModel[str]):
    root: str = Field(min_length=1)


class SessionMemoryInputV1(BaseModel):
    prompt_id: str = Field(min_length=1, max_length=60)
    session_id: int = Field(gt=0)
    project_id: int | None = Field(default=None, gt=0)
    previous_summary_id: int | None = Field(default=None, gt=0)
    message_count: int = Field(ge=0)
    from_round_no: int | None = Field(default=None, ge=0)
    to_round_no: int | None = Field(default=None, ge=0)
    has_previous_content: bool = False


class SessionMemoryOutputV1(RootModel[str]):
    root: str = Field(min_length=1)


class TopicJudgeInputV1(BaseModel):
    session_id: int = Field(gt=0)
    project_id: int | None = Field(default=None, gt=0)
    interview_plan_id: int | None = Field(default=None, gt=0)
    execution_id: int = Field(gt=0)
    answer_message_id: int = Field(gt=0)
    answer_content_length: int = Field(gt=0)
    round_no: int | None = Field(default=None, ge=0)
    current_section_key: str | None = None
    current_section_completed_rounds: int | None = Field(default=None, ge=0)
    current_section_target_rounds: int | None = Field(default=None, ge=0)
    probe_point_count: int = Field(default=0, ge=0)
    uncovered_probe_point_count: int = Field(default=0, ge=0)
    recent_history_count: int = Field(ge=0)


class TopicJudgeResultV1(BaseModel):
    topic_status: str = ""
    answer_quality: str = ""
    covered_probe_points: list[Any] = Field(default_factory=list)
    missing_probe_points: list[Any] = Field(default_factory=list)
    technical_highlights: list[Any] = Field(default_factory=list)
    open_threads: list[Any] = Field(default_factory=list)
    project_claims: list[Any] = Field(default_factory=list)
    missing_details: list[Any] = Field(default_factory=list)
    risk_signals: list[Any] = Field(default_factory=list)
    next_action: str = ""
    next_question_intent: str = ""
    reason: str = ""
    confidence: str = ""

# 
class EvaluationInputV1(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: int = Field(gt=0)
    project_id: int | None = Field(default=None, gt=0)
    history_message_count: int = Field(ge=0) # 必须大于 0
    full_history_message_count: int = Field(ge=0)
    execution_id: int | None = Field(default=None, gt=0)
    candidate_profile_summary_id: int | None = Field(default=None, gt=0) 
    conversation_summary_id: int | None = Field(default=None, gt=0)
    interview_plan_id: int | None = Field(default=None, gt=0)
    has_plan_context: bool = False


class InterviewEvaluationV1(BaseModel):
    strengths: str = ""
    weaknesses: str = ""
    suggestions: str = ""
    summary: str = ""
    technical_ability: str = ""
    project_experience: str = ""
    communication: str = ""
    improvement_suggestions: str = ""


class ProjectCandidateProfileInputV1(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_id: int = Field(gt=0)
    target_role: str | None = None
    source_session_id: int | None = Field(default=None, gt=0)
    has_evaluation: bool = False
    transcript_message_count: int = Field(ge=0)
    context_refs: ProjectAgentContextRefs = Field(default_factory=ProjectAgentContextRefs)


class ProjectCandidateProfileV1(BaseModel):
    basic_profile: dict[str, Any] = Field(default_factory=dict)
    project_experience: list[Any] = Field(default_factory=list)
    capability_profile: dict[str, Any] = Field(default_factory=dict)
    risk_profile: list[Any] = Field(default_factory=list)
    learning_needs: list[Any] = Field(default_factory=list)
    resume_optimization_focus: list[Any] = Field(default_factory=list)
    summary: str = ""


class ResumeAuthenticityInputV1(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    resume_content: str = Field(min_length=1)  # 不能为空字符串
    session_id: int | None = Field(default=None, gt=0)
    execution_state: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    transcript_messages: list[Any] | None = None
    context_refs: ProjectAgentContextRefs = Field(default_factory=ProjectAgentContextRefs)


class ResumeClaimCheckV1(BaseModel):
    resume_claim: str = ""
    status: str = ""
    evidence: str = ""
    risk_level: str = ""
    suggestion: str = ""


class ResumeAuthenticityReportV1(BaseModel):
    overall_authenticity: str = ""
    claim_checks: list[ResumeClaimCheckV1] = Field(default_factory=list)
    unsupported_claims: list[Any] = Field(default_factory=list)
    strongly_supported_claims: list[Any] = Field(default_factory=list)
    rewrite_constraints: list[str] = Field(default_factory=list)
    missing_evidence_to_collect: list[str] = Field(default_factory=list)
    summary: str = ""


class ResumeRewriteInputV1(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_id: int = Field(gt=0)
    resume_id: int = Field(gt=0)
    resume_content: str = Field(min_length=1)
    rewrite_mode: str = Field(min_length=1, max_length=30)
    authenticity_report_id: int | None = Field(default=None, gt=0)
    resume_authenticity: dict[str, Any] | None = None
    execution_state: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    transcript_messages: list[Any] | None = None
    context_refs: ProjectAgentContextRefs = Field(default_factory=ProjectAgentContextRefs)


class RewrittenSectionV1(BaseModel):
    section: str = ""
    original: str = ""
    rewritten: str = ""
    reason: str = ""
    evidence_basis: list[Any] = Field(default_factory=list)


class ResumeRewriteResultV1(BaseModel):
    rewrite_mode: str = ""
    summary: str = ""
    rewritten_sections: list[RewrittenSectionV1] = Field(default_factory=list)
    missing_info_to_collect: list[str] = Field(default_factory=list)
    risk_warnings: list[str] = Field(default_factory=list)
    ats_keywords: list[Any] = Field(default_factory=list)
    final_suggestions: list[str] = Field(default_factory=list)


class GrowthReportContextRefs(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    evaluation_id: int | None = None
    execution_id: int | None = None
    jd_analysis_id: int | None = None
    resume_profile_id: int | None = None
    gap_analysis_id: int | None = None
    project_candidate_profile_id: int | None = None
    resume_authenticity_report_id: int | None = None


class CandidateGrowthReportInputV1(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: int = Field(gt=0)
    project_id: int | None = Field(default=None, gt=0)
    role_name: str = Field(min_length=1)
    transcript_message_count: int = Field(ge=0)
    user_answer_count: int = Field(ge=0)
    has_evaluation: bool = False
    has_jd_analysis: bool = False
    has_resume_profile: bool = False
    has_gap_analysis: bool = False
    has_project_candidate_profile: bool = False
    has_resume_authenticity: bool = False
    context_refs: GrowthReportContextRefs = Field(default_factory=GrowthReportContextRefs)


class CandidateGrowthReportV1(BaseModel):
    report_version: str = "v1"
    overall_summary: dict[str, Any] = Field(default_factory=dict)
    job_match: dict[str, Any] = Field(default_factory=dict)
    technical_strengths: list[Any] = Field(default_factory=list)
    technical_gaps: list[Any] = Field(default_factory=list)
    project_storytelling: dict[str, Any] = Field(default_factory=dict)
    authenticity_risks: list[Any] = Field(default_factory=list)
    resume_suggestions: list[Any] = Field(default_factory=list)
    next_interview_focus: list[Any] = Field(default_factory=list)
    learning_plan: list[Any] = Field(default_factory=list)
    evidence_references: list[Any] = Field(default_factory=list)

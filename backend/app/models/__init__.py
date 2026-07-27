from app.models.agent import AgentEvidenceItem, AgentRun
from app.models.workflow import WorkflowRun
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.interview import (
    InterviewEvaluation,
    InterviewMessage,
    InterviewPlanExecution,
    InterviewSession,
    InterviewSummary,
)
from app.models.preparation import (
    CandidateGrowthReport,
    GapAnalysis,
    InterviewPlan,
    JDAnalysis,
    JobDescription,
    PreparationProject,
    ProjectCandidateProfile,
    ResumeAuthenticityReport,
    ResumeDocument,
    ResumeProfile,
    ResumeRewriteResult,
)

__all__ = [
    "AgentRun",
    "AgentEvidenceItem",
    "WorkflowRun",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "InterviewSession",
    "InterviewMessage",
    "InterviewEvaluation",
    "InterviewSummary",
    "InterviewPlanExecution",
    "PreparationProject",
    "JobDescription",
    "JDAnalysis",
    "ResumeDocument",
    "ResumeProfile",
    "GapAnalysis",
    "InterviewPlan",
    "ProjectCandidateProfile",
    "ResumeAuthenticityReport",
    "ResumeRewriteResult",
    "CandidateGrowthReport",
]


# 将散落在不同子模块的模型类统一导入到当前模块中，方便在其他地方直接从 app.models 导入使用
#如果没有这段代码，外部使用的时候必须从子模块导入模型类，例如 from app.models.agent import AgentRun，而不能直接 from app.models import AgentRun

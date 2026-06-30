from dataclasses import dataclass, field


@dataclass(frozen=True)
class PromptDefinition:
    prompt_id: str
    prompt_file: str
    version: str
    owner_agent: str
    task: str
    input_schema: str
    output_schema: str
    required_context: tuple[str, ...] = field(default_factory=tuple)
    optional_context: tuple[str, ...] = field(default_factory=tuple)
    required_evidence: tuple[str, ...] = field(default_factory=tuple)


class PromptRegistry:
    def __init__(self) -> None:
        self._definitions = {
            item.prompt_id: item
            for item in (
                PromptDefinition(
                    prompt_id="resume_authenticity",
                    prompt_file="resume_authenticity.txt",
                    version="3.0.0",
                    owner_agent="ResumeAuthenticityAgent",
                    task="resume_authenticity_check",
                    input_schema="ResumeAuthenticityInput.v1",
                    output_schema="ResumeAuthenticityReport.v1",
                    required_context=("ResumeDocument", "ResumeProfile"),
                    optional_context=("JDAnalysis", "GapAnalysis", "ProjectCandidateProfile", "Evaluation"),
                    required_evidence=("resume_claim", "interview_answer", "execution_probe"),
                ),
                PromptDefinition(
                    prompt_id="resume_rewrite",
                    prompt_file="resume_rewrite.txt",
                    version="3.0.0",
                    owner_agent="ResumeRewriteAgent",
                    task="resume_rewrite",
                    input_schema="ResumeRewriteInput.v1",
                    output_schema="ResumeRewriteResult.v1",
                    required_context=("ResumeDocument", "ResumeProfile"),
                    optional_context=("JDAnalysis", "GapAnalysis", "ProjectCandidateProfile", "Evaluation"),
                    required_evidence=("resume_claim", "authenticity_check"),
                ),
            )
        }

    def get(self, prompt_id: str) -> PromptDefinition:
        definition = self._definitions.get(prompt_id)
        if not definition:
            raise KeyError(f"Prompt definition not found: {prompt_id}")
        return definition


prompt_registry = PromptRegistry()

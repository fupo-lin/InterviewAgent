from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt(name: str, **kwargs: str) -> str:
    template = (PROMPT_DIR / name).read_text(encoding="utf-8")
    if not kwargs:
        return template

    for key, value in kwargs.items():
        template = template.replace("{" + key + "}", value)
    return template

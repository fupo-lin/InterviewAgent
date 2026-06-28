from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"

## **kwargs: str：接收任意数量的关键字参数（键值对），用于替换模板中的占位符。例如 role_name="Python工程师"。
def load_prompt(name: str, **kwargs: str) -> str:
    template = (PROMPT_DIR / name).read_text(encoding="utf-8")
    if not kwargs:
        return template

    for key, value in kwargs.items():
        template = template.replace("{" + key + "}", value)
    return template

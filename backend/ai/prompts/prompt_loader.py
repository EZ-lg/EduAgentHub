"""
Prompt 模板加载器 — 基于 Jinja2

用法：
    from backend.ai.prompts.prompt_loader import render_prompt
    prompt = render_prompt("conversation.txt", subject_name="数学", student_name="张三", history=...)
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROMPT_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(str(PROMPT_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    # 模板中未传入的变量直接报错，避免静默渲染成空串导致 Prompt 缺失
    undefined=StrictUndefined,
)


def render_prompt(name: str, **kwargs) -> str:
    """渲染指定名称的 prompt 模板（name 如 conversation.txt）"""
    template = _env.get_template(name)
    return template.render(**kwargs)


def get_template(name: str):
    """获取 Jinja2 Template 对象（需要自定义渲染控制时用）"""
    return _env.get_template(name)
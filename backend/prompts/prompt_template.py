import os
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader

from pydantic import BaseModel, Field


def apply_prompt_template(template: str, **kwargs) -> str:
    template_dir = os.path.join(os.path.dirname(__file__))
    loader = FileSystemLoader(template_dir)
    env = Environment(loader=loader)
    template = env.get_template(f"{template}.jinja-md")
    return template.render(**kwargs)


if __name__ == "__main__":
    print(apply_prompt_template("researcher"))

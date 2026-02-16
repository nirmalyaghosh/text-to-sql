import json

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


def get_prompt(
        agent_name: str,
        prompt_key: str = "system_prompt_lines") -> str:
    prompts = load_prompts()
    if agent_name not in prompts:
        raise KeyError(f"No prompts found for agent: {agent_name}")
    agent_prompts = prompts[agent_name]
    if prompt_key not in agent_prompts:
        raise KeyError(f"No '{prompt_key}' found for agent: {agent_name}")
    return "\n".join(agent_prompts[prompt_key])


@lru_cache(maxsize=1)
def load_prompts(prompt_json_file_path: Path | None = None) -> Dict[str, Any]:
    if prompt_json_file_path:
        p = Path(prompt_json_file_path)
        if not p.exists():
            raise FileNotFoundError(f"Prompt file not found: {p}")
    else:
        p = Path(__file__).parent / "prompts.json"
        if not p.exists():
            raise FileNotFoundError("prompts.json not found")
    return json.loads(p.read_text(encoding="utf-8"))

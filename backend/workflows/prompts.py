"""Prompt template loading helpers for workflow nodes."""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_prompt(agent_name: str) -> str:
    """Read the system prompt from the markdown file."""
    file_path = PROJECT_ROOT / ".agents" / "agents" / f"{agent_name}.md"
    try:
        return file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"System prompt for {agent_name} not found."

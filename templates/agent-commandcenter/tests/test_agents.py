"""CommandCenter CI gate — these tests must pass for the agent to be registered.

From agent_repo_compatibility.md v6.0 §12, plus a --help smoke of every skill script.
Run: python -m pytest tests/ -v
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def test_build_agents_importable():
    """agents.py must be importable without errors."""
    import agents  # noqa: F401


def test_build_agents_returns_list():
    """build_agents() must return a non-empty list."""
    try:
        from agents import build_agents
        result = build_agents()
        assert isinstance(result, list) and len(result) >= 1
    except ImportError:
        pytest.skip("MAF runtime not available — skipping in local env")


def test_agent_has_name_and_instructions():
    """Agent must have a name and a non-trivial system prompt."""
    try:
        from agents import build_agents
        agent = build_agents()[0]
        instructions = getattr(agent, "instructions", None) or getattr(agent, "_instructions", None)
        assert instructions and len(instructions) > 50
    except ImportError:
        pytest.skip("MAF runtime not available")


def test_agent_has_tools():
    """Agent must have at least one tool — an empty tools list means it can only apologise."""
    try:
        from agents import build_agents
        agent = build_agents()[0]
        tools = getattr(agent, "tools", None) or getattr(agent, "_tools", None) or []
        assert len(tools) > 0, "Agent has no tools — it will only apologise"
    except ImportError:
        pytest.skip("MAF runtime not available")


def test_system_prompt_contains_skills():
    """System prompt must include the system prompt file and skill content."""
    from agents import SYSTEM_PROMPT
    assert len(SYSTEM_PROMPT) > 100


def test_all_skill_scripts_help_works():
    """Every skill script answers --help — catches broken paths after a restructure."""
    for script in sorted(REPO.glob(".github/skills/*/scripts/*.py")):
        if script.name.startswith("_"):
            continue
        r = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, cwd=str(REPO))
        assert r.returncode == 0, f"{script.relative_to(REPO)} --help failed: {r.stderr[:200]}"

# file: terminal/__init__.py
"""
Robodog Terminal Mode — a Claude Code-style interactive terminal.

Provides an agentic tool-use loop (prompted tool-calling), file editing,
and shell command execution, on top of pluggable LLM backends (ELSA / echo /
OpenAI-compatible). See docs/TERMINAL_MODE_PLAN.md.
"""
__version__ = "0.2.0"
from .llm_client import LLMClient, Completion, EchoClient, ElsaClient
from .tools import ToolRegistry, default_registry
from .loop import AgentLoop

__all__ = [
    "LLMClient", "Completion", "EchoClient", "ElsaClient",
    "ToolRegistry", "default_registry", "AgentLoop",
]

# file: robodog_terminal/__init__.py
"""
Robodog Terminal Mode — an agentic interactive terminal.

Provides an agentic tool-use loop (prompted tool-calling), file editing,
and shell command execution, on top of pluggable LLM backends (the gateway / echo /
OpenAI-compatible). See docs/TERMINAL_MODE_PLAN.md.
"""
__version__ = "0.3.76"
from .llm_client import LLMClient, Completion, EchoClient, GatewayClient
from .tools import ToolRegistry, default_registry
from .loop import AgentLoop

__all__ = [
    "LLMClient", "Completion", "EchoClient", "GatewayClient",
    "ToolRegistry", "default_registry", "AgentLoop",
]

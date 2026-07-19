# file: terminal/loop.py
"""
The agentic loop for terminal mode.

Because ELSA has no native tool API, this is a prompted tool-calling loop:
  1. system context = tool catalog + output contract
  2. build a transcript prompt from the running history
  3. ask the model to complete
  4. parse <tool> blocks from the text; if any, execute and append results
  5. repeat until the model returns a message with no tool blocks (final answer)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .llm_client import LLMClient, Completion
from .tools import ToolRegistry
from .toolcall import parse_tool_calls

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    role: str          # "user" | "assistant" | "tool"
    content: str
    tool_name: str = ""


@dataclass
class LoopResult:
    final_text: str
    iterations: int
    total_tokens: int
    turns: List[Turn]
    duration: float = 0.0   # wall-clock seconds for the turn


class AgentLoop:
    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        max_iterations: int = 25,
        max_tokens: int = 8192,
        temperature: float = 0.3,
        on_event: Optional[Callable[[str, dict], None]] = None,
        system_suffix: str = "",
        cancel_event=None,
    ):
        self.client = client
        self.registry = registry
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.on_event = on_event or (lambda kind, data: None)
        self.system_suffix = system_suffix
        self.cancel_event = cancel_event  # threading.Event; checked between steps
        self.history: List[Turn] = []
        # ELSA re-sends the full transcript every iteration, so trim old tool
        # outputs first (Claude Code's compaction order) before any summarizing.
        self.max_transcript_chars = 120_000  # ~30k tokens

    def transcript_chars(self) -> int:
        return sum(len(t.content) for t in self.history)

    def _trim_history(self):
        total = self.transcript_chars()
        if total <= self.max_transcript_chars:
            return
        placeholder = "[old tool output cleared to save context]"
        for t in self.history[:-8]:  # never touch the 8 most recent turns
            if t.role == "tool" and len(t.content) > len(placeholder):
                total -= len(t.content) - len(placeholder)
                t.content = placeholder
                if total <= self.max_transcript_chars:
                    break

    # ---- prompt rendering ----------------------------------------------
    def _system_context(self) -> str:
        base = self.registry.catalog()
        return base + "\n\n" + self.system_suffix if self.system_suffix else base

    def _render_prompt(self) -> str:
        self._trim_history()
        buf = []
        for t in self.history:
            if t.role == "user":
                buf.append(f"USER: {t.content}")
            elif t.role == "assistant":
                buf.append(f"ASSISTANT: {t.content}")
            elif t.role == "tool":
                buf.append(f"TOOL RESULT [{t.tool_name}]:\n{t.content}")
        buf.append("ASSISTANT:")
        return "\n\n".join(buf)

    # ---- main entry -----------------------------------------------------
    def run(self, user_message: str) -> LoopResult:
        import time as _time
        _t0 = _time.time()
        self.history.append(Turn("user", user_message))
        total_tokens = 0
        iterations = 0
        final_text = ""
        nudged = False
        repeats: dict = {}   # (call sig + result sig) -> count; breaks stuck loops
        aborted = False

        while iterations < self.max_iterations:
            if self.cancel_event is not None and self.cancel_event.is_set():
                final_text = "[cancelled]"
                break
            iterations += 1
            prompt = self._render_prompt()
            self.on_event("llm_start", {"iteration": iterations})
            completion: Completion = self.client.complete(
                prompt,
                context=self._system_context(),
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            total_tokens += completion.total_tokens
            text = completion.text or ""
            calls, prose = parse_tool_calls(text)
            self.on_event("llm_done", {
                "iteration": iterations, "text": text,
                "prose": prose, "n_calls": len(calls),
                "tokens": completion.total_tokens,
            })

            # Record the assistant turn (full text incl. tool blocks so history
            # stays faithful to what the model produced).
            self.history.append(Turn("assistant", text))

            if not calls:
                # Nudge once if the model narrated intent without acting
                # ("I'll create the file...") — words without tool blocks do nothing.
                intent = any(p in text for p in
                             ("I'll ", "I will ", "Let me ", "First, I", "Now I"))
                if intent and not nudged and iterations < self.max_iterations:
                    nudged = True
                    self.history.append(Turn(
                        "tool",
                        "You emitted NO <tool> blocks, so nothing happened. "
                        "Do not describe actions — emit the <tool> blocks now.",
                        tool_name="system"))
                    continue
                final_text = prose or text
                break

            for call in calls:
                if self.cancel_event is not None and self.cancel_event.is_set():
                    break
                self.on_event("tool_start", {"name": call.name, "args": call.args})
                result = self.registry.execute(call.name, call.args)
                self.on_event("tool_done", {"name": call.name, "result": result})
                self.history.append(Turn("tool", result, tool_name=call.name))

                # Circuit breaker: the same call producing the same result over
                # and over means the model is stuck (e.g. rewriting a file with
                # the same broken content). Warn once, then abort the turn.
                sig = (call.name,
                       tuple(sorted(call.args.items()))[:6].__str__()[:500],
                       result[:200])
                repeats[sig] = repeats.get(sig, 0) + 1
                if repeats[sig] == 2:
                    self.history.append(Turn(
                        "tool",
                        "WARNING: you repeated the SAME tool call and got the SAME "
                        "result. Do not repeat it again — change your approach. "
                        "If content contains literal \\n sequences, use real "
                        "newlines instead.",
                        tool_name="system"))
                elif repeats[sig] >= 3:
                    final_text = ("[aborted: the model repeated the same failing "
                                  f"tool call ({call.name}) 3 times]")
                    aborted = True
                    break
            if aborted:
                break
        else:
            final_text = (final_text or "").strip() + \
                f"\n\n[stopped: reached max_iterations={self.max_iterations}]"

        return LoopResult(
            final_text=final_text,
            iterations=iterations,
            total_tokens=total_tokens,
            turns=list(self.history),
            duration=_time.time() - _t0,
        )

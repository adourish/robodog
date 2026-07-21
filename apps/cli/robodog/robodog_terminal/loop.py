# file: robodog_terminal/loop.py
"""
The agentic loop for terminal mode.

Because the gateway has no native tool API, this is a prompted tool-calling loop:
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
from .toolcall import (parse_tool_calls, has_unclosed_tool_call,
                       looks_like_attempted_tool)

logger = logging.getLogger(__name__)

# Re-embedded at the point of failure (models forget the format 100k tokens back).
_TOOL_FORMAT_REMINDER = (
    "Emit tool calls in EXACTLY this format — nothing else is parsed:\n"
    '<tool name="TOOL_NAME">\n'
    '<param name="PARAM_NAME">VALUE</param>\n'
    "</tool>\n"
    'Example: <tool name="read_file"><param name="path">src/app.py</param></tool>\n'
    "Do NOT wrap tool calls in markdown fences and do NOT describe them in prose.")

# Max self-correction turns per user message before stopping and handing back.
_MAX_MISTAKES = 3


@dataclass
class Turn:
    role: str          # "user" | "assistant" | "tool"
    content: str
    tool_name: str = ""


# Tools that are safe to run concurrently within one turn. Subagents (`agent`)
# are isolated contexts; read-only tools have no side effects. Mutating file/
# shell tools stay sequential to avoid write conflicts.
_PARALLEL_SAFE = {"agent", "task_output", "read_file", "glob", "grep",
                  "list_dir", "ask_user"}


def _batch_parallel_safe(registry, calls) -> bool:
    """True when a batch of >1 tool calls can be executed concurrently."""
    if len(calls) < 2:
        return False
    return all(c.name in _PARALLEL_SAFE for c in calls)


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
        self.api_retry_pause = 4.0        # seconds before the loop-level API retry
        self.history: List[Turn] = []
        # the gateway re-sends the full transcript every iteration, so trim old tool
        # outputs first (a modern agentic terminal's compaction order) before any summarizing.
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

    # Structured schema so the compaction summary keeps what a resuming agent
    # actually needs (mirrors OpenHands' condenser summary shape).
    _COMPACT_PROMPT = (
        "Summarize the EARLIER part of this coding session so the agent can keep "
        "working without re-reading it. Use these exact headings and be concise "
        "but keep every fact needed to resume:\n"
        "## Goal\n## Decisions made\n## Files touched (and what changed)\n"
        "## Current state\n## Next steps\n## Open problems / failing tests\n\n"
        "=== transcript to summarize ===\n")

    def compact(self, keep_recent: int = 6) -> bool:
        """Summarize the MIDDLE of the transcript while preserving the FIRST turn
        (the user's original goal, verbatim) and the last `keep_recent` turns
        (recent work, verbatim). Returns True if it compacted. Fail-safe: on any
        error, or if it wouldn't actually shrink things, the history is untouched.
        """
        if len(self.history) <= keep_recent + 2:
            return False
        first = self.history[0]
        recent = self.history[-keep_recent:]
        middle = self.history[1:-keep_recent]
        if not middle:
            return False
        parts = []
        for t in middle:
            if t.role == "user":
                parts.append(f"USER: {t.content}")
            elif t.role == "assistant":
                parts.append(f"ASSISTANT: {t.content}")
            else:
                parts.append(f"TOOL RESULT [{t.tool_name}]:\n{t.content}")
        middle_text = "\n\n".join(parts)
        try:
            summary = self.client.complete(
                self._COMPACT_PROMPT + middle_text,
                context=self._system_context(), max_tokens=1500).text
        except Exception:   # a summarization failure must never lose the history
            return False
        if not (summary or "").strip():
            return False
        rebuilt = [first, Turn("user", f"[earlier conversation summary]\n{summary}")]
        rebuilt.extend(recent)
        # Only adopt the compaction if it actually shrank the transcript (a summary
        # somehow larger than the middle it replaced would be worse than nothing).
        old_chars = self.transcript_chars()
        new_chars = sum(len(t.content) for t in rebuilt)
        if new_chars >= old_chars:
            return False
        self.history[:] = rebuilt
        return True

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

    def _abort_text(self, reason: str, prose: str) -> str:
        """Message for a circuit-breaker abort that PRESERVES any answer the
        model produced this turn, so partial work isn't thrown away."""
        note = f"[stopped: {reason} — changing approach was needed]"
        prose = (prose or "").strip()
        return f"{prose}\n\n{note}" if prose else note

    def _safe_complete(self, prompt: str):
        """Call the client with one loop-level retry ABOVE its own backoff, so a
        transient backend outage (e.g. a gateway ReadTimeout) that outlasts the
        client's retries doesn't crash the whole turn. Returns the Completion,
        or (None, exc) when it finally gives up — the caller ends the turn
        gracefully with context preserved instead of raising."""
        import time as _t
        last_exc = None
        for attempt in range(2):   # 1 retry on top of the client's internal backoff
            try:
                return self.client.complete(
                    prompt, context=self._system_context(),
                    max_tokens=self.max_tokens, temperature=self.temperature), None
            except Exception as exc:   # noqa: BLE001 — any client failure is recoverable here
                last_exc = exc
                self.on_event("llm_error", {"error": str(exc)[:200],
                                            "attempt": attempt + 1, "will_retry": attempt == 0})
                if attempt == 0 and self.api_retry_pause > 0:
                    # brief pause before the loop-level retry; honor cancel
                    if self.cancel_event is not None:
                        if self.cancel_event.wait(self.api_retry_pause):
                            return None, last_exc
                    else:
                        _t.sleep(self.api_retry_pause)
        return None, last_exc

    # ---- main entry -----------------------------------------------------
    def run(self, user_message: str) -> LoopResult:
        import time as _time
        _t0 = _time.time()
        self.history.append(Turn("user", user_message))
        total_tokens = 0
        iterations = 0
        final_text = ""
        nudged = False
        mistakes = 0             # consecutive malformed/truncated turns (reflection cap)
        repeats: dict = {}       # (call+args+result sig) -> count; breaks stuck loops
        tool_errors: dict = {}   # tool name -> consecutive ERROR/BLOCKED count
        aborted = False

        while iterations < self.max_iterations:
            if self.cancel_event is not None and self.cancel_event.is_set():
                final_text = "[cancelled]"
                break
            iterations += 1
            prompt = self._render_prompt()
            self.on_event("llm_start", {"iteration": iterations})
            completion, api_exc = self._safe_complete(prompt)
            if completion is None:
                if self.cancel_event is not None and self.cancel_event.is_set():
                    final_text = "[cancelled]"
                    break
                # Backend unreachable after retries — end gracefully, keep context.
                name = type(api_exc).__name__ if api_exc else "error"
                final_text = ((final_text or "").strip() + "\n\n"
                              f"[the model backend is unreachable right now ({name}). "
                              "Your conversation is kept — just try again in a moment.]").strip()
                break
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
                more_turns_left = iterations < self.max_iterations
                # (1.2) TRUNCATION: cut off at max_tokens (finish_reason=length) or
                # an unclosed <tool>/<param> tag. The call never finished, so it
                # didn't run — must NOT be read as "no tool / final answer" (this
                # is the classic permanent-stall bug). Ask to re-emit, don't finalize.
                truncated = completion.truncated or has_unclosed_tool_call(text)
                if truncated and mistakes < _MAX_MISTAKES and more_turns_left:
                    mistakes += 1
                    self.on_event("truncated", {"iteration": iterations})
                    self.history.append(Turn(
                        "tool",
                        "[ERROR] Your previous response was CUT OFF (truncated) before "
                        "it finished — the tool call is incomplete, so nothing ran. "
                        "Re-send ONLY that tool call, complete this time. If the "
                        "content was large, make a smaller edit or split it.\n\n"
                        + _TOOL_FORMAT_REMINDER,
                        tool_name="system"))
                    continue
                # (1.1) MALFORMED: tool-shaped text that didn't parse (wrong tags,
                # emitted as prose). Re-teach the format at the point of failure.
                if (looks_like_attempted_tool(text) and mistakes < _MAX_MISTAKES
                        and more_turns_left):
                    mistakes += 1
                    self.on_event("malformed_toolcall", {"iteration": iterations})
                    self.history.append(Turn(
                        "tool",
                        "[ERROR] No valid tool call was parsed from your last response "
                        "— it wasn't in the required format, so nothing happened.\n\n"
                        + _TOOL_FORMAT_REMINDER
                        + "\n(This is an automated message; do not reply to it "
                        "conversationally — just emit the corrected tool call.)",
                        tool_name="system"))
                    continue
                # Nudge once if the model narrated intent without acting
                # ("I'll create the file...") — words without tool blocks do nothing.
                intent = any(p in text for p in
                             ("I'll ", "I will ", "Let me ", "First, I", "Now I"))
                if intent and not nudged and more_turns_left:
                    nudged = True
                    self.history.append(Turn(
                        "tool",
                        "You emitted NO <tool> blocks, so nothing happened. "
                        "Do not describe actions — emit the <tool> blocks now.",
                        tool_name="system"))
                    continue
                final_text = prose or text
                break

            # A turn that produced real tool calls clears the malformed counter.
            mistakes = 0

            # Execute the batch of tool calls. When the whole batch is
            # parallel-safe (multiple subagents, or read-only tools), run them
            # CONCURRENTLY and collect results in order; otherwise sequentially.
            if self.cancel_event is not None and self.cancel_event.is_set():
                break
            if _batch_parallel_safe(self.registry, calls):
                for call in calls:
                    self.on_event("tool_start", {"name": call.name, "args": call.args})
                import concurrent.futures as _cf
                with _cf.ThreadPoolExecutor(max_workers=min(8, len(calls))) as _ex:
                    results = list(_ex.map(
                        lambda c: self.registry.execute(c.name, c.args), calls))
            else:
                results = []
                for call in calls:
                    if self.cancel_event is not None and self.cancel_event.is_set():
                        break
                    self.on_event("tool_start", {"name": call.name, "args": call.args})
                    results.append(self.registry.execute(call.name, call.args))

            for call, result in zip(calls, results):
                # (1.4) Never feed back an empty result — a blank tool result can
                # loop the model (it can't tell the call ran). Name the emptiness.
                if not (result or "").strip():
                    result = "(tool did not return anything)"
                self.on_event("tool_done", {"name": call.name, "result": result})
                self.history.append(Turn("tool", result, tool_name=call.name))
                # Polling a background task legitimately repeats — never treat
                # task_output/ask_user as a stuck loop.
                if call.name in ("task_output", "ask_user"):
                    continue

                is_error = result.lstrip().startswith(("ERROR", "BLOCKED"))

                # Breaker 1 — a tool that keeps FAILING, even with different args
                # (e.g. read_file on one missing path after another). Counts
                # consecutive errors per tool; a success resets it.
                if is_error:
                    tool_errors[call.name] = tool_errors.get(call.name, 0) + 1
                else:
                    tool_errors[call.name] = 0
                if tool_errors.get(call.name, 0) == 3:
                    self.history.append(Turn(
                        "tool",
                        f"NOTE: {call.name} has failed 3 times in a row. Stop "
                        f"retrying it — the target likely does not exist or the "
                        f"approach is wrong. Try a DIFFERENT tool (e.g. list_dir "
                        f"or glob to discover what's actually there), or give your "
                        f"best final answer with what you already know.",
                        tool_name="system"))
                elif tool_errors.get(call.name, 0) >= 5:
                    final_text = self._abort_text(
                        f"{call.name} failed 5 times in a row", prose)
                    aborted = True
                    break

                # Breaker 2 — the exact same call+result repeating (a true stuck
                # loop). Warn once, then abort.
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
                    final_text = self._abort_text(
                        f"repeated the same {call.name} call 3 times", prose)
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

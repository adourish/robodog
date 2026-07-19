# file: robodog_terminal/toolcall.py
"""
Parse prompted (text-based) tool calls out of an LLM completion.

Since the gateway has no native tool API, the model is instructed (via the system
`context`) to emit tool calls as XML-tag blocks:

    <tool name="bash">
      <param name="command">pytest -q</param>
      <param name="timeout">60</param>
    </tool>

Multiple blocks may appear. Any text outside tool blocks is treated as the
model's prose. If no tool blocks are present, the completion is a final answer.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

# Tolerate extra attributes on the <tool> tag (e.g. models that emit
# <tool name="run_script" interpreter="python">) — capture them in `attrs`.
_TOOL_RE = re.compile(
    r"<tool\s+name\s*=\s*[\"']?(?P<name>[\w.\-]+)[\"']?(?P<attrs>[^>]*)>(?P<body>.*?)</tool>",
    re.DOTALL | re.IGNORECASE,
)
_PARAM_RE = re.compile(
    r"<param\s+name\s*=\s*[\"']?(?P<pname>[\w.\-]+)[\"']?\s*>(?P<pval>.*?)</param>",
    re.DOTALL | re.IGNORECASE,
)
# key="value" / key='value' attributes on a tag.
_ATTR_RE = re.compile(r"(?P<k>[\w.\-]+)\s*=\s*\"(?P<v>[^\"]*)\"|(?P<k2>[\w.\-]+)\s*=\s*'(?P<v2>[^']*)'")


_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


@dataclass
class ToolCall:
    name: str
    args: Dict[str, str]
    raw: str


def _unwrap_pure_tool_fences(text: str) -> str:
    """
    Models sometimes wrap their tool calls in markdown fences despite being told
    not to. If a fenced region contains ONLY tool blocks (+ whitespace), unwrap
    it so the calls execute. Mixed-content fences are left alone.
    """
    def repl(m):
        inner = m.group(1)
        leftover = _TOOL_RE.sub("", inner)
        if _TOOL_RE.search(inner) and not leftover.strip():
            return inner
        return m.group(0)
    return _FENCE_RE.sub(repl, text)


def _mask_impure_fences(text: str) -> str:
    """
    Replace remaining fenced regions with equal-length filler so tool-looking
    syntax QUOTED inside code examples (e.g. in a final answer explaining the
    format) is never parsed as a real call. Length is preserved so match spans
    map back onto the original text.
    """
    def repl(m):
        return "\x00" * len(m.group(0))
    return _FENCE_RE.sub(repl, text)


def parse_tool_calls(text: str) -> Tuple[List[ToolCall], str]:
    """
    Return (tool_calls, prose). `prose` is the text with tool blocks removed.
    Hardened: unwraps fence-wrapped tool calls; ignores tool syntax quoted
    inside mixed-content code fences.
    """
    normalized = _unwrap_pure_tool_fences(text)
    matchable = _mask_impure_fences(normalized)
    calls: List[ToolCall] = []
    spans = []
    for m in _TOOL_RE.finditer(matchable):
        raw = normalized[m.start():m.end()]
        name = m.group("name").strip()
        body = raw  # parse params from the real text at the same span
        args: Dict[str, str] = {}
        # Attributes on the <tool ...> tag become params (models sometimes put
        # small scalar args there, e.g. interpreter="python").
        attrs = m.group("attrs") or ""
        for am in _ATTR_RE.finditer(attrs):
            k = am.group("k") or am.group("k2")
            v = am.group("v") if am.group("v") is not None else am.group("v2")
            if k and k.lower() != "name":
                args[k] = html.unescape(v)
        for pm in _PARAM_RE.finditer(body):
            pname = pm.group("pname").strip()
            pval = pm.group("pval")
            # Unescape HTML entities the model may have emitted (&lt; etc.)
            val = html.unescape(pval).strip("\n")
            # Models sometimes emit literal backslash-n instead of newlines in
            # multi-statement content (observed with gpt-4o-mini). If a value
            # has NO real newlines but contains \n escapes, decode them.
            if "\n" not in val and "\\n" in val:
                val = (val.replace("\\r\\n", "\n").replace("\\n", "\n")
                          .replace("\\t", "\t"))
            args[pname] = val
        calls.append(ToolCall(name=name, args=args, raw=raw))
        spans.append((m.start(), m.end()))
    # prose = normalized text minus the tool-call spans
    out = []
    last = 0
    for s, e in spans:
        out.append(normalized[last:s])
        last = e
    out.append(normalized[last:])
    prose = "".join(out).strip()
    return calls, prose


def has_tool_calls(text: str) -> bool:
    return bool(_TOOL_RE.search(text))

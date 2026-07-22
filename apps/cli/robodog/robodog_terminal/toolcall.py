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
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Accept <tool …>…</tool> AND Anthropic-style <invoke …>…</invoke> (some models
# emit the format they were trained on). Either close tag is tolerated. Extra
# attributes on the tag (e.g. <tool name="run_script" interpreter="python">) are
# captured in `attrs`.
_TOOL_RE = re.compile(
    r"<(?:tool|invoke)\s+name\s*=\s*[\"']?(?P<name>[\w.\-]+)[\"']?(?P<attrs>[^>]*)>"
    r"(?P<body>.*?)</(?:tool|invoke)>",
    re.DOTALL | re.IGNORECASE,
)
# Anthropic wraps calls in <function_calls>…</function_calls>; strip those (and
# the matching results wrapper) so they never leak into the model's prose.
_WRAPPER_RE = re.compile(r"</?function_(?:calls|results)>", re.IGNORECASE)
_PARAM_RE = re.compile(
    # Open tag is <param> OR <parameter> (models trained on Anthropic tool syntax
    # reach for <parameter>). Close tag may be the matching </param>/</parameter>,
    # OR the param NAME the model echoed by mistake (`<param name="path">…</path>`)
    # — otherwise the value swallows every following param up to the next close.
    r"<param(?:eter)?\s+name\s*=\s*[\"']?(?P<pname>[\w.\-]+)[\"']?\s*>"
    r"(?P<pval>.*?)</(?:param(?:eter)?|(?P=pname))>",
    re.DOTALL | re.IGNORECASE,
)
# key="value" / key='value' attributes on a tag.
_ATTR_RE = re.compile(r"(?P<k>[\w.\-]+)\s*=\s*\"(?P<v>[^\"]*)\"|(?P<k2>[\w.\-]+)\s*=\s*'(?P<v2>[^']*)'")
# A self-closing tag (<tool name="x" path="y" />) — no body, no separate close
# tag. Models occasionally emit this for calls with only scalar args. _TOOL_RE
# can't match it (there's no </tool> immediately after), and worse, its lazy
# body match would either fail outright or bleed forward to some LATER call's
# close tag, swallowing everything between as bogus "body" — so these must be
# pulled out and blanked before _TOOL_RE ever runs.
_SELF_CLOSING_TOOL_RE = re.compile(
    r"<(?:tool|invoke)\s+name\s*=\s*[\"']?(?P<name>[\w.\-]+)[\"']?(?P<attrs>[^>]*)/>",
    re.IGNORECASE)


_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)

# Params where a literal `\n`/`\t` should be decoded to a real newline/tab (the
# model sometimes escapes newlines in multi-line CODE). NEVER includes command/
# path/cwd — decoding there mangles Windows paths (`\node_modules`, `C:\temp`).
_ESCAPE_DECODE_PARAMS = {"content", "new_string", "old_string", "text", "body"}


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


# Reasoning-model scratchpad. Qwen/DeepSeek emit <think>…</think> and the real
# tool call AFTER it; strip it before parsing (and streaming can drop the OPEN
# tag, leaking reasoning with only a trailing </think> — handle that too).
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_THINK_LEAK_RE = re.compile(r"^.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    if "</think>" not in text.lower():
        return text
    t = _THINK_RE.sub("", text)
    # A stray </think> with no opener == reasoning leaked without the open tag.
    if "</think>" in t.lower() and "<think>" not in t.lower():
        t = _THINK_LEAK_RE.sub("", t, count=1)
    return t


def _json_tool_fallback(prose: str) -> Optional[ToolCall]:
    """Some models (Qwen2.5-coder, GLM) emit a tool call as a JSON object in the
    content instead of XML. VERY conservative: only when the ENTIRE prose is a
    single JSON object naming a tool, so a normal JSON answer isn't hijacked."""
    s = (prose or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    try:
        obj = json.loads(s)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("name") or obj.get("tool") or obj.get("tool_name")
    raw_args = (obj.get("arguments") or obj.get("parameters")
                or obj.get("args") or obj.get("input") or {})
    if not (isinstance(name, str) and name.strip() and isinstance(raw_args, dict)):
        return None
    args = {k: (v if isinstance(v, str) else json.dumps(v)
                if isinstance(v, (dict, list)) else str(v))
            for k, v in raw_args.items()}
    return ToolCall(name=name.strip(), args=args, raw=prose)


def parse_tool_calls(text: str) -> Tuple[List[ToolCall], str]:
    """
    Return (tool_calls, prose). `prose` is the text with tool blocks removed.
    Hardened: strips <think> reasoning; unwraps fence-wrapped tool calls; ignores
    tool syntax quoted inside mixed-content fences; falls back to a JSON tool call
    when the model emitted one instead of XML.
    """
    stripped = _strip_think(text)
    calls, prose = _parse_xml(stripped)
    # A tool call emitted INSIDE the reasoning block: if stripping lost it and we
    # found nothing, re-parse the original (keep the clean, think-stripped prose).
    if not calls and stripped != text:
        recovered, _ = _parse_xml(text)
        if recovered:
            return recovered, prose
    # No XML tool at all: maybe the model emitted a JSON tool call as content.
    if not calls:
        jc = _json_tool_fallback(prose)
        if jc is not None:
            return [jc], ""
    return calls, prose


def _parse_xml(text: str) -> Tuple[List[ToolCall], str]:
    normalized = _unwrap_pure_tool_fences(text)
    matchable = _mask_impure_fences(normalized)
    calls: List[ToolCall] = []
    spans = []

    # Self-closing tags first: extract them into calls, then blank their span
    # (length preserved, so spans still map onto `normalized`) so _TOOL_RE
    # below never sees the dangling open tag.
    self_closing_spans = []
    for m in _SELF_CLOSING_TOOL_RE.finditer(matchable):
        name = m.group("name").strip()
        args: Dict[str, str] = {}
        attrs = m.group("attrs") or ""
        for am in _ATTR_RE.finditer(attrs):
            k = am.group("k") or am.group("k2")
            v = am.group("v") if am.group("v") is not None else am.group("v2")
            if k and k.lower() != "name":
                args[k] = html.unescape(v)
        raw = normalized[m.start():m.end()]
        calls.append(ToolCall(name=name, args=args, raw=raw))
        spans.append((m.start(), m.end()))
        self_closing_spans.append((m.start(), m.end()))
    if self_closing_spans:
        chars = list(matchable)
        for s, e in self_closing_spans:
            for i in range(s, e):
                chars[i] = "\x00"
        matchable = "".join(chars)

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
            # Some weak models emit literal backslash-n for real newlines in
            # multi-line CODE. Decode it — but ONLY for text/code params. Applying
            # it to a command or path CORRUPTS Windows paths: `\nodeids` -> newline,
            # `C:\temp` -> C:<tab>emp. So restrict it to content-style params.
            if (pname.lower() in _ESCAPE_DECODE_PARAMS
                    and "\n" not in val and "\\n" in val):
                val = (val.replace("\\r\\n", "\n").replace("\\n", "\n")
                          .replace("\\t", "\t"))
            args[pname] = val
        calls.append(ToolCall(name=name, args=args, raw=raw))
        spans.append((m.start(), m.end()))

    # Self-closing calls were collected before _TOOL_RE ran, so `calls`/`spans`
    # may be out of document order — sort both together so tool calls execute
    # in the order the model actually emitted them.
    order = sorted(range(len(spans)), key=lambda i: spans[i][0])
    calls = [calls[i] for i in order]
    spans = [spans[i] for i in order]

    # prose = normalized text minus the tool-call spans
    out = []
    last = 0
    for s, e in spans:
        out.append(normalized[last:s])
        last = e
    out.append(normalized[last:])
    # Drop any leftover <function_calls>/<function_results> wrapper tags so the
    # Anthropic wrapper never shows up as prose.
    prose = _WRAPPER_RE.sub("", "".join(out)).strip()
    return calls, prose


def has_tool_calls(text: str) -> bool:
    return bool(_TOOL_RE.search(text))


_OPEN_TOOL_RE = re.compile(r"<(?:tool|invoke)\s+name\s*=", re.IGNORECASE)
_OPEN_PARAM_RE = re.compile(r"<param(?:eter)?\s+name\s*=", re.IGNORECASE)


def has_unclosed_tool_call(text: str) -> bool:
    """True if `text` opens a tool/param tag that never closes — the signature of
    a response TRUNCATED mid-tool-call (the gateway hit max_tokens). Used as a
    fallback truncation signal when finish_reason isn't reported: after removing
    every COMPLETE <tool>…</tool> block AND every complete self-closing
    <tool .../> tag (a full, valid call — not a truncation), a leftover
    `<tool name=` / `<param name=` open tag means the model was cut off before
    finishing the call."""
    remainder = _SELF_CLOSING_TOOL_RE.sub("", _TOOL_RE.sub("", text))
    return bool(_OPEN_TOOL_RE.search(remainder) or _OPEN_PARAM_RE.search(remainder))


def looks_like_attempted_tool(text: str) -> bool:
    """True if the text looks like the model TRIED to call a tool but it didn't
    parse (wrong/garbled format, or emitted as plain prose) — so we should send a
    format reminder rather than treating it as a final answer."""
    return bool(_OPEN_TOOL_RE.search(text) or _OPEN_PARAM_RE.search(text)
                or re.search(r"</?(?:function_calls|invoke|tool)\b", text, re.IGNORECASE))

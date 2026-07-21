# file: robodog_terminal/skills.py
"""
Discovery + loading of user-extensible features, mirroring a modern agentic terminal's custom
commands, subagents, and skills.

Roots are scanned in order — PROJECT first, then USER — and the first entry
found wins on any name clash (a later-found entry never overrides one already
registered). Within each scope, `.robodog` wins over `.claude`, so an existing
Claude Code project's extensions work unchanged and robodog-specific overrides
are possible:

    PROJECT = <cwd>/.robodog, then <cwd>/.claude
    USER    = ~/.robodog,     then ~/.claude

Three feature types live under each root:

1. CUSTOM COMMANDS  <root>/commands/*.md
   `foo.md` defines the slash command `/foo`. The body is a prompt template with
   substitutions applied at invocation time (see CustomCommand.render):
     $ARGUMENTS               -> the full argument string
     $1, $2, ...              -> positional args (whitespace-split)
     ${CLAUDE_PROJECT_DIR}    -> cwd
     ${ROBODOG_PROJECT_DIR}   -> cwd
   Optional frontmatter keys: description, argument-hint.

2. CUSTOM AGENTS  <root>/agents/*.md
   Frontmatter: name (default = filename stem), description, tools (space/comma
   separated -> restricts the subagent's tools; empty/absent = all tools),
   max_iterations (int, default 20). Body = the agent's system prompt. Exposed
   via agent_type_overrides() in an AGENT_TYPES-compatible shape.

3. SKILLS  <root>/skills/<name>/SKILL.md
   Frontmatter: name (default = directory name), description. Body = skill
   instructions. Invoked as `/name`; the body is returned to be injected into
   the conversation as a context turn.

No third-party YAML dependency: frontmatter is parsed manually (simple
`key: value` lines only).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 20


# ========================================================================
# Frontmatter parsing (no yaml dependency)
# ========================================================================
def parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Return (frontmatter_dict, body).

    Supports a leading ``---`` ... ``---`` block of simple ``key: value`` lines
    (values are strings, trimmed; no nested YAML — only the first colon splits a
    line, so values may contain colons). If no frontmatter block is present,
    returns ({}, text).
    """
    if text is None:
        return {}, ""
    # Normalize newlines so \r\n files parse identically.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    # A frontmatter block must start on the very first line with '---'.
    if not lines or lines[0].strip() != "---":
        return {}, text
    fm: dict = {}
    end_idx: Optional[int] = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        # No closing fence — treat the whole thing as body (tolerant).
        return {}, text
    for raw in lines[1:end_idx]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue  # skip malformed line rather than crash
        key, value = line.split(":", 1)
        fm[key.strip()] = value.strip()
    body = "\n".join(lines[end_idx + 1:])
    # Drop a single leading blank line left after the closing fence.
    if body.startswith("\n"):
        body = body[1:]
    return fm, body


# ========================================================================
# Dataclasses
# ========================================================================
@dataclass
class CustomCommand:
    name: str
    description: str
    argument_hint: str
    template: str            # raw body
    source: str              # file path

    def render(self, args_str: str, cwd: str) -> str:
        """Apply invocation-time substitutions and return the final prompt.

        Order matters: positional ``$1``.. and ``$ARGUMENTS`` are substituted,
        along with the ``${CLAUDE_PROJECT_DIR}`` / ``${ROBODOG_PROJECT_DIR}``
        directory tokens.
        """
        args_str = args_str or ""
        result = self.template
        # Directory tokens first (they are unambiguous ${...} forms).
        result = result.replace("${CLAUDE_PROJECT_DIR}", cwd)
        result = result.replace("${ROBODOG_PROJECT_DIR}", cwd)
        # Positional args. Replace higher indices first so $10 is not shadowed
        # by $1 (defensive, even though we rarely have that many).
        positional = args_str.split()
        for idx in range(len(positional), 0, -1):
            result = result.replace(f"${idx}", positional[idx - 1])
        # $ARGUMENTS last so a literal '$ARGUMENTS' inside args isn't re-expanded.
        result = result.replace("$ARGUMENTS", args_str)
        return result


@dataclass
class CustomAgentDef:
    name: str
    description: str
    tools: Optional[list]    # None = all tools
    max_iterations: int
    system_prompt: str
    source: str


@dataclass
class SkillDef:
    name: str
    description: str
    body: str
    source: str
    # Keyword triggers (frontmatter `triggers: k8s, kubernetes`). When the user's
    # message matches one, the skill is auto-injected for that turn — conditional
    # context that costs nothing until it's relevant (OpenHands microagents).
    triggers: Optional[List[str]] = None


def _parse_triggers(value) -> List[str]:
    """Parse a frontmatter `triggers` value: comma/space/`[...]`-separated words."""
    if not value:
        return []
    s = str(value).strip().strip("[]")
    parts = re.split(r"[,\s]+", s)
    return [p.strip().strip("'\"").lower() for p in parts if p.strip().strip("'\"")]


# ========================================================================
# Registry
# ========================================================================
class SkillsRegistry:
    """Discovers and holds custom commands, agents, and skills.

    Args:
        cwd: the project working directory; project roots default to
            ``<cwd>/.robodog`` then ``<cwd>/.claude``.
        project_root: optional override for the primary project root (defaults
            to ``<cwd>/.robodog``). Injectable so tests can point it at a temp
            dir. When set, the ``.claude`` sibling of the SAME directory is
            scanned second (so tests exercise both layouts).
        user_root: optional override for the primary user root (defaults to
            ``~/.robodog``; ``~/.claude`` is scanned after it). Injectable so
            tests can exercise project-wins-over-user behavior without touching
            the real home directory.
    """

    def __init__(
        self,
        cwd: str,
        project_root: Optional[str] = None,
        user_root: Optional[str] = None,
    ) -> None:
        self.cwd = str(cwd)
        self.project_root = Path(project_root) if project_root else Path(cwd) / ".robodog"
        self.user_root = (
            Path(user_root) if user_root
            else Path(os.path.expanduser("~")) / ".robodog"
        )
        self.commands: Dict[str, CustomCommand] = {}
        self.agents: Dict[str, CustomAgentDef] = {}
        self.skills: Dict[str, SkillDef] = {}

    def _roots(self) -> List[Path]:
        """Scan order: project .robodog, project .claude, user .robodog,
        user .claude — first found wins, so .robodog can override .claude and
        project can override user. The .claude sibling is derived from each
        primary root's parent, so injected test roots exercise both layouts."""
        return [
            self.project_root,
            self.project_root.parent / ".claude",
            self.user_root,
            self.user_root.parent / ".claude",
        ]

    # ---- discovery ------------------------------------------------------
    def discover(self) -> None:
        """Scan all roots and populate the three dicts.

        First-found entries win on name clash (already-registered names are
        not overwritten). Missing directories and unreadable/garbled files are
        tolerated: they are skipped and logged.
        """
        self.commands.clear()
        self.agents.clear()
        self.skills.clear()
        for root in self._roots():
            self._scan_root(root)

    def _scan_root(self, root: Path) -> None:
        if not root or not root.is_dir():
            logger.debug("skills: root not found, skipping: %s", root)
            return
        self._scan_commands(root / "commands")
        self._scan_agents(root / "agents")
        self._scan_skills(root / "skills")

    def _read_text(self, path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("skills: cannot read %s: %s", path, exc)
            return None

    def _scan_commands(self, cdir: Path) -> None:
        if not cdir.is_dir():
            return
        for path in sorted(cdir.glob("*.md")):
            try:
                text = self._read_text(path)
                if text is None:
                    continue
                fm, body = parse_frontmatter(text)
                name = path.stem
                if name in self.commands:
                    continue  # project wins
                self.commands[name] = CustomCommand(
                    name=name,
                    description=fm.get("description", ""),
                    argument_hint=fm.get("argument-hint", ""),
                    template=body,
                    source=str(path),
                )
            except Exception as exc:  # never let one bad file abort discovery
                logger.warning("skills: failed to load command %s: %s", path, exc)

    def _scan_agents(self, adir: Path) -> None:
        if not adir.is_dir():
            return
        for path in sorted(adir.glob("*.md")):
            try:
                text = self._read_text(path)
                if text is None:
                    continue
                fm, body = parse_frontmatter(text)
                name = fm.get("name") or path.stem
                if name in self.agents:
                    continue  # project wins
                tools = _parse_tools(fm.get("tools"))
                max_iter = _parse_int(fm.get("max_iterations"), DEFAULT_MAX_ITERATIONS)
                self.agents[name] = CustomAgentDef(
                    name=name,
                    description=fm.get("description", ""),
                    tools=tools,
                    max_iterations=max_iter,
                    system_prompt=body,
                    source=str(path),
                )
            except Exception as exc:
                logger.warning("skills: failed to load agent %s: %s", path, exc)

    def _scan_skills(self, sdir: Path) -> None:
        if not sdir.is_dir():
            return
        for sub in sorted(sdir.iterdir()):
            try:
                if not sub.is_dir():
                    continue
                skill_md = sub / "SKILL.md"
                if not skill_md.is_file():
                    logger.debug("skills: no SKILL.md in %s, skipping", sub)
                    continue
                text = self._read_text(skill_md)
                if text is None:
                    continue
                fm, body = parse_frontmatter(text)
                name = fm.get("name") or sub.name
                if name in self.skills:
                    continue  # project wins
                self.skills[name] = SkillDef(
                    name=name,
                    description=fm.get("description", ""),
                    body=body,
                    source=str(skill_md),
                    triggers=_parse_triggers(fm.get("triggers")),
                )
            except Exception as exc:
                logger.warning("skills: failed to load skill %s: %s", sub, exc)

    # ---- accessors ------------------------------------------------------
    def command_names(self) -> List[str]:
        """Return ['/foo', ...] for the completer."""
        return [f"/{name}" for name in sorted(self.commands)]

    def skill_names(self) -> List[str]:
        """Return ['/bar', ...] for the completer."""
        return [f"/{name}" for name in sorted(self.skills)]

    def triggered(self, message: str) -> List[SkillDef]:
        """Skills whose frontmatter `triggers` keyword appears (whole word,
        case-insensitive) in `message` — for auto-injecting relevant skills into
        a turn without the user typing /skill. Empty when nothing matches."""
        text = (message or "").lower()
        hits = []
        for sk in self.skills.values():
            for kw in (sk.triggers or []):
                if re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", text):
                    hits.append(sk)
                    break
        return hits

    def agent_type_overrides(self) -> dict:
        """Return a mapping to merge into an AGENT_TYPES-shaped dict.

        Shape: ``{name: {'tools': list|None, 'max_iterations': int,
        'note': system_prompt}}``.
        """
        return {
            name: {
                "tools": a.tools,
                "max_iterations": a.max_iterations,
                "note": a.system_prompt,
            }
            for name, a in self.agents.items()
        }

    def get_command(self, name: str) -> Optional[CustomCommand]:
        """Look up a command by name (without leading slash)."""
        return self.commands.get(name.lstrip("/"))

    def get_skill(self, name: str) -> Optional[SkillDef]:
        """Look up a skill by name (without leading slash)."""
        return self.skills.get(name.lstrip("/"))

    def summary(self) -> str:
        """Human-readable one-liner, e.g. '2 commands, 1 agent, 3 skills'."""
        parts = []
        n_c, n_a, n_s = len(self.commands), len(self.agents), len(self.skills)
        if not (n_c or n_a or n_s):
            return "none"
        parts.append(f"{n_c} command{'s' if n_c != 1 else ''}")
        parts.append(f"{n_a} agent{'s' if n_a != 1 else ''}")
        parts.append(f"{n_s} skill{'s' if n_s != 1 else ''}")
        return ", ".join(parts)


# ========================================================================
# Small parsing helpers
# ========================================================================
def _parse_tools(raw: Optional[str]) -> Optional[list]:
    """Parse a space/comma-separated tool list. Empty/absent -> None (all)."""
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    parts = [p.strip() for p in cleaned.replace(",", " ").split()]
    tools = [p for p in parts if p]
    return tools or None


def _parse_int(raw: Optional[str], default: int) -> int:
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except (ValueError, TypeError):
        return default

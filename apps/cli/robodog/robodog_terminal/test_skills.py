# file: robodog_terminal/test_skills.py
"""
Offline unit tests for robodog_terminal/skills.py — frontmatter parsing, discovery of
custom commands / agents / skills across project and user roots, command
substitutions, and the accessor/summary API.

Run:  python robodog_terminal/test_skills.py        (from robodogcli/robodog/)
   or: python -m robodog.robodog_terminal.test_skills

ASCII PASS/FAIL output; exit 0 on all-pass, 1 on any failure.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Several tests deliberately trigger warning-level logs (unreadable/garbled
# files); silence them so the ASCII PASS/FAIL output stays clean.
logging.getLogger("robodog_terminal.skills").setLevel(logging.CRITICAL)

# Support both "python -m robodog.robodog_terminal.test_skills" and direct execution.
try:
    from .skills import (
        CustomCommand,
        SkillsRegistry,
        parse_frontmatter,
    )
except ImportError:  # direct run: add parent so `terminal` is importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from robodog_terminal.skills import (
        CustomCommand,
        SkillsRegistry,
        parse_frontmatter,
    )


_OK = True


def check(cond: bool, msg: str) -> None:
    global _OK
    status = "PASS" if cond else "FAIL"
    if not cond:
        _OK = False
    print(f"  [{status}] {msg}")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_project(root: Path) -> None:
    """Create a sample .robodog project tree under `root`."""
    rb = root / ".robodog"
    # command with frontmatter + substitution tokens in body
    _write(rb / "commands" / "deploy.md", (
        "---\n"
        "description: Deploy the app to an environment\n"
        "argument-hint: <env> [tag]\n"
        "---\n"
        "Deploy to environment $1 with all args: $ARGUMENTS.\n"
        "Project dir is ${ROBODOG_PROJECT_DIR}.\n"
    ))
    # agent with tools list + max_iterations
    _write(rb / "agents" / "reviewer.md", (
        "---\n"
        "name: reviewer\n"
        "description: Reviews code changes\n"
        "tools: read_file grep\n"
        "max_iterations: 5\n"
        "---\n"
        "You are a meticulous code reviewer. Report issues only.\n"
    ))
    # skill directory
    _write(rb / "skills" / "greet" / "SKILL.md", (
        "---\n"
        "name: greet\n"
        "description: Friendly greeting helper\n"
        "---\n"
        "When greeting, be warm and concise.\n"
    ))
    # a malformed skill dir (no SKILL.md) — must be tolerated
    (rb / "skills" / "broken").mkdir(parents=True, exist_ok=True)
    # a malformed command file (garbage frontmatter) — must be tolerated
    _write(rb / "commands" / "garbled.md", (
        "---\n"
        "this line has no colon and is nonsense @@@ ###\n"
        "no closing fence here so treat whole thing as body\n"
        "still going\n"
    ))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="robodog_skilltest_"))
    try:
        # ---- parse_frontmatter ------------------------------------------
        print("=== parse_frontmatter ===")
        fm, body = parse_frontmatter(
            "---\ndescription: hi\nargument-hint: <x>\n---\nBODY LINE\n")
        check(fm.get("description") == "hi", "frontmatter description parsed")
        check(fm.get("argument-hint") == "<x>", "frontmatter argument-hint parsed")
        check(body.strip() == "BODY LINE", "body extracted after fence")

        fm2, body2 = parse_frontmatter("no frontmatter here\njust body")
        check(fm2 == {}, "no-frontmatter returns empty dict")
        check(body2 == "no frontmatter here\njust body", "no-frontmatter body intact")

        fm3, _ = parse_frontmatter("---\nurl: http://x:8080/a\n---\nb")
        check(fm3.get("url") == "http://x:8080/a", "colon inside value preserved")

        fm4, body4 = parse_frontmatter("")
        check(fm4 == {} and body4 == "", "empty text -> empty dict/body")

        fm5, body5 = parse_frontmatter(None)
        check(fm5 == {} and body5 == "", "None text -> empty dict/body")

        # comment + blank + no-colon lines inside a closed block are skipped;
        # a leading blank line in the body after the fence is trimmed.
        fm6, body6 = parse_frontmatter(
            "---\n\n# a comment\nnocolonhere\nname: x\n---\n\nreal body\n")
        check(fm6 == {"name": "x"}, "comment/blank/no-colon lines skipped")
        check(body6.startswith("real body"), "leading blank body line trimmed")

        # frontmatter fence that never closes -> whole text is body
        raw = "---\nname: y\nstill open"
        fm7, body7 = parse_frontmatter(raw)
        check(fm7 == {} and body7 == raw, "unclosed fence -> all body")

        # ---- discover ----------------------------------------------------
        print("=== discover (project root) ===")
        _build_project(tmp)
        reg = SkillsRegistry(cwd=str(tmp))
        reg.discover()
        # deploy + garbled both load as commands
        check("deploy" in reg.commands, "command 'deploy' discovered")
        check("garbled" in reg.commands, "malformed command tolerated (still loads)")
        check("reviewer" in reg.agents, "agent 'reviewer' discovered")
        check("greet" in reg.skills, "skill 'greet' discovered")
        check("broken" not in reg.skills, "skill dir without SKILL.md skipped")

        cmd = reg.commands["deploy"]
        check(cmd.description == "Deploy the app to an environment", "command description")
        check(cmd.argument_hint == "<env> [tag]", "command argument-hint")
        check(cmd.source.endswith("deploy.md"), "command source path recorded")

        # ---- CustomCommand.render ---------------------------------------
        print("=== CustomCommand.render ===")
        rendered = cmd.render("prod v1.2.3", str(tmp))
        check("environment prod" in rendered, "$1 substituted to first arg")
        check("all args: prod v1.2.3" in rendered, "$ARGUMENTS substituted")
        check(str(tmp) in rendered, "${ROBODOG_PROJECT_DIR} substituted to cwd")
        check("$1" not in rendered and "$ARGUMENTS" not in rendered,
              "no substitution tokens remain")

        c2 = CustomCommand("t", "", "", "a=$1 b=$2 all=$ARGUMENTS "
                           "cdir=${CLAUDE_PROJECT_DIR}", "src")
        r2 = c2.render("one two three", "/proj")
        check("a=one b=two" in r2, "positional $1/$2 substituted")
        check("all=one two three" in r2, "$ARGUMENTS full string")
        check("cdir=/proj" in r2, "${CLAUDE_PROJECT_DIR} substituted")
        r3 = c2.render("", "/proj")
        # No positional args: $1/$2 stay literal; $ARGUMENTS -> empty string.
        check("a=$1 b=$2" in r3, "unmatched positionals left literal")
        check("all= cdir=/proj" in r3, "empty $ARGUMENTS + dir token still render")

        # ---- completer name lists ---------------------------------------
        print("=== name lists ===")
        cnames = reg.command_names()
        check("/deploy" in cnames, "command_names has leading slash")
        check(all(n.startswith("/") for n in cnames), "all command names slashed")
        check(reg.skill_names() == ["/greet"], "skill_names formatting")

        # ---- agent_type_overrides ---------------------------------------
        print("=== agent_type_overrides ===")
        ov = reg.agent_type_overrides()
        check("reviewer" in ov, "override keyed by agent name")
        rv = ov["reviewer"]
        check(rv["tools"] == ["read_file", "grep"], "tools parsed to list")
        check(rv["max_iterations"] == 5, "max_iterations parsed to int")
        check("code reviewer" in rv["note"], "note = system prompt body")

        # ---- get_command / get_skill ------------------------------------
        print("=== accessors ===")
        check(reg.get_command("deploy") is cmd, "get_command by name")
        check(reg.get_command("/deploy") is cmd, "get_command tolerates leading slash")
        check(reg.get_command("nope") is None, "get_command missing -> None")
        check(reg.get_skill("greet") is reg.skills["greet"], "get_skill by name")
        check(reg.get_skill("/greet").name == "greet", "get_skill tolerates slash")
        check(reg.get_skill("nope") is None, "get_skill missing -> None")

        # ---- keyword-triggered skills (5.5) -----------------------------
        print("=== triggered skills ===")
        from robodog_terminal.skills import _parse_triggers
        check(_parse_triggers("k8s, kubernetes") == ["k8s", "kubernetes"],
              "triggers parsed from comma list")
        check(_parse_triggers("[deploy release]") == ["deploy", "release"],
              "triggers parsed from bracket/space list")
        check(_parse_triggers("") == [] and _parse_triggers(None) == [],
              "empty triggers -> []")
        trg = tmp / ".robodog" / "skills" / "kube"
        trg.mkdir(parents=True, exist_ok=True)
        (trg / "SKILL.md").write_text(
            "---\nname: kube\ndescription: k\ntriggers: k8s, kubernetes\n---\n"
            "kubectl guidance\n", encoding="utf-8")
        treg = SkillsRegistry(cwd=str(tmp), project_root=str(tmp / ".robodog"))
        treg.discover()
        check(treg.skills["kube"].triggers == ["k8s", "kubernetes"],
              "skill loads its trigger list")
        hits = treg.triggered("scale my Kubernetes deployment please")
        check(len(hits) == 1 and hits[0].name == "kube",
              "a trigger keyword (whole word, case-insensitive) matches")
        check(treg.triggered("the ok8sy thing") == [],
              "a substring does NOT trigger the skill")
        check(treg.triggered("an unrelated question") == [],
              "an unrelated message triggers nothing")

        # ---- summary -----------------------------------------------------
        print("=== summary ===")
        s = reg.summary()
        check("2 commands" in s, "summary counts commands (deploy+garbled)")
        check("1 agent" in s and "1 skill" in s, "summary counts agent/skill")
        empty = SkillsRegistry(cwd=str(tmp), project_root=str(tmp / "nope-x"),
                               user_root=str(tmp / "nope-y"))
        empty.discover()
        check(empty.summary() == "none", "empty registry summary -> 'none'")

        # ---- defaults when frontmatter absent ---------------------------
        print("=== defaults ===")
        # agent stem-name default + all-tools + default max_iterations
        _write(tmp / "u_root" / "agents" / "helper.md",
               "You are a plain helper with no frontmatter.\n")
        udef = SkillsRegistry(cwd=str(tmp),
                              project_root=str(tmp / "no-proj"),
                              user_root=str(tmp / "u_root"))
        udef.discover()
        check("helper" in udef.agents, "agent name defaults to filename stem")
        check(udef.agents["helper"].tools is None, "absent tools -> None (all)")
        check(udef.agents["helper"].max_iterations == 20, "default max_iterations 20")

        # empty tools string -> None; comma-separated tools -> list; bad
        # max_iterations -> default; plus unreadable/non-dir edge entries.
        edge = tmp / "edge"
        _write(edge / "agents" / "loose.md", (
            "---\ntools:   \nmax_iterations: notanumber\n---\nloose agent\n"))
        _write(edge / "agents" / "csv.md", (
            "---\nname: csv\ntools: read_file, grep , bash\n---\ncsv agent\n"))
        # a directory named like an agent file -> unreadable as text, skipped
        (edge / "agents" / "adir.md").mkdir(parents=True, exist_ok=True)
        # a plain file sitting inside skills/ (not a dir) -> skipped
        _write(edge / "skills" / "loosefile.txt", "not a skill dir\n")
        # a skill whose SKILL.md is itself a directory -> unreadable, skipped
        (edge / "skills" / "weird" / "SKILL.md").mkdir(parents=True, exist_ok=True)
        edgereg = SkillsRegistry(cwd=str(tmp), project_root=str(edge),
                                 user_root=str(tmp / "none-here"))
        edgereg.discover()
        check(edgereg.agents["loose"].tools is None, "empty tools string -> None")
        check(edgereg.agents["loose"].max_iterations == 20,
              "non-numeric max_iterations -> default 20")
        check(edgereg.agents["csv"].tools == ["read_file", "grep", "bash"],
              "comma-separated tools parsed")
        check("weird" not in edgereg.skills, "unreadable SKILL.md skipped")
        check(len(edgereg.skills) == 0, "non-dir entry inside skills/ ignored")

        # ---- project-wins-over-user on name clash -----------------------
        print("=== project wins over user ===")
        proj = tmp / "clash_proj"
        user = tmp / "clash_user"
        _write(proj / "commands" / "dup.md", "PROJECT version\n")
        _write(user / "commands" / "dup.md", "USER version\n")
        _write(proj / "agents" / "dupa.md", "---\nname: dupa\n---\nPROJECT agent\n")
        _write(user / "agents" / "dupa.md", "---\nname: dupa\n---\nUSER agent\n")
        _write(proj / "skills" / "dups" / "SKILL.md", "---\nname: dups\n---\nPROJECT skill\n")
        _write(user / "skills" / "dups" / "SKILL.md", "---\nname: dups\n---\nUSER skill\n")
        # a user-only command to prove the user root IS scanned
        _write(user / "commands" / "useronly.md", "user only cmd\n")
        clash = SkillsRegistry(cwd=str(tmp),
                               project_root=str(proj), user_root=str(user))
        clash.discover()
        check("PROJECT version" in clash.commands["dup"].template,
              "project command wins over user")
        check("PROJECT agent" in clash.agents["dupa"].system_prompt,
              "project agent wins over user")
        check("PROJECT skill" in clash.skills["dups"].body,
              "project skill wins over user")
        check("useronly" in clash.commands, "user-only entry still discovered")

        # ---- .claude layout: Claude Code projects work unchanged --------
        print("=== .claude root discovery ===")
        ccwd = tmp / "ccproj"
        _write(ccwd / ".claude" / "commands" / "ship.md",
               "---\ndescription: ship it\n---\nShip the release: $ARGUMENTS\n")
        _write(ccwd / ".claude" / "agents" / "tester.md",
               "---\nname: tester\ntools: bash\n---\nYou run tests.\n")
        _write(ccwd / ".claude" / "skills" / "release" / "SKILL.md",
               "---\ndescription: release process\n---\nTag, build, upload.\n")
        creg = SkillsRegistry(cwd=str(ccwd),
                              user_root=str(tmp / "no-user-root-here"))
        creg.discover()
        check("ship" in creg.commands, ".claude/commands discovered")
        check("tester" in creg.agents and creg.agents["tester"].tools == ["bash"],
              ".claude/agents discovered with tool restriction")
        check("release" in creg.skills, ".claude/skills discovered")

        # .robodog wins over .claude within the same scope
        _write(ccwd / ".robodog" / "commands" / "ship.md",
               "ROBODOG override: $ARGUMENTS\n")
        creg.discover()
        check("ROBODOG override" in creg.commands["ship"].template,
              ".robodog wins over .claude on a name clash")
        check("tester" in creg.agents, ".claude-only entries survive the override")

        # injected project_root still scans its .claude sibling
        sib = tmp / "sibproj"
        _write(sib / ".claude" / "commands" / "sibcmd.md", "sib body\n")
        sreg = SkillsRegistry(cwd=str(sib), project_root=str(sib / ".robodog"),
                              user_root=str(tmp / "no-user-root-here"))
        sreg.discover()
        check("sibcmd" in sreg.commands,
              "injected project_root scans its .claude sibling")

        # ---- tolerance: nonexistent + unreadable ------------------------
        print("=== tolerance ===")
        gone = SkillsRegistry(cwd=str(tmp / "does-not-exist-at-all"))
        gone.discover()  # must not raise
        check(gone.summary() == "none", "missing roots tolerated (no crash)")

        # A directory named like a command file (*.md) is unreadable as text —
        # _read_text hits OSError and the entry is skipped, not fatal.
        badroot = tmp / "badroot"
        (badroot / "commands" / "isadir.md").mkdir(parents=True, exist_ok=True)
        _write(badroot / "commands" / "ok.md", "fine\n")
        badreg = SkillsRegistry(cwd=str(tmp), project_root=str(badroot),
                                user_root=str(tmp / "nope-z"))
        badreg.discover()  # must not raise
        check("isadir" not in badreg.commands, "unreadable .md entry skipped")
        check("ok" in badreg.commands, "sibling command still loads")

        # If parsing itself blows up, discover() must swallow per-file errors and
        # keep going rather than crashing (hits the defensive except guards).
        import robodog_terminal.skills as skills_mod
        orig_pf = skills_mod.parse_frontmatter
        skills_mod.parse_frontmatter = lambda t: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            crashreg = SkillsRegistry(cwd=str(tmp), project_root=str(tmp / ".robodog"),
                                      user_root=str(tmp / "none-here"))
            crashreg.discover()  # must not raise
            check(crashreg.summary() == "none",
                  "parse errors swallowed; discover stays alive")
        finally:
            skills_mod.parse_frontmatter = orig_pf

        # A SKILL.md that reads as None mid-scan is skipped (unreadable file).
        greetreg = SkillsRegistry(cwd=str(tmp), project_root=str(tmp / ".robodog"),
                                  user_root=str(tmp / "none-here"))
        greetreg._read_text = lambda p: None  # simulate every read failing
        greetreg.discover()  # must not raise
        check(greetreg.summary() == "none", "unreadable files skipped mid-scan")

        # discover() is idempotent / re-runnable
        reg.discover()
        check("deploy" in reg.commands, "re-discover repopulates cleanly")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nRESULT:", "ALL PASS" if _OK else "FAILURES")
    return 0 if _OK else 1


if __name__ == "__main__":
    raise SystemExit(main())

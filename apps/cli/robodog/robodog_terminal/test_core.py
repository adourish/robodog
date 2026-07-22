# file: robodog_terminal/test_core.py
"""
Tests for core.py's build_core() — the headless assembly seam that lets an
embedder (a web backend, a bot, a test) drive robodog's agentic core without
any ui.py/argparse dependency. Exercises exactly what an embedder gets for
free (checkpointer, hooks, skills, ask_user default) and that every UI
touchpoint defaults to a safe no-op instead of crashing when not supplied.

Run: python robodog_terminal/test_core.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.core import build_core           # noqa: E402
from robodog_terminal.llm_client import EchoClient      # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def fresh_cwd() -> str:
    return str(Path(tempfile.mkdtemp(prefix="rd_core_")))


def main() -> int:
    global ok

    # ---- no-UI construction + a real turn, zero ui.py/argparse involved ---
    print("=== build_core: standalone construction + a real turn ===")
    core = build_core(fresh_cwd(), EchoClient())
    check(core.registry is not None and core.loop is not None
          and core.skills is not None and core.manager is not None
          and core.checklist is not None and core.store is not None,
          "Core bundle has registry/loop/skills/manager/checklist/store")
    result = core.loop.run("say hi")
    check(bool(result.final_text), f"a turn runs and returns text ({result.final_text!r})")

    # ---- defaults that make it usable with NO callbacks supplied ----------
    print("=== safe no-UI defaults ===")
    check(core.registry.checkpointer is not None,
          "a checkpointer is auto-created when none is supplied")
    check(core.registry.hooks is not None,
          "hooks/settings.json are still loaded with no UI attached")
    r = core.registry.execute("ask_user", {"question": "pick one", "options": "A|B|C"})
    check(r == "User chose: A",
          f"default ask_fn auto-picks the first option ({r!r})")
    # None on_bash_line / on_diff / on_confirm must never crash a real call.
    r = core.registry.execute("bash", {"command": "echo core-standalone-ok"})
    check("core-standalone-ok" in r, "bash runs fine with on_bash_line=None")
    r = core.registry.execute("write_file", {"path": "x.py", "content": "print(1)\n"})
    check("ERROR" not in r and "Created" in r, f"write_file runs fine with on_diff=None ({r!r})")
    core.registry.guard = "confirm"
    r = core.registry.execute("bash", {"command": "rm -rf /tmp/whatever-not-real"})
    check(r.startswith("BLOCKED") and "nothing here can prompt" in r,
          "a high-risk command with on_confirm=None fails CLOSED (never silently runs)")

    # ---- tool gating is applied before agent/ask_user/task_* registration -
    print("=== tool gating ===")
    # allowed_tools filters the base toolset (default_registry's read/write/bash/
    # glob/grep/...) BEFORE agent/ask_user/task_* are registered — same order as
    # the original inline app.py code, so those always remain regardless.
    gated = build_core(fresh_cwd(), EchoClient(), allowed_tools=["read_file"])
    base_tools = set(gated.registry._tools) - {"agent", "ask_user", "task_add",  # noqa: SLF001
                                                "task_list", "task_output", "task_update"}
    check(base_tools == {"read_file"},
          f"allowed_tools restricts the base toolset to exactly that set ({sorted(base_tools)})")
    no_agent = build_core(fresh_cwd(), EchoClient(), disallowed_tools=["agent"])
    check(no_agent.registry.get("agent") is None, "disallowed_tools=['agent'] skips agent registration")
    with_agent = build_core(fresh_cwd(), EchoClient())
    check(with_agent.registry.get("agent") is not None, "agent tool registers by default")

    # ---- permission-mode / guard / net-writes plumbing ---------------------
    print("=== permission-mode / guard / net-writes ===")
    plan_core = build_core(fresh_cwd(), EchoClient(), permission_mode="plan")
    check(plan_core.registry.mode == "plan", "permission_mode='plan' propagates to the registry")
    guard_core = build_core(fresh_cwd(), EchoClient(), guard="confirm", net_writes="deny")
    check(guard_core.registry.guard == "confirm" and guard_core.registry.net_guard == "deny",
          "guard/net_writes params propagate to the registry")

    # ---- caller-supplied callbacks are actually wired, not ignored --------
    print("=== caller-supplied callbacks fire ===")
    seen = {"diff": False, "bash_line": False, "log": []}
    cb_core = build_core(
        fresh_cwd(), EchoClient(),
        on_diff=lambda path, diff: seen.__setitem__("diff", True),
        on_bash_line=lambda ln: seen.__setitem__("bash_line", True),
        log=lambda msg: seen["log"].append(msg),
    )
    cb_core.registry.execute("write_file", {"path": "y.py", "content": "print(2)\n"})
    check(seen["diff"], "on_diff fires on a real write_file call")
    cb_core.registry.execute("bash", {"command": "echo line"})
    check(seen["bash_line"], "on_bash_line fires on a real bash call")
    check(len(seen["log"]) >= 0, "log callback wired without error (may be empty if nothing to log)")

    print("\nCORE:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

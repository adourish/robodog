# file: robodog_terminal/selftest.py
"""
Offline end-to-end self-test of the agentic loop, tools, and tool-call parser
using a scripted EchoClient. No network / no the gateway creds required.

Proves the core agentic flow: model asks to create a file, run it,
read the output, then gives a final answer.

Run:  python -m robodog.robodog_terminal.selftest      (from robodogcli/)
   or: python robodog_terminal/selftest.py             (from robodogcli/robodog/)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Support both "python -m robodog.robodog_terminal.selftest" and direct execution.
try:
    from .llm_client import EchoClient
    from .tools import default_registry
    from .loop import AgentLoop
    from .agents import register_agent_tool
except ImportError:  # direct run: add parent so `terminal` is importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from robodog_terminal.llm_client import EchoClient
    from robodog_terminal.tools import default_registry
    from robodog_terminal.loop import AgentLoop
    from robodog_terminal.agents import register_agent_tool


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="robodog_selftest_"))

    # Scripted model turns: each string is one LLM completion.
    script = [
        # 1) create a python file
        'I will create the script.\n'
        '<tool name="write_file">\n'
        '  <param name="path">hello.py</param>\n'
        '  <param name="content">print("hello from robodog " + str(2 + 2))</param>\n'
        '</tool>',
        # 2) run it
        'Now I will run it.\n'
        '<tool name="bash">\n'
        '  <param name="command">python hello.py</param>\n'
        '</tool>',
        # 3) read it back to confirm
        '<tool name="read_file">\n'
        '  <param name="path">hello.py</param>\n'
        '</tool>',
        # 4) final answer (no tool blocks)
        'Done. Created hello.py, ran it (printed "hello from robodog 4"), and verified its contents.',
    ]

    client = EchoClient(script=script)
    registry = default_registry(cwd=str(workdir))

    events = []
    loop = AgentLoop(client, registry, on_event=lambda k, d: events.append((k, d)))
    result = loop.run("Create hello.py that prints a greeting and 2+2, run it, and confirm.")

    # ---- assertions -----------------------------------------------------
    ok = True

    def check(cond, msg):
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        print(f"  [{status}] {msg}")

    hello = workdir / "hello.py"
    check(hello.exists(), "hello.py was created")
    check("hello from robodog" in hello.read_text(), "file content is correct")

    tool_dones = [d for k, d in events if k == "tool_done"]
    bash_results = [d["result"] for d in tool_dones if "$ python hello.py" in d["result"]]
    check(bool(bash_results), "bash tool executed the script")
    check(any("hello from robodog 4" in r for r in bash_results), "script printed expected output (2+2=4)")
    check(result.iterations == 4, f"loop ran 4 iterations (got {result.iterations})")
    check("Done." in result.final_text, "final answer returned without tool blocks")

    print("\n--- final answer ---")
    print(result.final_text)
    print(f"\n--- loop: {result.iterations} iterations, {result.total_tokens} tokens ---")

    # ================= scenario 2: subagent delegation ===================
    print("\n=== scenario 2: subagent (agent tool) ===")
    (workdir / "secret.txt").write_text("the magic word is XYZZY", encoding="utf-8")

    # Shared client script: parent turn 1 delegates; child turns interleave
    # (child reads the file, then answers); parent turn 2 finalizes.
    script2 = [
        # parent iteration 1: delegate to an explore subagent
        'Delegating to a subagent.\n'
        '<tool name="agent">\n'
        '  <param name="prompt">Read secret.txt and report the magic word.</param>\n'
        '  <param name="type">explore</param>\n'
        '</tool>',
        # child iteration 1: read the file
        '<tool name="read_file"><param name="path">secret.txt</param></tool>',
        # child iteration 2: final answer (returned to parent as tool result)
        'The magic word in secret.txt is XYZZY.',
        # parent iteration 2: final answer using the child's report
        'The subagent found it: the magic word is XYZZY.',
    ]
    client2 = EchoClient(script=script2)
    reg2 = default_registry(cwd=str(workdir))
    child_events = []
    register_agent_tool(reg2, client2,
                        on_child_event=lambda k, d: child_events.append((k, d)))
    parent_events = []
    loop2 = AgentLoop(client2, reg2, on_event=lambda k, d: parent_events.append((k, d)))
    r2 = loop2.run("What is the magic word in secret.txt? Use a subagent.")

    check("XYZZY" in r2.final_text, "parent's final answer contains child's finding")
    tool_results = [t for t in r2.turns if t.role == "tool" and t.tool_name == "agent"]
    import re as _re
    check(bool(tool_results) and _re.search(r"subagent#\d+:explore finished",
                                            tool_results[0].content),
          "agent tool result carries subagent summary header (with child id)")
    check(any(k == "tool_start" and d["name"] == "read_file" for k, d in child_events),
          "child subagent actually used read_file")
    check(any(d.get("child_id") for k, d in child_events),
          "child events are tagged with a child_id")
    # depth cap: child registry must not contain the agent tool
    from robodog_terminal.agents import _child_registry
    check("agent" not in _child_registry(reg2, "explore")._tools,
          "depth cap: child registry has no agent tool")
    check("bash" not in _child_registry(reg2, "explore")._tools,
          "explore type is read-only (no bash)")
    check("bash" in _child_registry(reg2, "general")._tools,
          "general type keeps bash")
    check(r2.iterations == 2, f"parent loop ran 2 iterations (got {r2.iterations})")

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

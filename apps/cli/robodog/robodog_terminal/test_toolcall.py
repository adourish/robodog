# file: robodog_terminal/test_toolcall.py
"""
Parser-hardening regression tests for toolcall.py.
Run: python robodog_terminal/test_toolcall.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal.toolcall import parse_tool_calls, has_tool_calls  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def main() -> int:
    global ok
    calls, prose = parse_tool_calls(
        'Doing it.\n<tool name="bash"><param name="command">ls</param></tool>')
    check(len(calls) == 1 and calls[0].name == 'bash'
          and calls[0].args['command'] == 'ls', 'plain tool block parses')
    check(prose == 'Doing it.', 'prose extracted')

    text = ('Here:\n```xml\n<tool name="write_file">\n'
            '<param name="path">x.py</param>\n'
            '<param name="content">print(1)</param>\n</tool>\n```')
    calls, prose = parse_tool_calls(text)
    check(len(calls) == 1 and calls[0].args['path'] == 'x.py',
          'fence-wrapped pure tool block unwrapped')

    text = ('All done! To call tools yourself you would write:\n'
            '```\nexample usage:\n<tool name="bash">'
            '<param name="command">rm -rf /</param></tool>\nsee?\n```\n'
            'That is the format.')
    calls, prose = parse_tool_calls(text)
    check(len(calls) == 0, 'quoted example inside mixed fence NOT executed')
    check('That is the format.' in prose, 'prose keeps surrounding text')

    text = ('<tool name="glob"><param name="pattern">*.py</param></tool>\n'
            'And an example not to run:\n```\ndocs: <tool name="bash">'
            '<param name="command">danger</param></tool>\n```\n'
            '<tool name="list_dir"></tool>')
    calls, prose = parse_tool_calls(text)
    check([c.name for c in calls] == ['glob', 'list_dir'],
          'real blocks run, fenced example skipped')

    calls, _ = parse_tool_calls(
        '<tool name="grep"><param name="pattern">a &lt; b &amp;&amp; c</param></tool>')
    check(calls[0].args['pattern'] == 'a < b && c', 'html entities unescaped')

    content = 'def f():\n    return "x > y"\n'
    calls, _ = parse_tool_calls(
        f'<tool name="write_file"><param name="path">f.py</param>'
        f'<param name="content">{content}</param></tool>')
    check('def f():' in calls[0].args['content']
          and '"x > y"' in calls[0].args['content'], 'multiline code content preserved')

    text = ('```\n<tool name="glob"><param name="pattern">*.md</param></tool>\n'
            '<tool name="list_dir"></tool>\n```')
    calls, _ = parse_tool_calls(text)
    check(len(calls) == 2, 'pure fence with two tool blocks unwraps both')

    # extra attributes on the <tool> tag are tolerated and captured as params
    calls, _ = parse_tool_calls(
        '<tool name="run_script" interpreter="python">'
        '<param name="content">print(1)</param></tool>')
    check(len(calls) == 1 and calls[0].name == "run_script"
          and calls[0].args.get("interpreter") == "python"
          and calls[0].args.get("content") == "print(1)",
          'tool tag attributes captured as params (interpreter=python)')

    # a <param> in the body overrides a same-named tag attribute
    calls, _ = parse_tool_calls(
        '<tool name="bash" timeout="5"><param name="command">ls</param>'
        '<param name="timeout">30</param></tool>')
    check(calls[0].args["timeout"] == "30" and calls[0].args["command"] == "ls",
          'body <param> overrides tag attribute of same name')

    # literal \n escapes in single-line content decode to real newlines
    calls, _ = parse_tool_calls(
        '<tool name="write_file"><param name="path">c.py</param>'
        '<param name="content">x = 1\\nprint(x)</param></tool>')
    check(calls[0].args['content'] == 'x = 1\nprint(x)',
          'literal backslash-n decoded in single-line content')

    # real newlines present -> \n inside strings preserved literally
    calls, _ = parse_tool_calls(
        '<tool name="write_file"><param name="path">d.py</param>'
        '<param name="content">a = "x\\ny"\nprint(a)</param></tool>')
    check(calls[0].args['content'] == 'a = "x\\ny"\nprint(a)',
          'real-newline content keeps literal \\n escapes untouched')

    # Anthropic-style close tag: <param> opened but </parameter> closed. From a
    # real session this DROPPED the command (bash ran empty) or contaminated it
    # with `</parameter> <param name="interpreter">…`.
    calls, _ = parse_tool_calls(
        '<tool name="bash"><param name="command">Get-ChildItem C:/x | '
        'Select-Object Name</parameter>'
        '<param name="interpreter">powershell</parameter></tool>')
    check(len(calls) == 1 and calls[0].args.get('command', '').startswith('Get-ChildItem')
          and '</param' not in calls[0].args.get('command', ''),
          '</parameter> close tag does not drop/contaminate the command')
    check(calls[0].args.get('interpreter') == 'powershell',
          'the following param is still parsed after a </parameter> close')

    # Full Anthropic format: <function_calls><invoke><parameter>…
    calls, prose = parse_tool_calls(
        'Let me look.\n<function_calls><invoke name="list_dir">'
        '<parameter name="path">C:/projects</parameter></invoke></function_calls>')
    check(len(calls) == 1 and calls[0].name == 'list_dir'
          and calls[0].args.get('path') == 'C:/projects',
          '<invoke>/<parameter> Anthropic format parses as a tool call')
    check('function_calls' not in prose and 'Let me look.' in prose,
          'the <function_calls> wrapper is stripped from prose (no leak)')
    check(has_tool_calls('<invoke name="bash"><parameter name="command">ls'
                         '</parameter></invoke>'),
          'has_tool_calls recognizes the <invoke> form')

    # Truncation / attempted-tool detectors (Phase 1 loop recovery).
    from robodog_terminal.toolcall import (has_unclosed_tool_call,
                                           looks_like_attempted_tool)
    check(has_unclosed_tool_call('<tool name="bash"><param name="command">ls C:/'),
          'unclosed <tool>/<param> detected (truncation)')
    check(not has_unclosed_tool_call('<tool name="read_file"><param name="path">a</param></tool>'),
          'a complete tool call is NOT flagged as unclosed')
    check(not has_unclosed_tool_call('just prose, nothing tool-like'),
          'plain prose is not flagged as unclosed')
    check(looks_like_attempted_tool('<function_calls> oops broke it'),
          'tool-shaped-but-unparsed text is detected as an attempt')
    check(not looks_like_attempted_tool('here is a normal final answer'),
          'a normal answer is not a tool attempt')

    print('PARSER:', 'ALL PASS' if ok else 'FAILURES')
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

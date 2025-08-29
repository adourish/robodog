#!/usr/bin/env python3
import os
import sys
import argparse
import logging
import json
from pprint import pprint

# pip install --upgrade requests   tiktoken   PyYAML   openai   playwright   pydantic   langchain setuptools
# support both “python -m robodog.cli” and “python cli.py” invocations:
try:
    from .service import RobodogService
    from .mcphandler import run_robodogmcp
    from .todo import TodoService
except ImportError:
    from service import RobodogService
    from mcphandler import run_robodogmcp
    from todo import TodoService

def print_help():
    cmds = {
        "help":                "show this help",
        "models":              "list configured models",
        "model <name>":        "switch model",
        "key <prov> <key>":    "set API key for provider",
        "getkey <prov>":       "get API key for provider",
        "import <glob>":       "import files into knowledge",
        "export <file>":       "export chat+knowledge snapshot",
        "clear":               "clear chat+knowledge",
        "stash <name>":        "stash state",
        "pop <name>":          "restore stash",
        "list":                "list stashes",
        "temperature <n>":     "set temperature",
        "top_p <n>":           "set top_p",
        "max_tokens <n>":      "set max_tokens",
        "frequency_penalty <n>":"set frequency_penalty",
        "presence_penalty <n>":"set presence_penalty",
        "stream":              "enable streaming",
        "rest":                "disable streaming",
        "folders <dirs>":      "set MCP roots",
        "include":             "include files via MCP",
        "curl":                "fetch web pages / scripts",
        "play":                "run AI-driven Playwright tests",
        "mcp":                 "invoke raw MCP operation",
        "todo":                "run next To Do task",
    }
    print("\nAvailable /commands:\n")
    for cmd, desc in cmds.items():
        print(f"  /{cmd:<20} — {desc}")
    print()

def parse_cmd(line):
    parts = line.strip().split()
    return parts[0][1:], parts[1:]

def interact(svc: RobodogService):
    """
    Read‐eval‐print loop. Commands prefixed with '/', otherwise free‐form chat.
    """
    prompt_symbol = lambda: f"[{svc.cur_model}]{'»' if svc.stream else '>'} "
    print("robodog CLI — type /help to list commands.")
    while True:
        try:
            line = input(prompt_symbol()).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        if not line:
            continue

        if line.startswith("/"):
            cmd, args = parse_cmd(line)
            try:
                if cmd == "help":
                    print_help()

                elif cmd == "models":
                    for m in svc.list_models():
                        print(" ", m)

                elif cmd == "model":
                    if not args:
                        print("Usage: /model <model_name>")
                    else:
                        svc.set_model(args[0])
                        print(f"Model set to: {svc.cur_model}")

                elif cmd == "key":
                    if len(args) < 2:
                        print("Usage: /key <provider> <api_key>")
                    else:
                        svc.set_key(args[0], args[1])
                        print(f"API key for '{args[0]}' set.")

                elif cmd == "getkey":
                    if not args:
                        print("Usage: /getkey <provider>")
                    else:
                        key = svc.get_key(args[0])
                        print(f"{args[0]} API key: {key or '<none>'}")

                elif cmd == "folders":
                    if not args:
                        print("Usage: /folders <dir1> [dir2 …]")
                    else:
                        resp = svc.call_mcp("SET_ROOTS", {"roots": args})
                        print("MCP server roots:")
                        for r in resp.get("roots", []):
                            print("  " + r)

                elif cmd == "include":
                    if not args:
                        print("Usage: /include [spec] [prompt]")
                    else:
                        spec_prompt = line[len("/include "):].strip()
                        parts = spec_prompt.split()
                        brk = 1
                        for i, t in enumerate(parts[1:], start=1):
                            if not (t == "recursive" or t.startswith(("file=", "dir=", "pattern="))):
                                brk = i
                                break
                        spec = " ".join(parts[:brk])
                        ptext = " ".join(parts[brk:]) or None
                        knowledge = svc.include(spec)
                        prompt = ptext + " " + knowledge
                        answer = svc.ask(prompt)
                        if answer is not None:
                            svc.context += f"\nAI: {answer}"

                elif cmd == "curl":
                    svc.curl(args)

                elif cmd == "play":
                    svc.play(" ".join(args))

                elif cmd == "mcp":
                    if not args:
                        print("Usage: /mcp OP [JSON]")
                    else:
                        op = args[0].upper()
                        raw = " ".join(args[1:]).strip()
                        payload = {}
                        if raw:
                            try:
                                payload = json.loads(raw)
                            except json.JSONDecodeError as e:
                                print("Invalid JSON payload:", e)
                                continue
                        res = svc.call_mcp(op, payload)
                        pprint(res)

                elif cmd == "import":
                    if not args:
                        print("Usage: /import <glob>")
                    else:
                        cnt = svc.import_files(args[0])
                        print(f"Imported {cnt} files.")

                elif cmd == "export":
                    if not args:
                        print("Usage: /export <filename>")
                    else:
                        svc.export_snapshot(args[0])
                        print(f"Exported to {args[0]}")

                elif cmd == "clear":
                    svc.clear()
                    print("Cleared chat history and knowledge.")

                elif cmd == "stash":
                    if not args:
                        print("Usage: /stash <name>")
                    else:
                        svc.stash(args[0])
                        print(f"Stashed under '{args[0]}'.")

                elif cmd == "pop":
                    if not args:
                        print("Usage: /pop <name>")
                    else:
                        svc.pop(args[0])
                        print(f"Popped '{args[0]}' into current session.")

                elif cmd == "list":
                    st = svc.list_stashes()
                    if not st:
                        print("No stashes.")
                    else:
                        print("Stashes:")
                        for name in st:
                            print(" ", name)

                elif cmd in ("temperature", "top_p", "max_tokens",
                             "frequency_penalty", "presence_penalty"):
                    if not args:
                        print(f"Usage: /{cmd} <value>")
                    else:
                        try:
                            val = float(args[0]) if "." in args[0] else int(args[0])
                            svc.set_param(cmd, val)
                            print(f"{cmd} set to {val}")
                        except Exception as e:
                            print("Invalid value:", e)

                elif cmd == "stream":
                    svc.stream = True
                    print("Switched to streaming mode.")

                elif cmd == "rest":
                    svc.stream = False
                    print("Switched to REST mode (no streaming).")

                elif cmd == "todo":
                    # run next To Do task
                    try:
                        svc.todo.run_next_task(svc)
                    except Exception as e:
                        print("Error running /todo:", e)

                else:
                    print(f"unknown /cmd: {cmd}")

            except Exception as err:
                print(f"Error: {err}")

        else:
            # free-form chat
            svc.context += f"\nUser: {line}"
            resp = svc.ask(line)
            svc.context += f"\nAI: {resp}"

def main():
    parser = argparse.ArgumentParser(prog="robodog",
        description="Combined MCP file-server + Robodog CLI")
    parser.add_argument('--config', default='config.yaml',
                        help='path to robodog YAML config')
    parser.add_argument('--folders', nargs='+', required=True,
                        help='one or more root folders to serve')
    parser.add_argument('--host', default='127.0.0.1',
                        help='MCP host (default 127.0.0.1)')
    parser.add_argument('--port', type=int, default=2500,
                        help='MCP port (default 2500)')
    parser.add_argument('--token', required=True,
                        help='MCP auth token')
    parser.add_argument('--model', '-m',
                        help='startup model name')
    parser.add_argument('--log-file', default='robodog.log',
                        help='path to log file')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'],
                        help='set the root logging level')
    # new flag for backups
    parser.add_argument('--backupFolder', default=r'c:\temp',
                        help='folder to store focus-file backups')
    args = parser.parse_args()

    # configure logging
    root = logging.getLogger()
    level = getattr(logging, args.log_level.upper(), logging.INFO)
    root.setLevel(logging.INFO)
    fmt = logging.Formatter('[%(asctime)s] %(levelname)s:%(message)s')
    ch = logging.StreamHandler(sys.stdout); ch.setFormatter(fmt); root.addHandler(ch)
    fh = logging.FileHandler(args.log_file); fh.setFormatter(fmt); root.addHandler(fh)
    logging.info("Starting robodog")

    # instantiate service
    svc = RobodogService(args.config)
    # wire up the To-Do engine
    svc.todo = TodoService(args.folders)
    # assign backup-folder into service so todo can use it
    svc.backup_folder = args.backupFolder

    # start MCP server
    server = run_robodogmcp(
        host    = args.host,
        port    = args.port,
        token   = args.token,
        folders = args.folders,
        svc     = svc
    )
    logging.info(f"MCP file server on {args.host}:{args.port}")

    # tell the service how to reach its own MCP server
    svc.mcp_cfg['baseUrl'] = f"http://{args.host}:{args.port}"
    svc.mcp_cfg['apiKey']  = args.token

    # optional startup model
    if args.model:
        svc.set_model(args.model)
        logging.info(f"Startup model set to {svc.cur_model}")

    try:
        interact(svc)
    finally:
        logging.info("Shutting down MCP server")
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    main()
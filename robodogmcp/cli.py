#!/usr/bin/env python3
import os
import sys
import re
import glob
import shutil
import datetime
import yaml
import argparse
import json
import requests
from pprint import pprint

# -----------------------------------------------------------------------------
DEFAULT_CONFIG = """
configs:
  providers:
    - provider: openAI
      baseUrl: "https://api.openai.com"
      apiKey: "<>"
      httpReferer: ""
  specialists: []
  mcpServer:
    baseUrl: "http://localhost:2500"
    apiKey: "testtoken"
  models:
    - provider: openAI
      model: gpt-3.5-turbo
      stream: true
      specialist: nlp
      about: "default"
"""

# -----------------------------------------------------------------------------
try:
    from openai import OpenAI
except ImportError:
    print("Please install the OpenAI Python client: pip install openai", file=sys.stderr)
    sys.exit(1)

class RoboDogCLI:
    def __init__(self, config_path: str, api_key: str = None):
        # load YAML config (creates a default one if missing)
        if not os.path.exists(config_path):
            with open(config_path, "w") as f:
                f.write(DEFAULT_CONFIG)
        with open(config_path) as f:
            cfg = yaml.safe_load(f)["configs"]

        # build provider map & models list
        self.provider_map = {p["provider"]: p for p in cfg["providers"]}
        self.cfg_models   = cfg["models"]
        self.mcp          = cfg.get("mcpServer", {})

        # chat state
        self.context      = ""       # accumulated chat history
        self.knowledge    = ""       # imported docs
        self.stash        = {}       # named snapshots

        # default model & params
        self.cur_model       = self.cfg_models[0]["model"]
        self.stream          = True
        self.temperature     = 1.0
        self.top_p           = 1.0
        self.max_tokens      = 1024
        self.frequency_penalty = 0.0
        self.presence_penalty  = 0.0

        # determine API key: arg > env > config
        self.api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY")
            or self.provider_map[self.model_provider(self.cur_model)]["apiKey"]
        )
        if not self.api_key:
            raise RuntimeError("Missing OpenAI API key")

        # instantiate the OpenAI client
        self.client = OpenAI(api_key=self.api_key)

    def model_provider(self, model_name: str):
        m = next((m for m in self.cfg_models if m["model"] == model_name), None)
        return m["provider"] if m else None

    # --- MCP support ---------------------------------------------------------
    def call_mcp(self, op: str, payload: dict, timeout: float = 5.0) -> dict:
        """
        Call the MCP server.  Format is: POST to baseUrl with
        text/plain body "OP {json_payload}\\n" and
        Authorization: Bearer <apiKey>.
        """
        if not self.mcp.get("baseUrl"):
            raise RuntimeError("MCP baseUrl not configured")
        url = self.mcp["baseUrl"]
        headers = {
            "Content-Type": "text/plain",
            "Authorization": f"Bearer {self.mcp['apiKey']}"
        }
        body = f"{op} {json.dumps(payload)}\n"
        r = requests.post(url, headers=headers, data=body, timeout=timeout)
        r.raise_for_status()
        # Last line is JSON
        lines = r.text.strip().split("\n")
        return json.loads(lines[-1])

    def parse_include(self, text: str) -> dict:
        """
        Parse tokens after '/include'.  Returns dict:
        {type: all|file|dir|pattern, file, dir, pattern, recursive}
        """
        parts = text.strip().split()
        cmd = {"type": None, "file": None, "dir": None, "pattern": "*", "recursive": False}
        if not parts:
            return cmd
        p0 = parts[0]
        # all
        if p0 == "all":
            cmd["type"] = "all"
        # file=...
        elif p0.startswith("file="):
            spec = p0[5:]
            if re.search(r"[*?\[]", spec):
                cmd["type"] = "pattern"
                cmd["pattern"], cmd["dir"], cmd["recursive"] = spec, "", True
            else:
                cmd["type"], cmd["file"] = "file", spec
        # dir=...
        elif p0.startswith("dir="):
            spec = p0[4:]
            cmd["type"], cmd["dir"] = "dir", spec
            for p in parts[1:]:
                if p.startswith("pattern="):
                    cmd["pattern"] = p.split("=",1)[1]
                if p == "recursive":
                    cmd["recursive"] = True
            # if dir itself is a glob:
            if re.search(r"[*?\[]", spec):
                cmd["type"], cmd["pattern"], cmd["dir"], cmd["recursive"] = "pattern", spec, "", True
        # pattern=...
        elif p0.startswith("pattern="):
            cmd["type"]     = "pattern"
            cmd["pattern"]  = p0.split("=",1)[1]
            cmd["recursive"]= True
        return cmd

    # --- command handlers ----------------------------------------------------
    def set_model(self, tokens): ...
    def set_key(self, tokens): ...
    def get_key(self, _): ...
    def clear(self, _): ...
    def show_help(self, _): ...
    def set_param(self, key, tokens): ...
    def do_stream(self, _): ...
    def do_rest(self, _): ...
    def do_list(self, _): ...
    def do_stash(self, tokens): ...
    def do_pop(self, tokens): ...
    def do_export(self, tokens): ...
    def do_import(self, tokens):
        # local files import (unchanged)
        if not tokens:
            print("Usage: /import <file|dir|glob>")
            return
        pat = tokens[0]
        files = glob.glob(pat, recursive=True)
        text = ""
        for fn in files:
            try:
                text += f"\n\n--- {fn} ---\n"
                text += open(fn, encoding="utf8", errors="ignore").read()
            except:
                pass
        self.knowledge += "\n" + text
        print(f"imported {len(files)} files")

    def do_include(self, tokens):
        """
        /include pattern=...|file=...|dir=... [recursive]
        uses MCP server if configured.
        """
        if not tokens:
            print("Usage: /include pattern=<glob>|file=<file>|dir=<dir> [recursive]")
            return
        inc = self.parse_include(" ".join(tokens))
        included = []

        try:
            if inc["type"] == "all":
                res = self.call_mcp("GET_ALL_CONTENTS", {})
                included = res.get("contents", [])

            elif inc["type"] == "file":
                # search for the file anywhere
                s = self.call_mcp("SEARCH", {
                    "root": inc["file"],
                    "pattern": inc["file"],
                    "recursive": True
                })
                if not s.get("matches"):
                    raise RuntimeError(f"No file {inc['file']}")
                f = self.call_mcp("READ_FILE", {"path": s["matches"][0]})
                included = [ {"path": f["path"], "content": f["content"]} ]

            elif inc["type"] in ("pattern","dir"):
                root = inc["dir"] if inc["type"] == "dir" else ""
                s = self.call_mcp("SEARCH", {
                    "root": root,
                    "pattern": inc["pattern"],
                    "recursive": inc["recursive"]
                })
                matches = s.get("matches", [])
                if not matches:
                    raise RuntimeError(f"No files matching {inc['pattern']}")
                for p in matches:
                    f = self.call_mcp("READ_FILE", {"path": p})
                    included.append({"path": f["path"], "content": f["content"]})

            else:
                raise RuntimeError("Bad include syntax")

            # stitch into knowledge
            text = ""
            for i in included:
                print(f"Include: {i['path']} ")
                text += f"\n\n--- {i['path']} ---\n{i['content']}"
            self.knowledge += text
            print(f"Include → {len(included)} files")

        except Exception as e:
            print("include error:", e)

    # --- parsing & main loop ------------------------------------------------
    def parse_command(self, line: str):
        parts = line.strip().split()
        return parts[0][1:], parts[1:]

    def interact(self):
        print("robodog CLI — type /help to list commands.")
        while True:
            try:
                prompt = input(f"[{self.cur_model}]{'»' if self.stream else '>'} ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
                break
            if not prompt:
                continue

            if prompt.startswith("/"):
                cmd, args = self.parse_command(prompt)
                fn = {
                    "help": self.show_help,
                    "model": self.set_model,
                    "key": self.set_key,
                    "getkey": self.get_key,
                    "clear": self.clear,
                    "import": self.do_import,
                    "export": self.do_export,
                    "stash": self.do_stash,
                    "pop": self.do_pop,
                    "list": self.do_list,
                    "temperature": lambda a: self.set_param("temperature", a),
                    "top_p":       lambda a: self.set_param("top_p", a),
                    "frequency_penalty": lambda a: self.set_param("frequency_penalty", a),
                    "presence_penalty":  lambda a: self.set_param("presence_penalty", a),
                    "stream": self.do_stream,
                    "rest":   self.do_rest,
                    "include": self.do_include
                }.get(cmd)
                if fn:
                    fn(args)
                else:
                    print("unknown /cmd:", cmd)
                continue

            # normal chat
            self.context += f"\nUser: {prompt}"
            reply = self.ask(prompt)
            if reply:
                print(reply)
                self.context += "\nAI: " + reply

    def ask(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": "You are Robodog, a helpful assistant."},
            {"role": "system", "content": "Chat History:\n" + self.context},
            {"role": "system", "content": "Knowledge Base:\n" + self.knowledge},
            {"role": "user",   "content": prompt},
        ]

        resp = self.client.chat.completions.create(
            model=self.cur_model,
            messages=messages,
            temperature=self.temperature,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            stream=self.stream,
        )

        if self.stream:
            answer = ""
            for chunk in resp:
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    print(delta, end="", flush=True)
                    answer += delta
            print()
            return answer
        else:
            return resp.choices[0].message.content.strip()

# -----------------------------------------------------------------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser(prog="robodog")
    p.add_argument("-c", "--config", default="config.yaml",
                   help="path to robodog YAML config")
    args = p.parse_args()
    cli = RoboDogCLI(args.config)
    cli.interact()
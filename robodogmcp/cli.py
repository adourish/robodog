#!/usr/bin/env python3
import os
import sys
import re
import glob
import shutil
import datetime
import yaml
import argparse
from pprint import pprint

# -----------------------------------------------------------------------------
DEFAULT_CONFIG = """
configs:
  providers:
    - provider: openAI
      baseUrl: "https://api.openai.com"
      apiKey: "<YOUR_OPENAI_KEY>"
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

        # instantiate the new OpenAI client
        self.client = OpenAI(api_key=self.api_key)

    def model_provider(self, model_name: str):
        m = next((m for m in self.cfg_models if m["model"] == model_name), None)
        return m["provider"] if m else None

    # --- command handlers ----------------------------------------------------
    def set_model(self, tokens):
        if not tokens:
            print("Usage: /model <name>")
            return
        name = tokens[0]
        if any(m["model"] == name for m in self.cfg_models):
            self.cur_model = name
            print(f"model ← {name}")
        else:
            print("Unknown model:", name)

    def set_key(self, tokens):
        if not tokens:
            print("Usage: /key <your-api-key>")
            return
        self.api_key = tokens[0]
        self.client = OpenAI(api_key=self.api_key)
        print("key ←", self.api_key[:4] + "…")

    def get_key(self, _):
        print("key →", self.api_key[:4] + "…")

    def clear(self, _):
        os.system("cls" if os.name == "nt" else "clear")

    def show_help(self, _):
        cmds = [
            "/help", "/model <name>", "/key <key>", "/getkey", "/clear",
            "/import <path>", "/export <name>", "/stash <name>", "/pop <name>", "/list",
            "/temperature <n>", "/top_p <n>", "/max_tokens <n>",
            "/frequency_penalty <n>", "/presence_penalty <n>",
            "/stream", "/rest", "include pattern=<glob>|file=<file>|recursive"
        ]
        print("Commands:")
        for c in cmds:
            print(" ", c)

    def set_param(self, key, tokens):
        if not tokens:
            print(f"Usage: /{key} <value>")
            return
        val = float(tokens[0])
        setattr(self, key, val)
        print(f"{key} ← {val}")

    def do_stream(self, _):
        self.stream = True
        print("stream ON")

    def do_rest(self, _):
        self.stream = False
        print("stream OFF")

    def do_list(self, _):
        print("stash list:", list(self.stash.keys()))

    def do_stash(self, tokens):
        if not tokens:
            print("Usage: /stash <name>")
            return
        name = tokens[0]
        self.stash[name] = {"context": self.context, "knowledge": self.knowledge}
        print("stashed →", name)

    def do_pop(self, tokens):
        if not tokens:
            print("Usage: /pop <name>")
            return
        name = tokens[0]
        snap = self.stash.get(name)
        if not snap:
            print("no such stash:", name)
        else:
            self.context   = snap["context"]
            self.knowledge = snap["knowledge"]
            print("popped →", name)

    def do_export(self, tokens):
        name = tokens[0] if tokens else f"snapshot-{datetime.datetime.now():%Y%m%d%H%M%S}.txt"
        data = (
            f"MODEL {self.cur_model}\n"
            f"TEMP {self.temperature}\n\n"
            f"Knowledge:\n{self.knowledge}\n\n"
            f"History:\n{self.context}\n"
        )
        with open(name, "w") as f:
            f.write(data)
        print("wrote", name)

    def do_import(self, tokens):
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
        opts = " ".join(tokens)
        m_file = re.search(r"file=([^ ]+)", opts)
        m_pat  = re.search(r"pattern=([^ ]+)", opts)
        rec    = "recursive" in opts
        files = []
        if m_file:
            fn = m_file.group(1)
            if os.path.exists(fn):
                files = [fn]
        elif m_pat:
            files = glob.glob(m_pat.group(1), recursive=rec)
        count = 0
        for fn in files:
            try:
                text = open(fn, encoding="utf8", errors="ignore").read()
                self.knowledge += f"\n\n--- {fn} ---\n{text}"
                count += 1
            except:
                pass
        print(f"include → {count} files")

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
                    "max_tokens":  lambda a: self.set_param("max_tokens", a),
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
            max_tokens=self.max_tokens,
            stream=self.stream,
        )

        if self.stream:
            answer = ""
            for chunk in resp:
            # delta is a ChoiceDelta object; pull its .content attribute
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
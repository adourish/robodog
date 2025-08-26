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
import tiktoken
import concurrent.futures
import logging
from pathlib import Path
import threading
import socketserver
import fnmatch
import hashlib
import asyncio
from pprint import pprint
from openai import OpenAI

# Attempt to import pyppeteer for legacy /curl (no longer used)
try:
    from pyppeteer import launch
except ImportError:
    launch = None

# Attempt to import Playwright for /curl and /play
try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

# ----------------------------------------
# DEFAULT CONFIG for the CLI portion
# ----------------------------------------
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

# ----------------------------------------
# Globals for MCP server (filled in main)
# ----------------------------------------
ROOTS = []
TOKEN = None

def is_utf8_text(path: str, check_bytes: int = 4096) -> bool:
    """
    Return True if the first `check_bytes` of the file at `path`
    can be decoded as UTF-8.
    """
    try:
        with open(path, 'rb') as f:
            raw = f.read(check_bytes)
        raw.decode('utf-8')
        return True
    except (UnicodeDecodeError, OSError):
        return False

def is_within_roots(path: str) -> bool:
    """
    Security check: ensure `path` is within one of the ROOTS.
    """
    ap = os.path.realpath(os.path.abspath(path))
    for r in ROOTS:
        if os.path.commonpath([os.path.realpath(r), ap]) == os.path.realpath(r):
            return True
    return False

def load_or_create_config(config_path: str) -> dict:
    """
    Ensure a Robodog YAML config exists at config_path.
    If missing, offer to create DEFAULT_CONFIG.
    """
    if not os.path.exists(config_path):
        resp = input(
            f"Config file not found at '{config_path}'.\n"
            "Create a new default config? [Y/n]: "
        ).strip().lower()
        if resp in ("", "y", "yes"):
            os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_CONFIG.lstrip())
            print(f"Created default config at '{config_path}'. Edit it and re-run.")
            sys.exit(0)
        else:
            print("Aborting: a configuration file is required.")
            sys.exit(1)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cfg = data.get("configs")
        if not isinstance(cfg, dict):
            raise ValueError("Top‐level 'configs' section missing or malformed.")
        return cfg
    except Exception as e:
        print(f"Error loading config '{config_path}': {e}")
        sys.exit(1)

# ----------------------------------------
# MCP protocol handler
# ----------------------------------------
class MCPHandler(socketserver.StreamRequestHandler):
    def execute_command(self, op: str, arg: str):
        payload = {}
        if arg:
            try:
                payload = json.loads(arg)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON payload: {e}")

        # Dispatch commands...
        if op == 'HELP':
            return {"commands": [
                "LIST_FILES",
                "GET_ALL_CONTENTS",
                "READ_FILE {\"path\":...}",
                "UPDATE_FILE {\"path\":...,\"content\":...}",
                "CREATE_FILE",
                "DELETE_FILE",
                "APPEND_FILE",
                "CREATE_DIR",
                "DELETE_DIR",
                "RENAME",
                "COPY_FILE",
                "SEARCH",
                "CHECKSUM",
                "..."], "status":"ok"}

        if op == 'SET_ROOTS':
            roots = payload.get("roots")
            if not isinstance(roots, list):
                raise ValueError("Missing or invalid 'roots' list")
            new_roots = []
            for r in roots:
                r_abs = os.path.abspath(r)
                if not os.path.isdir(r_abs):
                    raise FileNotFoundError(f"Not a directory: {r_abs}")
                new_roots.append(r_abs)
            global ROOTS
            ROOTS = new_roots
            return {"status":"ok","roots":ROOTS}

        if op == 'LIST_FILES':
            files = []
            for root in ROOTS:
                for dp, _, fns in os.walk(root):
                    for fn in fns:
                        files.append(os.path.join(dp, fn))
            return {"files": files, "status":"ok"}

        if op == 'GET_ALL_CONTENTS':
            contents = []
            for root in ROOTS:
                for dp, _, fns in os.walk(root):
                    for fn in fns:
                        fp = os.path.join(dp, fn)
                        if not is_utf8_text(fp):
                            continue
                        try:
                            txt = open(fp, 'r', encoding='utf-8').read()
                        except Exception as e:
                            txt = f"<error reading {fp}: {e}>"
                        contents.append({"path": fp, "content": txt})
            return {"contents": contents, "status":"ok"}

        if op == 'READ_FILE':
            path = payload.get("path")
            if not path: raise ValueError("Missing 'path'")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            if not os.path.isfile(path): raise FileNotFoundError(path)
            if not is_utf8_text(path): raise ValueError(f"Not valid UTF-8: {path}")
            data = open(path, 'r', encoding='utf-8').read()
            return {"path": path, "content": data, "status":"ok"}

        if op == 'UPDATE_FILE':
            path = payload.get("path"); content = payload.get("content")
            if path is None or content is None:
                raise ValueError("Need 'path' and 'content'")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            parent = os.path.dirname(path)
            if not os.path.isdir(parent): raise FileNotFoundError(parent)
            open(path, 'w', encoding='utf-8').write(content)
            return {"path": path, "status":"ok"}

        if op == 'CREATE_FILE':
            path = payload.get("path"); content = payload.get("content","")
            if not path: raise ValueError("Missing 'path'")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            parent = os.path.dirname(path)
            if not os.path.isdir(parent): raise FileNotFoundError(parent)
            open(path, 'w', encoding='utf-8').write(content)
            return {"path": path, "status":"ok"}

        if op == 'DELETE_FILE':
            path = payload.get("path")
            if not path: raise ValueError("Missing 'path'")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            if not os.path.isfile(path): raise FileNotFoundError(path)
            os.remove(path)
            return {"path": path, "status":"ok"}

        if op == 'APPEND_FILE':
            path = payload.get("path"); content = payload.get("content","")
            if not path: raise ValueError("Missing 'path'")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            open(path, 'a', encoding='utf-8').write(content)
            return {"path": path, "status":"ok"}

        if op == 'CREATE_DIR':
            path = payload.get("path"); mode = payload.get("mode", 0o755)
            if not path: raise ValueError("Missing 'path'")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            os.makedirs(path, mode, exist_ok=True)
            return {"path": path, "status":"ok"}

        if op == 'DELETE_DIR':
            path = payload.get("path"); recursive = payload.get("recursive", False)
            if not path: raise ValueError("Missing 'path'")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)
            return {"path": path, "status":"ok"}

        if op in ('RENAME','MOVE'):
            src = payload.get("src"); dst = payload.get("dst")
            if not src or not dst:
                raise ValueError("Need 'src' and 'dst'")
            if not is_within_roots(src) or not is_within_roots(dst):
                raise PermissionError("Not allowed")
            parent = os.path.dirname(dst)
            if not os.path.isdir(parent): raise FileNotFoundError(parent)
            os.rename(src, dst)
            return {"src": src, "dst": dst, "status":"ok"}

        if op == 'COPY_FILE':
            src = payload.get("src"); dst = payload.get("dst")
            if not src or not dst:
                raise ValueError("Need 'src' and 'dst'")
            if not is_within_roots(src) or not is_within_roots(dst):
                raise PermissionError("Not allowed")
            parent = os.path.dirname(dst)
            if not os.path.isdir(parent): raise FileNotFoundError(parent)
            shutil.copy2(src, dst)
            return {"src": src, "dst": dst, "status":"ok"}

        if op == 'SEARCH':
            raw = payload.get("pattern","*")
            patterns = raw.split('|') if isinstance(raw, str) else [raw]
            recursive = payload.get("recursive", True)
            root = payload.get("root","")
            matches = []
            roots = ROOTS if not root else [root]
            for r in roots:
                if not os.path.isdir(r): continue
                if recursive:
                    for dp, _, fns in os.walk(r):
                        for fn in fns:
                            fp = os.path.join(dp, fn)
                            for pat in patterns:
                                if fnmatch.fnmatch(fp, pat):
                                    matches.append(fp)
                                    break
                else:
                    for fn in os.listdir(r):
                        fp = os.path.join(r, fn)
                        if not os.path.isfile(fp): continue
                        for pat in patterns:
                            if fnmatch.fnmatch(fp, pat):
                                matches.append(fp)
                                break
            return {"matches": matches, "status":"ok"}

        if op == 'CHECKSUM':
            path = payload.get("path")
            if not path: raise ValueError("Missing 'path'")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            h = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return {"path": path, "checksum": h.hexdigest(), "status":"ok"}

        if op in ('QUIT','EXIT'):
            return {"message":"Goodbye!","status":"ok"}

        raise ValueError(f"Unknown command '{op}'")

    def handle(self):
        peer = self.client_address
        raw_first = self.rfile.readline()
        if not raw_first:
            return
        first = raw_first.decode('utf-8', errors='ignore').strip()
        is_http = first.upper().startswith(("GET ","POST ","OPTIONS ")) and "HTTP/" in first

        if is_http:
            # Parse HTTP request, support CORS & bearer auth
            try:
                method, uri, version = first.split(None,2)
            except:
                return
            method = method.upper()
            headers = {}
            while True:
                line = self.rfile.readline().decode('utf-8', errors='ignore')
                if not line or line in ('\r\n','\n'):
                    break
                name, val = line.split(":",1)
                headers[name.lower().strip()] = val.strip()
            if method == 'OPTIONS':
                resp = ["HTTP/1.1 204 No Content",
                        "Access-Control-Allow-Origin: *",
                        "Access-Control-Allow-Methods: POST, OPTIONS",
                        "Access-Control-Allow-Headers: Content-Type, Authorization",
                        "Access-Control-Max-Age: 86400",
                        "Connection: close","",""]
                self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
                return
            if method != 'POST':
                resp = ["HTTP/1.1 405 Method Not Allowed",
                        "Access-Control-Allow-Origin: *",
                        "Allow: POST, OPTIONS",
                        "Content-Type: text/plain; charset=utf-8",
                        "Connection: close","", "Only POST supported\n"]
                self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
                return
            authz = headers.get('authorization','')
            if authz != f"Bearer {TOKEN}":
                body = json.dumps({"status":"error","error":"Authentication required"})
                resp = ["HTTP/1.1 401 Unauthorized",
                        "Access-Control-Allow-Origin: *",
                        "Content-Type: application/json; charset=utf-8",
                        f"Content-Length: {len(body.encode('utf-8'))}",
                        "Connection: close","", body]
                self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
                return
            length = int(headers.get('content-length','0'))
            raw_body = self.rfile.read(length).decode('utf-8', errors='ignore').strip()
            try:
                parts = raw_body.split(' ',1)
                op  = parts[0].upper()
                arg = parts[1] if len(parts)>1 else None
                result = self.execute_command(op, arg)
            except Exception as e:
                result = {"status":"error","error": str(e)}
            body = json.dumps(result, ensure_ascii=False)
            resp = ["HTTP/1.1 200 OK",
                    "Access-Control-Allow-Origin: *",
                    "Access-Control-Allow-Headers: Content-Type, Authorization",
                    "Content-Type: application/json; charset=utf-8",
                    f"Content-Length: {len(body.encode('utf-8'))}",
                    "Connection: close","", body]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))

# ----------------------------------------
# Threaded TCP server for MCP
# ----------------------------------------
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

# ----------------------------------------
# CLI portion
# ----------------------------------------
class RoboDogCLI:
    def __init__(self, config_path: str, api_key: str = None):
        cfg = load_or_create_config(config_path)
        self.provider_map   = {p["provider"]: p for p in cfg["providers"]}
        self.cfg_models     = cfg["models"]
        self.mcp            = cfg.get("mcpServer", {})
        self.context        = ""
        self.knowledge      = ""
        self.stash          = {}
        mdl = self.cfg_models[0]
        self.cur_model       = mdl["model"]
        self.stream          = mdl.get("stream", True)
        self.temperature     = 1.0
        self.top_p           = 1.0
        self.max_tokens      = 1024
        self.frequency_penalty = 0.0
        self.presence_penalty  = 0.0
        self.api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY")
            or self.provider_map[self.model_provider(self.cur_model)]["apiKey"]
        )
        if not self.api_key:
            raise RuntimeError("Missing API key")
        self.client = OpenAI(api_key=self.api_key)

    def model_provider(self, model_name: str):
        m = next((m for m in self.cfg_models if m["model"] == model_name), None)
        return m["provider"] if m else None

    # ---------------------------------------------------
    # MCP helper
    def call_mcp(self, op: str, payload: dict, timeout: float = 30.0) -> dict:
        if not self.mcp.get("baseUrl"):
            raise RuntimeError("MCP baseUrl not configured")
        url = self.mcp["baseUrl"]
        headers = {
            "Content-Type": "text/plain",
            "Authorization": f"Bearer {self.mcp['apiKey']}"
        }
        body = f"{op} {json.dumps(payload)}\n"
        resp = requests.post(url, headers=headers, data=body, timeout=timeout)
        resp.raise_for_status()
        lines = resp.text.strip().split("\n")
        return json.loads(lines[-1])

    # ---------------------------------------------------
    # Core LLM ask
    def ask(self, prompt: str) -> str:
        messages = [
            {"role":"system","content":"You are Robodog, a helpful assistant."},
            {"role":"system","content":"Chat History:\n"+self.context},
            {"role":"system","content":"Knowledge Base:\n"+self.knowledge},
            {"role":"user","content":prompt},
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
        answer = ""
        if self.stream:
            for chunk in resp:
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    print(delta, end="", flush=True)
                    answer += delta
            print()
        else:
            answer = resp.choices[0].message.content.strip()
        return answer

    # ---------------------------------------------------
    # /model
    def set_model(self, tokens):
        if not tokens:
            print("Usage: /model <model_name>")
            print("Available models:", ", ".join(m["model"] for m in self.cfg_models))
            return
        new_model = tokens[0]
        if new_model not in [m["model"] for m in self.cfg_models]:
            print(f"Unknown model: '{new_model}'")
            return
        prov = self.model_provider(new_model)
        if not prov or prov not in self.provider_map:
            print(f"Provider '{prov}' not configured.")
            return
        self.cur_model = new_model
        self.api_key = (
            os.getenv("OPENAI_API_KEY")
            or self.provider_map[prov].get("apiKey")
        )
        if not self.api_key:
            print(f"No API key for provider '{prov}'")
            return
        self.client = OpenAI(api_key=self.api_key)
        print(f"Model set to: {self.cur_model}")

    # ---------------------------------------------------
    # /models
    def do_models(self, tokens):
        print("Available models:")
        for m in self.cfg_models:
            line = f"  {m['model']} (provider: {m['provider']})"
            if m.get("about"):
                line += f" – {m['about']}"
            print(line)

    # ---------------------------------------------------
    # /folders
    def do_folders(self, tokens):
        if not tokens:
            print("Usage: /folders <dir1> [dir2 …]")
            return
        for d in tokens:
            if not os.path.isdir(d):
                print(f"Warning: '{d}' is not a directory")
        try:
            resp = self.call_mcp("SET_ROOTS", {"roots": tokens})
            print("MCP server roots:")
            for r in resp.get("roots", []):
                print("  " + r)
        except Exception as e:
            print("Error updating roots:", e)

    # ---------------------------------------------------
    # /include (unchanged)
    def parse_include(self, text: str) -> dict:
        parts = text.strip().split()
        cmd = {"type":None,"file":None,"dir":None,"pattern":"*","recursive":False}
        if not parts:
            return cmd
        p0 = parts[0]
        if p0 == "all":
            cmd["type"] = "all"
        elif p0.startswith("file="):
            spec = p0[5:]
            if re.search(r"[*?\[]", spec):
                cmd["type"],cmd["pattern"],cmd["recursive"] = "pattern", spec, True
            else:
                cmd["type"],cmd["file"] = "file", spec
        elif p0.startswith("dir="):
            spec = p0[4:]
            cmd["type"],cmd["dir"] = "dir", spec
            for p in parts[1:]:
                if p.startswith("pattern="):
                    cmd["pattern"] = p.split("=",1)[1]
                if p == "recursive":
                    cmd["recursive"] = True
            if re.search(r"[*?\[]", spec):
                cmd["type"],cmd["pattern"],cmd["recursive"] = "pattern", spec, True
        elif p0.startswith("pattern="):
            cmd["type"],cmd["pattern"],cmd["recursive"] = "pattern", p0.split("=",1)[1], True
        return cmd

    def do_include(self, tokens):
        MAX_FILES = 500
        READ_TIMEOUT = 30
        MAX_WORKERS = 8
        if not tokens:
            print("Usage: /include [all|file=…|dir=… [pattern=…] [recursive]] [prompt]")
            return
        # split spec vs prompt
        spec_toks, prompt_toks = [], []
        for i, t in enumerate(tokens):
            if i == 0 or t == "recursive" or t.startswith(("file=","dir=","pattern=")):
                spec_toks.append(t)
            else:
                prompt_toks = tokens[i:]
                break
        inc = self.parse_include(" ".join(spec_toks))
        prompt = " ".join(prompt_toks) if prompt_toks else None

        try:
            searches = []
            if inc["type"] == "dir":
                searches.append({
                    "root": inc["dir"],
                    "pattern": inc["pattern"],
                    "recursive": inc["recursive"]
                })
            else:
                pat = inc["pattern"] if inc["type"] == "pattern" else (inc["file"] or "*")
                searches.append({"pattern": pat, "recursive": True})

            matches = []
            for payload in searches:
                res = self.call_mcp("SEARCH", payload, timeout=READ_TIMEOUT)
                matches.extend(res.get("matches", []))
            matches = [m for m in matches if "node_modules" not in Path(m).parts]

            if not matches:
                print("No files matched; aborting.")
                return

            if len(matches) > MAX_FILES:
                ans = input(f"{len(matches)} files; continue? [y/N]: ").strip().lower()
                if ans != "y":
                    print("Cancelled.")
                    return

            included = []
            def _read(p): return self.call_mcp("READ_FILE", {"path": p}, timeout=READ_TIMEOUT)
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                fut2p = {pool.submit(_read,p): p for p in matches}
                for fut in concurrent.futures.as_completed(fut2p):
                    p = fut2p[fut]
                    try:
                        blob = fut.result()
                        content = blob.get("content","")
                        enc = None
                        try:
                            enc = tiktoken.encoding_for_model(self.cur_model)
                        except:
                            enc = tiktoken.get_encoding("gpt2")
                        wc = len(content.split())
                        tc = len(enc.encode(content))
                        print(f"Included: {p} (words:{wc} tokens:{tc})")
                        included.append(content)
                    except Exception as e:
                        print(f"Error reading {p}: {e}")

            combined = "\n".join(included)
            if combined:
                self.knowledge += "\n" + combined + "\n"
                print(f"Total included files: {len(included)}")
            if prompt:
                print(f"→ Prompt: {prompt}")
                self.context += f"\nUser: {prompt}"
                ans = self.ask(prompt)
                self.context += f"\nAI: {ans}"

        except Exception as e:
            print("Include error:", e)

    # ---------------------------------------------------
    # /curl (unchanged)
    def do_curl(self, tokens):
        headless = True
        args = []
        for t in tokens:
            if t == "--no-headless":
                headless = False
            else:
                args.append(t)
        if not args:
            print("Usage: /curl [--no-headless] <url> [<url2>|<js>]")
            return
        url1 = args[0] if args[0].startswith(("http://","https://")) else "http://"+args[0]
        url2 = None; script = None
        if len(args) >= 2 and args[1].startswith(("http://","https://")):
            url2 = args[1] if args[1].startswith(("http://","https://")) else "http://"+args[1]
            if len(args) >= 3:
                script = " ".join(args[2:])
        else:
            if len(args) >= 2:
                script = " ".join(args[1:])
        if async_playwright is None:
            print("Install Playwright: `pip install playwright` + `playwright install`")
            return
        async def runner():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=headless)
                page = await browser.new_page()
                print(f"→ Navigating {url1}")
                await page.goto(url1)
                if url2:
                    print(f"→ Navigating {url2}")
                    await page.goto(url2)
                if script:
                    print("→ Exec script")
                    try:
                        result = await page.evaluate(script)
                    except Exception as e:
                        print("Script error:", e)
                        result = None
                else:
                    result = await page.evaluate("() => document.body.innerText")
                print("----- /curl result -----")
                print(result)
                await browser.close()
        try:
            asyncio.run(runner())
        except Exception as e:
            print("Error in /curl:", e)

    # ---------------------------------------------------
    # /play (unchanged)
    def do_play2(self, tokens):
        if async_playwright is None:
            print("Install Playwright: `pip install playwright` + `playwright install`")
            return
        if not tokens:
            print("Usage: /play <instructions>")
            return
        instructions = " ".join(tokens)
        print("Instructions:", instructions)
        parse_prompt = (
            "Parse into numbered steps:\n\n" + instructions +
            "\n\nRespond ONLY as '1. ...'"
        )
        parsed = self.ask(parse_prompt)
        print("----- Parsed steps -----")
        print(parsed)
        steps = []
        for line in parsed.splitlines():
            m = re.match(r"\s*\d+\.\s*(.+)", line)
            if m:
                steps.append(m.group(1).strip())
        if not steps:
            print("No steps parsed; aborting.")
            return
        results = []
        async def runner():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch()
                page = await browser.new_page()
                await page.route("**/*.{png,jpg,css,svg}", lambda r: r.abort())
                for idx, step in enumerate(steps):
                    print(f"\n>>> Step {idx+1}: {step}")
                    low = step.lower()
                    if low.startswith("navigate to"):
                        tgt = step.split("navigate to",1)[1].strip()
                        await page.goto(tgt, wait_until="domcontentloaded")
                        results.append(True)
                        continue
                    if low.startswith("click"):
                        tgt = step.split("click",1)[1].strip().strip("'\"")
                        await page.click(f"text={tgt}")
                        results.append(True)
                        continue
                    success = False
                    res = None
                    for attempt in (1,2):
                        title = await page.title() or "<no title>"
                        url = page.url
                        print(f"--- Attempt {attempt} on {title} ({url})")
                        mini = await page.evaluate("""
                            () => Array.from(
                                document.querySelectorAll('h1,h2,p,a,button,input')
                            ).slice(0,5).map(e=>({
                                tag: e.tagName,
                                text: e.innerText?.slice(0,80)||''
                            }))
                        """)
                        prompt = (
                            f"You are writing Playwright code.\nTitle: {title}\n"
                            f"URL: {url}\nMiniDOM: {json.dumps(mini)}\n"
                            f"Instruction: {step}\n"
                            "Write ONLY the await-page lines, assign to `result`, then return result."
                        )
                        snippet = self.ask(prompt).strip()
                        if snippet.startswith("```"):
                            snippet = "\n".join(snippet.splitlines()[1:-1])
                        fn_name = f"_step_{idx+1}_a{attempt}"
                        src = f"async def {fn_name}(page):\n"
                        for ln in snippet.splitlines():
                            src += f"    {ln}\n"
                        local = {}
                        try:
                            exec(src, globals(), local)
                            fn = local[fn_name]
                        except Exception as e:
                            print("Compile error:", e)
                            continue
                        try:
                            res = await fn(page)
                            assert res is not None
                            print(f"→ Success: {res!r}")
                            success = True
                            break
                        except Exception as e:
                            print("Runtime error:", e)
                    results.append(success)
                    if not success:
                        print(f"Step {idx+1} failed.")
                await browser.close()
        try:
            asyncio.run(runner())
        except Exception as e:
            print("Error in /play:", e)
        print("\n--- /play summary ---")
        for i, ok in enumerate(results,1):
            print(f"Step {i}: {'Success' if ok else 'Failure'}")

    def do_play(self, tokens):
        """
        /play <instructions>
        Runs AI-driven Playwright tests against a website.
        """
        if async_playwright is None:
            print("Error: Playwright not installed. Install with `pip install playwright` + `playwright install`.")
            return
        if not tokens:
            print("Usage: /play <instructions>")
            return

        instructions = " ".join(tokens)
        print("Instructions:", instructions)

        # 1) Parse instructions into discrete steps
        parse_prompt = (
            "Parse the following instructions into a numbered list of discrete steps:\n\n"
            f"{instructions}\n\n"
            "Respond ONLY as a numbered list (e.g. '1. ...')."
        )
        parsed = self.ask(parse_prompt)
        print("----- Parsed steps -----")
        print(parsed)

        # 2) Extract steps
        steps = [m.group(1).strip() for m in re.finditer(r"\d+\.\s*(.+)", parsed)]
        if not steps:
            print("Error: Couldn't parse any steps. Aborting.")
            return

        step_results = []

        async def runner():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch()
                page = await browser.new_page()
                # block heavy assets
                await page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2}", lambda r: r.abort())

                for idx, step in enumerate(steps):
                    print(f"\n>>> Step {idx+1}: {step}")
                    low = step.lower()

                    # simple shortcuts
                    if low.startswith("navigate to"):
                        url = step.split("navigate to",1)[1].strip()
                        print(f"→ navigate shortcut to {url}")
                        await page.goto(url, wait_until="domcontentloaded")
                        step_results.append(True)
                        continue
                    if low.startswith("click"):
                        target = step.split("click",1)[1].strip().strip("'\"")
                        print(f"→ click shortcut on text={target}")
                        await page.click(f"text={target}")
                        step_results.append(True)
                        continue

                    # non-trivial: up to 2 attempts
                    success = False
                    res = None
                    for attempt in (1,2):
                        title = await page.title() or "<no title>"
                        url   = page.url
                        print(f"--- Attempt {attempt} on {title} ({url}) ---")

                        mini_dom = await page.evaluate("""
                            () => Array.from(
                                document.querySelectorAll('h1,h2,p,a,button,input')
                            ).slice(0,5).map(e=>({
                                tag: e.tagName,
                                text: e.innerText?.trim()?.slice(0,80) || e.getAttribute('value') || ''
                            }))
                        """)

                        prompt_snip = (
                            "You are writing a Python Playwright snippet.\n"
                            f"Page title: {title}\n"
                            f"Page URL: {url}\n"
                            f"MiniDOM: {json.dumps(mini_dom, ensure_ascii=False)}\n"
                            f"Instruction: {step}\n"
                            "Write ONLY the await page code lines, assign output to `result`, then return result."
                        )
                        snippet = self.ask(prompt_snip).strip()

                        # strip markdown fences
                        if snippet.startswith("```"):
                            snippet = "\n".join(snippet.splitlines()[1:-1])

                        # break snippet into statements
                        stmt_lines = []
                        for part in re.split(r';|\n', snippet):
                            part = part.strip()
                            if not part:
                                continue
                            # handle single-line list “[ … ]”
                            if part.startswith('[') and part.endswith(']'):
                                inner = part[1:-1]
                                for sub in inner.split(','):
                                    sub = sub.strip()
                                    if sub:
                                        stmt_lines.append(sub)
                            else:
                                stmt_lines.append(part)

                        # ensure a return
                        if not any(ln.startswith("return") for ln in stmt_lines):
                            stmt_lines.append("return result")

                        # build the async fn
                        fn_name = f"_step_{idx+1}_a{attempt}"
                        src_lines = [f"async def {fn_name}(page):"]
                        for ln in stmt_lines:
                            src_lines.append("    " + ln)
                        src = "\n".join(src_lines)

                        local = {}
                        try:
                            exec(src, globals(), local)
                            fn = local[fn_name]
                        except Exception as e:
                            print(f"Compile error: {e}")
                            continue

                        # run it
                        try:
                            res = await fn(page)
                            assert res is not None, "returned None"
                            print(f"→ Success: {res!r}")
                            success = True
                            break
                        except AssertionError as ae:
                            print(f"Assertion: {ae}")
                        except Exception as e:
                            print(f"Runtime error: {e}")

                    step_results.append(success)
                    if not success:
                        print(f"Step {idx+1} failed after 2 attempts.")

                await browser.close()

        # 3) Execute runner
        try:
            asyncio.run(runner())
        except Exception as e:
            print("Error in /play:", e)

        # 4) Summary
        print("\n--- /play summary ---")
        for i, ok in enumerate(step_results,1):
            print(f"Step {i}: {'Success' if ok else 'Failure'}")

    # ---------------------------------------------------
    # /mcp – invoke any MCP operation
    def do_mcp(self, tokens):
        """
        /mcp OP [<json-payload>]
        Example: /mcp LIST_FILES
                 /mcp READ_FILE {"path":"./foo.py"}
        """
        if not tokens:
            print("Usage: /mcp OP [JSON]")
            return
        op = tokens[0].upper()
        raw = " ".join(tokens[1:]).strip()
        payload = {}
        if raw:
            try:
                payload = json.loads(raw)
            except Exception as e:
                print("Invalid JSON payload:", e)
                return
        try:
            result = self.call_mcp(op, payload)
            pprint(result)
        except Exception as e:
            print("MCP error:", e)

    # ---------------------------------------------------
    # /import (local)
    def do_import(self, tokens):
        if not tokens:
            print("Usage: /import <glob>")
            return
        pat = tokens[0]
        files = glob.glob(pat, recursive=True)
        cnt = 0
        for fn in files:
            try:
                txt = open(fn, encoding="utf-8", errors="ignore").read()
                self.knowledge += f"\n\n--- {fn} ---\n{txt}"
                cnt += 1
            except:
                pass
        print(f"Imported {cnt} files.")

    # ---------------------------------------------------
    # /export chat+knowledge snapshot
    def do_export(self, tokens):
        if not tokens:
            print("Usage: /export <filename>")
            return
        fn = tokens[0]
        try:
            with open(fn, 'w', encoding="utf-8") as f:
                f.write("=== Chat History ===\n")
                f.write(self.context+"\n")
                f.write("=== Knowledge ===\n")
                f.write(self.knowledge+"\n")
            print(f"Exported to {fn}")
        except Exception as e:
            print("Export error:", e)

    # ---------------------------------------------------
    # /clear
    def clear(self, _):
        self.context = ""
        self.knowledge = ""
        print("Cleared chat history and knowledge.")

    # ---------------------------------------------------
    # /stash <name>
    def do_stash(self, tokens):
        if not tokens:
            print("Usage: /stash <name>")
            return
        name = tokens[0]
        self.stash[name] = (self.context, self.knowledge)
        print(f"Stashed under '{name}'.")

    # ---------------------------------------------------
    # /pop <name>
    def do_pop(self, tokens):
        if not tokens:
            print("Usage: /pop <name>")
            return
        name = tokens[0]
        if name not in self.stash:
            print(f"No stash named '{name}'.")
            return
        self.context, self.knowledge = self.stash[name]
        print(f"Popped '{name}' into current session.")

    # ---------------------------------------------------
    # /list (stashes)
    def do_list(self, _):
        if not self.stash:
            print("No stashes.")
            return
        print("Stashes:")
        for name in self.stash:
            print("  " + name)

    # ---------------------------------------------------
    # /key <provider> <api_key>
    def set_key(self, tokens):
        if len(tokens) < 2:
            print("Usage: /key <provider> <api_key>")
            return
        prov, key = tokens[0], tokens[1]
        if prov not in self.provider_map:
            print(f"Unknown provider '{prov}'.")
            return
        self.provider_map[prov]["apiKey"] = key
        print(f"API key for '{prov}' set.")

    # ---------------------------------------------------
    # /getkey <provider>
    def get_key(self, tokens):
        if not tokens:
            print("Usage: /getkey <provider>")
            return
        prov = tokens[0]
        if prov not in self.provider_map:
            print(f"Unknown provider '{prov}'.")
            return
        print(f"{prov} API key: {self.provider_map[prov].get('apiKey','<none>')}")

    # ---------------------------------------------------
    # /stream
    def do_stream(self, _):
        self.stream = True
        print("Switched to streaming mode.")

    # ---------------------------------------------------
    # /rest
    def do_rest(self, _):
        self.stream = False
        print("Switched to REST mode (no streaming).")

    # ---------------------------------------------------
    # parameter setter for numeric params
    def set_param(self, key, tokens):
        if not tokens:
            print(f"Usage: /{key} <value>")
            return
        try:
            val = float(tokens[0]) if "." in tokens[0] else int(tokens[0])
            setattr(self, key, val)
            print(f"{key} set to {val}")
        except Exception as e:
            print(f"Invalid value for {key}:", e)

    # ---------------------------------------------------
    # /help
    def show_help(self, _):
        commands = {
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
        }
        print("\nAvailable /commands:\n")
        for cmd, desc in commands.items():
            print(f"  /{cmd:<20} — {desc}")
        print()

    # ---------------------------------------------------
    # parse and dispatch
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
                    "help":     self.show_help,
                    "models":   self.do_models,
                    "model":    self.set_model,
                    "key":      self.set_key,
                    "getkey":   self.get_key,
                    "import":   self.do_import,
                    "export":   self.do_export,
                    "clear":    self.clear,
                    "stash":    self.do_stash,
                    "pop":      self.do_pop,
                    "list":     self.do_list,
                    "temperature":     lambda a: self.set_param("temperature",a),
                    "top_p":           lambda a: self.set_param("top_p",a),
                    "max_tokens":      lambda a: self.set_param("max_tokens",a),
                    "frequency_penalty": lambda a: self.set_param("frequency_penalty",a),
                    "presence_penalty":  lambda a: self.set_param("presence_penalty",a),
                    "stream":    self.do_stream,
                    "rest":      self.do_rest,
                    "folders":   self.do_folders,
                    "include":   self.do_include,
                    "curl":      self.do_curl,
                    "play":      self.do_play,
                    "mcp":       self.do_mcp,
                }.get(cmd)
                if fn:
                    fn(args)
                else:
                    print("unknown /cmd:", cmd)
                continue
            # free‐form chat
            self.context += f"\nUser: {prompt}"
            reply = self.ask(prompt)
            if reply:
                self.context += f"\nAI: {reply}"

# ----------------------------------------
# Main: CLI + MCP server
# ----------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog="robodog",
        description="Combined MCP file‐server + Robodog CLI")
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
    args = parser.parse_args()

    # configure logging
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter('[%(asctime)s] %(levelname)s:%(message)s')
    ch = logging.StreamHandler(sys.stdout); ch.setFormatter(fmt); root.addHandler(ch)
    fh = logging.FileHandler(args.log_file); fh.setFormatter(fmt); root.addHandler(fh)
    logging.info("Starting robodog")

    # prepare MCP globals
    TOKEN = args.token
    ROOTS.clear()
    for p in args.folders:
        ap = os.path.abspath(p)
        if not os.path.isdir(ap):
            logging.error(f"Not a directory: {p}")
            sys.exit(1)
        ROOTS.append(ap)

    # launch MCP server
    server = ThreadedTCPServer((args.host, args.port), MCPHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logging.info(f"MCP file server on {args.host}:{args.port}, roots={ROOTS}")

    # start CLI
    cli = RoboDogCLI(args.config)
    cli.mcp['baseUrl'] = f"http://{args.host}:{args.port}"
    cli.mcp['apiKey']  = args.token
    if args.model:
        cli.set_model([args.model])

    try:
        cli.interact()
    finally:
        logging.info("Shutting down MCP server")
        server.shutdown()
        server.server_close()
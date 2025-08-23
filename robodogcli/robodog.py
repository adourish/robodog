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
import threading
import logging
import socketserver
import fnmatch
import hashlib
import asyncio
from pathlib import Path
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

# ----------------------------------------
# Security helper for MCP
# ----------------------------------------
def is_within_roots(path: str) -> bool:
    ap = os.path.abspath(path)
    ap = os.path.realpath(ap)
    for r in ROOTS:
        rr = os.path.realpath(r)
        if os.path.commonpath([rr, ap]) == rr:
            return True
    return False

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
            return {"commands": ["LIST_FILES","GET_ALL_CONTENTS","READ_FILE <json:{\"path\":\"...\"}>", "..."], "status":"ok"}

        if op == 'LIST_FILES':
            files = []
            for root in ROOTS:
                for dirpath, _, filenames in os.walk(root):
                    for fn in filenames:
                        files.append(os.path.join(dirpath, fn))
            return {"files": files, "status": "ok"}

        if op == 'GET_ALL_CONTENTS':
            contents = []
            for root in ROOTS:
                for dirpath, _, filenames in os.walk(root):
                    for fn in filenames:
                        fp = os.path.join(dirpath, fn)
                        try:
                            data = open(fp, 'r', encoding='utf-8').read()
                        except Exception as e:
                            data = f"<error: {e}>"
                        contents.append({"path": fp, "content": data})
            return {"contents": contents, "status": "ok"}

        if op == 'READ_FILE':
            path = payload.get("path")
            if not path: raise ValueError("Missing 'path'")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            if not os.path.isfile(path): raise FileNotFoundError(path)
            data = open(path, 'r', encoding='utf-8').read()
            return {"path": path, "content": data, "status": "ok"}

        if op == 'UPDATE_FILE':
            path = payload.get("path"); content = payload.get("content")
            if path is None or content is None: raise ValueError("Need path and content")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            parent = os.path.dirname(path)
            if not os.path.isdir(parent): raise FileNotFoundError(parent)
            open(path, 'w', encoding='utf-8').write(content)
            return {"path": path, "status": "ok"}

        if op == 'CREATE_FILE':
            path = payload.get("path"); content = payload.get("content","")
            if not path: raise ValueError("Missing path")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            parent = os.path.dirname(path)
            if not os.path.isdir(parent): raise FileNotFoundError(parent)
            open(path, 'w', encoding='utf-8').write(content)
            return {"path": path, "status": "ok"}

        if op == 'DELETE_FILE':
            path = payload.get("path")
            if not path: raise ValueError("Missing path")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            if not os.path.isfile(path): raise FileNotFoundError(path)
            os.remove(path)
            return {"path": path, "status": "ok"}

        if op == 'APPEND_FILE':
            path = payload.get("path"); content = payload.get("content","")
            if not path: raise ValueError("Missing path")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            open(path, 'a', encoding='utf-8').write(content)
            return {"path": path, "status": "ok"}

        if op == 'CREATE_DIR':
            path = payload.get("path"); mode = payload.get("mode", 0o755)
            if not path: raise ValueError("Missing path")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            os.makedirs(path, mode, exist_ok=True)
            return {"path": path, "status": "ok"}

        if op == 'DELETE_DIR':
            path = payload.get("path"); recursive = payload.get("recursive", False)
            if not path: raise ValueError("Missing path")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)
            return {"path": path, "status": "ok"}

        if op in ('RENAME','MOVE'):
            src = payload.get("src"); dst = payload.get("dst")
            if not src or not dst: raise ValueError("Need src and dst")
            if not is_within_roots(src) or not is_within_roots(dst): raise PermissionError("Not allowed")
            parent = os.path.dirname(dst)
            if not os.path.isdir(parent): raise FileNotFoundError(parent)
            os.rename(src, dst)
            return {"src": src, "dst": dst, "status":"ok"}

        if op == 'COPY_FILE':
            src = payload.get("src"); dst = payload.get("dst")
            if not src or not dst: raise ValueError("Need src and dst")
            if not is_within_roots(src) or not is_within_roots(dst): raise PermissionError("Not allowed")
            parent = os.path.dirname(dst)
            if not os.path.isdir(parent): raise FileNotFoundError(parent)
            shutil.copy2(src, dst)
            return {"src": src, "dst": dst, "status":"ok"}

        if op == 'SEARCH':
            raw = payload.get("pattern","*")
            patterns = raw.split('|') if isinstance(raw,str) else [raw]
            recursive = payload.get("recursive", True)
            root = payload.get("root","")
            matches = []
            roots = ROOTS if not root else [root]
            for r in roots:
                if not os.path.isdir(r): continue
                if recursive:
                    for dp,_,fns in os.walk(r):
                        for fn in fns:
                            fp = os.path.join(dp,fn)
                            for pat in patterns:
                                if fnmatch.fnmatch(fn,pat) or fnmatch.fnmatch(fp,pat):
                                    matches.append(fp); break
                else:
                    for fn in os.listdir(r):
                        fp = os.path.join(r,fn)
                        if not os.path.isfile(fp): continue
                        for pat in patterns:
                            if fnmatch.fnmatch(fn,pat) or fnmatch.fnmatch(fp,pat):
                                matches.append(fp); break
            return {"matches": matches, "status":"ok"}

        if op == 'CHECKSUM':
            path = payload.get("path")
            if not path: raise ValueError("Missing 'path'")
            if not is_within_roots(path): raise PermissionError("Not allowed")
            h = hashlib.sha256()
            with open(path,'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return {"path": path, "checksum": h.hexdigest(), "status":"ok"}

        if op in ('QUIT','EXIT'):
            return {"message":"Goodbye!","status":"ok"}

        raise ValueError(f"Unknown command '{op}'")

    def send_json(self, obj: dict):
        raw = json.dumps(obj, ensure_ascii=False) + "\n"
        self.wfile.write(raw.encode('utf-8'))

    def handle(self):
        peer = self.client_address
        raw_first = self.rfile.readline()
        if not raw_first:
            return
        first = raw_first.decode('utf-8', errors='ignore').strip()
        is_http = first.upper().startswith(("GET ","POST ","OPTIONS ")) and "HTTP/" in first

        if is_http:
            logging.debug(f"[{peer}] HTTP request: {first}")
            # parse request line
            try:
                method, uri, version = first.split(None,2)
            except:
                self.send_http_error(400,"Bad Request"); return
            method = method.upper()

            # read headers
            headers = {}
            while True:
                line = self.rfile.readline().decode('utf-8',errors='ignore')
                if not line or line in ('\r\n','\n'): break
                name,val = line.split(":",1)
                headers[name.lower().strip()] = val.strip()

            # CORS preflight
            if method=='OPTIONS':
                resp = ["HTTP/1.1 204 No Content",
                        "Access-Control-Allow-Origin: *",
                        "Access-Control-Allow-Methods: POST, OPTIONS",
                        "Access-Control-Allow-Headers: Content-Type, Authorization",
                        "Access-Control-Max-Age: 86400",
                        "Connection: close","",""]
                self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
                return

            if method!='POST':
                resp = ["HTTP/1.1 405 Method Not Allowed",
                        "Access-Control-Allow-Origin: *",
                        "Allow: POST, OPTIONS",
                        "Content-Type: text/plain; charset=utf-8",
                        "Content-Length: 23",
                        "Connection: close","","Only POST is supported\n"]
                self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
                return

            # auth
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

            # read body
            length = int(headers.get('content-length','0'))
            raw_body = self.rfile.read(length).decode('utf-8', errors='ignore').strip()
            logging.debug(f"[{peer}] HTTP POST body: {raw_body!r}")

            try:
                parts = raw_body.split(' ',1)
                op = parts[0].upper()
                arg = parts[1] if len(parts)>1 else None
                result = self.execute_command(op,arg)
            except Exception as e:
                logging.error(f"[{peer}] Error: {e}")
                result = {"status":"error","error": str(e)}

            json_body = json.dumps(result, ensure_ascii=False)
            resp = ["HTTP/1.1 200 OK",
                    "Access-Control-Allow-Origin: *",
                    "Access-Control-Allow-Headers: Content-Type, Authorization",
                    "Content-Type: application/json; charset=utf-8",
                    f"Content-Length: {len(json_body.encode('utf-8'))}",
                    "Connection: close","", json_body]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return

        # raw‐TCP not supported
        logging.info(f"[{peer}] Closing raw connection")
        return

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

# ----------------------------------------
# CLI portion
# ----------------------------------------
class RoboDogCLI:
    def __init__(self, config_path: str, api_key: str = None):
        if not os.path.exists(config_path):
            with open(config_path, "w") as f:
                f.write(DEFAULT_CONFIG)
        with open(config_path) as f:
            cfg = yaml.safe_load(f)["configs"]

        self.provider_map = {p["provider"]: p for p in cfg["providers"]}
        self.cfg_models   = cfg["models"]
        self.mcp          = cfg.get("mcpServer", {})

        self.context      = ""
        self.knowledge    = ""
        self.stash        = {}

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
        r = requests.post(url, headers=headers, data=body, timeout=timeout)
        r.raise_for_status()
        lines = r.text.strip().split("\n")
        return json.loads(lines[-1])

    # ---------------------------------------------------
    # /model command
    def set_model(self, tokens):
        if not tokens:
            models = [m["model"] for m in self.cfg_models]
            print("Usage: /model <model_name>")
            print("Available models:", ", ".join(models))
            return

        new_model = tokens[0]
        models = [m["model"] for m in self.cfg_models]
        if new_model not in models:
            print(f"Unknown model: '{new_model}'")
            print("Available models:", ", ".join(models))
            return

        self.cur_model = new_model
        prov = self.model_provider(self.cur_model)
        self.api_key = (
            os.getenv("OPENAI_API_KEY")
            or self.provider_map[prov]["apiKey"]
        )
        if not self.api_key:
            print(f"No API key for provider '{prov}'")
            return
        self.client = OpenAI(api_key=self.api_key)
        print(f"Model set to: {self.cur_model}")
        logging.info(f"Model switched to {self.cur_model}")

    # ---------------------------------------------------
    # ask via OpenAI
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
                delta = getattr(chunk.choices[0].delta,"content",None)
                if delta:
                    print(delta,end="",flush=True)
                    answer += delta
            print()
        else:
            answer = resp.choices[0].message.content.strip()
        return answer

    # ---------------------------------------------------
    # ask via MCP or OpenAI
    def ask2(self, prompt: str) -> str:
        # Bypass MCP and always use direct OpenAI call to avoid unsupported 'COMPLETE' op
        return self.ask(prompt)

    # ---------------------------------------------------
    # /include command (unchanged)...
    def parse_include(self, text: str) -> dict:
        parts = text.strip().split()
        cmd = {"type":None,"file":None,"dir":None,"pattern":"*","recursive":False}
        if not parts: return cmd
        p0 = parts[0]
        if p0=="all":
            cmd["type"]="all"
        elif p0.startswith("file="):
            spec = p0[5:]
            if re.search(r"[*?\[]",spec):
                cmd["type"]="pattern"; cmd["pattern"],cmd["dir"],cmd["recursive"]=spec,"",True
            else:
                cmd["type"],cmd["file"]="file",spec
        elif p0.startswith("dir="):
            spec = p0[4:]
            cmd["type"],cmd["dir"]="dir",spec
            for p in parts[1:]:
                if p.startswith("pattern="):
                    cmd["pattern"]=p.split("=",1)[1]
                if p=="recursive":
                    cmd["recursive"]=True
            if re.search(r"[*?\[]",spec):
                cmd["type"],cmd["pattern"],cmd["dir"],cmd["recursive"]="pattern",spec,"",True
        elif p0.startswith("pattern="):
            cmd["type"]="pattern"; cmd["pattern"]=p0.split("=",1)[1]; cmd["recursive"]=True
        return cmd

    def do_include(self, tokens):
        # ... unchanged ...
        if not tokens:
            print("Usage: /include [all|file=<file>|dir=<dir> [pattern=<glob>] [recursive]] [prompt]")
            return

        spec_tokens = []
        prompt_tokens = []
        for i, t in enumerate(tokens):
            if i == 0 or t == "recursive" or t.startswith(("file=", "dir=", "pattern=")):
                spec_tokens.append(t)
            else:
                prompt_tokens = tokens[i:]
                break

        spec_text = " ".join(spec_tokens)
        prompt_text = " ".join(prompt_tokens).strip() if prompt_tokens else None

        inc = self.parse_include(spec_text)
        included = []

        try:
            if inc["type"] == "all":
                res = self.call_mcp("GET_ALL_CONTENTS", {})
                included = res.get("contents", [])
            elif inc["type"] == "file":
                s = self.call_mcp("SEARCH", {
                    "root": inc["file"],
                    "pattern": inc["file"],
                    "recursive": True
                })
                if not s.get("matches"):
                    raise RuntimeError(f"No file {inc['file']}")
                f = self.call_mcp("READ_FILE", {"path": s["matches"][0]})
                included = [{"path": f["path"], "content": f["content"]}]
            elif inc["type"] in ("pattern", "dir"):
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

            text = ""
            for i in included:
                print(f"Include: {i['path']}")
                text += f"\n\n--- {i['path']} ---\n{i['content']}"
            self.knowledge += text
            print(f"Included {len(included)} files into knowledge.")

            if prompt_text:
                print(f"Prompt → {prompt_text}")
                self.context += f"\nUser: {prompt_text}"
                answer = self.ask(prompt_text)
                self.context += "\nAI: " + answer
            else:
                print("No prompt given after include; nothing asked.")

        except Exception as e:
            print("include error:", e)
            logging.error(f"Include error: {e}")

    # ---------------------------------------------------
    # /curl command (unchanged)...
    def do_curl(self, tokens):
        # ... unchanged ...
        headless = True
        args = []
        for t in tokens:
            if t == "--no-headless":
                headless = False
            else:
                args.append(t)

        if not args:
            print("Usage: /curl [--no-headless] <url1> [url2] [js_script]")
            return

        url1 = args[0]
        if not url1.startswith(("http://", "https://")):
            url1 = "http://" + url1

        url2 = None
        script = None

        if len(args) >= 2 and args[1].startswith(("http://", "https://")):
            url2 = args[1]
            if not url2.startswith(("http://", "https://")):
                url2 = "http://" + url2
            if len(args) >= 3:
                script = " ".join(args[2:])
        else:
            if len(args) >= 2:
                script = " ".join(args[1:])

        if async_playwright is None:
            print("Error: Playwright is not installed. Install with `pip install playwright` and run `playwright install`.")
            return

        async def runner():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=headless)
                page = await browser.new_page()
                print(f"Navigating to {url1} ...")
                await page.goto(url1)
                if url2:
                    print(f"Navigating to {url2} ...")
                    await page.goto(url2)

                if script:
                    print("Executing custom script…")
                    try:
                        result = await page.evaluate(script)
                    except Exception as e:
                        print("Script execution error:", e)
                        result = None
                else:
                    print("Extracting page text content…")
                    result = await page.evaluate("() => document.body.innerText")

                print("----- /curl result -----")
                print(result)
                await browser.close()

        try:
            asyncio.run(runner())
        except Exception as e:
            print("Error in /curl:", e)

    # ---------------------------------------------------
    # /play command: natural-language testing via Playwright + LLM,
    # now with page-title logging and retry-on-failure logic.
    def do_play(self, tokens):
        if async_playwright is None:
            print("Error: Playwright is not installed. Install with `pip install playwright` and run `playwright install`.")
            return
        if not tokens:
            print("Usage: /play <test instructions>")
            return

        instructions = " ".join(tokens)
        print("Instructions:", instructions)

        # 1) Parse into numbered steps
        parse_prompt = (
            "Parse the following instructions into a numbered list of discrete steps:\n\n"
            f"{instructions}\n\n"
            "Respond ONLY as a numbered list (e.g. '1. ...')."
        )
        parsed = self.ask2(parse_prompt)
        print("----- Parsed steps -----")
        print(parsed)

        # extract into Python list
        steps = []
        for line in parsed.splitlines():
            m = re.match(r"\s*\d+\.\s*(.+)", line)
            if m:
                steps.append(m.group(1).strip())
        if not steps:
            print("Error: Couldn't parse any steps. Aborting.")
            return

        # helper to strip markdown fences
        def strip_code_blocks(snip: str) -> str:
            lines = snip.splitlines()
            if lines and lines[0].strip().startswith("```"):
                end = None
                for i, ln in enumerate(lines[1:], start=1):
                    if ln.strip().startswith("```"):
                        end = i
                        break
                if end is not None:
                    return "\n".join(lines[1:end])
            return snip

        # 2) Run them in one browser/page session, generating snippet per step
        async def runner():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch()
                page = await browser.new_page()

                for idx, step in enumerate(steps):
                    # We'll allow up to 2 attempts per step
                    snippet = None
                    for attempt in range(2):
                        # Always report current page
                        try:
                            title = await page.title()
                        except Exception:
                            title = "<no title>"
                        url = page.url
                        print(f"\n--- Step {idx+1}, attempt {attempt+1} on page: {title} ({url}) ---")

                        # Inspect current HTML
                        html = await page.content()

                        # Ask LLM for the exact snippet given HTML + instruction
                        if attempt == 0:
                            prompt_snip = (
                                "You are given the HTML of the current page and an instruction. "
                                "Write a snippet of Python Playwright code using only 'await page...' lines to perform the instruction. "
                                "Assign any extracted data to a variable named 'result' and end with 'return result'.\n\n"
                                f"HTML:\n{html[:2000]}...\n\nInstruction:\n{step}"
                            )
                        else:
                            prompt_snip = (
                                f"The previous snippet for instruction '{step}' failed on attempt 1. "
                                "Given the HTML of the current page, write a corrected Python Playwright snippet using only 'await page...' lines. "
                                "Assign any extracted data to a variable named 'result' and end with 'return result'.\n\n"
                                f"HTML:\n{html[:2000]}...\n\nInstruction:\n{step}"
                            )

                        snippet = self.ask2(prompt_snip)
                        print(f"----- Snippet for step {idx+1}, attempt {attempt+1} -----")
                        print(snippet)
                        snippet = strip_code_blocks(snippet).strip()

                        # Build and compile the step function
                        fn_name = f"step_fn_{idx+1}_a{attempt+1}"
                        src = f"async def {fn_name}(page):\n"
                        for ln in snippet.splitlines():
                            src += f"    {ln.rstrip()}\n"
                        local = {}
                        try:
                            exec(src, globals(), local)
                            fn = local[fn_name]
                        except Exception as e:
                            print(f"Error compiling snippet for step {idx+1}, attempt {attempt+1}:", e)
                            logging.error(f"Compilation error in /play step {idx+1}, attempt {attempt+1}: {e}")
                            fn = None

                        # Execute
                        res = None
                        if fn:
                            try:
                                res = await fn(page)
                                print(f"Result of step {idx+1}:", res)
                                break  # success, exit attempt loop
                            except Exception as e:
                                print(f"Error executing step {idx+1}, attempt {attempt+1}:", e)
                                logging.error(f"Execution error in /play step {idx+1}, attempt {attempt+1}: {e}")

                        # If we're here and it was the second attempt, give up
                        if attempt == 1:
                            print(f"Step {idx+1} failed after retry. Skipping.")
                        else:
                            print("Retrying with alternate snippet…")

                    # If this wasn't the last step, ask LLM if we should continue
                    if idx < len(steps)-1:
                        next_prompt = (
                            f"I executed step '{step}' and got result: {res!r}.\n"
                            f"The original instructions are: {instructions}\n"
                            "What should be the next step? If all done, respond 'done'."
                        )
                        suggestion = self.ask2(next_prompt).strip()
                        print("LLM next-step suggestion:", suggestion)
                        if suggestion.lower() == 'done':
                            print("LLM indicates completion. Stopping early.")
                            break

                await browser.close()

        try:
            asyncio.run(runner())
        except Exception as e:
            print("Error in /play:", e)
            logging.error(f"Unexpected error in /play: {e}")
    # ---------------------------------------------------
    # /play command: natural-language testing via Playwright + LLM, but now
    # interleaving HTML inspection so each snippet adapts to real structure.
    def do_play2(self, tokens):
        if async_playwright is None:
            print("Error: Playwright is not installed. Install with `pip install playwright` and run `playwright install`.")
            return
        if not tokens:
            print("Usage: /play <test instructions>")
            return

        instructions = " ".join(tokens)
        print("Instructions:", instructions)

        # 1) Parse into numbered steps
        parse_prompt = (
            "Parse the following instructions into a numbered list of discrete steps:\n\n"
            f"{instructions}\n\n"
            "Respond ONLY as a numbered list (e.g. '1. ...')."
        )
        parsed = self.ask2(parse_prompt)
        print("----- Parsed steps -----")
        print(parsed)

        # extract into Python list
        steps = []
        for line in parsed.splitlines():
            m = re.match(r"\s*\d+\.\s*(.+)", line)
            if m:
                steps.append(m.group(1).strip())
        if not steps:
            print("Error: Couldn't parse any steps. Aborting.")
            return

        # helper to strip markdown fences
        def strip_code_blocks(snip: str) -> str:
            lines = snip.splitlines()
            if lines and lines[0].strip().startswith("```"):
                end = None
                for i, ln in enumerate(lines[1:], start=1):
                    if ln.strip().startswith("```"):
                        end = i
                        break
                if end is not None:
                    return "\n".join(lines[1:end])
            return snip

        # 2) Run them in one browser/page session, generating snippet per step
        async def runner():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch()
                page = await browser.new_page()
                for idx, step in enumerate(steps):
                    print(f"\n--- Executing step {idx+1}: {step} ---")
                    # Inspect current HTML
                    html = await page.content()
                    # Ask LLM for the exact snippet given HTML + instruction
                    snippet_prompt = (
                        "You are given the HTML of the current page and an instruction. "
                        "Write a snippet of Python Playwright code using only 'await page...' lines to perform the instruction. "
                        "Assign any extracted data to a variable named 'result' and end with 'return result'.\n\n"
                        f"HTML:\n{html[:2000]}...\n\nInstruction:\n{step}"
                    )
                    snippet = self.ask2(snippet_prompt)
                    print(f"----- Snippet for step {idx+1} -----")
                    print(snippet)
                    snippet = strip_code_blocks(snippet).strip()

                    # Build and compile the step function
                    fn_name = f"step_fn_{idx+1}"
                    src = f"async def {fn_name}(page):\n"
                    for ln in snippet.splitlines():
                        src += f"    {ln.rstrip()}\n"
                    local = {}
                    try:
                        exec(src, globals(), local)
                        fn = local[fn_name]
                    except Exception as e:
                        print(f"Error compiling snippet for step {idx+1}:", e)
                        logging.error(f"Compilation error in /play step {idx+1}: {e}")
                        async def _dummy(page, idx=idx+1):
                            print(f"(Dummy) Skipping step {idx} due to compile error.")
                            return None
                        fn = _dummy

                    # Execute
                    try:
                        res = await fn(page)
                        print(f"Result of step {idx+1}:", res)
                    except Exception as e:
                        print(f"Error executing step {idx+1}:", e)
                        logging.error(f"Execution error in /play step {idx+1}: {e}")
                        res = None

                    # Ask LLM for next-step confirmation or early stop
                    if idx < len(steps)-1:
                        next_prompt = (
                            f"I executed step '{step}' and got result: {res!r}.\n"
                            f"The original instructions are: {instructions}\n"
                            "What should be the next step? If all done, respond 'done'."
                        )
                        suggestion = self.ask2(next_prompt).strip()
                        print("LLM next-step suggestion:", suggestion)
                        if suggestion.lower() == 'done':
                            print("LLM indicates completion. Stopping early.")
                            break

                await browser.close()

        try:
            asyncio.run(runner())
        except Exception as e:
            print("Error in /play:", e)
            logging.error(f"Unexpected error in /play: {e}")

    # ---------------------------------------------------
    # stub other commands...
    def set_key(self, tokens): pass
    def get_key(self, _): pass
    def clear(self, _): pass
    def show_help(self, _): pass
    def set_param(self, key, tokens): pass
    def do_stream(self, _): pass
    def do_rest(self, _): pass
    def do_list(self, _): pass
    def do_stash(self, tokens): pass
    def do_pop(self, tokens): pass
    def do_export(self, tokens): pass

    def do_import(self, tokens):
        if not tokens:
            print("Usage: /import <file|dir|glob>"); return
        pat = tokens[0]
        files = glob.glob(pat, recursive=True)
        text = ""
        for fn in files:
            try:
                text += f"\n\n--- {fn} ---\n"
                text += open(fn, encoding="utf8", errors="ignore").read()
            except:
                pass
        self.knowledge += "\n"+text
        print(f"imported {len(files)} files")
        logging.debug(f"Imported {len(files)} files with pattern {pat}")

    # ---------------------------------------------------
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
                logging.info("CLI session ended by user")
                break
            if not prompt:
                continue

            logging.debug(f"User input: {prompt}")

            if prompt.startswith("/"):
                cmd,args = self.parse_command(prompt)
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
                    "temperature": lambda a: self.set_param("temperature",a),
                    "top_p":       lambda a: self.set_param("top_p",a),
                    "frequency_penalty": lambda a: self.set_param("frequency_penalty",a),
                    "presence_penalty":  lambda a: self.set_param("presence_penalty",a),
                    "stream": self.do_stream,
                    "rest":   self.do_rest,
                    "include": self.do_include,
                    "curl":   self.do_curl,
                    "play":   self.do_play,
                }.get(cmd)
                if fn:
                    fn(args)
                else:
                    print("unknown /cmd:", cmd)
                continue

            self.context += f"\nUser: {prompt}"
            reply = self.ask(prompt)
            if reply:
                logging.debug(f"AI response: {reply.strip()}")
                self.context += "\nAI: "+reply

# ----------------------------------------
# Main: parse args, set up logging, launch MCP & CLI
# ----------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog="robodog",
        description="Combined MCP file‐server + Robodog CLI with file logging")
    parser.add_argument('--config', default='config.yaml',
                        help='path to robodog YAML config')
    parser.add_argument('--folders', nargs='+', required=True,
                        help='one or more root folders to serve (recursive)')
    parser.add_argument('--host', default='127.0.0.1',
                        help='host for MCP server (default 127.0.0.1)')
    parser.add_argument('--port', type=int, default=2500,
                        help='port for MCP server (default 2500)')
    parser.add_argument('--token', required=True,
                        help='authentication token clients must present')
    parser.add_argument('--model', '-m',
                        help='startup model name (overrides default in config)')
    parser.add_argument('--log-file', default='robodog.log',
                        help='path to log file')
    args = parser.parse_args()

    # configure logging: console + file
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    fmt = logging.Formatter('[%(asctime)s] %(levelname)s:%(message)s')

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root_logger.addHandler(ch)

    fh = logging.FileHandler(args.log_file)
    fh.setFormatter(fmt)
    root_logger.addHandler(fh)

    logging.info("Starting robodog")

    # prepare MCP globals
    TOKEN = args.token
    ROOTS = []
    for p in args.folders:
        absp = os.path.abspath(p)
        if not os.path.isdir(absp):
            logging.error(f"Error: not a directory: {p}")
            sys.exit(1)
        ROOTS.append(absp)

    # launch MCP server in background
    server = ThreadedTCPServer((args.host, args.port), MCPHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logging.info(f"Robodog MCP file server serving {ROOTS} on {args.host}:{args.port}")

    # start CLI
    cli = RoboDogCLI(args.config)
    cli.mcp['baseUrl'] = f"http://{args.host}:{args.port}"
    cli.mcp['apiKey']  = args.token

    # if user specified startup model, apply it now
    if args.model:
        cli.set_model([args.model])

    try:
        cli.interact()
    finally:
        logging.info("Shutting down MCP server")
        server.shutdown()
        server.server_close()
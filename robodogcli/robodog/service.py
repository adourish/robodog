# file: robodog/cli/service.py
import os
import re
import json
import shutil
import fnmatch
import hashlib
import threading
import concurrent.futures
import asyncio
from pathlib import Path
import requests
import tiktoken
import yaml
from openai import OpenAI
from playwright.async_api import async_playwright
import logging
logger = logging.getLogger('robodog.service')

class RobodogService:
    def __init__(self, config_path: str, api_key: str = None):
        self._load_config(config_path)
        self.context   = ""
        self.knowledge = ""
        self.stashes   = {}
        self._init_llm(api_key)

    def _load_config(self, config_path):
        data = yaml.safe_load(open(config_path, 'r', encoding='utf-8'))
        cfg = data.get("configs", {})
        self.providers = {p["provider"]: p for p in cfg.get("providers",[])}
        self.models    = cfg.get("models",[])
        self.mcp_cfg   = cfg.get("mcpServer",{})
        self.cur_model = self.models[0]["model"]
        self.stream    = self.models[0].get("stream",True)
        self.temperature     = 1.0
        self.top_p           = 1.0
        self.max_tokens      = 1024
        self.frequency_penalty = 0.0
        self.presence_penalty  = 0.0

    def _init_llm(self, api_key):
        self.api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY")
            or self.providers[self.model_provider(self.cur_model)]["apiKey"]
        )
        if not self.api_key:
            raise RuntimeError("Missing API key")
        self.client = OpenAI(api_key=self.api_key)

    def model_provider(self, model_name):
        for m in self.models:
            if m["model"] == model_name:
                return m["provider"]
        return None

    # ————————————————————————————————————————————————————————————
    # CORE LLM / CHAT
    def ask(self, prompt: str) -> str:
        logger.debug(f"ask {prompt!r}")
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

    # ————————————————————————————————————————————————————————————
    # MODEL / KEY MANAGEMENT
    def list_models(self):
        return [m["model"] for m in self.models]

    def set_model(self, model_name: str):
        if model_name not in self.list_models():
            raise ValueError(f"Unknown model: {model_name}")
        self.cur_model = model_name
        self._init_llm(None)

    def set_key(self, provider: str, key: str):
        if provider not in self.providers:
            raise KeyError(f"No such provider {provider}")
        self.providers[provider]["apiKey"] = key

    def get_key(self, provider: str):
        return self.providers.get(provider,{}).get("apiKey")

    # ————————————————————————————————————————————————————————————
    # STASH / POP / LIST / CLEAR / IMPORT / EXPORT
    def stash(self, name: str):
        self.stashes[name] = (self.context, self.knowledge)

    def pop(self, name: str):
        if name not in self.stashes:
            raise KeyError(f"No stash {name}")
        self.context, self.knowledge = self.stashes[name]

    def list_stashes(self):
        return list(self.stashes.keys())

    def clear(self):
        self.context = ""
        self.knowledge = ""

    def import_files(self, glob_pattern: str) -> int:
        count = 0
        for fn in __import__('glob').glob(glob_pattern, recursive=True):
            try:
                txt = open(fn, 'r', encoding='utf-8', errors='ignore').read()
                self.knowledge += f"\n\n--- {fn} ---\n{txt}"
                count += 1
            except:
                pass
        return count

    def export_snapshot(self, filename: str):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=== Chat History ===\n"+self.context+"\n")
            f.write("=== Knowledge ===\n"+self.knowledge+"\n")

    # ————————————————————————————————————————————————————————————
    # NUMERIC PARAMS
    def set_param(self, key: str, value):
        if not hasattr(self, key):
            raise KeyError(f"No such param {key}")
        setattr(self, key, value)

    # ————————————————————————————————————————————————————————————
    # MCP CLIENT (used by CLI to reach server)
    def call_mcp(self, op: str, payload: dict, timeout: float = 30.0) -> dict:
        url = self.mcp_cfg["baseUrl"]
        headers = {
            "Content-Type": "text/plain",
            "Authorization": f"Bearer {self.mcp_cfg['apiKey']}"
        }
        body = f"{op} {json.dumps(payload)}\n"
        r = requests.post(url, headers=headers, data=body, timeout=timeout)
        r.raise_for_status()
        return json.loads(r.text.strip().splitlines()[-1])

    # ————————————————————————————————————————————————————————————
    # /INCLUDE IMPLEMENTATION
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
                cmd.update(type="pattern", pattern=spec, recursive=True)
            else:
                cmd.update(type="file", file=spec)
        elif p0.startswith("dir="):
            spec = p0[4:]
            cmd.update(type="dir", dir=spec)
            for p in parts[1:]:
                if p.startswith("pattern="):
                    cmd["pattern"] = p.split("=",1)[1]
                if p == "recursive":
                    cmd["recursive"] = True
            if re.search(r"[*?\[]", spec):
                cmd.update(type="pattern", pattern=spec, recursive=True)
        elif p0.startswith("pattern="):
            cmd.update(type="pattern", pattern=p0.split("=",1)[1], recursive=True)
        return cmd

    def include(self, spec_text: str, prompt: str = None):
        inc = self.parse_include(spec_text)
        # build search payloads
        searches = []
        if inc["type"] == "dir":
            searches.append({"root": inc["dir"], "pattern": inc["pattern"], "recursive": inc["recursive"]})
        else:
            pat = inc["pattern"] if inc["type"]=="pattern" else (inc["file"] or "*")
            searches.append({"pattern": pat, "recursive": True})

        # SEARCH via MCP
        matches = []
        for p in searches:
            res = self.call_mcp("SEARCH", p)
            matches.extend(res.get("matches", []))
        matches = [m for m in matches if "node_modules" not in Path(m).parts]
        if not matches:
            return None

        # READ_FILE in parallel
        included_txts = []
        def _read(path):
            blob = self.call_mcp("READ_FILE", {"path": path})
            return path, blob.get("content", "")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for path, txt in pool.map(_read, matches):
                # token count
                try:
                    enc = tiktoken.encoding_for_model(self.cur_model)
                except:
                    enc = tiktoken.get_encoding("gpt2")
                wc = len(txt.split())
                tc = len(enc.encode(txt))
                # fixed print statement
                print(f"Included: {path} ({wc} tokens)")
                included_txts.append(txt)
                combined = "\n".join(included_txts)
                self.knowledge += "\n" + combined + "\n"

        # if prompt, ask & update context
        if prompt:
            print(f"→ Prompt: {prompt}")
            self.context += f"\nUser: {prompt}"
            ans = self.ask(prompt)
            self.context += f"\nAI: {ans}"
            return ans
        return None
    
    # ----------------------------------------------------------------
    DEFAULT_EXCLUDE_DIRS = {"node_modules", "dist"}
    logger = logging.getLogger(__name__)

    def search_files(self,
                    patterns="*",
                    recursive=True,
                    roots=None,
                    exclude_dirs=None):
        """
        patterns: a string (e.g. '*.js|*.jsx') or a list of patterns
        recursive: whether to walk subdirectories
        roots:       list of root folders to search
        exclude_dirs: iterable of dir‐names to skip (default: node_modules, dist)
        """
        # Normalize inputs
        self.logger.debug("Raw patterns input: %r", patterns)
        if isinstance(patterns, str):
            patterns = patterns.split("|")
        else:
            patterns = list(patterns)
        self.logger.debug("Normalized patterns list: %r", patterns)

        exclude_dirs = set(exclude_dirs or self.DEFAULT_EXCLUDE_DIRS)
        self.logger.debug("Excluding directories: %r", exclude_dirs)

        matches = []

        for root in roots or []:
            self.logger.debug(">> Entering root: %r", root)
            if not os.path.isdir(root):
                self.logger.debug("   Skipping %r because it is not a directory", root)
                continue

            if recursive:
                for dirpath, dirnames, filenames in os.walk(root):
                    self.logger.debug("Walking into %r, subdirs=%r, files=%r",
                                dirpath, dirnames, filenames)

                    # prune excluded dirs in-place
                    before = list(dirnames)
                    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
                    removed = set(before) - set(dirnames)
                    if removed:
                        self.logger.debug("   Pruned dirs %r from %r", removed, dirpath)

                    for fn in filenames:
                        full_path = os.path.join(dirpath, fn)
                        self.logger.debug("   Considering file: %r", full_path)
                        matched = False
                        for pat in patterns:
                            if fnmatch.fnmatch(full_path, pat) or fnmatch.fnmatch(fn, pat):
                                self.logger.debug("      MATCH: %r matches pattern %r", full_path, pat)
                                matches.append(full_path)
                                matched = True
                                break
                            else:
                                self.logger.debug("      no match: %r !~ %r", full_path, pat)
                        if not matched:
                            self.logger.debug("   -> File %r did not match any pattern", full_path)

            else:
                self.logger.debug("Non-recursive mode in root: %r", root)
                for fn in os.listdir(root):
                    full = os.path.join(root, fn)
                    self.logger.debug("   Top-level entry: %r", full)
                    if not os.path.isfile(full):
                        self.logger.debug("      Skipped %r (not a file)", full)
                        continue
                    if fn in exclude_dirs:
                        self.logger.debug("      Skipped %r (in exclude_dirs)", fn)
                        continue

                    matched = False
                    for pat in patterns:
                        if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                            self.logger.debug("      MATCH: %r matches pattern %r", full, pat)
                            matches.append(full)
                            matched = True
                            break
                        else:
                            self.logger.debug("      no match: %r !~ %r", full, pat)
                    if not matched:
                        self.logger.debug("   -> File %r did not match any pattern", full)

        self.logger.debug("Search complete. Found %d matches: %r", len(matches), matches)
        return matches
    def search_files3(self,
                     patterns="*",
                     recursive=True,
                     roots=None,
                     exclude_dirs=None):
        """
        patterns: a string (e.g. '*.js|*.jsx') or a list of patterns
        recursive: whether to walk subdirectories
        roots:       list of root folders to search
        exclude_dirs: iterable of dir‐names to skip (default: node_modules, dist)
        """
        # normalize inputs
        if isinstance(patterns, str):
            patterns = patterns.split("|")
        else:
            patterns = list(patterns)

        exclude_dirs = set(exclude_dirs or self.DEFAULT_EXCLUDE_DIRS)
        matches = []

        for root in roots or []:

            if not os.path.isdir(root):
                continue

            if recursive:
                for dirpath, dirnames, filenames in os.walk(root):
                    # prune excluded dirs in-place
                    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

                    for fn in filenames:
                        # quick basename match
                        for pat in patterns:
                            if fnmatch.fnmatch(fn, pat):
                                matches.append(os.path.join(dirpath, fn))
                                break
            else:
                # non-recursive: only top-level files
                for fn in os.listdir(root):
                    full = os.path.join(root, fn)
                    if not os.path.isfile(full):
                        continue
                    if fn in exclude_dirs:
                        continue
                    for pat in patterns:
                        if fnmatch.fnmatch(fn, pat):
                            matches.append(full)
                            break

        return matches
    # ————————————————————————————————————————————————————————————
    # /CURL IMPLEMENTATION
    def curl(self, tokens: list):
        headless = True
        args = []
        for t in tokens:
            if t == "--no-headless":
                headless = False
            else:
                args.append(t)
        if not args:
            raise ValueError("Usage: curl <url> [<url2>|<js>]")
        url1 = args[0] if args[0].startswith(("http://","https://")) else "http://"+args[0]
        url2 = None; script = None
        if len(args)>=2 and args[1].startswith(("http://","https://")):
            url2 = args[1]
            script = " ".join(args[2:]) if len(args)>2 else None
        else:
            script = " ".join(args[1:]) if len(args)>1 else None

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
                        result = f"<script error: {e}>"
                else:
                    result = await page.evaluate("() => document.body.innerText")
                print("----- curl result -----")
                print(result)
                await browser.close()
        asyncio.run(runner())

    # ————————————————————————————————————————————————————————————
    # /PLAY IMPLEMENTATION
    def play(self, instructions: str):
        if not async_playwright:
            raise RuntimeError("Playwright not installed")
        # 1) parse steps
        parse_prompt = (
            "Parse the following instructions into a numbered list of discrete steps:\n\n"
            f"{instructions}\n\n"
            "Respond ONLY as a numbered list."
        )
        parsed = self.ask(parse_prompt)
        print("----- Parsed steps -----")
        print(parsed)
        steps = [m.group(1).strip() for m in re.finditer(r"\d+\.\s*(.+)", parsed)]
        if not steps:
            raise RuntimeError("No steps parsed")

        # 2) run through steps
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
                        url = step.split("navigate to",1)[1].strip()
                        await page.goto(url, wait_until="domcontentloaded")
                        results.append(True)
                        continue
                    if low.startswith("click"):
                        tgt = step.split("click",1)[1].strip().strip("'\"")
                        await page.click(f"text={tgt}")
                        results.append(True)
                        continue
                    # try AI snippet
                    success = False
                    for attempt in (1,2):
                        title = await page.title() or "<no title>"
                        url   = page.url
                        print(f"--- Attempt {attempt} on {title} ({url})")
                        mini = await page.evaluate("""
                            () => Array.from(
                                document.querySelectorAll('h1,h2,p,a,button,input')
                            ).slice(0,5).map(e=>({tag:e.tagName, text:e.innerText?.slice(0,80)||''}))
                        """)
                        prompt_snip = (
                            "You are writing a Python Playwright snippet.\n"
                            f"Title: {title}\nURL: {url}\nMiniDOM: {json.dumps(mini)}\n"
                            f"Instruction: {step}\n"
                            "Write ONLY the await page.* lines, assign to `result`, then return result."
                        )
                        snippet = self.ask(prompt_snip).strip()
                        if snippet.startswith("```"):
                            snippet = "\n".join(snippet.splitlines()[1:-1])
                        # build async fn
                        fn_name = f"_step_{idx+1}_a{attempt}"
                        src = "async def "+fn_name+"(page):\n"
                        for ln in snippet.splitlines():
                            src += "    "+ln+"\n"
                        if "return" not in snippet:
                            src += "    return result\n"
                        local = {}
                        try:
                            exec(src, globals(), local)
                            fn = local[fn_name]
                            res = await fn(page)
                            assert res is not None
                            print(f"→ Success: {res!r}")
                            success = True
                            break
                        except Exception as e:
                            print(f"Error: {e}")
                    results.append(success)
                await browser.close()

        asyncio.run(runner())
        # summary
        print("\n--- /play summary ---")
        for i, ok in enumerate(results,1):
            print(f"Step {i}: {'Success' if ok else 'Failure'}")

    # ————————————————————————————————————————————————————————————
    # MCP-SERVER FILE-OPS (called by mcp_server.py)
    def list_files(self, roots):
        out = []
        for r in roots:
            for dp, _, fns in os.walk(r):
                for fn in fns:
                    out.append(os.path.join(dp,fn))
        return out

    def get_all_contents(self, roots):
        out = []
        for r in roots:
            for dp, _, fns in os.walk(r):
                for fn in fns:
                    path = os.path.join(dp,fn)
                    try:
                        txt = open(path,'r',encoding='utf-8').read()
                    except:
                        continue
                    out.append({"path":path,"content":txt})
        return out

    def read_file(self, path: str):
        return open(path, 'r', encoding='utf-8').read()

    def update_file(self, path: str, content: str):
        open(path, 'w', encoding='utf-8').write(content)

    def create_file(self, path: str, content: str=""):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'w', encoding='utf-8').write(content)

    def delete_file(self, path: str):
        os.remove(path)

    def append_file(self, path: str, content: str):
        open(path, 'a', encoding='utf-8').write(content)

    def create_dir(self, path: str, mode: int=0o755):
        os.makedirs(path, mode, exist_ok=True)

    def delete_dir(self, path: str, recursive: bool=False):
        if recursive:
            shutil.rmtree(path)
        else:
            os.rmdir(path)

    def rename(self, src: str, dst: str):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)

    def copy_file(self, src: str, dst: str):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


        raw = p.get("pattern","*")
        patterns = raw.split('|') if isinstance(raw, str) else [raw]
        recursive = p.get("recursive", True)
        root = p.get("root","")
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

    def checksum(self, path: str):
        h = hashlib.sha256()
        with open(path,'rb') as f:
            for chunk in iter(lambda: f.read(8192),b''):
                h.update(chunk)
        return h.hexdigest()
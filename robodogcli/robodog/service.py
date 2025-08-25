import os
import json
import shutil
import hashlib
import fnmatch
import glob
import yaml
import requests
import threading
import concurrent.futures
import tiktoken
from pathlib import Path
from openai import OpenAI

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

class RobodogService:
    def __init__(self, config_path: str, api_key: str = None):
        self._load_config(config_path)
        self.context   = ""
        self.knowledge = ""
        self.stashes   = {}
        self._init_llm(api_key)

    def _load_config(self, path):
        data = yaml.safe_load(open(path, 'r', encoding='utf-8'))
        cfg  = data.get("configs", {})
        self.providers = {p["provider"]: p for p in cfg.get("providers",[])}
        self.models    = cfg.get("models",[])
        self.mcp_cfg   = cfg.get("mcpServer",{})
        if not self.models:
            raise RuntimeError("No models configured")
        self.cur_model = self.models[0]["model"]
        self.stream    = self.models[0].get("stream", True)
        # sampling params
        self.temperature      = 1.0
        self.top_p            = 1.0
        self.max_tokens       = 1024
        self.frequency_penalty= 0.0
        self.presence_penalty = 0.0

    def _init_llm(self, api_key):
        self.api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY")
            or self.providers[self.model_provider(self.cur_model)]["apiKey"]
        )
        if not self.api_key:
            raise RuntimeError("Missing API key")
        self.client = OpenAI(api_key=self.api_key)

    def model_provider(self, name):
        for m in self.models:
            if m["model"] == name:
                return m["provider"]
        return None

    # —————————————————————————————————————————————————
    # LLM / Chat
    def ask(self, prompt: str) -> str:
        msgs = [
            {"role":"system","content":"You are Robodog, a helpful assistant."},
            {"role":"system","content":"Chat History:\n"+self.context},
            {"role":"system","content":"Knowledge Base:\n"+self.knowledge},
            {"role":"user","content":prompt},
        ]
        resp = self.client.chat.completions.create(
            model=self.cur_model,
            messages=msgs,
            temperature=self.temperature,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            stream=self.stream,
        )
        out = ""
        if self.stream:
            for chunk in resp:
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    print(delta, end="", flush=True)
                    out += delta
            print()
        else:
            out = resp.choices[0].message.content.strip()
        return out

    # —————————————————————————————————————————————————
    # Model management
    def list_models(self):
        return [m["model"] for m in self.models]

    def set_model(self, name: str):
        if name not in self.list_models():
            raise ValueError(f"Unknown model: {name}")
        self.cur_model = name
        self._init_llm(None)

    # —————————————————————————————————————————————————
    # API key management
    def set_key(self, provider: str, key: str):
        if provider not in self.providers:
            raise KeyError(f"No such provider: {provider}")
        self.providers[provider]["apiKey"] = key

    def get_key(self, provider: str):
        return self.providers.get(provider, {}).get("apiKey")

    # —————————————————————————————————————————————————
    # Stash / pop / list
    def stash(self, name: str):
        self.stashes[name] = (self.context, self.knowledge)

    def pop(self, name: str):
        if name not in self.stashes:
            raise KeyError(f"No stash: {name}")
        self.context, self.knowledge = self.stashes[name]

    def list_stashes(self):
        return list(self.stashes.keys())

    # —————————————————————————————————————————————————
    # Clear / export / import
    def clear(self):
        self.context = ""
        self.knowledge = ""

    def export_snapshot(self, filename: str):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=== Chat History ===\n"+self.context+"\n")
            f.write("=== Knowledge ===\n"+self.knowledge+"\n")

    def import_files(self, glob_pattern: str) -> int:
        cnt = 0
        for fn in glob.glob(glob_pattern, recursive=True):
            try:
                txt = open(fn, 'r', encoding='utf-8', errors='ignore').read()
                self.knowledge += f"\n\n--- {fn} ---\n{txt}"
                cnt += 1
            except:
                pass
        return cnt

    # —————————————————————————————————————————————————
    # Numeric params setter
    def set_param(self, key: str, value):
        if not hasattr(self, key):
            raise KeyError(f"No such param: {key}")
        setattr(self, key, value)

    # —————————————————————————————————————————————————
    # MCP‐client (for include, folders, etc.)
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

    # —————————————————————————————————————————————————
    # /include
    def include(self, spec: str, prompt: str = None):
        inc = self._parse_include(spec)
        # build SEARCH payloads
        searches = []
        if inc["type"] == "dir":
            searches.append({"root": inc["dir"], "pattern": inc["pattern"], "recursive": inc["recursive"]})
        else:
            pat = inc["pattern"] if inc["type"]=="pattern" else (inc["file"] or "*")
            searches.append({"pattern": pat, "recursive": True})
        # collect matches
        matches = []
        for p in searches:
            res = self.call_mcp("SEARCH", p)
            matches.extend(res.get("matches", []))
        matches = [m for m in matches if "node_modules" not in Path(m).parts]
        if not matches:
            raise RuntimeError("No files matched")
        # read them in parallel
        included = []
        def _r(path): return self.call_mcp("READ_FILE", {"path":path})
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            fut2p = {pool.submit(_r,p):p for p in matches}
            for fut in concurrent.futures.as_completed(fut2p):
                p = fut2p[fut]
                try:
                    blob = fut.result()
                    txt = blob.get("content","")
                    included.append(txt)
                except:
                    pass
        combined = "\n".join(included)
        if combined:
            self.knowledge += "\n"+combined+"\n"
        if prompt:
            self.context += f"\nUser: {prompt}"
            ans = self.ask(prompt)
            self.context += f"\nAI: {ans}"

    def _parse_include(self, text:str)->dict:
        parts = text.strip().split()
        cmd = {"type":None,"file":None,"dir":None,"pattern":"*","recursive":False}
        if not parts: return cmd
        p0=parts[0]
        if p0=="all":
            cmd["type"]="all"
        elif p0.startswith("file="):
            spec=p0[5:]
            if fnmatch.fnmatchcase(spec, spec) and any(x in spec for x in "*?[]"):
                cmd.update(type="pattern", pattern=spec, recursive=True)
            else:
                cmd.update(type="file", file=spec)
        elif p0.startswith("dir="):
            spec=p0[4:]
            cmd.update(type="dir", dir=spec)
            for t in parts[1:]:
                if t=="recursive": cmd["recursive"]=True
                if t.startswith("pattern="): cmd["pattern"]=t.split("=",1)[1]
        elif p0.startswith("pattern="):
            cmd.update(type="pattern", pattern=p0.split("=",1)[1], recursive=True)
        return cmd

    # —————————————————————————————————————————————————
    # /curl
    def curl(self, args):
        if async_playwright is None:
            raise RuntimeError("Install Playwright")
        # copy over CLI logic here as needed…

    # —————————————————————————————————————————————————
    # /play
    def play(self, instructions):
        if async_playwright is None:
            raise RuntimeError("Install Playwright")
        # copy over CLI logic…

    # —————————————————————————————————————————————————
    # MCP‐server file ops
    def list_files(self, roots):
        out=[]
        for r in roots:
            for dp,_,fns in os.walk(r):
                for fn in fns:
                    out.append(os.path.join(dp,fn))
        return out

    def get_all_contents(self, roots):
        out=[]
        for r in roots:
            for dp,_,fns in os.walk(r):
                for fn in fns:
                    fp=os.path.join(dp,fn)
                    try:
                        txt=open(fp,'r',encoding='utf-8').read()
                    except:
                        continue
                    out.append({"path":fp,"content":txt})
        return out

    def read_file(self, path):   return open(path,'r',encoding='utf-8').read()
    def update_file(self, path, content):
        open(path,'w',encoding='utf-8').write(content)
    def create_file(self, path, content=""):
        open(path,'w',encoding='utf-8').write(content)
    def delete_file(self, path): os.remove(path)
    def append_file(self, path, content):
        open(path,'a',encoding='utf-8').write(content)
    def create_dir(self, path, mode=0o755):
        os.makedirs(path, mode, exist_ok=True)
    def delete_dir(self, path, recursive=False):
        if recursive: shutil.rmtree(path)
        else:        os.rmdir(path)
    def rename(self, src, dst): os.rename(src,dst)
    def copy_file(self, src, dst): shutil.copy2(src,dst)
    def search(self, roots, pattern="*", recursive=True):
        matches=[]
        pats=pattern.split("|")
        for r in roots:
            if recursive:
                for dp,_,fns in os.walk(r):
                    for fn in fns:
                        for pat in pats:
                            if fnmatch.fnmatch(fn,pat):
                                matches.append(os.path.join(dp,fn))
                                break
            else:
                for fn in os.listdir(r):
                    fp=os.path.join(r,fn)
                    if os.path.isfile(fp):
                        for pat in pats:
                            if fnmatch.fnmatch(fn,pat):
                                matches.append(fp)
                                break
        return matches

    def checksum(self, path):
        h=hashlib.sha256()
        with open(path,'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''): h.update(chunk)
        return h.hexdigest()
# file: service.py
#!/usr/bin/env python3
import os
import re
import json
import shutil
import fnmatch
import hashlib
import sys
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
from typing import List, Optional
logger = logging.getLogger('robodog.service')


class RobodogService:
    def __init__(self, config_path: str, api_key: str = None, exclude_dirs: set = None , backupFolder:str = None, file_service: Optional[object] = None, spin: object = None, app=None):
        # --- load YAML config and LLM setup ---
        self._load_config(config_path)
        # --- ensure we always have a _roots attribute ---
        #    If svc.todo is set later by the CLI, include() will pick up svc.todo._roots.
        #    Otherwise we default to cwd.
        self._roots = [os.getcwd()]
        self._exclude_dirs = exclude_dirs or {"node_modules", "dist", "diffoutput"}
        self.stashes = {}
        self.backupFolder = backupFolder
        self.file_service = file_service
        self._spin = spin
        self._ui_callback = None  # New: callback for UI updates
        self._init_llm(api_key)
        self._app = app

    def set_ui_callback(self, callback):
        """Set callback for UI updates during streaming. Ensures no logger conflicts."""
        self._ui_callback = callback

    def _load_config(self, config_path):
        data = yaml.safe_load(open(config_path, 'r', encoding='utf-8'))
        cfg = data.get("configs", {})
        self.providers = {p["provider"]: p for p in cfg.get("providers", [])}
        self.models = cfg.get("models", [])
        self.mcp_cfg = cfg.get("mcpServer", {})
        self.cur_model = self.models[0]["model"]
        self.stream = self.models[0].get("stream", True)
        self.temperature = 1.0
        self.top_p = 1.0
        self.max_tokens = 1024
        self.frequency_penalty = 0.0
        self.presence_penalty = 0.0

    def _init_llm(self, api_key):
        provider_name = self.model_provider(self.cur_model)
        provider_cfg = self.providers.get(provider_name)

        if not provider_cfg:
            raise RuntimeError(f"No configuration found for provider: {provider_name}")

        self.api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY")
            or provider_cfg.get("apiKey")
        )

        if not self.api_key:
            raise RuntimeError("Missing API key")

        base_url = provider_cfg.get("baseUrl")
        if not base_url:
            raise RuntimeError(f"Missing baseUrl for provider: {provider_name}")

        # Initialize OpenAI client with provider's base URL
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url  # Ensure proper v1 endpoint
        )

    def get_cur_model(self):
        return self.cur_model
    
    def model_provider(self, model_name):
        for m in self.models:
            if m["model"] == model_name:
                return m["provider"]
        return None

    # ————————————————————————————————————————————————————————————
    # CORE LLM / CHAT - Enhanced for Textual UI
    def ask(self, prompt: str) -> str:
        logger.debug(f"ask {prompt!r}")
        messages = [{"role": "user", "content": prompt}]
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
        self._spin.start()
        if self.stream:
            for chunk in resp:
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    self._spin.spin(False)
                    answer += delta
                    # Enhanced: callback for UI updates during streaming (no console log)
                    #if self._ui_callback:
                        #self._ui_callback(delta)
                    # Avoid logger output here to prevent screen mess
        else:
            answer = resp.choices[0].message.content.strip()
            
        self._spin.stop()
        return answer
    
    # ————————————————————————————————————————————————————————————
    # MODEL / KEY MANAGEMENT
    def list_models(self):
        return [m["model"] for m in self.models]
    
    def list_models_about(self):
        return [m["model"] + ": " + m["about"] for m in self.models]

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
        return self.providers.get(provider, {}).get("apiKey")

    # ————————————————————————————————————————————————————————————
    # STASH / POP / LIST / CLEAR / IMPORT / EXPORT

    def list_stashes(self):
        return list(self.stashes.keys())

    def clear(self):
        pass

    def export_snapshot(self, filename: str):
        content = "=== Chat History ===\n" + getattr(self, 'context', '') + "\n" + "=== Knowledge ===\n" + getattr(self, 'knowledge', '') + "\n"
        self.file_service.write_file(Path(filename), content)

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
        cmd = {"type": None, "file": None, "dir": None, "pattern": "*", "recursive": False}
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
                    cmd["pattern"] = p.split("=", 1)[1]
                if p == "recursive":
                    cmd["recursive"] = True
            if re.search(r"[*?\[]", spec):
                cmd.update(type="pattern", pattern=spec, recursive=True)
        elif p0.startswith("pattern="):
            cmd.update(type="pattern", pattern=p0.split("=", 1)[1], recursive=True)
        return cmd

    def include_list(self, spec_text: str, prompt: str = None):
        """
        Discover files as before but return a list of metadata dicts:
        [
          {
            "filename": "/path/to/foo.py",
            "content": "... file text ...",
            "token_count": 123
          },
          …
        ]
        """
        inc    = self.parse_include(spec_text)
        searches = []

        if inc["type"] == "dir":
            searches.append({
                "root":      inc["dir"],
                "pattern":   inc["pattern"],
                "recursive": inc["recursive"]
            })
        else:
            pat = inc.get("pattern") or inc.get("file") or "*"
            searches.append({
                "pattern":   pat,
                "recursive": True
            })

        # collect all matching paths
        matches = []
        for p in searches:
            if p.get("root"):
                roots = [p["root"]]
            elif hasattr(self, "todo") and getattr(self.todo, "_roots", None):
                roots = self.todo._roots
            else:
                roots = self._roots

            found = self.search_files(
                patterns=p.get("pattern", "*"),
                recursive=p.get("recursive", True),
                roots=roots
            )
            matches.extend(found)

        if not matches:
            return []

        # read each file in parallel
        def _read(path):
            content = self.read_file(path)
            return path, content

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for path, content in pool.map(_read, matches):
                token_count = len(content.split())
                logger.info(f"Included file: {path} ({token_count} tokens)")
                results.append({
                    "filename":    path,
                    "content":     content,
                    "token_count": token_count
                })

        return results
    
    def combine_knowledge(self, entries: list) -> str:
        """
        Given a list of {filename, content, token_count, …} dictionaries,
        return a single string in the old “knowledge” format:
            # file: /path/to/foo.py
            <content of foo.py>

            # file: /path/to/bar.txt
            <content of bar.txt>
        """
        blocks = []
        for entry in entries:
            fname   = entry.get("filename", "<unknown>")
            content = entry.get("content", "")
            blocks.append(f"# file: {fname}")
            blocks.append(content)
            blocks.append("")   # blank line between files
        # join with newline
        return "\n".join(blocks).strip()  # strip to avoid leading/trailing blank lines
    
    def include(self, spec_text: str, prompt: str = None):
        entries = self.include_list(spec_text=spec_text, prompt=prompt)
        knowledge = self.combine_knowledge(entries=entries)
        return knowledge
    
    def include_files_text(self, spec_text: str, prompt: str = None):
        inc = self.parse_include(spec_text)
        knowledge = ""
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
        for p in searches:
            root = p.get("root")
            # fix: pick up __roots injected from CLI's TodoService, or default to cwd
            if root:
                roots = [root]
            elif hasattr(self, 'todo') and getattr(self.todo, '_roots', None):
                roots = self.todo._roots
            else:
                roots = self._roots

            found = self.search_files(
                patterns=p.get("pattern", "*"),
                recursive=p.get("recursive", True),
                roots=roots
            )
            matches.extend(found)

        if not matches:
            return None

       

        def _read(path):
            content = self.read_file(path)
            return path, content

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for path, txt in pool.map(_read, matches):
                wc = len(txt.split())
                included_txts = []
                logger.info(f"Included file: {path} ({wc} tokens)")
                included_txts.append("# file: " + path)
                included_txts.append(txt)
                combined = "\n".join(included_txts)
                knowledge += "\n" + combined + "\n"

        return knowledge

    # Default exclude directories
    DEFAULT_EXCLUDE_DIRS = {"node_modules", "dist", "diffoutput"}

    def search_files(self, patterns="*", recursive=True, roots=None, exclude_dirs=None):
        if isinstance(patterns, str):
            patterns = patterns.split("|")
        else:
            patterns = list(patterns)
        exclude_dirs = set(exclude_dirs or self._exclude_dirs)
        matches = []
        for root in roots or []:
            if not os.path.isdir(root):
                continue
            if recursive:
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
                    for fn in filenames:
                        full = os.path.join(dirpath, fn)
                        for pat in patterns:
                            if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                                matches.append(full)
                                break
            else:
                for fn in os.listdir(root):
                    full = os.path.join(root, fn)
                    if not os.path.isfile(full) or fn in exclude_dirs:
                        continue
                    for pat in patterns:
                        if fnmatch.fnmatch(full, pat) or fnmatch.fnmatch(fn, pat):
                            matches.append(full)
                            break
        return matches

    # ————————————————————————————————————————————————————————————
    # /CURL IMPLEMENTATION
    def curl(self, tokens: list):
        pass

    # ————————————————————————————————————————————————————————————
    # /PLAY IMPLEMENTATION
    def play(self, instructions: str):
        pass

    # ————————————————————————————————————————————————————————————
    # MCP-SERVER FILE-OPS
    def read_file(self, path: str):
        return self.file_service.safe_read_file(Path(path))

    def update_file(self, path: str, content: str):
        self.file_service.write_file(Path(path), content)

    def create_file(self, path: str, content: str = ""):
        self.file_service.write_file(Path(path), content)

    def delete_file(self, path: str):
        self.file_service.delete_file(Path(path))

    def append_file(self, path: str, content: str):
        self.file_service.append_file(Path(path), content)

    def create_dir(self, path: str, mode: int = 0o755):
        self.file_service.ensure_dir(Path(path))

    def delete_dir(self, path: str, recursive: bool = False):
        self.file_service.delete_dir(Path(path), recursive=recursive)

    def rename(self, src: str, dst: str):
        self.file_service.rename(Path(src), Path(dst))

    def copy_file(self, src: str, dst: str):
        self.file_service.copy_file(Path(src), Path(dst))

    def _parse_base_dir(self) -> Optional[str]:
        """
        Look for a YAML front-matter block at the top of any todo.md,
        scan it line-by-line for the first line starting with `base:`
        and return its value.
        """
        for fn in self._find_files():
            text = self.file_service.safe_read_file(Path(fn))
            lines = text.splitlines()
            # Must start a YAML block
            if not lines or lines[0].strip() != '---':
                continue

            # Find end of that block
            try:
                end_idx = lines.index('---', 1)
            except ValueError:
                # no closing '---'
                continue

            # Scan only the lines inside the front-matter
            for lm in lines[1:end_idx]:
                stripped = lm.strip()
                if stripped.startswith('base:'):
                    # split on first colon, strip whitespace
                    _, _, val = stripped.partition(':')
                    base = val.strip()
                    if base:
                        return os.path.normpath(base)
        return None

    def _find_files(self) -> List[str]:
        out = []
        for r in self._roots:
            for dp, _, fns in os.walk(r):
                if self.FILENAME in fns:
                    out.append(os.path.join(dp, self.FILENAME))
        return out

    def checksum(self, path: str):
        content = self.file_service.binary_read(Path(path))
        h = hashlib.sha256(content)
        return h.hexdigest()

# Original file length: 555 lines
# Updated file length: 555 lines
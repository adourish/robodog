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
    def __init__(self, config_path: str, api_key: str = None, exclude_dirs: set = None):
        # --- load YAML config and LLM setup ---
        self._load_config(config_path)
        # --- ensure we always have a _roots attribute ---
        #    If svc.todo is set later by the CLI, include() will pick up svc.todo._roots.
        #    Otherwise we default to cwd.
        self._roots = [os.getcwd()]
        self._exclude_dirs = exclude_dirs or {"node_modules", "dist"}
        self.stashes = {}
        self._init_llm(api_key)

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
    # CORE LLM / CHAT
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
        spinner = [
            "[•-----]",
            "[-•----]",
            "[--•---]",
            "[---•--]",
            "[----•-]",
            "[-----•]",
            "[----•-]",
            "[---•--]",
            "[--•---]",
            "[-•----]",
            "[•-----]",
            "[-•----]",
            "[--•---]",
            "[---•--]",
            "[----•-]",
            "[-----•]",
            "[----•-]",
            "[---•--]",
            "[--•---]",
            "[-•----]",
            "[•-----]",
            "[-•----]",
            "[--•---]",
            "[---•--]",
            "[----•-]",
            "[-----•]",
            "[----•-]",
            "[---•--]",
            "[--•---]",
            "[-•----]",
        ]
        idx    = 0
        answer = ""
        if self.stream:
            for chunk in resp:
                # accumulate the streamed text
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    answer += delta

                # grab the last line (or everything if no newline yet)
                last_line = answer.splitlines()[-1] if "\n" in answer else answer

                # pick our fighter‐vs‐fighter frame
                frame = spinner[idx % len(spinner)]
                if idx % 50 == 0:
                    sys.stdout.write(
                        f"\r{frame}  {last_line[:60]}{'…' if len(last_line) > 60 else ''}"
                    )
                    sys.stdout.flush()
                    sys.stdout.write(f"\x1b]0;{last_line[:60].strip()}…\x07")
                    sys.stdout.flush()

                idx += 1

            # done streaming!
            sys.stdout.write("\n\n")
        else:
            answer = resp.choices[0].message.content.strip()
        return answer

    # ————————————————————————————————————————————————————————————
    # MODEL / KEY MANAGEMENT
    def list_models(self):
        return [m["model"] for m in self.models]
    
    # ————————————————————————————————————————————————————————————
    # MODEL / KEY MANAGEMENT
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
    def stash(self, name: str):
        self.stashes[name] = str

    def pop(self, name: str):
        if name not in self.stashes:
            raise KeyError(f"No stash {name}")
        return self.stashes[name]

    def list_stashes(self):
        return list(self.stashes.keys())

    def clear(self):
        pass

    def import_files(self, glob_pattern: str) -> int:
        count = 0
        knowledge = ""
        for fn in __import__('glob').glob(glob_pattern, recursive=True):
            try:
                txt = open(fn, 'r', encoding='utf-8', errors='ignore').read()
                knowledge += f"\n\n--- {fn} ---\n{txt}"
                count += 1
            except:
                pass
        return knowledge

    def export_snapshot(self, filename: str):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=== Chat History ===\n" + self.context + "\n")
            f.write("=== Knowledge ===\n" + self.knowledge + "\n")

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
    def parse_include(self, text: str
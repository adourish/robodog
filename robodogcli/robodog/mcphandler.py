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

import threading
import socketserver
from service import RobodogService

ROOTS    = []
TOKEN    = None
SERVICE  = None

class MCPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        # Read first line
        raw = self.rfile.readline().decode('utf-8', errors='ignore')
        if not raw:
            return
        line = raw.rstrip('\r\n')
        is_http = line.upper().startswith(("GET ","POST ","OPTIONS ")) and "HTTP/" in line

        if is_http:
            self._handle_http(line)
        else:
            # raw MCP protocol
            op, _, arg = line.partition(" ")
            try:
                payload = json.loads(arg) if arg else {}
            except json.JSONDecodeError:
                self._write_json({"status":"error","error":"Invalid JSON payload"})
                return
            res = self._dispatch(op.upper(), payload)
            self._write_json(res)

    def _handle_http(self, first_line):
        # parse request line
        try:
            method, uri, version = first_line.split(None,2)
        except ValueError:
            return
        headers = {}
        # read headers
        while True:
            h = self.rfile.readline().decode('utf-8', errors='ignore')
            if not h or h in ('\r\n','\n'):
                break
            name, val = h.split(":",1)
            headers[name.lower().strip()] = val.strip()
        # CORS preflight
        if method.upper() == "OPTIONS":
            resp = [
                "HTTP/1.1 204 No Content",
                "Access-Control-Allow-Origin: *",
                "Access-Control-Allow-Methods: POST, OPTIONS",
                "Access-Control-Allow-Headers: Content-Type, Authorization",
                "Access-Control-Max-Age: 86400",
                "Connection: close", "", ""
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return
        if method.upper() != "POST":
            resp = [
                "HTTP/1.1 405 Method Not Allowed",
                "Access-Control-Allow-Origin: *",
                "Allow: POST, OPTIONS",
                "Content-Type: text/plain; charset=utf-8",
                "Connection: close", "", "Only POST supported\n"
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return
        # auth
        auth = headers.get("authorization","")
        if auth != f"Bearer {TOKEN}":
            body = json.dumps({"status":"error","error":"Authentication required"})
            resp = [
                "HTTP/1.1 401 Unauthorized",
                "Access-Control-Allow-Origin: *",
                "Content-Type: application/json; charset=utf-8",
                f"Content-Length: {len(body.encode('utf-8'))}",
                "Connection: close", "", body
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return
        # read body
        length = int(headers.get("content-length","0"))
        raw_body = self.rfile.read(length).decode('utf-8', errors='ignore').strip()
        op, _, arg = raw_body.partition(" ")
        try:
            payload = json.loads(arg) if arg else {}
        except json.JSONDecodeError:
            result = {"status":"error","error":"Invalid JSON payload"}
        else:
            result = self._dispatch(op.upper(), payload)
        body = json.dumps(result, ensure_ascii=False)
        resp = [
            "HTTP/1.1 200 OK",
            "Access-Control-Allow-Origin: *",
            "Access-Control-Allow-Headers: Content-Type, Authorization",
            "Content-Type: application/json; charset=utf-8",
            f"Content-Length: {len(body.encode('utf-8'))}",
            "Connection: close", "", body
        ]
        self.wfile.write(("\r\n".join(resp)).encode('utf-8'))

    def _dispatch(self, op, p):
        svc = SERVICE
        try:
            # ==== BASIC MCP FILE OPERATIONS ====
            if op == "HELP":
                return {"status":"ok","commands": [
                    "LIST_FILES","GET_ALL_CONTENTS","READ_FILE","UPDATE_FILE",
                    "CREATE_FILE","DELETE_FILE","APPEND_FILE","CREATE_DIR",
                    "DELETE_DIR","RENAME","MOVE","COPY_FILE","SEARCH",
                    "CHECKSUM","QUIT","EXIT"
                ]}
            if op == "SET_ROOTS":
                roots = p.get("roots")
                if not isinstance(roots, list):
                    raise ValueError("Missing 'roots' list")
                absr = []
                for r in roots:
                    a = os.path.abspath(r)
                    if not os.path.isdir(a):
                        raise FileNotFoundError(a)
                    absr.append(a)
                global ROOTS
                ROOTS = absr
                return {"status":"ok","roots":ROOTS}
            if op == "LIST_FILES":
                files = svc.list_files(ROOTS)
                return {"status":"ok","files": files}
            if op == "GET_ALL_CONTENTS":
                contents = svc.get_all_contents(ROOTS)
                return {"status":"ok","contents": contents}
            if op == "READ_FILE":
                path = p.get("path")
                return {"status":"ok","path":path,
                        "content": svc.read_file(path)}
            if op == "UPDATE_FILE":
                svc.update_file(p["path"], p["content"])
                return {"status":"ok","path":p["path"]}
            if op == "CREATE_FILE":
                svc.create_file(p["path"], p.get("content",""))
                return {"status":"ok","path":p["path"]}
            if op == "DELETE_FILE":
                svc.delete_file(p["path"])
                return {"status":"ok","path":p["path"]}
            if op == "APPEND_FILE":
                svc.append_file(p["path"], p.get("content",""))
                return {"status":"ok","path":p["path"]}
            if op == "CREATE_DIR":
                svc.create_dir(p["path"], p.get("mode",0o755))
                return {"status":"ok","path":p["path"]}
            if op == "DELETE_DIR":
                svc.delete_dir(p["path"], p.get("recursive",False))
                return {"status":"ok","path":p["path"]}
            if op in ("RENAME","MOVE"):
                svc.rename(p["src"], p["dst"])
                return {"status":"ok","src":p["src"],"dst":p["dst"]}
            if op == "COPY_FILE":
                svc.copy_file(p["src"], p["dst"])
                return {"status":"ok","src":p["src"],"dst":p["dst"]}
            if op == "SEARCH":
                pattern   = p.get("pattern","*")
                recursive = p.get("recursive",True)
                roots     = [p["root"]] if p.get("root") else ROOTS
                matches   = svc.search(roots, pattern, recursive)
                return {"status":"ok","matches": matches}
            if op == "CHECKSUM":
                cs = svc.checksum(p["path"])
                return {"status":"ok","path":p["path"],"checksum":cs}

            # ==== ROBODOG SERVICE (CLI) OPERATIONS ====
            if op == "ASK":
                prompt = p.get("prompt")
                if prompt is None:
                    raise ValueError("Missing 'prompt'")
                response = svc.ask(prompt)
                return {"status":"ok","response": response}

            if op == "LIST_MODELS":
                return {"status":"ok","models": svc.list_models()}

            if op == "SET_MODEL":
                model = p.get("model")
                svc.set_model(model)
                return {"status":"ok","model": model}

            if op == "SET_KEY":
                prov = p.get("provider")
                key  = p.get("key")
                svc.set_key(prov, key)
                return {"status":"ok","provider": prov}

            if op == "GET_KEY":
                prov = p.get("provider")
                key  = svc.get_key(prov)
                return {"status":"ok","provider":prov,"key":key}

            if op == "STASH":
                name = p.get("name")
                svc.stash(name)
                return {"status":"ok","stashed":name}

            if op == "POP":
                name = p.get("name")
                svc.pop(name)
                return {"status":"ok","popped":name}

            if op == "LIST_STASHES":
                return {"status":"ok","stashes": svc.list_stashes()}

            if op == "CLEAR":
                svc.clear()
                return {"status":"ok"}

            if op == "IMPORT_FILES":
                pattern = p.get("pattern")
                count = svc.import_files(pattern)
                return {"status":"ok","imported":count}

            if op == "EXPORT_SNAPSHOT":
                filename = p.get("filename")
                svc.export_snapshot(filename)
                return {"status":"ok","snapshot":filename}

            if op == "SET_PARAM":
                key   = p.get("key")
                value = p.get("value")
                svc.set_param(key, value)
                return {"status":"ok","param":key,"value":value}

            if op == "INCLUDE":
                spec   = p.get("spec")
                prompt = p.get("prompt", None)
                answer = svc.include(spec, prompt)
                resp = {"status":"ok"}
                if answer is not None:
                    resp["answer"] = answer
                return resp

            if op == "CURL":
                tokens = p.get("tokens", [])
                svc.curl(tokens)
                return {"status":"ok"}

            if op == "PLAY":
                instructions = p.get("instructions")
                svc.play(instructions)
                return {"status":"ok"}

            if op in ("QUIT","EXIT"):
                return {"status":"ok","message":"Goodbye!"}

            # unknown
            raise ValueError(f"Unknown op: {op}")

        except Exception as e:
            return {"status":"error","error": str(e)}

    def _write_json(self, obj):
        self.wfile.write((json.dumps(obj)+"\n").encode('utf-8'))

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads      = True
    allow_reuse_address = True

def run_robodogmcp(host: str, port: int, token: str,
                   folders: list, svc: RobodogService):
    """
    Launches a threaded MCP server on (host,port), with bearer auth token,
    serving the given folders via the provided RobodogService.
    Returns the server instance (call shutdown()/server_close() when done).
    """
    global TOKEN, ROOTS, SERVICE
    TOKEN   = token
    SERVICE = svc
    ROOTS   = [os.path.abspath(f) for f in folders]
    server  = ThreadedTCPServer((host, port), MCPHandler)
    t       = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
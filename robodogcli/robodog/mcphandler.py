# file: mcphandler.py

#!/usr/bin/env python3
import os
import json
import threading
import socketserver
import fnmatch
import hashlib
import shutil
import logging

try:
    from .service import RobodogService
except ImportError:
    from service import RobodogService

logger = logging.getLogger('robodog.mcphandler')

ROOTS   = []
TOKEN   = None
SERVICE = None

def _is_path_allowed(path: str) -> bool:
    abs_path = os.path.abspath(path)
    for r in ROOTS:
        r_abs = os.path.abspath(r)
        if abs_path == r_abs or abs_path.startswith(r_abs + os.sep):
            return True
    return False

class MCPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        raw = self.rfile.readline()
        if not raw:
            return
        first = raw.decode('utf-8', errors='ignore').rstrip('\r\n')
        is_http = first.upper().startswith(("GET ","POST ","OPTIONS ")) and "HTTP/" in first
        if is_http:
            return self._handle_http(first)
        op, _, arg = first.partition(" ")
        try:
            payload = json.loads(arg) if arg.strip() else {}
        except json.JSONDecodeError:
            return self._write_json({"status":"error","error":"Invalid JSON payload"})
        resp = self._dispatch(op.upper(), payload)
        self._write_json(resp)

    def _dispatch(self, op, p):
        try:
            if op == "HELP":
                return {"status":"ok","commands":[
                    "LIST_FILES","GET_ALL_CONTENTS","READ_FILE","UPDATE_FILE",
                    "CREATE_FILE","DELETE_FILE","APPEND_FILE","CREATE_DIR",
                    "DELETE_DIR","RENAME","MOVE","COPY_FILE","SEARCH",
                    "CHECKSUM","TODO","INCLUDE","CURL","PLAY",
                    "FIND_UNUSED","QUIT","EXIT"
                ]}

            # ... existing handlers unchanged ...

            if op == "PLAY":
                SERVICE.play(p.get("instructions",""))
                return {"status":"ok"}

            # NEW: Find unused functions
            if op == "FIND_UNUSED":
                roots = p.get("roots") or ROOTS
                unused = SERVICE.find_unused_functions(roots)
                return {"status":"ok","unused": unused}

            if op in ("QUIT","EXIT"):
                return {"status":"ok","message":"Goodbye!"}

            raise ValueError(f"Unknown command '{op}'")
        except PermissionError as pe:
            return {"status":"error","error": str(pe)}
        except Exception as e:
            return {"status":"error","error": str(e)}

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads      = True
    allow_reuse_address = True

def run_robodogmcp(host: str, port: int, token: str,
                   folders: list, svc: RobodogService):
    global TOKEN, ROOTS, SERVICE
    TOKEN   = token
    SERVICE = svc
    ROOTS   = [os.path.abspath(f) for f in folders]
    server  = ThreadedTCPServer((host, port), MCPHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

# original file length: 256 lines
# updated file length: 266 lines

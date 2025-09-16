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
import requests

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

    def _handle_http(self, first_line):
        # Minimal HTTP support: read headers, respond with JSON status
        while True:
            line = self.rfile.readline()
            if not line or line in (b'\r\n', b'\n'):
                break
        body = {"status":"ok","message":"robodog MCP server"}
        data = json.dumps(body)
        resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            f"Content-Length: {len(data)}\r\n"
            "\r\n"
            f"{data}"
        )
        self.wfile.write(resp.encode('utf-8'))

    def _write_json(self, obj):
        try:
            s = json.dumps(obj)
        except Exception:
            s = json.dumps({"status":"error","error":"Serialization error"})
        self.wfile.write((s + "\n").encode('utf-8'))

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

            # File operations
            if op in ("LIST_FILES", "SEARCH"):
                pattern = p.get("pattern", "*")
                recursive = p.get("recursive", True)
                roots = [os.path.abspath(f) for f in (p.get("roots") or ROOTS)]
                files = SERVICE.search_files(patterns=pattern, recursive=recursive, roots=roots)
                return {"status":"ok","files": files}

            if op == "GET_ALL_CONTENTS":
                pattern = p.get("pattern", "*")
                recursive = p.get("recursive", True)
                roots = [os.path.abspath(f) for f in (p.get("roots") or ROOTS)]
                files = SERVICE.search_files(patterns=pattern, recursive=recursive, roots=roots)
                contents = {}
                for f in files:
                    if not _is_path_allowed(f):
                        continue
                    try:
                        contents[f] = SERVICE.read_file(f)
                    except Exception as e:
                        contents[f] = f"Error: {e}"
                return {"status":"ok","contents": contents}

            if op == "READ_FILE":
                path = p.get("path")
                if not path or not _is_path_allowed(path):
                    raise PermissionError(f"Access denied or missing path: {path}")
                content = SERVICE.read_file(path)
                return {"status":"ok","content": content}

            if op == "UPDATE_FILE":
                path = p.get("path"); content = p.get("content","")
                if not path or not _is_path_allowed(path):
                    raise PermissionError(f"Access denied or missing path: {path}")
                SERVICE.update_file(path, content)
                return {"status":"ok"}

            if op == "CREATE_FILE":
                path = p.get("path"); content = p.get("content","")
                if not path or not _is_path_allowed(path):
                    raise PermissionError(f"Access denied or missing path: {path}")
                SERVICE.create_file(path, content)
                return {"status":"ok"}

            if op == "DELETE_FILE":
                path = p.get("path")
                if not path or not _is_path_allowed(path):
                    raise PermissionError(f"Access denied or missing path: {path}")
                SERVICE.delete_file(path)
                return {"status":"ok"}

            if op == "APPEND_FILE":
                path = p.get("path"); content = p.get("content","")
                if not path or not _is_path_allowed(path):
                    raise PermissionError(f"Access denied or missing path: {path}")
                SERVICE.append_file(path, content)
                return {"status":"ok"}

            if op == "CREATE_DIR":
                path = p.get("path"); mode = p.get("mode", 0o755)
                if not path or not _is_path_allowed(path):
                    raise PermissionError(f"Access denied or missing path: {path}")
                SERVICE.create_dir(path, mode)
                return {"status":"ok"}

            if op == "DELETE_DIR":
                path = p.get("path"); recursive = p.get("recursive", False)
                if not path or not _is_path_allowed(path):
                    raise PermissionError(f"Access denied or missing path: {path}")
                SERVICE.delete_dir(path, recursive)
                return {"status":"ok"}

            if op in ("RENAME", "MOVE"):
                src = p.get("src"); dst = p.get("dst")
                if not src or not dst or not _is_path_allowed(src) or not _is_path_allowed(dst):
                    raise PermissionError(f"Access denied or missing src/dst: {src} -> {dst}")
                SERVICE.rename(src, dst)
                return {"status":"ok"}

            if op == "COPY_FILE":
                src = p.get("src"); dst = p.get("dst")
                if not src or not dst or not _is_path_allowed(src) or not _is_path_allowed(dst):
                    raise PermissionError(f"Access denied or missing src/dst: {src} -> {dst}")
                SERVICE.copy_file(src, dst)
                return {"status":"ok"}

            if op == "CHECKSUM":
                path = p.get("path")
                if not path or not _is_path_allowed(path):
                    raise PermissionError(f"Access denied or missing path: {path}")
                cs = SERVICE.checksum(path)
                return {"status":"ok","checksum": cs}

            # Include files into knowledge
            if op == "INCLUDE":
                spec = p.get("spec")
                if not spec:
                    if 'pattern' in p:
                        spec = f"pattern={p['pattern']}" + (" recursive" if p.get("recursive") else "")
                    elif 'file' in p:
                        spec = f"file={p['file']}"
                    elif 'dir' in p:
                        spec = f"dir={p['dir']}" + (" recursive" if p.get("recursive") else "")
                    else:
                        return {"status":"error","error":"No include specification provided"}
                included = SERVICE.include(spec)
                return {"status":"ok","knowledge": included}

            # Curl a URL
            if op == "CURL":
                url = p.get("url") or p.get("path")
                if not url or not url.startswith(("http://","https://")):
                    return {"status":"error","error":f"Invalid URL: {url}"}
                try:
                    r = requests.get(url, timeout=10)
                    r.raise_for_status()
                    return {"status":"ok","data": r.text}
                except Exception as e:
                    return {"status":"error","error": str(e)}

            # TODO listing - not implemented
            if op == "TODO":
                return {"status":"error","error":"TODO command not implemented"}

            # Play instructions
            if op == "PLAY":
                SERVICE.play(p.get("instructions",""))
                return {"status":"ok"}

            # Find unused functions
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
            logger.exception("Error handling operation")
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

# original file length: 266 lines
# updated file length: 366 lines
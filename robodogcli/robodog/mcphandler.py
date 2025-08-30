# file: robodog/cli/mcphandler.py
#!/usr/bin/env python3
import os
import json
import threading
import socketserver
import fnmatch
import hashlib
import shutil
import logging

from service import RobodogService  # your existing service.py
logger = logging.getLogger('robodog.mcphandler')

ROOTS   = []
TOKEN   = None
SERVICE = None

class MCPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        raw = self.rfile.readline()
        if not raw:
            return
        first = raw.decode('utf-8', errors='ignore').rstrip('\r\n')
        # detect HTTP vs raw MCP
        is_http = first.upper().startswith(("GET ","POST ","OPTIONS ")) and "HTTP/" in first
        if is_http:
            return self._handle_http(first)
        # raw MCP
        op, _, arg = first.partition(" ")
        try:
            payload = json.loads(arg) if arg.strip() else {}
        except json.JSONDecodeError:
            return self._write_json({"status":"error","error":"Invalid JSON payload"})
        resp = self._dispatch(op.upper(), payload)
        self._write_json(resp)

    def _handle_http(self, first_line):
        # parse HTTP request + CORS + auth + body
        try:
            method, uri, version = first_line.split(None, 2)
        except ValueError:
            return
        headers = {}
        # read headers
        while True:
            line = self.rfile.readline().decode('utf-8', errors='ignore')
            if not line or line in ('\r\n','\n'):
                break
            key, val = line.split(":",1)
            headers[key.lower().strip()] = val.strip()

        if method.upper() == 'OPTIONS':
            resp = [
                "HTTP/1.1 204 No Content",
                "Access-Control-Allow-Origin: *",
                "Access-Control-Allow-Methods: POST, OPTIONS",
                "Access-Control-Allow-Headers: Content-Type, Authorization",
                "Connection: close", "", ""
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return

        if method.upper() != 'POST':
            resp = [
                "HTTP/1.1 405 Method Not Allowed",
                "Access-Control-Allow-Origin: *",
                "Allow: POST, OPTIONS",
                "Connection: close", "", "Only POST supported"
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return

        # auth
        if headers.get('authorization') != f"Bearer {TOKEN}":
            body = json.dumps({"status":"error","error":"Authentication required"})
            resp = [
                "HTTP/1.1 401 Unauthorized",
                "Access-Control-Allow-Origin: *",
                "Content-Type: application/json",
                f"Content-Length: {len(body)}",
                "Connection: close", "", body
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return

        length = int(headers.get('content-length','0'))
        body_raw = self.rfile.read(length).decode('utf-8', errors='ignore')
        op, _, arg = body_raw.partition(" ")
        try:
            payload = json.loads(arg) if arg.strip() else {}
        except json.JSONDecodeError:
            result = {"status":"error","error":"Invalid JSON payload"}
        else:
            result = self._dispatch(op.upper(), payload)

        body = json.dumps(result, ensure_ascii=False)
        resp = [
            "HTTP/1.1 200 OK",
            "Access-Control-Allow-Origin: *",
            "Content-Type: application/json; charset=utf-8",
            f"Content-Length: {len(body.encode('utf-8'))}",
            "Connection: close", "", body
        ]
        self.wfile.write(("\r\n".join(resp)).encode('utf-8'))

    def _write_json(self, obj):
        data = json.dumps(obj) + "\n"
        self.wfile.write(data.encode('utf-8'))

    def _dispatch(self, op, p):
        try:
            # --- file‐service ops ---
            if op == "HELP":
                return {"status":"ok","commands":[
                    "LIST_FILES","GET_ALL_CONTENTS","READ_FILE","UPDATE_FILE",
                    "CREATE_FILE","DELETE_FILE","APPEND_FILE","CREATE_DIR",
                    "DELETE_DIR","RENAME","MOVE","COPY_FILE","SEARCH",
                    "CHECKSUM","TODO","INCLUDE","CURL","PLAY",
                    "QUIT","EXIT"
                ]}

            if op == "SET_ROOTS":
                roots = p.get("roots")
                if not isinstance(roots, list):
                    raise ValueError("Missing 'roots' list")
                absr = [os.path.abspath(r) for r in roots]
                for r in absr:
                    if not os.path.isdir(r):
                        raise FileNotFoundError(f"Not a directory: {r}")
                global ROOTS; ROOTS = absr
                return {"status":"ok","roots":ROOTS}

            if op == "LIST_FILES":
                files = SERVICE.list_files(ROOTS)
                return {"status":"ok","files":files}

            if op == "GET_ALL_CONTENTS":
                contents = SERVICE.get_all_contents(ROOTS)
                return {"status":"ok","contents":contents}

            if op == "READ_FILE":
                path = p.get("path") or ""
                if not path: raise ValueError("Missing 'path'")
                data = SERVICE.read_file(path)
                return {"status":"ok","path":path,"content":data}

            if op == "UPDATE_FILE":
                path = p.get("path") or ""
                if not path: raise ValueError("Missing 'path'")
                content = p.get("content","")
                if not os.path.exists(path):
                    SERVICE.create_file(path, content)
                else:
                    SERVICE.update_file(path, content)
                return {"status":"ok","path":path}

            if op == "CREATE_FILE":
                path = p.get("path") or ""
                content = p.get("content","")
                if not path: raise ValueError("Missing 'path'")
                SERVICE.create_file(path, content)
                return {"status":"ok","path":path}

            if op == "DELETE_FILE":
                path = p.get("path") or ""
                if not path: raise ValueError("Missing 'path'")
                SERVICE.delete_file(path)
                return {"status":"ok","path":path}

            if op == "APPEND_FILE":
                path = p.get("path") or ""
                content = p.get("content","")
                if not path: raise ValueError("Missing 'path'")
                SERVICE.append_file(path, content)
                return {"status":"ok","path":path}

            if op == "CREATE_DIR":
                path = p.get("path") or ""
                mode = p.get("mode", 0o755)
                if not path: raise ValueError("Missing 'path'")
                SERVICE.create_dir(path, mode)
                return {"status":"ok","path":path}

            if op == "DELETE_DIR":
                path = p.get("path") or ""
                rec  = bool(p.get("recursive", False))
                if not path: raise ValueError("Missing 'path'")
                SERVICE.delete_dir(path, rec)
                return {"status":"ok","path":path}

            if op in ("RENAME","MOVE"):
                src = p.get("src") or p.get("path")
                dst = p.get("dst") or p.get("dest")
                if not src or not dst:
                    raise ValueError("Missing 'src' or 'dst'")
                SERVICE.rename(src, dst)
                return {"status":"ok","src":src,"dst":dst}

            if op == "COPY_FILE":
                src = p.get("src")
                dst = p.get("dst")
                if not src or not dst:
                    raise ValueError("Missing 'src' or 'dst'")
                SERVICE.copy_file(src, dst)
                return {"status":"ok","src":src,"dst":dst}

            if op == "SEARCH":
                patt = p.get("pattern","*")
                rec  = bool(p.get("recursive", True))
                excl = p.get("exclude", None)
                roots = ROOTS if not p.get("root") else [p.get("root")]
                found = SERVICE.search_files(patterns=patt, recursive=rec,
                                             roots=roots, exclude_dirs=excl)
                return {"status":"ok","matches":found}

            if op == "CHECKSUM":
                path = p.get("path") or ""
                if not path: raise ValueError("Missing 'path'")
                cs = SERVICE.checksum(path)
                return {"status":"ok","path":path,"checksum":cs}

            # --- todo ---
            if op == "TODO":
                SERVICE.todo.run_next_task(SERVICE)
                return {"status":"ok"}

            # --- include/ask ---
            if op == "INCLUDE":
                spec   = p.get("spec","")
                prompt = p.get("prompt","")
                know   = SERVICE.include(spec) or ""
                result = {"status":"ok","knowledge":know}
                if prompt:
                    ans = SERVICE.ask(f"{prompt} {know}".strip())
                    result["answer"] = ans
                return result

            # --- passthrough LLM/meta ---
            if op == "ASK":
                prompt = p.get("prompt")
                if prompt is None: raise ValueError("Missing 'prompt'")
                resp = SERVICE.ask(prompt)
                return {"status":"ok","response":resp}

            if op == "LIST_MODELS":
                return {"status":"ok","models":SERVICE.list_models()}

            if op == "SET_MODEL":
                m = p.get("model")
                SERVICE.set_model(m)
                return {"status":"ok","model":m}

            if op == "SET_KEY":
                prov, key = p.get("provider"), p.get("key")
                SERVICE.set_key(prov, key)
                return {"status":"ok","provider":prov}

            if op == "GET_KEY":
                prov = p.get("provider")
                key  = SERVICE.get_key(prov)
                return {"status":"ok","provider":prov,"key":key}

            if op == "STASH":
                name = p.get("name")
                SERVICE.stash(name)
                return {"status":"ok","stashed":name}

            if op == "POP":
                name = p.get("name")
                SERVICE.pop(name)
                return {"status":"ok","popped":name}

            if op == "LIST_STASHES":
                return {"status":"ok","stashes":SERVICE.list_stashes()}

            if op == "CLEAR":
                SERVICE.clear()
                return {"status":"ok"}

            if op == "IMPORT_FILES":
                cnt = SERVICE.import_files(p.get("pattern",""))
                return {"status":"ok","imported":cnt}

            if op == "EXPORT_SNAPSHOT":
                fn = p.get("filename")
                SERVICE.export_snapshot(fn)
                return {"status":"ok","snapshot":fn}

            if op == "SET_PARAM":
                SERVICE.set_param(p.get("key"), p.get("value"))
                return {"status":"ok"}

            if op == "CURL":
                SERVICE.curl(p.get("tokens", []))
                return {"status":"ok"}

            if op == "PLAY":
                SERVICE.play(p.get("instructions",""))
                return {"status":"ok"}

            if op in ("QUIT","EXIT"):
                return {"status":"ok","message":"Goodbye!"}

            raise ValueError(f"Unknown command '{op}'")

        except Exception as e:
            return {"status":"error","error": str(e)}

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads      = True
    allow_reuse_address = True

def run_robodogmcp(host: str, port: int, token: str,
                   folders: list, svc: RobodogService):
    """
    Launch a threaded MCP server on (host,port) with bearer‐auth and
    hook into the provided RobodogService instance.
    """
    global TOKEN, ROOTS, SERVICE
    TOKEN   = token
    SERVICE = svc
    ROOTS   = [os.path.abspath(f) for f in folders]
    server  = ThreadedTCPServer((host, port), MCPHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
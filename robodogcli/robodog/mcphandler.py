#!/usr/bin/env python3
import os
import json
import threading
import socketserver
import fnmatch
import hashlib
import shutil
from service import RobodogService  # your existing service.py
import logging
logger = logging.getLogger('robodog.mcphandler')
ROOTS    = []
TOKEN    = None
SERVICE  = None

class MCPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        # Read the first line
        raw_first = self.rfile.readline()
        peer = self.client_address
        logger.debug(f"Connection from {peer!r}")
        if not raw_first:
            return
        first = raw_first.decode('utf-8', errors='ignore').rstrip('\r\n')
        is_http = first.upper().startswith(("GET ","POST ","OPTIONS ")) and "HTTP/" in first

        if is_http:
            self._handle_http(first)
        else:
            # raw MCP protocol
            op, _, arg = first.partition(" ")
            try:
                payload = json.loads(arg) if arg else {}
            except json.JSONDecodeError:
                return self._write_json({"status":"error","error":"Invalid JSON payload"})
            res = self._dispatch(op.upper(), payload)
            self._write_json(res)

    def _handle_http(self, first_line):
        # parse request line
        try:
            method, uri, version = first_line.split(None, 2)
        except ValueError:
            return
        headers = {}
        # read headers
        while True:
            line = self.rfile.readline().decode('utf-8', errors='ignore')
            if not line or line in ('\r\n', '\n'):
                break
            name, val = line.split(":",1)
            headers[name.lower().strip()] = val.strip()

        # CORS preflight
        if method.upper() == 'OPTIONS':
            resp = [
                "HTTP/1.1 204 No Content",
                "Access-Control-Allow-Origin: *",
                "Access-Control-Allow-Methods: POST, OPTIONS",
                "Access-Control-Allow-Headers: Content-Type, Authorization",
                "Access-Control-Max-Age: 86400",
                "Connection: close", "", ""
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            self.wfile.flush()
            return

        if method.upper() != 'POST':
            resp = [
                "HTTP/1.1 405 Method Not Allowed",
                "Access-Control-Allow-Origin: *",
                "Allow: POST, OPTIONS",
                "Content-Type: text/plain; charset=utf-8",
                "Connection: close", "", "Only POST supported\n"
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            self.wfile.flush()
            return

        # Authorization
        authz = headers.get('authorization','')
        if authz != f"Bearer {TOKEN}":
            body = json.dumps({"status":"error","error":"Authentication required"})
            resp = [
                "HTTP/1.1 401 Unauthorized",
                "Access-Control-Allow-Origin: *",
                "Content-Type: application/json; charset=utf-8",
                f"Content-Length: {len(body.encode('utf-8'))}",
                "Connection: close", "", body
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            self.wfile.flush()
            return

        # Read body
        length = int(headers.get('content-length','0'))
        raw_body = self.rfile.read(length).decode('utf-8', errors='ignore')
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
        self.wfile.flush()

    def _write_json(self, obj):
        data = json.dumps(obj) + "\n"
        self.wfile.write(data.encode('utf-8'))
        self.wfile.flush()

    def _dispatch(self, op, p):
        try:
            # --- file‐service ops ---
            if op == "HELP":
                return {"status":"ok","commands":[
                    "LIST_FILES","GET_ALL_CONTENTS","READ_FILE","UPDATE_FILE",
                    "CREATE_FILE","DELETE_FILE","APPEND_FILE","CREATE_DIR",
                    "DELETE_DIR","RENAME","MOVE","COPY_FILE","SEARCH",
                    "CHECKSUM","QUIT","EXIT"
                ]}

            if op == 'SET_ROOTS':
                roots = p.get("roots")
                if not isinstance(roots, list):
                    raise ValueError("Missing 'roots' list")
                absr = []
                for r in roots:
                    a = os.path.abspath(r)
                    if not os.path.isdir(a):
                        raise FileNotFoundError(f"Not a directory: {r}")
                    absr.append(a)
                global ROOTS
                ROOTS = absr
                return {"status":"ok","roots":ROOTS}

            if op == 'LIST_FILES':
                files = SERVICE.list_files(ROOTS)
                return {"status":"ok","files":files}

            if op == 'GET_ALL_CONTENTS':
                contents = SERVICE.get_all_contents(ROOTS)
                return {"status":"ok","contents":contents}

            if op == 'READ_FILE':
                path = p.get("path")
                if not path: raise ValueError("Missing 'path'")
                content = SERVICE.read_file(path)
                return {"status":"ok","path":path,"content":content}

            if op == 'SEARCH':
                raw = p.get("pattern", "*")
                # pass through exclude if provided, or let service use its default
                exclude = p.get("exclude", None)
                patterns = raw if isinstance(raw, list) else raw.split("|")
                recursive = p.get("recursive", True)
                root_param = p.get("root", "")
                roots = ROOTS if not root_param else [root_param]

                found = SERVICE.search_files(
                    patterns=patterns,
                    recursive=recursive,
                    roots=roots,
                    exclude_dirs=exclude
                )
                return {"status":"ok", "matches": found}

            if op == 'CHECKSUM':
                path = p.get("path")
                if not path: raise ValueError("Missing 'path'")
                cs = SERVICE.checksum(path)
                return {"status":"ok","path":path,"checksum":cs}

            # --- pass‐through RobodogService operations ---
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
                prov = p.get("provider"); key = p.get("key")
                SERVICE.set_key(prov, key)
                return {"status":"ok","provider":prov}

            if op == "GET_KEY":
                prov = p.get("provider")
                key  = SERVICE.get_key(prov)
                return {"status":"ok","provider":prov,"key":key}

            if op == "STASH":
                SERVICE.stash(p.get("name"))
                return {"status":"ok","stashed":p.get("name")}

            if op == "POP":
                SERVICE.pop(p.get("name"))
                return {"status":"ok","popped":p.get("name")}

            if op == "LIST_STASHES":
                return {"status":"ok","stashes":SERVICE.list_stashes()}

            if op == "CLEAR":
                SERVICE.clear()
                return {"status":"ok"}

            if op == "IMPORT_FILES":
                cnt = SERVICE.import_files(p.get("pattern"))
                return {"status":"ok","imported":cnt}

            if op == "EXPORT_SNAPSHOT":
                fn = p.get("filename")
                SERVICE.export_snapshot(fn)
                return {"status":"ok","snapshot":fn}

            if op == "SET_PARAM":
                SERVICE.set_param(p.get("key"), p.get("value"))
                return {"status":"ok"}

            if op == "INCLUDE":
                answer = SERVICE.include(p.get("spec"), p.get("prompt",None))
                resp = {"status":"ok"}
                if answer is not None: resp["answer"] = answer
                return resp

            if op == "CURL":
                SERVICE.curl(p.get("tokens",[]))
                return {"status":"ok"}

            if op == "PLAY":
                SERVICE.play(p.get("instructions"))
                return {"status":"ok"}

            if op in ("QUIT","EXIT"):
                return {"status":"ok","message":"Goodbye!"}

            raise ValueError(f"Unknown command '{op}'")

        except Exception as e:
            return {"status":"error","error":str(e)}

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
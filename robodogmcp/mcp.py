#!/usr/bin/env python3
import argparse
import json
import logging
import os
import shutil
import socketserver
import fnmatch
import hashlib
from pathlib import Path

# —————————————————————————————————————————————————————————————————————————————
#    Command-line parsing
# —————————————————————————————————————————————————————————————————————————————
parser = argparse.ArgumentParser(
    description="MCP file server: expose LIST, READ, UPDATE and full file manipulation over TCP/HTTP"
)
parser.add_argument('--host', default='127.0.0.1',
                    help="Host to bind to (default: 127.0.0.1)")
parser.add_argument('--port', type=int, default=2500,
                    help="TCP port (default: 2500)")
parser.add_argument('--folders', nargs='+', required=True,
                    help="One or more root folders to serve (recursive)")
args = parser.parse_args()

# Normalize and validate roots
ROOTS = []
for p in args.folders:
    absp = os.path.abspath(p)
    if not os.path.isdir(absp):
        print(f"Error: not a directory: {p}")
        exit(1)
    ROOTS.append(absp)

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s:%(message)s')

# —————————————————————————————————————————————————————————————————————————————
#    Security helper: ensure any target path lies within one of the roots
# —————————————————————————————————————————————————————————————————————————————
def is_within_roots(path: str) -> bool:
    ap = os.path.abspath(path)
    ap = os.path.realpath(ap)
    for r in ROOTS:
        rr = os.path.realpath(r)
        if os.path.commonpath([rr, ap]) == rr:
            return True
    return False

# —————————————————————————————————————————————————————————————————————————————
#    MCP protocol handler
# —————————————————————————————————————————————————————————————————————————————
class MCPHandler(socketserver.StreamRequestHandler):

    def execute_command(self, op: str, arg: str):
        """
        Take the uppercase op and optional JSON payload arg,
        and return a Python dict as the result.
        """
        payload = {}
        if arg:
            try:
                payload = json.loads(arg)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON payload: {e}")

        # Dispatch
        if op == 'HELP':
            return {
                "commands": [
                    "LIST_FILES",
                    "GET_ALL_CONTENTS",
                    "READ_FILE <json:{\"path\":\"...\"}>",
                    "UPDATE_FILE <json:{\"path\":\"...\",\"content\":\"...\"}>",
                    "CREATE_FILE <json:{\"path\":\"...\",\"content\":\"optional\"}>",
                    "DELETE_FILE <json:{\"path\":\"...\"}>",
                    "APPEND_FILE <json:{\"path\":\"...\",\"content\":\"...\"}>",
                    "CREATE_DIR <json:{\"path\":\"...\",\"mode\":493}>",
                    "DELETE_DIR <json:{\"path\":\"...\",\"recursive\":false}>",
                    "RENAME <json:{\"src\":\"...\",\"dst\":\"...\"}>",
                    "COPY_FILE <json:{\"src\":\"...\",\"dst\":\"...\"}>",
                    "STAT <json:{\"path\":\"...\"}>",
                    "SEARCH <json:{\"root\":\"...\",\"pattern\":\"*.py\",\"recursive\":true}>",
                    "CHECKSUM <json:{\"path\":\"...\"}>",
                    "QUIT / EXIT"
                ],
                "status": "ok"
            }

        elif op == 'LIST_FILES':
            files = []
            for root in ROOTS:
                for dirpath, _, filenames in os.walk(root):
                    for fn in filenames:
                        files.append(os.path.join(dirpath, fn))
            return {"files": files, "status": "ok"}

        elif op == 'GET_ALL_CONTENTS':
            contents = []
            for root in ROOTS:
                for dirpath, _, filenames in os.walk(root):
                    for fn in filenames:
                        fp = os.path.join(dirpath, fn)
                        try:
                            with open(fp, 'r', encoding='utf-8') as f:
                                data = f.read()
                        except Exception as e:
                            data = f"<error reading: {e}>"
                        contents.append({"path": fp, "content": data})
            return {"contents": contents, "status": "ok"}

        elif op == 'READ_FILE':
            path = payload.get("path")
            if not path:
                raise ValueError("Missing 'path'")
            if not is_within_roots(path):
                raise PermissionError("Path not allowed")
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            with open(path, 'r', encoding='utf-8') as f:
                data = f.read()
            return {"path": path, "content": data, "status": "ok"}

        elif op == 'UPDATE_FILE':
            path = payload.get("path")
            content = payload.get("content")
            if path is None or content is None:
                raise ValueError("Must provide 'path' and 'content'")
            if not is_within_roots(path):
                raise PermissionError("Path not allowed")
            parent = os.path.dirname(path)
            if not os.path.isdir(parent):
                raise FileNotFoundError(f"Directory does not exist: {parent}")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"path": path, "status": "ok"}

        elif op == 'CREATE_FILE':
            path = payload.get("path")
            content = payload.get("content", "")
            if not path:
                raise ValueError("Missing 'path'")
            if not is_within_roots(path):
                raise PermissionError("Path not allowed")
            parent = os.path.dirname(path)
            if not os.path.isdir(parent):
                raise FileNotFoundError(f"Directory does not exist: {parent}")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"path": path, "status": "ok"}

        elif op == 'DELETE_FILE':
            path = payload.get("path")
            if not path:
                raise ValueError("Missing 'path'")
            if not is_within_roots(path):
                raise PermissionError("Path not allowed")
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            os.remove(path)
            return {"path": path, "status": "ok"}

        elif op == 'APPEND_FILE':
            path = payload.get("path")
            content = payload.get("content", "")
            if not path:
                raise ValueError("Missing 'path'")
            if not is_within_roots(path):
                raise PermissionError("Path not allowed")
            parent = os.path.dirname(path)
            if not os.path.isdir(parent):
                raise FileNotFoundError(f"Directory does not exist: {parent}")
            with open(path, 'a', encoding='utf-8') as f:
                f.write(content)
            return {"path": path, "status": "ok"}

        elif op == 'CREATE_DIR':
            path = payload.get("path")
            mode = payload.get("mode", 0o755)
            if not path:
                raise ValueError("Missing 'path'")
            if not is_within_roots(path):
                raise PermissionError("Path not allowed")
            os.makedirs(path, mode, exist_ok=True)
            return {"path": path, "status": "ok"}

        elif op == 'DELETE_DIR':
            path = payload.get("path")
            recursive = payload.get("recursive", False)
            if not path:
                raise ValueError("Missing 'path'")
            if not is_within_roots(path):
                raise PermissionError("Path not allowed")
            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)
            return {"path": path, "status": "ok"}

        elif op in ('RENAME', 'MOVE'):
            src = payload.get("src")
            dst = payload.get("dst")
            if not src or not dst:
                raise ValueError("Must provide 'src' and 'dst'")
            if not is_within_roots(src) or not is_within_roots(dst):
                raise PermissionError("Path not allowed")
            parent = os.path.dirname(dst)
            if not os.path.isdir(parent):
                raise FileNotFoundError(f"Directory does not exist: {parent}")
            os.rename(src, dst)
            return {"src": src, "dst": dst, "status": "ok"}

        elif op == 'COPY_FILE':
            src = payload.get("src")
            dst = payload.get("dst")
            if not src or not dst:
                raise ValueError("Must provide 'src' and 'dst'")
            if not is_within_roots(src) or not is_within_roots(dst):
                raise PermissionError("Path not allowed")
            parent = os.path.dirname(dst)
            if not os.path.isdir(parent):
                raise FileNotFoundError(f"Directory does not exist: {parent}")
            shutil.copy2(src, dst)
            return {"src": src, "dst": dst, "status": "ok"}

        elif op == 'SEARCH':
            root = payload.get("root")
            pattern = payload.get("pattern", "*")
            recursive = payload.get("recursive", True)
            if not root:
                raise ValueError("Missing 'root'")
            if not is_within_roots(root):
                raise PermissionError("Root not allowed")
            matches = []
            if recursive:
                for dirpath, _, filenames in os.walk(root):
                    for fn in filenames:
                        if fnmatch.fnmatch(fn, pattern):
                            matches.append(os.path.join(dirpath, fn))
            else:
                # only this directory, no recursion
                for fn in os.listdir(root):
                    fp = os.path.join(root, fn)
                    if os.path.isfile(fp) and fnmatch.fnmatch(fn, pattern):
                        matches.append(fp)
            return {"matches": matches, "status": "ok"}

        elif op == 'CHECKSUM':
            path = payload.get("path")
            if not path:
                raise ValueError("Missing 'path'")
            if not is_within_roots(path):
                raise PermissionError("Path not allowed")
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            h = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return {"path": path, "checksum": h.hexdigest(), "status": "ok"}

        elif op in ('QUIT', 'EXIT'):
            return {"message": "Goodbye!", "status": "ok"}

        else:
            raise ValueError(f"Unknown command '{op}'")

    def send_json(self, obj: dict):
        raw = json.dumps(obj, ensure_ascii=False) + "\n"
        self.wfile.write(raw.encode('utf-8'))

    def handle(self):
        peer = self.client_address
        # Peek first line (HTTP or raw MCP?)
        line = self.rfile.readline()
        if not line:
            return

        first = line.decode('utf-8', errors='ignore').strip()
        is_http = first.upper().startswith(("GET ", "POST ", "OPTIONS ")) and "HTTP/" in first

        if is_http:
            logging.info(f"[{peer}] HTTP request: {first}")
            method, path, version = first.split(None, 2)
            headers = {}
            # read headers
            while True:
                hdr = self.rfile.readline().decode('utf-8', errors='ignore')
                if not hdr or hdr in ('\r\n','\n'):
                    break
                k,v = hdr.split(":",1)
                headers[k.lower().strip()] = v.strip()

            # CORS preflight
            if method == 'OPTIONS':
                resp = [
                    "HTTP/1.1 204 No Content",
                    "Access-Control-Allow-Origin: *",
                    "Access-Control-Allow-Methods: POST, OPTIONS",
                    "Access-Control-Allow-Headers: Content-Type",
                    "Content-Length: 0",
                    "Connection: close",
                    "", ""
                ]
                self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
                return

            if method != 'POST':
                resp = (
                    "HTTP/1.1 405 Method Not Allowed\r\n"
                    "Content-Type: text/plain; charset=utf-8\r\n"
                    "Content-Length: 23\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    "Only POST is supported\n"
                )
                self.wfile.write(resp.encode('utf-8'))
                return

            length = int(headers.get('content-length','0'))
            body = self.rfile.read(length).decode('utf-8',errors='ignore').strip()
            logging.info(f"[{peer}] HTTP POST body: {body!r}")

            try:
                parts = body.split(' ',1)
                op = parts[0].upper()
                arg = parts[1] if len(parts)>1 else None
                result = self.execute_command(op, arg)
            except Exception as e:
                logging.error(f"[{peer}] HTTP command error: {e}")
                result = {"error": str(e), "status": "error"}

            json_body = json.dumps(result, ensure_ascii=False)
            resp = [
                "HTTP/1.1 200 OK",
                "Access-Control-Allow-Origin: *",
                "Content-Type: application/json; charset=utf-8",
                f"Content-Length: {len(json_body.encode('utf-8'))}",
                "Connection: close",
                "", json_body
            ]
            self.wfile.write(("\r\n".join(resp)).encode('utf-8'))
            return

        # ————————————————————————————————————————————————————————————————
        #    Fallback to plain‐MCP/TCP loop
        # ————————————————————————————————————————————————————————————————
        logging.info(f"[{peer}] Plain MCP connection")
        self.wfile.write(b"Welcome to the MCP file server. Type HELP\n")
        while True:
            line = self.rfile.readline()
            if not line:
                break
            cmdline = line.decode('utf-8',errors='ignore').strip()
            if not cmdline:
                continue

            parts = cmdline.split(' ',1)
            op = parts[0].upper()
            arg = parts[1] if len(parts)>1 else None
            logging.info(f"[{peer}] Command: {op} {arg or ''}")

            try:
                res = self.execute_command(op, arg)
                self.send_json(res)
                if op in ('QUIT','EXIT'):
                    break
            except Exception as e:
                logging.error(f"[{peer}] {op} error: {e}")
                self.send_json({"error": str(e), "status": "error"})
        logging.info(f"[{peer}] Connection closed")


# —————————————————————————————————————————————————————————————————————————————
#    Launch threaded TCP server
# —————————————————————————————————————————————————————————————————————————————
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    server = ThreadedTCPServer((args.host, args.port), MCPHandler)
    logging.info(f"Serving MCP file server on {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down")
        server.shutdown()
        server.server_close()
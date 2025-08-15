import argparse
import json
import logging
import os
import shutil
import socketserver
import threading
import fnmatch
import hashlib
import stat as statmod

from pathlib import Path

# python mcp.py --host 0.0.0.0 --port 2500 --folders c:\projects\robodog

# —————————————————————————————————————————————————————————————————————————————
#    Command-line parsing
# —————————————————————————————————————————————————————————————————————————————
parser = argparse.ArgumentParser(
    description="MCP file server: expose LIST, READ, UPDATE and full file manipulation over TCP"
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

    def handle(self):
        peer = self.client_address
        logging.info(f"Connection from {peer}")
        try:
            self.wfile.write(b"Welcome to the MCP file server. Type HELP\n")
        except Exception:
            return

        while True:
            line = self.rfile.readline()
            if not line:
                break
            cmdline = line.decode('utf-8', errors='ignore').strip()
            if not cmdline:
                continue

            # reject accidental HTTP
            if cmdline.upper().startswith("GET ") and "HTTP/" in cmdline:
                resp = (
                    "HTTP/1.1 400 Bad Request\r\n"
                    "Content-Type: text/plain; charset=utf-8\r\n"
                    "Content-Length: 21\r\n"
                    "\r\n"
                    "MCP server only.\n"
                )
                self.wfile.write(resp.encode('utf-8'))
                break

            parts = cmdline.split(' ', 1)
            op = parts[0].upper()
            arg = parts[1] if len(parts) > 1 else None
            logging.info(f"[{peer}] Command: {op} {arg or ''}")

            try:
                if op == 'HELP':
                    self.send_json({
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
                            "SEARCH <json:{\"root\":\"...\",\"pattern\":\"*.py\"}>",
                            "CHECKSUM <json:{\"path\":\"...\"}>",
                            "QUIT / EXIT"
                        ],
                        "status": "ok"
                    })

                elif op == 'LIST_FILES':
                    files = []
                    for root in ROOTS:
                        for dirpath, _, filenames in os.walk(root):
                            for fn in filenames:
                                files.append(os.path.join(dirpath, fn))
                    self.send_json({"files": files, "status": "ok"})

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
                    self.send_json({"contents": contents, "status": "ok"})

                elif op == 'READ_FILE':
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    path = req.get("path")
                    if not path: raise ValueError("Missing 'path'")
                    if not is_within_roots(path): raise PermissionError("Path not allowed")
                    if not os.path.isfile(path): raise FileNotFoundError(path)
                    with open(path, 'r', encoding='utf-8') as f:
                        data = f.read()
                    self.send_json({"path": path, "content": data, "status": "ok"})

                elif op == 'UPDATE_FILE':
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    path = req.get("path")
                    content = req.get("content")
                    if path is None or content is None:
                        raise ValueError("Must provide 'path' and 'content'")
                    if not is_within_roots(path): raise PermissionError("Path not allowed")
                    parent = os.path.dirname(path)
                    if not os.path.isdir(parent):
                        raise FileNotFoundError(f"Directory does not exist: {parent}")
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    self.send_json({"path": path, "status": "ok"})

                elif op == 'CREATE_FILE':
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    path = req.get("path")
                    content = req.get("content", "")
                    if not path: raise ValueError("Missing 'path'")
                    if not is_within_roots(path): raise PermissionError("Path not allowed")
                    parent = os.path.dirname(path)
                    if not os.path.isdir(parent):
                        raise FileNotFoundError(f"Directory does not exist: {parent}")
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    self.send_json({"path": path, "status": "ok"})

                elif op == 'DELETE_FILE':
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    path = req.get("path")
                    if not path: raise ValueError("Missing 'path'")
                    if not is_within_roots(path): raise PermissionError("Path not allowed")
                    if not os.path.isfile(path): raise FileNotFoundError(path)
                    os.remove(path)
                    self.send_json({"path": path, "status": "ok"})

                elif op == 'APPEND_FILE':
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    path = req.get("path")
                    content = req.get("content", "")
                    if not path: raise ValueError("Missing 'path'")
                    if not is_within_roots(path): raise PermissionError("Path not allowed")
                    parent = os.path.dirname(path)
                    if not os.path.isdir(parent):
                        raise FileNotFoundError(f"Directory does not exist: {parent}")
                    with open(path, 'a', encoding='utf-8') as f:
                        f.write(content)
                    self.send_json({"path": path, "status": "ok"})

                elif op == 'CREATE_DIR':
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    path = req.get("path")
                    mode = req.get("mode", 0o755)
                    if not path: raise ValueError("Missing 'path'")
                    if not is_within_roots(path): raise PermissionError("Path not allowed")
                    os.makedirs(path, mode, exist_ok=True)
                    self.send_json({"path": path, "status": "ok"})

                elif op == 'DELETE_DIR':
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    path = req.get("path")
                    recursive = req.get("recursive", False)
                    if not path: raise ValueError("Missing 'path'")
                    if not is_within_roots(path): raise PermissionError("Path not allowed")
                    if recursive:
                        shutil.rmtree(path)
                    else:
                        os.rmdir(path)
                    self.send_json({"path": path, "status": "ok"})

                elif op in ('RENAME', 'MOVE'):
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    src = req.get("src"); dst = req.get("dst")
                    if not src or not dst:
                        raise ValueError("Must provide 'src' and 'dst'")
                    if not is_within_roots(src) or not is_within_roots(dst):
                        raise PermissionError("Path not allowed")
                    parent = os.path.dirname(dst)
                    if not os.path.isdir(parent):
                        raise FileNotFoundError(f"Directory does not exist: {parent}")
                    os.rename(src, dst)
                    self.send_json({"src": src, "dst": dst, "status": "ok"})

                elif op == 'COPY_FILE':
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    src = req.get("src"); dst = req.get("dst")
                    if not src or not dst:
                        raise ValueError("Must provide 'src' and 'dst'")
                    if not is_within_roots(src) or not is_within_roots(dst):
                        raise PermissionError("Path not allowed")
                    parent = os.path.dirname(dst)
                    if not os.path.isdir(parent):
                        raise FileNotFoundError(f"Directory does not exist: {parent}")
                    shutil.copy2(src, dst)
                    self.send_json({"src": src, "dst": dst, "status": "ok"})

               
                elif op == 'SEARCH':
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    root = req.get("root")
                    pattern = req.get("pattern", "*")
                    if not root: raise ValueError("Missing 'root'")
                    if not is_within_roots(root): raise PermissionError("Root not allowed")
                    matches = []
                    for dirpath, _, filenames in os.walk(root):
                        for fn in filenames:
                            if fnmatch.fnmatch(fn, pattern):
                                matches.append(os.path.join(dirpath, fn))
                    self.send_json({"matches": matches, "status": "ok"})

                elif op == 'CHECKSUM':
                    if not arg: raise ValueError("Missing JSON payload")
                    req = json.loads(arg)
                    path = req.get("path")
                    if not path: raise ValueError("Missing 'path'")
                    if not is_within_roots(path): raise PermissionError("Path not allowed")
                    if not os.path.isfile(path): raise FileNotFoundError(path)
                    h = hashlib.sha256()
                    with open(path, 'rb') as f:
                        for chunk in iter(lambda: f.read(8192), b''):
                            h.update(chunk)
                    self.send_json({"path": path, "checksum": h.hexdigest(), "status": "ok"})

                elif op == 'WATCH':
                    # Advanced: not implemented
                    self.send_json({"error": "WATCH not implemented", "status": "error"})

                elif op in ('QUIT', 'EXIT'):
                    logging.info(f"[{peer}] Closing connection")
                    self.wfile.write(b"Goodbye!\n")
                    break

                else:
                    raise ValueError(f"Unknown command '{op}'")

                logging.info(f"[{peer}] {op} succeeded")

            except json.JSONDecodeError:
                logging.error(f"[{peer}] {op} invalid JSON")
                self.send_json({"error": "Invalid JSON", "status": "error"})
            except Exception as e:
                logging.error(f"[{peer}] {op} error: {e}")
                self.send_json({"error": str(e), "status": "error"})

        logging.info(f"Connection closed {peer}")

    def send_json(self, obj):
        raw = json.dumps(obj, ensure_ascii=False) + "\n"
        self.wfile.write(raw.encode('utf-8'))


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
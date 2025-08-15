#!/usr/bin/env python3
import argparse
import fnmatch
import json
import logging
import os
import socketserver
import threading
import yaml

#
# —————————————————————————————————————————————————————————————————————————————
#    Load configuration & handle command‐line
# —————————————————————————————————————————————————————————————————————————————
#
parser = argparse.ArgumentParser()
parser.add_argument('--host', default='localhost',
                    help="Host or IP to bind to (default: localhost)")
parser.add_argument('--port', type=int, default=2500,
                    help="TCP port to listen on (default: 2500)")
parser.add_argument('--file', default='k2.txt',
                    help="Active file for SEND_MESSAGE (default: k2.txt)")
parser.add_argument('--group', default='g1',
                    help="Active group for GET_MESSAGES (default: g1)")
args = parser.parse_args()

# load robodogw.yaml
try:
    with open('robodogw.yaml','r') as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    print("Could not find robodogw.yaml in cwd.")
    exit(1)

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s:%(message)s')


#
# —————————————————————————————————————————————————————————————————————————————
#    Shared logic from your Flask version
# —————————————————————————————————————————————————————————————————————————————
#
def update_listof_files():
    """Return list of files in the active group, filtered by allow/deny."""
    L = []
    for group in config.get('groups', []):
        if group.get('name') != args.group:
            continue
        for rel in group.get('files', []):
            full = os.path.abspath(rel)
            low = full.lower()
            # check allow
            if not any(fnmatch.fnmatch(low, pat.lower()) for pat in config.get('allow', [])):
                continue
            # check deny
            if any(fnmatch.fnmatch(low, pat.lower()) for pat in config.get('deny', [])):
                continue
            L.append(rel)
    return L

def get_messages_text():
    out = ""
    for fn in update_listof_files():
        if not os.path.exists(fn):
            continue
        with open(fn, 'r', encoding='utf-8') as f:
            data = f.read()
        out += f"group:{args.group}\n{fn}:\n{data}\n"
    return out


#
# —————————————————————————————————————————————————————————————————————————————
#    The MCP protocol handler
# —————————————————————————————————————————————————————————————————————————————
#
class MCPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        peer = self.client_address
        logging.info(f"Connection from {peer}")

        # send welcome message
        try:
            self.wfile.write(b"Welcome to the MCP file server. Type HELP\n")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            logging.info(f"Client {peer} disconnected before greeting.")
            return

        while True:
            try:
                line = self.rfile.readline()
                if not line:
                    # client closed connection cleanly
                    break
                try:
                    cmd = line.decode('utf-8', errors='ignore').strip()
                except:
                    break
                if not cmd:
                    continue

                # detect a simple HTTP GET line and reply with 400
                if cmd.upper().startswith("GET ") and "HTTP/" in cmd:
                    http_resp = (
                        "HTTP/1.1 400 Bad Request\r\n"
                        "Content-Type: text/plain; charset=utf-8\r\n"
                        "Content-Length: 21\r\n"
                        "\r\n"
                        "MCP server only.\n"
                    )
                    try:
                        self.wfile.write(http_resp.encode('utf-8'))
                    except:
                        pass
                    break

                parts = cmd.split(' ', 1)
                op = parts[0].upper()
                arg = parts[1] if len(parts) > 1 else None

                if op == 'HELP':
                    resp = {
                        "commands": [
                            "GET_GROUPS",
                            "ACTIVATE_GROUP <name>",
                            "ACTIVATE_FILE <path>",
                            "GET_MESSAGES",
                            "SEND_MESSAGE <json>",
                            "QUIT"
                        ],
                        "status": "ok"
                    }
                    self.send_json(resp)

                elif op == 'GET_GROUPS':
                    groups = [g['name'] for g in config.get('groups', [])]
                    self.send_json({"groups": groups, "status": "ok"})

                elif op == 'ACTIVATE_GROUP':
                    if not arg:
                        raise ValueError("Missing group name")
                    grp = arg.strip()
                    if grp in [g['name'] for g in config.get('groups', [])]:
                        args.group = grp
                        self.send_json({"group": grp, "status": "ok"})
                    else:
                        self.send_json({"error": f"unknown group {grp}", "status": "error"})

                elif op == 'ACTIVATE_FILE':
                    if not arg:
                        raise ValueError("Missing file path")
                    fpath = arg.strip()
                    if os.path.isfile(fpath):
                        args.file = fpath
                        self.send_json({"file": fpath, "status": "ok"})
                    else:
                        self.send_json({"error": f"no such file {fpath}", "status": "error"})

                elif op == 'GET_MESSAGES':
                    txt = get_messages_text()
                    self.send_json({"message": txt, "status": "ok"})

                elif op == 'SEND_MESSAGE':
                    if not arg:
                        raise ValueError("Missing JSON payload")
                    try:
                        msg = json.loads(arg)
                    except json.JSONDecodeError:
                        raise ValueError("Invalid JSON")
                    with open(args.file, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                    self.send_json({"status": "ok"})

                elif op in ('QUIT', 'EXIT'):
                    try:
                        self.wfile.write(b"Goodbye!\n")
                    except:
                        pass
                    break

                else:
                    self.send_json({"error": f"unknown command '{op}'", "status": "error"})

            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # client hung up
                break

            except Exception as e:
                # application‐level error--try to report it
                try:
                    self.send_json({"error": str(e), "status": "error"})
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    break

        logging.info(f"Connection closed {peer}")

    def send_json(self, obj):
        raw = json.dumps(obj, ensure_ascii=False) + "\n"
        # let ConnectionErrors bubble up to the outer catch
        self.wfile.write(raw.encode('utf-8'))


#
# —————————————————————————————————————————————————————————————————————————————
#    Launch the threaded server
# —————————————————————————————————————————————————————————————————————————————
#
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    serv = ThreadedTCPServer((args.host, args.port), MCPHandler)
    logging.info(f"Serving MCP on {args.host}:{args.port}")
    try:
        serv.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down")
        serv.shutdown()
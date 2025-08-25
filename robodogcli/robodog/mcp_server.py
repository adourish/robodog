import os
import json
import socketserver
from service import RobodogService

ROOTS   = []
TOKEN   = None
SERVICE : RobodogService = None

class MCPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline().decode().strip()
        # HTTP CORS, auth omitted here for brevity…
        # raw MCP
        op,_,arg = line.partition(" ")
        op = op.upper()
        p   = json.loads(arg) if arg else {}
        try:
            res = self.dispatch(op,p)
        except Exception as e:
            res = {"status":"error","error":str(e)}
        self.wfile.write((json.dumps(res)+"\n").encode())

    def dispatch(self, op, p):
        svc=SERVICE
        if op=="HELP":
            return {"commands": ["LIST_FILES","GET_ALL_CONTENTS",
                                 "READ_FILE","UPDATE_FILE","CREATE_FILE",
                                 "DELETE_FILE","APPEND_FILE","CREATE_DIR",
                                 "DELETE_DIR","RENAME","COPY_FILE",
                                 "SEARCH","CHECKSUM"], "status":"ok"}
        if op=="SET_ROOTS":
            roots=[os.path.abspath(r) for r in p["roots"]]
            for r in roots:
                if not os.path.isdir(r):
                    raise FileNotFoundError(r)
            global ROOTS
            ROOTS=roots
            return {"status":"ok","roots":ROOTS}

        if op=="LIST_FILES":
            return {"status":"ok","files": svc.list_files(ROOTS)}

        if op=="GET_ALL_CONTENTS":
            return {"status":"ok","contents": svc.get_all_contents(ROOTS)}

        if op=="READ_FILE":
            return {"status":"ok","path":p["path"],"content": svc.read_file(p["path"])}

        if op=="UPDATE_FILE":
            svc.update_file(p["path"], p["content"])
            return {"status":"ok","path":p["path"]}

        if op=="CREATE_FILE":
            svc.create_file(p["path"], p.get("content",""))
            return {"status":"ok","path":p["path"]}

        if op=="DELETE_FILE":
            svc.delete_file(p["path"])
            return {"status":"ok","path":p["path"]}

        if op=="APPEND_FILE":
            svc.append_file(p["path"], p.get("content",""))
            return {"status":"ok","path":p["path"]}

        if op=="CREATE_DIR":
            svc.create_dir(p["path"], p.get("mode",0o755))
            return {"status":"ok","path":p["path"]}

        if op=="DELETE_DIR":
            svc.delete_dir(p["path"], p.get("recursive",False))
            return {"status":"ok","path":p["path"]}

        if op in ("RENAME","MOVE"):
            svc.rename(p["src"], p["dst"])
            return {"status":"ok","src":p["src"],"dst":p["dst"]}

        if op=="COPY_FILE":
            svc.copy_file(p["src"], p["dst"])
            return {"status":"ok","src":p["src"],"dst":p["dst"]}

        if op=="SEARCH":
            m = svc.search(ROOTS, p.get("pattern","*"), p.get("recursive",True))
            return {"status":"ok","matches":m}

        if op=="CHECKSUM":
            cs = svc.checksum(p["path"])
            return {"status":"ok","path":p["path"],"checksum":cs}

        raise ValueError(f"Unknown op: {op}")

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads    = True
    allow_reuse_address = True

def run_mcp_server(host, port, token, folders, svc:RobodogService):
    global TOKEN, ROOTS, SERVICE
    TOKEN   = token
    ROOTS   = [os.path.abspath(f) for f in folders]
    SERVICE = svc
    srv = ThreadedTCPServer((host,port), MCPHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv
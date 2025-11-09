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
import ssl

try:
    from .service import RobodogService
except ImportError:
    from service import RobodogService

logger = logging.getLogger('robodog.mcphandler')

ROOTS   = []
TOKEN   = None
SERVICE = None

def _is_path_allowed(path: str) -> bool:
    """
    Ensure the given path is within one of the allowed ROOTS.
    """
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
                    "CHECKSUM","TODO","TODO_LIST","TODO_ADD","TODO_UPDATE",
                    "TODO_DELETE","TODO_STATS","TODO_FILES","TODO_CREATE",
                    "MAP_SCAN","MAP_FIND","MAP_CONTEXT","MAP_SUMMARY",
                    "MAP_USAGES","MAP_SAVE","MAP_LOAD","MAP_INDEX",
                    "ANALYZE_CALLGRAPH","ANALYZE_IMPACT","ANALYZE_DEPS","ANALYZE_STATS",
                    "CASCADE_RUN",
                    "INCLUDE","CURL","PLAY","QUIT","EXIT"
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
                if not path:
                    raise ValueError("Missing 'path'")
                if not _is_path_allowed(path):
                    raise PermissionError("Access denied")
                data = SERVICE.read_file(path)
                return {"status":"ok","path":path,"content":data}

            if op == "UPDATE_FILE":
                path = p.get("path") or ""
                if not path:
                    raise ValueError("Missing 'path'")
                if not _is_path_allowed(path):
                    raise PermissionError("Access denied")
                content = p.get("content","")
                if not os.path.exists(path):
                    SERVICE.create_file(path, content)
                else:
                    SERVICE.update_file(path, content)
                return {"status":"ok","path":path}

            if op == "CREATE_FILE":
                path = p.get("path") or ""
                content = p.get("content","")
                if not path:
                    raise ValueError("Missing 'path'")
                if not _is_path_allowed(path):
                    raise PermissionError("Access denied")
                SERVICE.create_file(path, content)
                return {"status":"ok","path":path}

            if op == "DELETE_FILE":
                path = p.get("path") or ""
                if not path:
                    raise ValueError("Missing 'path'")
                if not _is_path_allowed(path):
                    raise PermissionError("Access denied")
                SERVICE.delete_file(path)
                return {"status":"ok","path":path}

            if op == "APPEND_FILE":
                path = p.get("path") or ""
                content = p.get("content","")
                if not path:
                    raise ValueError("Missing 'path'")
                if not _is_path_allowed(path):
                    raise PermissionError("Access denied")
                SERVICE.append_file(path, content)
                return {"status":"ok","path":path}

            if op == "CREATE_DIR":
                path = p.get("path") or ""
                mode = p.get("mode", 0o755)
                if not path:
                    raise ValueError("Missing 'path'")
                if not _is_path_allowed(path):
                    raise PermissionError("Access denied")
                SERVICE.create_dir(path, mode)
                return {"status":"ok","path":path}

            if op == "DELETE_DIR":
                path = p.get("path") or ""
                rec  = bool(p.get("recursive", False))
                if not path:
                    raise ValueError("Missing 'path'")
                if not _is_path_allowed(path):
                    raise PermissionError("Access denied")
                SERVICE.delete_dir(path, rec)
                return {"status":"ok","path":path}

            if op in ("RENAME","MOVE"):
                src = p.get("src") or p.get("path")
                dst = p.get("dst") or p.get("dest")
                if not src or not dst:
                    raise ValueError("Missing 'src' or 'dst'")
                if not _is_path_allowed(src) or not _is_path_allowed(dst):
                    raise PermissionError("Access denied")
                SERVICE.rename(src, dst)
                return {"status":"ok","src":src,"dst":dst}

            if op == "COPY_FILE":
                src = p.get("src")
                dst = p.get("dst")
                if not src or not dst:
                    raise ValueError("Missing 'src' or 'dst'")
                if not _is_path_allowed(src) or not _is_path_allowed(dst):
                    raise PermissionError("Access denied")
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
                if not path:
                    raise ValueError("Missing 'path'")
                if not _is_path_allowed(path):
                    raise PermissionError("Access denied")
                cs = SERVICE.checksum(path)
                return {"status":"ok","path":path,"checksum":cs}

            # --- todo ---
            if op == "TODO":
                SERVICE.todo.run_next_task(SERVICE)
                return {"status":"ok"}

            if op == "LIST_TODO_TASKS":
                SERVICE.todo._load_all()
                tasks = SERVICE.todo._tasks
                return {"status":"ok","tasks":tasks}
            
            if op == "TODO_LIST":
                # List tasks with optional filtering
                path = p.get("path")
                status = p.get("status")
                tasks = SERVICE.todo_mgr.list_tasks(path, status)
                return {"status":"ok","tasks":tasks}
            
            if op == "TODO_ADD":
                # Add a new task with three-bracket format
                desc = p.get("description")
                if not desc:
                    raise ValueError("Missing 'description'")
                path = p.get("path")
                plan_status = p.get("plan_status", ' ')
                llm_status = p.get("llm_status", ' ')
                commit_status = p.get("commit_status", ' ')
                priority = p.get("priority")
                tags = p.get("tags", [])
                include = p.get("include")
                plan_spec = p.get("plan_spec")
                result = SERVICE.todo_mgr.add_task(desc, path, plan_status, llm_status, 
                                                   commit_status, priority, tags, include, plan_spec)
                return {"status":"ok","task":result}
            
            if op == "TODO_UPDATE":
                # Update task status for a specific stage
                path = p.get("path")
                line_num = p.get("line_number")
                new_status = p.get("new_status")
                stage = p.get("stage", 'plan')  # Default to plan stage
                if not path or not line_num or not new_status:
                    raise ValueError("Missing 'path', 'line_number', or 'new_status'")
                result = SERVICE.todo_mgr.update_task_status(path, line_num, new_status, stage)
                return {"status":"ok","task":result}
            
            if op == "TODO_DELETE":
                # Delete a task
                path = p.get("path")
                line_num = p.get("line_number")
                if not path or not line_num:
                    raise ValueError("Missing 'path' or 'line_number'")
                result = SERVICE.todo_mgr.delete_task(path, line_num)
                return {"status":"ok","deleted":result}
            
            if op == "TODO_STATS":
                # Get todo statistics
                stats = SERVICE.todo_mgr.get_statistics()
                return {"status":"ok","statistics":stats}
            
            if op == "TODO_FILES":
                # Find all todo.md files
                files = SERVICE.todo_mgr.find_todo_files()
                return {"status":"ok","files":files}
            
            if op == "TODO_CREATE":
                # Create a new todo.md file
                path = p.get("path")
                created_path = SERVICE.todo_mgr.create_todo_file(path)
                return {"status":"ok","path":created_path}
            
            # --- code map ---
            if op == "MAP_SCAN":
                # Scan codebase and create map
                extensions = p.get("extensions")
                file_maps = SERVICE.code_mapper.scan_codebase(extensions)
                return {
                    "status": "ok",
                    "file_count": len(file_maps),
                    "class_count": len(SERVICE.code_mapper.index['classes']),
                    "function_count": len(SERVICE.code_mapper.index['functions'])
                }
            
            if op == "MAP_FIND":
                # Find definition of class or function
                name = p.get("name")
                if not name:
                    raise ValueError("Missing 'name'")
                results = SERVICE.code_mapper.find_definition(name)
                return {"status": "ok", "results": results}
            
            if op == "MAP_CONTEXT":
                # Get context for a task
                task_desc = p.get("task_description")
                if not task_desc:
                    raise ValueError("Missing 'task_description'")
                patterns = p.get("include_patterns")
                context = SERVICE.code_mapper.get_context_for_task(task_desc, patterns)
                return {"status": "ok", "context": context}
            
            if op == "MAP_SUMMARY":
                # Get file summary
                file_path = p.get("file_path")
                if not file_path:
                    raise ValueError("Missing 'file_path'")
                summary = SERVICE.code_mapper.get_file_summary(file_path)
                if not summary:
                    raise ValueError(f"File not found in map: {file_path}")
                return {"status": "ok", "summary": summary}
            
            if op == "MAP_USAGES":
                # Find module usages
                module = p.get("module")
                if not module:
                    raise ValueError("Missing 'module'")
                files = SERVICE.code_mapper.find_usages(module)
                return {"status": "ok", "module": module, "files": files}
            
            if op == "MAP_SAVE":
                # Save map to file
                output_path = p.get("output_path", "codemap.json")
                SERVICE.code_mapper.save_map(output_path)
                return {"status": "ok", "path": output_path}
            
            if op == "MAP_LOAD":
                # Load map from file
                input_path = p.get("input_path", "codemap.json")
                SERVICE.code_mapper.load_map(input_path)
                return {
                    "status": "ok",
                    "path": input_path,
                    "file_count": len(SERVICE.code_mapper.file_maps)
                }
            
            if op == "MAP_INDEX":
                # Get index statistics
                return {
                    "status": "ok",
                    "index": {
                        "classes": {k: len(v) for k, v in SERVICE.code_mapper.index['classes'].items()},
                        "functions": {k: len(v) for k, v in SERVICE.code_mapper.index['functions'].items()},
                        "imports": {k: len(v) for k, v in SERVICE.code_mapper.index['imports'].items()}
                    },
                    "total_files": len(SERVICE.code_mapper.file_maps)
                }
            
            # --- Advanced Analysis ---
            if op == "ANALYZE_CALLGRAPH":
                # Build call graph
                if not hasattr(SERVICE, 'analyzer'):
                    from advanced_analysis import AdvancedCodeAnalyzer
                    SERVICE.analyzer = AdvancedCodeAnalyzer(SERVICE.code_mapper)
                
                call_graph = SERVICE.analyzer.build_call_graph()
                return {
                    "status": "ok",
                    "function_count": len(call_graph.functions),
                    "total_calls": sum(len(calls) for calls in call_graph.functions.values())
                }
            
            if op == "ANALYZE_IMPACT":
                # Analyze impact of changing a function
                if not hasattr(SERVICE, 'analyzer'):
                    from advanced_analysis import AdvancedCodeAnalyzer
                    SERVICE.analyzer = AdvancedCodeAnalyzer(SERVICE.code_mapper)
                
                function_name = p.get("function_name")
                if not function_name:
                    raise ValueError("Missing 'function_name'")
                
                impact = SERVICE.analyzer.find_impact(function_name)
                return {
                    "status": "ok",
                    "impact": impact
                }
            
            if op == "ANALYZE_DEPS":
                # Analyze file dependencies
                if not hasattr(SERVICE, 'analyzer'):
                    from advanced_analysis import AdvancedCodeAnalyzer
                    SERVICE.analyzer = AdvancedCodeAnalyzer(SERVICE.code_mapper)
                
                file_path = p.get("file_path")
                if not file_path:
                    raise ValueError("Missing 'file_path'")
                
                deps = SERVICE.analyzer.find_dependencies(file_path)
                return {
                    "status": "ok",
                    "dependencies": {
                        "file_path": deps.file_path,
                        "imports": deps.imports,
                        "internal": deps.internal_deps,
                        "external": deps.external_deps
                    }
                }
            
            if op == "ANALYZE_STATS":
                # Get codebase statistics
                if not hasattr(SERVICE, 'analyzer'):
                    from advanced_analysis import AdvancedCodeAnalyzer
                    SERVICE.analyzer = AdvancedCodeAnalyzer(SERVICE.code_mapper)
                
                stats = SERVICE.analyzer.get_stats()
                return {
                    "status": "ok",
                    "stats": stats
                }
            
            # --- Cascade Mode ---
            if op == "CASCADE_RUN":
                # Run task with cascade mode
                if not hasattr(SERVICE, 'cascade_engine'):
                    from cascade_mode import CascadeEngine
                    SERVICE.cascade_engine = CascadeEngine(SERVICE, SERVICE.code_mapper, SERVICE.file_service)
                
                task = p.get("task")
                context = p.get("context", "")
                
                if not task:
                    raise ValueError("Missing 'task'")
                
                import asyncio
                result = asyncio.run(SERVICE.cascade_engine.execute_cascade(task, context))
                return {
                    "status": "ok",
                    "result": result
                }

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
                if prompt is None:
                    raise ValueError("Missing 'prompt'")
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
        except PermissionError as pe:
            return {"status":"error","error": str(pe)}
        except Exception as e:
            return {"status":"error","error": str(e)}

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads      = True
    allow_reuse_address = True

class SSLThreadedTCPServer(ThreadedTCPServer):
    def __init__(self, server_address, RequestHandlerClass, certfile=None, keyfile=None, ssl_context=None, **kwargs):
        self.certfile = certfile
        self.keyfile = keyfile
        self.ssl_context = ssl_context
        super().__init__(server_address, RequestHandlerClass, **kwargs)

    def get_request(self):
        newsock, sock = super().get_request()
        if self.ssl_context:
            newsock = self.ssl_context.wrap_socket(newsock, server_side=True)
        return newsock, sock

def run_robodogmcp(host: str, port: int, token: str,
                   folders: list, svc: RobodogService, cert: str = None, key: str = None):
    """
    Launch a threaded MCP server on (host,port) with bearer‐auth and
    hook into the provided RobodogService instance.
    Supports SSL if cert and key files are provided.
    """
    global TOKEN, ROOTS, SERVICE
    TOKEN   = token
    SERVICE = svc
    ROOTS   = [os.path.abspath(f) for f in folders]
    
    if cert and key:
        # Create SSL context for server-side
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=cert, keyfile=key)
        # Use custom SSL server
        server = SSLThreadedTCPServer((host, port), MCPHandler, certfile=cert, keyfile=key, ssl_context=ssl_context)
        logger.info("SSL MCP server started with cert: %s, key: %s", cert, key)
    else:
        # Plain TCP server
        server = ThreadedTCPServer((host, port), MCPHandler)
        logger.info("Plain MCP server started (no SSL)")
    
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

# original file length: 256 lines
# updated file length: 312 lines
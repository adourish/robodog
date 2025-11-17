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
                    "AMPLENOTE_AUTH","AMPLENOTE_LIST","AMPLENOTE_CREATE","AMPLENOTE_ADD",
                    "AMPLENOTE_TASK","AMPLENOTE_LINK","AMPLENOTE_UPLOAD",
                    "TODOIST_AUTH","TODOIST_PROJECTS","TODOIST_TASKS","TODOIST_CREATE",
                    "TODOIST_COMPLETE","TODOIST_PROJECT","TODOIST_LABELS","TODOIST_COMMENT",
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
            
            # --- Amplenote Integration ---
            if op == "AMPLENOTE_AUTH":
                if not SERVICE.amplenote:
                    raise ValueError("Amplenote service not configured")
                redirect_uri = p.get("redirect_uri", "http://localhost:8080/callback")
                success = SERVICE.amplenote.authenticate(redirect_uri)
                return {"status":"ok" if success else "error","authenticated":success}
            
            if op == "AMPLENOTE_LIST":
                if not SERVICE.amplenote or not SERVICE.amplenote.is_authenticated():
                    raise ValueError("Not authenticated with Amplenote")
                since = p.get("since")
                notes = SERVICE.amplenote.list_notes(since=since)
                return {"status":"ok","notes":notes}
            
            if op == "AMPLENOTE_CREATE":
                if not SERVICE.amplenote or not SERVICE.amplenote.is_authenticated():
                    raise ValueError("Not authenticated with Amplenote")
                name = p.get("name")
                if not name:
                    raise ValueError("Missing 'name'")
                tags = p.get("tags")
                note = SERVICE.amplenote.create_note(name, tags=tags)
                return {"status":"ok","note":note}
            
            if op == "AMPLENOTE_ADD":
                if not SERVICE.amplenote or not SERVICE.amplenote.is_authenticated():
                    raise ValueError("Not authenticated with Amplenote")
                note_uuid = p.get("note_uuid")
                content = p.get("content")
                if not note_uuid or not content:
                    raise ValueError("Missing 'note_uuid' or 'content'")
                content_type = p.get("content_type", "paragraph")
                SERVICE.amplenote.insert_content(note_uuid, content, content_type)
                return {"status":"ok"}
            
            if op == "AMPLENOTE_TASK":
                if not SERVICE.amplenote or not SERVICE.amplenote.is_authenticated():
                    raise ValueError("Not authenticated with Amplenote")
                note_uuid = p.get("note_uuid")
                task_text = p.get("task_text")
                if not note_uuid or not task_text:
                    raise ValueError("Missing 'note_uuid' or 'task_text'")
                due = p.get("due")
                flags = p.get("flags")
                SERVICE.amplenote.insert_task(note_uuid, task_text, due=due, flags=flags)
                return {"status":"ok"}
            
            if op == "AMPLENOTE_LINK":
                if not SERVICE.amplenote or not SERVICE.amplenote.is_authenticated():
                    raise ValueError("Not authenticated with Amplenote")
                note_uuid = p.get("note_uuid")
                url = p.get("url")
                link_text = p.get("link_text")
                if not note_uuid or not url or not link_text:
                    raise ValueError("Missing 'note_uuid', 'url', or 'link_text'")
                description = p.get("description")
                SERVICE.amplenote.insert_link(note_uuid, url, link_text, description=description)
                return {"status":"ok"}
            
            if op == "AMPLENOTE_UPLOAD":
                if not SERVICE.amplenote or not SERVICE.amplenote.is_authenticated():
                    raise ValueError("Not authenticated with Amplenote")
                note_uuid = p.get("note_uuid")
                file_path = p.get("file_path")
                if not note_uuid or not file_path:
                    raise ValueError("Missing 'note_uuid' or 'file_path'")
                if not _is_path_allowed(file_path):
                    raise PermissionError("Access denied")
                src_url = SERVICE.amplenote.upload_media(note_uuid, file_path)
                return {"status":"ok","src_url":src_url}
            
            # --- Todoist Integration ---
            if op == "TODOIST_AUTH":
                if not SERVICE.todoist:
                    raise ValueError("Todoist service not configured")
                redirect_uri = p.get("redirect_uri", "http://localhost:8080")
                success = SERVICE.todoist.authenticate(redirect_uri)
                return {"status":"ok" if success else "error","authenticated":success}
            
            if op == "TODOIST_PROJECTS":
                if not SERVICE.todoist or not SERVICE.todoist.is_authenticated():
                    raise ValueError("Not authenticated with Todoist")
                projects = SERVICE.todoist.get_projects()
                return {"status":"ok","projects":projects}
            
            if op == "TODOIST_TASKS":
                if not SERVICE.todoist or not SERVICE.todoist.is_authenticated():
                    raise ValueError("Not authenticated with Todoist")
                project_id = p.get("project_id")
                label = p.get("label")
                filter_query = p.get("filter")
                tasks = SERVICE.todoist.get_tasks(project_id=project_id, label=label, filter_query=filter_query)
                return {"status":"ok","tasks":tasks}
            
            if op == "TODOIST_CREATE":
                if not SERVICE.todoist or not SERVICE.todoist.is_authenticated():
                    raise ValueError("Not authenticated with Todoist")
                content = p.get("content")
                if not content:
                    raise ValueError("Missing 'content'")
                description = p.get("description")
                project_id = p.get("project_id")
                due_string = p.get("due_string")
                priority = p.get("priority", 1)
                labels = p.get("labels")
                task = SERVICE.todoist.create_task(
                    content=content,
                    description=description,
                    project_id=project_id,
                    due_string=due_string,
                    priority=priority,
                    labels=labels
                )
                return {"status":"ok","task":task}
            
            if op == "TODOIST_COMPLETE":
                if not SERVICE.todoist or not SERVICE.todoist.is_authenticated():
                    raise ValueError("Not authenticated with Todoist")
                task_id = p.get("task_id")
                if not task_id:
                    raise ValueError("Missing 'task_id'")
                SERVICE.todoist.close_task(task_id)
                return {"status":"ok"}
            
            if op == "TODOIST_PROJECT":
                if not SERVICE.todoist or not SERVICE.todoist.is_authenticated():
                    raise ValueError("Not authenticated with Todoist")
                name = p.get("name")
                if not name:
                    raise ValueError("Missing 'name'")
                color = p.get("color")
                is_favorite = p.get("is_favorite", False)
                project = SERVICE.todoist.create_project(name, color=color, is_favorite=is_favorite)
                return {"status":"ok","project":project}
            
            if op == "TODOIST_LABELS":
                if not SERVICE.todoist or not SERVICE.todoist.is_authenticated():
                    raise ValueError("Not authenticated with Todoist")
                labels = SERVICE.todoist.get_labels()
                return {"status":"ok","labels":labels}
            
            if op == "TODOIST_COMMENT":
                if not SERVICE.todoist or not SERVICE.todoist.is_authenticated():
                    raise ValueError("Not authenticated with Todoist")
                task_id = p.get("task_id")
                content = p.get("content")
                if not task_id or not content:
                    raise ValueError("Missing 'task_id' or 'content'")
                comment = SERVICE.todoist.create_comment(content, task_id=task_id)
                return {"status":"ok","comment":comment}
            
            # ==================== Google API Operations ====================
            
            if op == "GOOGLE_AUTH":
                # Authenticate with Google
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                result = SERVICE.google.authenticate()
                return {"status":"ok","authenticated":True,"result":result}
            
            if op == "GOOGLE_SET_TOKEN":
                # Set Google access token manually
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                token = p.get("token")
                refresh_token = p.get("refresh_token")
                if not token:
                    raise ValueError("Missing 'token'")
                SERVICE.google.set_access_token(token, refresh_token)
                return {"status":"ok","authenticated":True}
            
            if op == "GOOGLE_STATUS":
                # Check Google authentication status
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    return {"status":"ok","authenticated":False,"available":False}
                is_auth = SERVICE.google.is_authenticated()
                token = SERVICE.google.get_access_token()
                return {"status":"ok","authenticated":is_auth,"has_token":bool(token),"available":True}
            
            # --- Google Docs Operations ---
            
            if op == "GDOC_CREATE":
                # Create a new Google Doc
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google. Run GOOGLE_AUTH first.")
                title = p.get("title")
                content = p.get("content", "")
                if not title:
                    raise ValueError("Missing 'title'")
                doc = SERVICE.google.create_document(title, content)
                return {"status":"ok","document":doc}
            
            if op == "GDOC_GET":
                # Get a Google Doc
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                doc_id = p.get("document_id") or p.get("doc_id")
                if not doc_id:
                    raise ValueError("Missing 'document_id'")
                doc = SERVICE.google.get_document(doc_id)
                return {"status":"ok","document":doc}
            
            if op == "GDOC_READ":
                # Read text content from a Google Doc
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                doc_id = p.get("document_id") or p.get("doc_id")
                if not doc_id:
                    raise ValueError("Missing 'document_id'")
                text = SERVICE.google.read_document_text(doc_id)
                return {"status":"ok","document_id":doc_id,"text":text}
            
            if op == "GDOC_UPDATE":
                # Update a Google Doc
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                doc_id = p.get("document_id") or p.get("doc_id")
                content = p.get("content")
                insert_index = p.get("insert_index", 1)
                if not doc_id or not content:
                    raise ValueError("Missing 'document_id' or 'content'")
                result = SERVICE.google.update_document(doc_id, content, insert_index)
                return {"status":"ok","document_id":doc_id,"result":result}
            
            if op == "GDOC_DELETE":
                # Delete a Google Doc (move to trash)
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                doc_id = p.get("document_id") or p.get("doc_id")
                if not doc_id:
                    raise ValueError("Missing 'document_id'")
                result = SERVICE.google.delete_document(doc_id)
                return {"status":"ok","document_id":doc_id,"deleted":True}
            
            # --- Gmail Operations ---
            
            if op == "GMAIL_SEND":
                # Send an email via Gmail
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                to = p.get("to")
                subject = p.get("subject")
                body = p.get("body")
                is_html = p.get("is_html", False)
                cc = p.get("cc")
                bcc = p.get("bcc")
                if not to or not subject or not body:
                    raise ValueError("Missing 'to', 'subject', or 'body'")
                result = SERVICE.google.send_email(to, subject, body, is_html, cc, bcc)
                return {"status":"ok","email":result}
            
            if op == "GMAIL_LIST":
                # List emails
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                max_results = p.get("max_results", 10)
                query = p.get("query", "")
                emails = SERVICE.google.list_emails(max_results, query)
                return {"status":"ok","emails":emails}
            
            if op == "GMAIL_GET":
                # Get a specific email
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                message_id = p.get("message_id")
                if not message_id:
                    raise ValueError("Missing 'message_id'")
                email = SERVICE.google.get_email(message_id)
                return {"status":"ok","email":email}
            
            if op == "GMAIL_DRAFT":
                # Create an email draft
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                to = p.get("to")
                subject = p.get("subject")
                body = p.get("body")
                is_html = p.get("is_html", False)
                cc = p.get("cc")
                bcc = p.get("bcc")
                if not to or not subject or not body:
                    raise ValueError("Missing 'to', 'subject', or 'body'")
                draft = SERVICE.google.create_draft(to, subject, body, is_html, cc, bcc)
                return {"status":"ok","draft":draft}
            
            if op == "GMAIL_DELETE_DRAFT":
                # Delete an email draft
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                draft_id = p.get("draft_id")
                if not draft_id:
                    raise ValueError("Missing 'draft_id'")
                result = SERVICE.google.delete_draft(draft_id)
                return {"status":"ok","draft_id":draft_id,"deleted":True}
            
            # ==================== Google Calendar Operations ====================
            
            # --- Calendar Management ---
            
            if op == "GCAL_LIST":
                # List all calendars
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                calendars = SERVICE.google.list_calendars()
                return {"status":"ok","calendars":calendars}
            
            if op == "GCAL_CREATE":
                # Create a new calendar
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                summary = p.get("summary")
                if not summary:
                    raise ValueError("Missing 'summary'")
                description = p.get("description", "")
                timezone = p.get("timezone", "America/New_York")
                calendar = SERVICE.google.create_calendar(summary, description, timezone)
                return {"status":"ok","calendar":calendar}
            
            if op == "GCAL_GET":
                # Get calendar details
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                calendar_id = p.get("calendar_id")
                if not calendar_id:
                    raise ValueError("Missing 'calendar_id'")
                calendar = SERVICE.google.get_calendar(calendar_id)
                return {"status":"ok","calendar":calendar}
            
            if op == "GCAL_UPDATE":
                # Update calendar
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                calendar_id = p.get("calendar_id")
                if not calendar_id:
                    raise ValueError("Missing 'calendar_id'")
                summary = p.get("summary")
                description = p.get("description")
                timezone = p.get("timezone")
                calendar = SERVICE.google.update_calendar(calendar_id, summary, description, timezone)
                return {"status":"ok","calendar":calendar}
            
            if op == "GCAL_DELETE":
                # Delete calendar
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                calendar_id = p.get("calendar_id")
                if not calendar_id:
                    raise ValueError("Missing 'calendar_id'")
                result = SERVICE.google.delete_calendar(calendar_id)
                return {"status":"ok","calendar_id":calendar_id,"deleted":True}
            
            if op == "GCAL_SEARCH":
                # Search calendars (wildcard)
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                query = p.get("query", "")
                result = SERVICE.google.search_calendars(query)
                return {"status":"ok","calendars":result}
            
            # --- Calendar Events ---
            
            if op == "GEVENT_LIST":
                # List events from a calendar
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                calendar_id = p.get("calendar_id", "primary")
                max_results = p.get("max_results", 10)
                time_min = p.get("time_min")
                time_max = p.get("time_max")
                query = p.get("query")
                events = SERVICE.google.list_events(calendar_id, max_results, time_min, time_max, query)
                return {"status":"ok","events":events}
            
            if op == "GEVENT_CREATE":
                # Create a calendar event
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                calendar_id = p.get("calendar_id", "primary")
                summary = p.get("summary")
                if not summary:
                    raise ValueError("Missing 'summary'")
                description = p.get("description", "")
                start_time = p.get("start_time")
                end_time = p.get("end_time")
                if not start_time or not end_time:
                    raise ValueError("Missing 'start_time' or 'end_time'")
                location = p.get("location", "")
                attendees = p.get("attendees")
                event = SERVICE.google.create_event(calendar_id, summary, description, start_time, end_time, location, attendees)
                return {"status":"ok","event":event}
            
            if op == "GEVENT_GET":
                # Get event details
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                calendar_id = p.get("calendar_id", "primary")
                event_id = p.get("event_id")
                if not event_id:
                    raise ValueError("Missing 'event_id'")
                event = SERVICE.google.get_event(calendar_id, event_id)
                return {"status":"ok","event":event}
            
            if op == "GEVENT_UPDATE":
                # Update an event
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                calendar_id = p.get("calendar_id", "primary")
                event_id = p.get("event_id")
                if not event_id:
                    raise ValueError("Missing 'event_id'")
                summary = p.get("summary")
                description = p.get("description")
                start_time = p.get("start_time")
                end_time = p.get("end_time")
                location = p.get("location")
                event = SERVICE.google.update_event(calendar_id, event_id, summary, description, start_time, end_time, location)
                return {"status":"ok","event":event}
            
            if op == "GEVENT_DELETE":
                # Delete an event
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                calendar_id = p.get("calendar_id", "primary")
                event_id = p.get("event_id")
                if not event_id:
                    raise ValueError("Missing 'event_id'")
                result = SERVICE.google.delete_event(calendar_id, event_id)
                return {"status":"ok","event_id":event_id,"deleted":True}
            
            if op == "GEVENT_SEARCH":
                # Search events (wildcard)
                if not hasattr(SERVICE, 'google') or not SERVICE.google:
                    raise ValueError("Google service not initialized")
                if not SERVICE.google.is_authenticated():
                    raise ValueError("Not authenticated with Google")
                calendar_id = p.get("calendar_id", "primary")
                query = p.get("query", "")
                max_results = p.get("max_results", 25)
                events = SERVICE.google.search_events(calendar_id, query, max_results)
                return {"status":"ok","events":events}

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
Here are all of the top-level functions and methods defined in robodogcli/robodog/todo.py:

1. Change (Pydantic model)  
2. ChangesList (Pydantic RootModel)  

Class TodoService:  
- __init__(self, roots: List[str])  
- _parse_base_dir(self)  
- _find_files(self)  
- _load_allb(self)  
- _load_all(self)  
- _watch_loop(self)  
- _write_file(fn: str, file_lines: List[str]) [@staticmethod]  
- _format_summary(indent: str, start: str, end: Optional[str], know: Optional[int], prompt: Optional[int], total: Optional[int]) [@staticmethod]  
- _start_task(task: dict, file_lines_map: dict) [@staticmethod]  
- _complete_task(task: dict, file_lines_map: dict) [@staticmethod]  
- run_next_task(self, svc)  
- _get_token_count(self, text: str)  
- _gather_include_knowledge(self, include: dict, svc)  
- _resolve_path(self, frag: str)  
- _process_one(self, task: dict, svc, file_lines_map: dict)  

That covers every top-level function or method in that module.
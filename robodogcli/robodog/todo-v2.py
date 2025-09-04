Here are all of the standalone function/method definitions in `todo.py` (the `TodoService` class and its helpers):

• __init__(self, roots: List[str])  
• _parse_base_dir(self) -> Optional[str]  
• _find_files(self) -> List[str]  
• _load_all(self)  
• _load_allb(self)                    (alternate loader)  
• _watch_loop(self)  
• _write_file(fn: str, file_lines: List[str])      (static)  
• _format_summary(indent: str, start: str, end: Optional[str], know: Optional[int], prompt: Optional[int], total: Optional[int]) -> str  (static)  
• _start_task(task: dict, file_lines_map: dict)   (static)  
• _complete_task(task: dict, file_lines_map: dict) (static)  
• run_next_task(self, svc)  
• _get_token_count(self, text: str) -> int  
• _gather_include_knowledge(self, include: dict, svc) -> str  
• _resolve_path(self, frag: str) -> Optional[Path]  
• _process_one(self, task: dict, svc, file_lines_map: dict)
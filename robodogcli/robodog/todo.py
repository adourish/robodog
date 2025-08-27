import os, re
from datetime import datetime
from pathlib import Path

class TodoService:
    def __init__(self, roots, work_path="work.txt"):
        self.roots = roots
        self.todo_path = self._find_todo()
        self.work_path = work_path
        self.tasks = []
        self._load_todos()

    def _find_todo(self):
        for r in self.roots:
            cand = Path(r) / "todos.md"
            if cand.is_file():
                return str(cand)
        return None

    def _load_todos(self):
        if not self.todo_path:
            return
        with open(self.todo_path, encoding="utf-8") as f:
            lines = f.readlines()
        self.tasks = []
        for ln in lines:
            m = re.match(r"(\d+)\.\s*(.+?)\.\s*(To Do|Doing|Done)", ln)
            if m:
                num, desc, status = m.groups()
                self.tasks.append({
                    "num": int(num),
                    "desc": desc.strip(),
                    "status": status,
                })

    def process_new_tasks(self):
        new = [t for t in self.tasks if t["status"]=="To Do"]
        if not new:
            return
        with open(self.work_path, "a", encoding="utf-8") as w:
            for t in new:
                w.write(f"{datetime.utcnow().isoformat()}  ⬜ Task {t['num']}: {t['desc']}\n")
        # mark them Doing in todos.md
        updated = []
        for t in self.tasks:
            if t["status"]=="To Do":
                updated.append(f"{t['num']}. {t['desc']}. Doing (Started: {datetime.today().strftime('%Y-%m-%d')})\n")
            else:
                # leave existing line untouched
                pass
        # simple rewrite of all To Do → Doing
        content = ""
        with open(self.todo_path, encoding="utf-8") as f:
            for ln in f:
                if re.match(r"\d+\.\s*.+?\.\s*To Do", ln):
                    n = int(ln.split(".",1)[0])
                    desc = next(t["desc"] for t in self.tasks if t["num"]==n)
                    content += f"{n}. {desc}. Doing (Started: {datetime.today().strftime('%Y-%m-%d')})\n"
                else:
                    content += ln
        with open(self.todo_path, "w", encoding="utf-8") as f:
            f.write(content)
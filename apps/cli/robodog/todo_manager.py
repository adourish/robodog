#!/usr/bin/env python3
"""
Todo Management Module
Provides high-level operations for managing todo.md files
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

STATUS_MAP = {' ': 'To Do', '~': 'Doing', 'x': 'Done', '-': 'Ignore'}
REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}


class TodoManager:
    """High-level todo.md management"""
    
    def __init__(self, roots: List[str]):
        self.roots = roots
    
    def find_todo_files(self) -> List[str]:
        """Find all todo.md files in roots"""
        todo_files = []
        for root in self.roots:
            root_path = Path(root)
            if not root_path.exists():
                continue
            
            # Check root directory
            todo_path = root_path / "todo.md"
            if todo_path.exists():
                todo_files.append(str(todo_path))
            
            # Check subdirectories
            for todo_path in root_path.rglob("todo.md"):
                todo_files.append(str(todo_path))
        
        return todo_files
    
    def create_todo_file(self, path: Optional[str] = None) -> str:
        """Create a new todo.md file"""
        if path is None:
            # Use first root
            if not self.roots:
                raise ValueError("No roots configured")
            path = os.path.join(self.roots[0], "todo.md")
        
        path = os.path.abspath(path)
        
        # Create directory if needed
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Create file with template
        template = """# Todo List

## Tasks

- [ ] Example task - This is an example task

## Completed

"""
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(template)
        
        logger.info(f"Created todo.md at {path}")
        return path
    
    def add_task(self, description: str, path: Optional[str] = None, 
                 plan_status: str = ' ', llm_status: str = ' ', commit_status: str = ' ',
                 priority: Optional[str] = None,
                 tags: Optional[List[str]] = None,
                 include: Optional[str] = None,
                 plan_spec: Optional[str] = None) -> Dict[str, Any]:
        """
        Add a new task to todo.md with plan, llm, and commit stages
        
        Args:
            description: Task description
            path: Path to todo.md (uses first root if None)
            plan_status: Plan stage status (' ', '~', 'x', '-')
            llm_status: LLM stage status (' ', '~', 'x', '-')
            commit_status: Commit stage status (' ', '~', 'x', '-')
            priority: Priority level (optional)
            tags: List of tags (optional)
            include: Include pattern (optional)
            plan_spec: Plan specification pattern (optional)
        
        Returns:
            Dict with task info
        """
        if path is None:
            # Find or create todo.md in first root
            todo_files = self.find_todo_files()
            if todo_files:
                path = todo_files[0]
            else:
                path = self.create_todo_file()
        
        path = os.path.abspath(path)
        
        # Build task line with three-bracket format: [plan][llm][commit]
        task_line = f"- [{plan_status}][{llm_status}][{commit_status}] {description}"
        
        if priority:
            task_line += f" !{priority}"
        
        if tags:
            task_line += " " + " ".join(f"#{tag}" for tag in tags)
        
        # Read existing content
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = "# Todo List\n\n## Tasks\n\n"
        
        # Find insertion point (after ## Tasks or at end)
        lines = content.split('\n')
        insert_idx = len(lines)
        
        for i, line in enumerate(lines):
            if line.strip().startswith('## Tasks'):
                # Insert after this header (skip empty lines)
                insert_idx = i + 1
                while insert_idx < len(lines) and not lines[insert_idx].strip():
                    insert_idx += 1
                break
        
        # Insert task
        lines.insert(insert_idx, task_line)
        insert_idx += 1
        
        # Add sub-lines if provided
        if include:
            lines.insert(insert_idx, f"  - include: {include}")
            insert_idx += 1
        
        if plan_spec:
            lines.insert(insert_idx, f"  - plan: {plan_spec}")
            insert_idx += 1
        
        # Write back
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        logger.info(f"Added task to {path}: {description}")
        
        return {
            "path": path,
            "description": description,
            "plan_status": STATUS_MAP.get(plan_status, 'To Do'),
            "llm_status": STATUS_MAP.get(llm_status, 'To Do'),
            "commit_status": STATUS_MAP.get(commit_status, 'To Do'),
            "line": task_line,
            "line_number": insert_idx - (2 if plan_spec else 1 if include else 0)
        }
    
    def list_tasks(self, path: Optional[str] = None, 
                   status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all tasks from todo.md
        
        Args:
            path: Path to todo.md (searches all if None)
            status_filter: Filter by status (' ', '~', 'x', '-')
        
        Returns:
            List of task dictionaries
        """
        if path is None:
            todo_files = self.find_todo_files()
        else:
            todo_files = [os.path.abspath(path)]
        
        all_tasks = []
        
        for todo_path in todo_files:
            if not os.path.exists(todo_path):
                continue
            
            with open(todo_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for line_num, line in enumerate(lines, 1):
                # Match task lines: - [plan][llm][commit] description
                stripped = line.strip()
                if not stripped.startswith('- ['):
                    continue
                
                # Parse three-bracket format: - [p][l][c] description
                # Pattern: - [X][Y][Z] where X, Y, Z are status chars
                import re
                match = re.match(r'^-\s*\[(.)\]\[(.)\]\[(.)\]\s+(.+)$', stripped)
                if not match:
                    # Try old single-bracket format for backward compatibility
                    if len(stripped) >= 5 and stripped[3] in STATUS_MAP:
                        status_char = stripped[3]
                        plan_status = llm_status = commit_status = status_char
                        desc_start = stripped.find('] ') + 2
                        if desc_start < 2:
                            continue
                        description = stripped[desc_start:]
                    else:
                        continue
                else:
                    plan_status = match.group(1)
                    llm_status = match.group(2)
                    commit_status = match.group(3)
                    description = match.group(4)
                    
                    # Validate status characters
                    if plan_status not in STATUS_MAP or llm_status not in STATUS_MAP or commit_status not in STATUS_MAP:
                        continue
                    
                    # For filtering, use plan status as primary
                    status_char = plan_status
                
                # Apply filter
                if status_filter and status_char != status_filter:
                    continue
                
                # Parse priority and tags
                priority = None
                tags = []
                
                # Extract priority (!1, !2, etc)
                if '!' in description:
                    parts = description.split('!')
                    if len(parts) > 1:
                        priority_part = parts[1].split()[0]
                        if priority_part.isdigit():
                            priority = priority_part
                
                # Extract tags (#tag)
                words = description.split()
                for word in words:
                    if word.startswith('#'):
                        tags.append(word[1:])
                
                # Clean description (remove priority and tags)
                clean_desc = description
                for word in words:
                    if word.startswith('#') or word.startswith('!'):
                        clean_desc = clean_desc.replace(word, '')
                clean_desc = ' '.join(clean_desc.split())
                
                all_tasks.append({
                    "file": todo_path,
                    "line_number": line_num,
                    "status": STATUS_MAP[status_char],
                    "status_char": status_char,
                    "plan_status": STATUS_MAP.get(plan_status, 'To Do'),
                    "llm_status": STATUS_MAP.get(llm_status, 'To Do'),
                    "commit_status": STATUS_MAP.get(commit_status, 'To Do'),
                    "description": clean_desc,
                    "full_description": description,
                    "priority": priority,
                    "tags": tags,
                    "raw_line": line.rstrip()
                })
        
        return all_tasks
    
    def update_task_status(self, path: str, line_number: int, 
                          new_status: str, stage: str = 'plan') -> Dict[str, Any]:
        """
        Update task status for a specific stage
        
        Args:
            path: Path to todo.md
            line_number: Line number (1-indexed)
            new_status: New status character (' ', '~', 'x', '-')
            stage: Which stage to update ('plan', 'llm', 'commit', or 'all')
        
        Returns:
            Updated task info
        """
        path = os.path.abspath(path)
        
        if new_status not in STATUS_MAP:
            raise ValueError(f"Invalid status: {new_status}")
        
        if stage not in ['plan', 'llm', 'commit', 'all']:
            raise ValueError(f"Invalid stage: {stage}. Must be 'plan', 'llm', 'commit', or 'all'")
        
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if line_number < 1 or line_number > len(lines):
            raise ValueError(f"Invalid line number: {line_number}")
        
        line = lines[line_number - 1]
        stripped = line.strip()
        
        # Try to parse three-bracket format
        import re
        match = re.match(r'^-\s*\[(.)\]\[(.)\]\[(.)\]\s+(.+)$', stripped)
        
        if match:
            plan_status = match.group(1)
            llm_status = match.group(2)
            commit_status = match.group(3)
            description = match.group(4)
            
            # Update the appropriate stage(s)
            if stage == 'plan' or stage == 'all':
                plan_status = new_status
            if stage == 'llm' or stage == 'all':
                llm_status = new_status
            if stage == 'commit' or stage == 'all':
                commit_status = new_status
            
            # Rebuild line
            indent = line[:len(line) - len(line.lstrip())]
            new_line = f"{indent}- [{plan_status}][{llm_status}][{commit_status}] {description}\n"
            lines[line_number - 1] = new_line
            
            # Write back
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            logger.info(f"Updated task {stage} status at {path}:{line_number} to '{STATUS_MAP[new_status]}'")
            
            return {
                "path": path,
                "line_number": line_number,
                "plan_status": STATUS_MAP[plan_status],
                "llm_status": STATUS_MAP[llm_status],
                "commit_status": STATUS_MAP[commit_status],
                "line": new_line.rstrip()
            }
        else:
            raise ValueError(f"Line {line_number} is not a valid three-bracket task")
    
    def delete_task(self, path: str, line_number: int) -> Dict[str, Any]:
        """
        Delete a task
        
        Args:
            path: Path to todo.md
            line_number: Line number (1-indexed)
        
        Returns:
            Deleted task info
        """
        path = os.path.abspath(path)
        
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if line_number < 1 or line_number > len(lines):
            raise ValueError(f"Invalid line number: {line_number}")
        
        deleted_line = lines[line_number - 1]
        del lines[line_number - 1]
        
        # Write back
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        logger.info(f"Deleted task at {path}:{line_number}")
        
        return {
            "path": path,
            "line_number": line_number,
            "deleted_line": deleted_line.rstrip()
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get todo statistics across all files"""
        all_tasks = self.list_tasks()
        
        stats = {
            "total": len(all_tasks),
            "todo": 0,
            "doing": 0,
            "done": 0,
            "ignore": 0,
            "by_file": {},
            "by_priority": {},
            "by_tag": {}
        }
        
        for task in all_tasks:
            # Count by status
            status = task['status']
            if status == 'To Do':
                stats['todo'] += 1
            elif status == 'Doing':
                stats['doing'] += 1
            elif status == 'Done':
                stats['done'] += 1
            elif status == 'Ignore':
                stats['ignore'] += 1
            
            # Count by file
            file_path = task['file']
            if file_path not in stats['by_file']:
                stats['by_file'][file_path] = 0
            stats['by_file'][file_path] += 1
            
            # Count by priority
            priority = task.get('priority')
            if priority:
                if priority not in stats['by_priority']:
                    stats['by_priority'][priority] = 0
                stats['by_priority'][priority] += 1
            
            # Count by tag
            for tag in task.get('tags', []):
                if tag not in stats['by_tag']:
                    stats['by_tag'][tag] = 0
                stats['by_tag'][tag] += 1
        
        return stats


# file: robodog/models.py
#!/usr/bin/env python3
"""Pydantic models for robodog."""
from typing import List, Optional
from pydantic import BaseModel, RootModel


class Change(BaseModel):
    """Represents a file change."""
    path: str
    start_line: int
    end_line: Optional[int]
    new_content: str


class ChangesList(RootModel[List[Change]]):
    """List of changes."""
    pass


class TaskModel(BaseModel):
    """Task model for validation."""
    file: str
    line_no: int
    indent: str
    llm: str
    commit: Optional[str]
    desc: str
    include: Optional[dict] = None
    out: Optional[dict] = None
    knowledge: str = ""
    
    # Private fields for tracking
    _start_stamp: Optional[str] = None
    _know_tokens: int = 0
    _in_tokens: int = 0
    _prompt_tokens: int = 0
    _include_tokens: int = 0


class IncludeSpec(BaseModel):
    """Include specification model."""
    pattern: str
    recursive: bool = False

# original file length: 35 lines
# updated file length: 35 lines

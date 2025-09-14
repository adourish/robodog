# file: C:\Projects\robodog\robodogcli\robodog\base.py
# filename: robodog/base.py
# originalfilename: robodog/base.py
# matchedfilename: C:\Projects\robodog\robodogcli\robodog\base.py
# original file length: 57 lines
# updated file length: 51 lines
from typing import List, Optional, Dict, Any, Union
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)


class BaseService:
    """Base classes and common utilities for robodog services."""
    
    def __init__(self, roots: List[str] = None):
        self._roots = roots or [os.getcwd()]
    
    @property
    def roots(self) -> List[str]:
        """Get the root directories."""
        return self._roots
    
    @roots.setter
    def roots(self, value: List[str]):
        """Set the root directories."""
        self._roots = value or [os.getcwd()]


class TaskBase:
    """Base class for task-related functionality."""
    
    STATUS_MAP = {' ': 'To Do', '~': 'Doing', 'x': 'Done'}
    REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}
    
    @staticmethod
    def format_summary(
        indent: str,
        start: str,
        end: Optional[str] = None,
        know: Optional[int] = None,
        prompt: Optional[int] = None,
        incount: Optional[int] = None,
        include: Optional[int] = None,
        cur_model: str = None,
        compare: Optional[List[str]] = None
    ) -> str:
        """Format a task summary line, now including optional compare info inline."""
        parts = [f"started: {start}"]
        if end:
            parts.append(f"completed: {end}")
        if know is not None:
            parts.append(f"knowledge_tokens: {know}")
        if include is not None:
            parts.append(f"include_tokens
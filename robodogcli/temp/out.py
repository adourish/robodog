# file: robodog/file_service.py
#!/usr/bin/env python3
"""File operations and path resolution service."""
import os
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class FileService:
    """Handles file operations and path resolution."""
    
    def __init__(self, roots: List[str], base_dir: str = None, exclude_dirs: Optional[List[str]] = None):
        logger.info(f"Initializing FileService with roots: {roots}, base_dir: {base_dir}, exclude_dirs: {exclude_dirs}")
        self._roots = roots
        self._base_dir = base_dir
        self._exclude_dirs = set(exclude_dirs or [])
    
    @property
    def base_dir(self) -> Optional[str]:
        return self._base_dir
    
    @base_dir.setter
    def base_dir(self, value: str):
        logger.debug(f"Setting base_dir to: {value}")
        self._base_dir = value
    
    def find_files_by_pattern(self, pattern: str, recursive: bool, svc=None) -> List[str]:
        """Find files matching the given glob pattern."""
        logger.debug(f"find_files_by_pattern called with pattern: {pattern}, recursive: {recursive}")
        if svc:
            return svc.search_files(patterns=pattern, recursive=recursive,
                                    roots=self._roots, exclude_dirs=self._exclude_dirs)
        logger.warning("Svc not provided, returning empty list")
        return []
    
    def find_matching_file(self, filename: str, include_spec: dict, svc=None) -> Optional[Path]:
        """Find a file by name based on the include pattern."""
        logger.debug(f"find_matching_file called for {filename}")
        files = self.find_files_by_pattern(
            include_spec['pattern'], 
            include_spec.get('recursive', False),
            svc
        )
        for f in files:
            if Path(f).name == filename:
                logger.debug(f"Matching file found: {f}")
                return Path(f)
        logger.debug("No matching file found")
        return None
    
    def resolve_path(self, frag: str) -> Optional[Path]:
        """Resolve a file fragment to an absolute path."""
        logger.debug(f"Resolving path for frag: {frag}")
        if not frag:
            return None
        
        f = frag.strip('"').strip('`')
        
        # Simple filename in base_dir
        if self._base_dir and not any(sep in f for sep in (os.sep,'/','\\')):
            candidate = Path(self._base_dir) / f
            logger.debug(f"Resolved to base_dir candidate: {candidate}")
            return candidate.resolve()
        
        # Path with separators in base_dir
        if self._base_dir and any(sep in f for sep in ('/','\\')):
            candidate = Path(self._base_dir) / Path(f)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Resolved to base_dir path candidate: {candidate}")
            return candidate.resolve()
        
        # Search in roots
        search_roots = ([self._base_dir] if self._base_dir else []) + self._roots
        for root in search_roots:
            cand = Path(root) / f
            if cand.is_file():
                logger.debug(f"Found in roots: {cand}")
                return cand.resolve()
        
        # Create in first root
        p = Path(f)
        base = Path(self._roots[0]) / p.parent
        base.mkdir(parents=True, exist_ok=True)
        created = (base / p.name).resolve()
        logger.debug(f"Created new path: {created}")
        return created
    
    def safe_read_file(self, path: Path) -> str:
        """Safely read a file, handling binary files and encoding issues."""
        logger.debug(f"Safe read of: {path.absolute()}")
        try:
            # Check for binary content
            with open(path, 'rb') as bf:
                if b'\x00' in bf.read(1024):
                    raise UnicodeDecodeError("binary", b"", 0, 1, "null")
            content = path.read_text(encoding='utf-8')
            logger.debug(f"Successfully read file, {len(content.split())} tokens")
            return content
        except UnicodeDecodeError:
            logger.warning(f"Binary content detected for {path}, trying with ignore")
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
                logger.debug(f"Read with ignore, {len(content.split())} tokens")
                return content
            except Exception as e:
                logger.error(f"Failed to read {path}: {e}")
                return ""
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")
            return ""

    def write_file(self, path: Path, content: str):
        """Write content to the given path, creating directories as needed."""
        logger.debug(f"Writing file: {path}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            logger.info(f"Written file via FileService: {path} ({len(content.split())} tokens)")
        except Exception as e:
            logger.error(f"FileService.write_file failed for {path}: {e}")

    def write_file_lines(self, filepath: str, file_lines: List[str]):
        """Write file and update watcher."""
        logger.debug(f"Writing file lines to: {filepath}")
        Path(filepath).write_text(''.join(file_lines), encoding='utf-8')

    def write_file_text (self, filepath: str, content: str):
        """Write file and update watcher."""
        logger.debug(f"Writing text to: {filepath}")
        Path(filepath).write_text(content, encoding='utf-8')

# original file length: 102 lines
# updated file length: 109 lines


# file: robodog/cli.py
#!/usr/bin/env python3
import os
import sys
import argparse
import logging
import json
from pprint import pprint

import colorlog

from service        import RobodogService
from parse_service  import ParseService
from file_service   import FileService
from file_watcher   import FileWatcher
from task_parser    import TaskParser
from task_manager   import TaskManager
from prompt_builder import PromptBuilder
from todo           import TodoService

try:
    from .service import RobodogService
    from .mcphandler import run_robodogmcp
    from .todo import TodoService
    from .parse_service import ParseService
    from .models import TaskModel, Change, ChangesList, IncludeSpec
    from .file_service import FileService
    from .file_watcher import FileWatcher
    from .task_manager import TaskManager
    from .task_parser import TaskParser
    from .prompt_builder import PromptBuilder
except ImportError:
    from service import RobodogService
    from mcphandler import run_robodogmcp
    from todo import TodoService
    from parse_service import ParseService
    from models import TaskModel, Change, ChangesList, IncludeSpec
    from file_service import FileService
    from file_watcher import FileWatcher
    from task_manager import TaskManager
    from task_parser import TaskParser
    from prompt_builder import PromptBuilder


def print_help():
    cmds = {
        "help":                "show this help",
        "models":              "list configured models",
        "model <name>":        "switch model",
        "key <prov> <key>":    "set API key for provider",
        "getkey <prov>":       "get API key for provider",
        "import <glob>":       "import files into knowledge",
        "export <file>":       "export chat+knowledge snapshot",
        "clear":               "clear chat+knowledge",
        "stash <name>":        "stash state",
        "pop <name>":          "restore stash",
        "list":                "list stashes",
        "temperature <n>":     "set temperature",
        "top_p <n>":           "set top_p",
        "max_tokens <n>":      "set max_tokens",
        "frequency_penalty <n>":"set frequency_penalty",
        "presence_penalty <n>":"set presence_penalty",
        "stream":              "enable streaming",
        "rest":                "disable streaming",
        "folders <dirs>":      "set MCP roots",
        "exclude":             "directories to exclude",
        "include":             "include files via MCP",
        "curl":                "fetch web pages / scripts",
        "play":                "run AI-driven Playwright tests",
        "mcp":                 "invoke raw MCP operation",
        "todo":                "run next To Do task",
    }
    logging.info("Available /commands:")
    for cmd, desc in cmds.items():
        logging.info(f"  /{cmd:<20} — {desc}")


def parse_cmd(line):
    parts = line.strip().split()
    return parts[0][1:], parts[1:]


def _init_services(args):
    # 1) core Robodog service + parser
    svc    = RobodogService(args.config)
    parser = ParseService()
    svc.parse_service = parser

    # 2) file-service (for ad hoc file lookups and reads), with exclude dirs
    svc.file_service = FileService(roots=args.folders,
                                   base_dir=None,
                                   exclude_dirs=args.exclude)

    # 3) file-watcher (used by TaskManager / TodoService to ignore self-writes)
    watcher = FileWatcher()
    watcher.start()
    svc.file_watcher = watcher

    # 4) task-parsing + task-manager (status updates in todo.md)
    task_parser  = TaskParser()
    svc.task_parser = task_parser
    task_manager = TaskManager(
        base=None,
        file_watcher=watcher,
        task_parser=task_parser,
        svc=svc
    )
    svc.task_manager = task_manager

    # 5) prompt builder for formalizing AI prompts
    svc.prompt_builder = PromptBuilder()

    # 6) todo runner / watcher
    svc.todo = TodoService(args.folders, svc, svc.prompt_builder,
                           svc.task_manager, svc.task_parser,
                           svc.file_watcher, svc.file_service)

    # 7) where to stash old focus-file backups
    svc.backup_folder = args.backupFolder

    return svc, parser


def main():
    parser = argparse.ArgumentParser(prog="robodog",
        description="Combined MCP file-server + Robodog CLI")
    parser.add_argument('--config', default='config.yaml',
                        help='path to robodog YAML config')
    parser.add_argument('--folders', nargs='+', required=True,
                        help='one or more root folders to serve')
    parser.add_argument('--exclude', nargs='*', default=None,
                        help='directories to exclude from file operations')
    parser.add_argument('--host', default='127.0.0.1',
                        help='MCP host')
    parser.add_argument('--port', type=int, default=2500,
                        help='MCP port')
    parser.add_argument('--token', required=True,
                        help='MCP auth token')
    parser.add_argument('--model', '-m',
                        help='startup model name')
    parser.add_argument('--log-file', default='robodog.log',
                        help='path to log file')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'],
                        help='set root logging level')
    parser.add_argument('--backupFolder', default=r'c:\temp',
                        help='folder to store focus-file backups')
    args = parser.parse_args()

    # configure colored logging
    root = logging.getLogger()
    root.setLevel(getattr(logging, args.log_level))
    fmt = colorlog.ColoredFormatter(
        "%(log_color)s[%(asctime)s] %(levelname)s:%(reset)s %(message)s",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
        }
    )
    ch = colorlog.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    fh = logging.FileHandler(args.log_file)
    fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
    root.addHandler(fh)

    logging.info("Starting robodog")

    svc, _ = _init_services(args)
    server = run_robodogmcp(
        host    = args.host,
        port    = args.port,
        token   = args.token,
        folders = args.folders,
        svc     = svc
    )
    logging.info("MCP server on %s:%d", args.host, args.port)

    svc.mcp_cfg['baseUrl'] = f"http://{args.host}:{args.port}"
    svc.mcp_cfg['apiKey']  = args.token
    if args.model:
        svc.set_model(args.model)
        logging.info("Startup model set to %s", svc.cur_model)

    try:
        interact(svc)
    finally:
        logging.info("Shutting down MCP server")
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    main()

# original file length: 228 lines
# updated file length: 241 lines
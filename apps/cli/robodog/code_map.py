#!/usr/bin/env python3
"""
Code Map Generator
Creates a lightweight map of the codebase for efficient context gathering
"""

import os
import ast
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, asdict
import json

logger = logging.getLogger(__name__)


@dataclass
class FunctionInfo:
    """Information about a function or method"""
    name: str
    line_start: int
    line_end: int
    args: List[str]
    returns: Optional[str]
    docstring: Optional[str]
    is_async: bool
    is_method: bool
    decorators: List[str]


@dataclass
class ClassInfo:
    """Information about a class"""
    name: str
    line_start: int
    line_end: int
    bases: List[str]
    methods: List[FunctionInfo]
    docstring: Optional[str]
    decorators: List[str]


@dataclass
class ImportInfo:
    """Information about imports"""
    module: str
    names: List[str]
    is_from: bool
    line: int


@dataclass
class FileMap:
    """Map of a single file"""
    path: str
    language: str
    size: int
    lines: int
    imports: List[ImportInfo]
    classes: List[ClassInfo]
    functions: List[FunctionInfo]
    global_vars: List[str]
    docstring: Optional[str]
    dependencies: Set[str]


class CodeMapper:
    """Generate and manage code maps for efficient context gathering"""
    
    def __init__(self, roots: List[str], exclude_dirs: Optional[Set[str]] = None):
        self.roots = roots
        self.exclude_dirs = exclude_dirs or {'node_modules', 'dist', 'diffoutput', '__pycache__', '.git', 'venv', 'env'}
        self.file_maps: Dict[str, FileMap] = {}
        self.index: Dict[str, List[str]] = {
            'classes': {},      # class_name -> [file_paths]
            'functions': {},    # function_name -> [file_paths]
            'imports': {},      # module_name -> [file_paths]
        }
    
    def scan_codebase(self, extensions: Optional[List[str]] = None) -> Dict[str, FileMap]:
        """
        Scan entire codebase and create maps
        
        Args:
            extensions: File extensions to scan (default: ['.py', '.js', '.ts', '.tsx'])
        
        Returns:
            Dictionary of file paths to FileMaps
        """
        if extensions is None:
            extensions = ['.py', '.js', '.ts', '.tsx', '.jsx']
        
        logger.info(f"Scanning codebase in {len(self.roots)} roots")
        
        for root in self.roots:
            root_path = Path(root)
            if not root_path.exists():
                logger.warning(f"Root does not exist: {root}")
                continue
            
            for file_path in self._walk_directory(root_path, extensions):
                try:
                    file_map = self._map_file(file_path)
                    if file_map:
                        self.file_maps[str(file_path)] = file_map
                        self._update_index(file_map)
                except Exception as e:
                    logger.warning(f"Failed to map {file_path}: {e}")
        
        logger.info(f"Mapped {len(self.file_maps)} files")
        return self.file_maps
    
    def _walk_directory(self, root: Path, extensions: List[str]) -> List[Path]:
        """Walk directory and find files with given extensions"""
        files = []
        
        for item in root.rglob('*'):
            # Skip excluded directories
            if any(excluded in item.parts for excluded in self.exclude_dirs):
                continue
            
            # Check extension
            if item.is_file() and item.suffix in extensions:
                files.append(item)
        
        return files
    
    def _map_file(self, file_path: Path) -> Optional[FileMap]:
        """Create a map for a single file"""
        ext = file_path.suffix
        
        if ext == '.py':
            return self._map_python_file(file_path)
        elif ext in ['.js', '.ts', '.tsx', '.jsx']:
            return self._map_javascript_file(file_path)
        
        return None
    
    def _map_python_file(self, file_path: Path) -> Optional[FileMap]:
        """Map a Python file using AST"""
        try:
            content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(content, filename=str(file_path))
            
            imports = []
            classes = []
            functions = []
            global_vars = []
            docstring = ast.get_docstring(tree)
            dependencies = set()
            
            for node in ast.walk(tree):
                # Imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(ImportInfo(
                            module=alias.name,
                            names=[alias.asname or alias.name],
                            is_from=False,
                            line=node.lineno
                        ))
                        dependencies.add(alias.name.split('.')[0])
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(ImportInfo(
                            module=node.module,
                            names=[alias.name for alias in node.names],
                            is_from=True,
                            line=node.lineno
                        ))
                        dependencies.add(node.module.split('.')[0])
            
            # Top-level definitions
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    classes.append(self._parse_class(node))
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    functions.append(self._parse_function(node, is_method=False))
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            global_vars.append(target.id)
            
            return FileMap(
                path=str(file_path),
                language='python',
                size=len(content),
                lines=len(content.splitlines()),
                imports=imports,
                classes=classes,
                functions=functions,
                global_vars=global_vars,
                docstring=docstring,
                dependencies=dependencies
            )
        
        except Exception as e:
            logger.debug(f"Failed to parse Python file {file_path}: {e}")
            return None
    
    def _parse_class(self, node: ast.ClassDef) -> ClassInfo:
        """Parse a class definition"""
        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._parse_function(item, is_method=True))
        
        return ClassInfo(
            name=node.name,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            bases=[self._get_name(base) for base in node.bases],
            methods=methods,
            docstring=ast.get_docstring(node),
            decorators=[self._get_decorator_name(dec) for dec in node.decorator_list]
        )
    
    def _parse_function(self, node: ast.FunctionDef, is_method: bool = False) -> FunctionInfo:
        """Parse a function or method definition"""
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        
        returns = None
        if node.returns:
            returns = self._get_name(node.returns)
        
        return FunctionInfo(
            name=node.name,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            args=args,
            returns=returns,
            docstring=ast.get_docstring(node),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method=is_method,
            decorators=[self._get_decorator_name(dec) for dec in node.decorator_list]
        )
    
    def _get_name(self, node) -> str:
        """Get name from AST node"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            return f"{self._get_name(node.value)}[...]"
        return str(node)
    
    def _get_decorator_name(self, node) -> str:
        """Get decorator name"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Call):
            return self._get_name(node.func)
        return str(node)
    
    def _map_javascript_file(self, file_path: Path) -> Optional[FileMap]:
        """Map a JavaScript/TypeScript file using regex patterns"""
        try:
            content = file_path.read_text(encoding='utf-8')
            
            imports = self._parse_js_imports(content)
            classes = self._parse_js_classes(content)
            functions = self._parse_js_functions(content)
            dependencies = set()
            
            # Extract dependencies from imports
            for imp in imports:
                if not imp.module.startswith('.'):
                    dependencies.add(imp.module.split('/')[0])
            
            return FileMap(
                path=str(file_path),
                language='javascript' if file_path.suffix == '.js' else 'typescript',
                size=len(content),
                lines=len(content.splitlines()),
                imports=imports,
                classes=classes,
                functions=functions,
                global_vars=[],
                docstring=None,
                dependencies=dependencies
            )
        
        except Exception as e:
            logger.debug(f"Failed to parse JS file {file_path}: {e}")
            return None
    
    def _parse_js_imports(self, content: str) -> List[ImportInfo]:
        """Parse JavaScript imports"""
        imports = []
        
        # import ... from '...'
        pattern = r"import\s+(?:{([^}]+)}|(\w+))\s+from\s+['\"]([^'\"]+)['\"]"
        for match in re.finditer(pattern, content):
            names = []
            if match.group(1):  # Named imports
                names = [n.strip() for n in match.group(1).split(',')]
            elif match.group(2):  # Default import
                names = [match.group(2)]
            
            imports.append(ImportInfo(
                module=match.group(3),
                names=names,
                is_from=True,
                line=content[:match.start()].count('\n') + 1
            ))
        
        # require('...')
        pattern = r"(?:const|let|var)\s+(?:{([^}]+)}|(\w+))\s*=\s*require\(['\"]([^'\"]+)['\"]\)"
        for match in re.finditer(pattern, content):
            names = []
            if match.group(1):
                names = [n.strip() for n in match.group(1).split(',')]
            elif match.group(2):
                names = [match.group(2)]
            
            imports.append(ImportInfo(
                module=match.group(3),
                names=names,
                is_from=True,
                line=content[:match.start()].count('\n') + 1
            ))
        
        return imports
    
    def _parse_js_classes(self, content: str) -> List[ClassInfo]:
        """Parse JavaScript classes"""
        classes = []
        
        # class ClassName extends Base {
        pattern = r"class\s+(\w+)(?:\s+extends\s+(\w+))?\s*{"
        for match in re.finditer(pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            classes.append(ClassInfo(
                name=match.group(1),
                line_start=line_num,
                line_end=line_num,  # Approximate
                bases=[match.group(2)] if match.group(2) else [],
                methods=[],
                docstring=None,
                decorators=[]
            ))
        
        return classes
    
    def _parse_js_functions(self, content: str) -> List[FunctionInfo]:
        """Parse JavaScript functions"""
        functions = []
        
        # function name(...) {
        pattern = r"(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)"
        for match in re.finditer(pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            args = [a.strip() for a in match.group(2).split(',') if a.strip()]
            is_async = 'async' in content[max(0, match.start()-10):match.start()]
            
            functions.append(FunctionInfo(
                name=match.group(1),
                line_start=line_num,
                line_end=line_num,
                args=args,
                returns=None,
                docstring=None,
                is_async=is_async,
                is_method=False,
                decorators=[]
            ))
        
        # const name = (...) => {
        pattern = r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>"
        for match in re.finditer(pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            args = [a.strip() for a in match.group(2).split(',') if a.strip()]
            is_async = 'async' in match.group(0)
            
            functions.append(FunctionInfo(
                name=match.group(1),
                line_start=line_num,
                line_end=line_num,
                args=args,
                returns=None,
                docstring=None,
                is_async=is_async,
                is_method=False,
                decorators=[]
            ))
        
        return functions
    
    def _update_index(self, file_map: FileMap):
        """Update search index with file map"""
        # Index classes
        for cls in file_map.classes:
            if cls.name not in self.index['classes']:
                self.index['classes'][cls.name] = []
            self.index['classes'][cls.name].append(file_map.path)
        
        # Index functions
        for func in file_map.functions:
            if func.name not in self.index['functions']:
                self.index['functions'][func.name] = []
            self.index['functions'][func.name].append(file_map.path)
        
        # Index imports
        for imp in file_map.imports:
            if imp.module not in self.index['imports']:
                self.index['imports'][imp.module] = []
            self.index['imports'][imp.module].append(file_map.path)
    
    def find_definition(self, name: str) -> List[Dict[str, Any]]:
        """
        Find where a class or function is defined
        
        Returns:
            List of matches with file path and line information
        """
        results = []
        
        # Search classes
        if name in self.index['classes']:
            for file_path in self.index['classes'][name]:
                file_map = self.file_maps.get(file_path)
                if file_map:
                    for cls in file_map.classes:
                        if cls.name == name:
                            results.append({
                                'type': 'class',
                                'name': name,
                                'file': file_path,
                                'line_start': cls.line_start,
                                'line_end': cls.line_end,
                                'docstring': cls.docstring
                            })
        
        # Search functions
        if name in self.index['functions']:
            for file_path in self.index['functions'][name]:
                file_map = self.file_maps.get(file_path)
                if file_map:
                    for func in file_map.functions:
                        if func.name == name:
                            results.append({
                                'type': 'function',
                                'name': name,
                                'file': file_path,
                                'line_start': func.line_start,
                                'line_end': func.line_end,
                                'args': func.args,
                                'docstring': func.docstring
                            })
        
        return results
    
    def find_usages(self, module: str) -> List[str]:
        """Find files that import a module"""
        return self.index['imports'].get(module, [])
    
    def get_file_summary(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get a summary of a file"""
        file_map = self.file_maps.get(file_path)
        if not file_map:
            return None
        
        return {
            'path': file_map.path,
            'language': file_map.language,
            'lines': file_map.lines,
            'classes': [cls.name for cls in file_map.classes],
            'functions': [func.name for func in file_map.functions],
            'imports': [imp.module for imp in file_map.imports],
            'dependencies': list(file_map.dependencies),
            'docstring': file_map.docstring
        }
    
    def get_context_for_task(self, task_desc: str, include_patterns: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get relevant context for a task based on description and patterns
        
        Args:
            task_desc: Task description
            include_patterns: File patterns to include
        
        Returns:
            Dictionary with relevant files and their summaries
        """
        relevant_files = {}
        
        # Extract keywords from task description
        keywords = self._extract_keywords(task_desc)
        
        # Find files matching keywords
        for file_path, file_map in self.file_maps.items():
            score = 0
            
            # Check if file matches include patterns
            if include_patterns:
                if not any(self._matches_pattern(file_path, pattern) for pattern in include_patterns):
                    continue
            
            # Score based on keyword matches
            for keyword in keywords:
                # Check in class names
                if any(keyword.lower() in cls.name.lower() for cls in file_map.classes):
                    score += 3
                
                # Check in function names
                if any(keyword.lower() in func.name.lower() for func in file_map.functions):
                    score += 2
                
                # Check in file path
                if keyword.lower() in file_path.lower():
                    score += 1
            
            if score > 0:
                relevant_files[file_path] = {
                    'score': score,
                    'summary': self.get_file_summary(file_path)
                }
        
        # Sort by score
        sorted_files = dict(sorted(relevant_files.items(), key=lambda x: x[1]['score'], reverse=True))
        
        return {
            'task': task_desc,
            'keywords': keywords,
            'relevant_files': sorted_files,
            'total_files': len(sorted_files)
        }
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        # Remove common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        
        # Split and clean
        words = re.findall(r'\w+', text.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        return list(set(keywords))
    
    def _matches_pattern(self, file_path: str, pattern: str) -> bool:
        """Check if file path matches pattern"""
        import fnmatch
        return fnmatch.fnmatch(file_path, pattern)
    
    def save_map(self, output_path: str):
        """Save code map to JSON file"""
        data = {
            'roots': self.roots,
            'file_count': len(self.file_maps),
            'files': {},
            'index': {
                'classes': self.index['classes'],
                'functions': self.index['functions'],
                'imports': self.index['imports']
            }
        }
        
        # Convert file maps to serializable format
        for path, file_map in self.file_maps.items():
            data['files'][path] = {
                'path': file_map.path,
                'language': file_map.language,
                'size': file_map.size,
                'lines': file_map.lines,
                'classes': [asdict(cls) for cls in file_map.classes],
                'functions': [asdict(func) for func in file_map.functions],
                'imports': [asdict(imp) for imp in file_map.imports],
                'global_vars': file_map.global_vars,
                'docstring': file_map.docstring,
                'dependencies': list(file_map.dependencies)
            }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved code map to {output_path}")
    
    def load_map(self, input_path: str):
        """Load code map from JSON file"""
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.roots = data['roots']
        self.index = data['index']
        
        # Reconstruct file maps
        for path, file_data in data['files'].items():
            self.file_maps[path] = FileMap(
                path=file_data['path'],
                language=file_data['language'],
                size=file_data['size'],
                lines=file_data['lines'],
                imports=[ImportInfo(**imp) for imp in file_data['imports']],
                classes=[ClassInfo(**{**cls, 'methods': [FunctionInfo(**m) for m in cls['methods']]}) 
                        for cls in file_data['classes']],
                functions=[FunctionInfo(**func) for func in file_data['functions']],
                global_vars=file_data['global_vars'],
                docstring=file_data['docstring'],
                dependencies=set(file_data['dependencies'])
            )
        
        logger.info(f"Loaded code map from {input_path} ({len(self.file_maps)} files)")

#!/usr/bin/env python3
"""
Advanced Code Analysis Module
Provides call graph, impact analysis, and dependency tracking
"""

import ast
import os
from typing import Dict, List, Set, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class CallGraph:
    """Call graph for a codebase"""
    functions: Dict[str, Set[str]] = field(default_factory=dict)  # function -> called functions
    callers: Dict[str, Set[str]] = field(default_factory=dict)    # function -> callers
    function_locations: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # function -> file/line info


@dataclass
class DependencyInfo:
    """Dependency information for a file"""
    file_path: str
    imports: List[str] = field(default_factory=list)
    internal_deps: List[str] = field(default_factory=list)
    external_deps: List[str] = field(default_factory=list)


class AdvancedCodeAnalyzer:
    """
    Advanced code analysis beyond basic code map.
    Provides:
    - Call graph analysis
    - Impact analysis (what breaks if I change this?)
    - Dependency tracking
    - Semantic search improvements
    """
    
    def __init__(self, code_mapper=None):
        self.code_mapper = code_mapper
        self.call_graph: Optional[CallGraph] = None
        self.dependencies: Dict[str, DependencyInfo] = {}
        
    def build_call_graph(self) -> CallGraph:
        """Build call graph for entire codebase"""
        
        logger.info("Building call graph...")
        call_graph = CallGraph()
        
        if not self.code_mapper:
            logger.warning("No code mapper available")
            return call_graph
        
        # Analyze each file
        for file_path, file_map in self.code_mapper.file_maps.items():
            if file_path.endswith('.py'):
                self._analyze_python_calls(file_path, call_graph)
            elif file_path.endswith(('.js', '.jsx', '.ts', '.tsx')):
                self._analyze_js_calls(file_path, call_graph)
        
        self.call_graph = call_graph
        logger.info(f"Call graph built: {len(call_graph.functions)} functions")
        
        return call_graph
    
    def _analyze_python_calls(self, file_path: str, call_graph: CallGraph):
        """Analyze function calls in Python file"""
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=file_path)
            
            # Find all function definitions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_name = node.name
                    
                    # Store location
                    call_graph.function_locations[func_name] = {
                        'file': file_path,
                        'line': node.lineno,
                        'type': 'function'
                    }
                    
                    # Initialize call set
                    if func_name not in call_graph.functions:
                        call_graph.functions[func_name] = set()
                    
                    # Find all function calls within this function
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            called_name = self._extract_call_name(child)
                            if called_name:
                                call_graph.functions[func_name].add(called_name)
                                
                                # Track callers
                                if called_name not in call_graph.callers:
                                    call_graph.callers[called_name] = set()
                                call_graph.callers[called_name].add(func_name)
                
                elif isinstance(node, ast.ClassDef):
                    class_name = node.name
                    
                    # Store location
                    call_graph.function_locations[class_name] = {
                        'file': file_path,
                        'line': node.lineno,
                        'type': 'class'
                    }
        
        except Exception as e:
            logger.debug(f"Error analyzing {file_path}: {e}")
    
    def _extract_call_name(self, call_node: ast.Call) -> Optional[str]:
        """Extract function name from call node"""
        
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        elif isinstance(call_node.func, ast.Attribute):
            return call_node.func.attr
        return None
    
    def _analyze_js_calls(self, file_path: str, call_graph: CallGraph):
        """Analyze function calls in JavaScript/TypeScript file (basic)"""
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple regex-based analysis for JS
            # This is basic - a full implementation would use a JS parser
            import re
            
            # Find function declarations
            func_pattern = r'(?:function|const|let|var)\s+(\w+)\s*(?:=\s*)?(?:\([^)]*\)|async)'
            for match in re.finditer(func_pattern, content):
                func_name = match.group(1)
                
                call_graph.function_locations[func_name] = {
                    'file': file_path,
                    'line': content[:match.start()].count('\n') + 1,
                    'type': 'function'
                }
                
                if func_name not in call_graph.functions:
                    call_graph.functions[func_name] = set()
        
        except Exception as e:
            logger.debug(f"Error analyzing {file_path}: {e}")
    
    def find_impact(self, function_name: str, max_depth: int = 10) -> Dict[str, Any]:
        """
        Find what would be impacted by changing a function.
        Returns all direct and indirect callers.
        """
        
        if not self.call_graph:
            self.build_call_graph()
        
        # Find all callers (direct and indirect) using BFS
        impacted = set()
        to_check = {function_name}
        checked = set()
        depth_map = {function_name: 0}
        
        while to_check and len(checked) < max_depth * 10:
            func = to_check.pop()
            if func in checked:
                continue
            
            checked.add(func)
            current_depth = depth_map.get(func, 0)
            
            if current_depth >= max_depth:
                continue
            
            callers = self.call_graph.callers.get(func, set())
            
            for caller in callers:
                if caller not in impacted:
                    impacted.add(caller)
                    to_check.add(caller)
                    depth_map[caller] = current_depth + 1
        
        # Get location info for impacted functions
        impacted_details = []
        for func in impacted:
            loc = self.call_graph.function_locations.get(func, {})
            impacted_details.append({
                'name': func,
                'file': loc.get('file', 'unknown'),
                'line': loc.get('line', 0),
                'type': loc.get('type', 'function'),
                'depth': depth_map.get(func, 0)
            })
        
        # Sort by depth (closest first)
        impacted_details.sort(key=lambda x: x['depth'])
        
        return {
            'function': function_name,
            'location': self.call_graph.function_locations.get(function_name, {}),
            'direct_callers': list(self.call_graph.callers.get(function_name, set())),
            'all_impacted': impacted_details,
            'impact_count': len(impacted),
            'max_depth_reached': max(depth_map.values()) if depth_map else 0
        }
    
    def find_dependencies(self, file_path: str) -> DependencyInfo:
        """Find all dependencies of a file"""
        
        if file_path in self.dependencies:
            return self.dependencies[file_path]
        
        deps = DependencyInfo(file_path=file_path)
        
        try:
            if file_path.endswith('.py'):
                deps = self._analyze_python_deps(file_path)
            elif file_path.endswith(('.js', '.jsx', '.ts', '.tsx')):
                deps = self._analyze_js_deps(file_path)
            
            self.dependencies[file_path] = deps
        
        except Exception as e:
            logger.debug(f"Error analyzing dependencies for {file_path}: {e}")
        
        return deps
    
    def _analyze_python_deps(self, file_path: str) -> DependencyInfo:
        """Analyze Python file dependencies"""
        
        deps = DependencyInfo(file_path=file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=file_path)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                        deps.imports.append(module)
                        
                        # Classify as internal or external
                        if self._is_internal_module(module, file_path):
                            deps.internal_deps.append(module)
                        else:
                            deps.external_deps.append(module)
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module = node.module
                        deps.imports.append(module)
                        
                        if self._is_internal_module(module, file_path):
                            deps.internal_deps.append(module)
                        else:
                            deps.external_deps.append(module)
        
        except Exception as e:
            logger.debug(f"Error parsing {file_path}: {e}")
        
        return deps
    
    def _analyze_js_deps(self, file_path: str) -> DependencyInfo:
        """Analyze JavaScript/TypeScript file dependencies"""
        
        deps = DependencyInfo(file_path=file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import re
            
            # Find import statements
            import_pattern = r'import\s+(?:{[^}]+}|\w+)\s+from\s+[\'"]([^\'"]+)[\'"]'
            for match in re.finditer(import_pattern, content):
                module = match.group(1)
                deps.imports.append(module)
                
                if module.startswith('.'):
                    deps.internal_deps.append(module)
                else:
                    deps.external_deps.append(module)
            
            # Find require statements
            require_pattern = r'require\([\'"]([^\'"]+)[\'"]\)'
            for match in re.finditer(require_pattern, content):
                module = match.group(1)
                deps.imports.append(module)
                
                if module.startswith('.'):
                    deps.internal_deps.append(module)
                else:
                    deps.external_deps.append(module)
        
        except Exception as e:
            logger.debug(f"Error parsing {file_path}: {e}")
        
        return deps
    
    def _is_internal_module(self, module: str, file_path: str) -> bool:
        """Check if a module is internal to the project"""
        
        # Check if module starts with relative import
        if module.startswith('.'):
            return True
        
        # Check if module exists in project
        if self.code_mapper:
            for fpath in self.code_mapper.file_maps.keys():
                if module.replace('.', os.sep) in fpath:
                    return True
        
        return False
    
    def get_call_chain(self, from_func: str, to_func: str, max_depth: int = 10) -> List[List[str]]:
        """Find all call chains from one function to another"""
        
        if not self.call_graph:
            self.build_call_graph()
        
        chains = []
        
        def dfs(current: str, target: str, path: List[str], depth: int):
            if depth > max_depth:
                return
            
            if current == target:
                chains.append(path + [current])
                return
            
            if current in path:  # Avoid cycles
                return
            
            called = self.call_graph.functions.get(current, set())
            for next_func in called:
                dfs(next_func, target, path + [current], depth + 1)
        
        dfs(from_func, to_func, [], 0)
        
        return chains
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the codebase"""
        
        if not self.call_graph:
            self.build_call_graph()
        
        # Calculate various metrics
        total_functions = len(self.call_graph.functions)
        total_calls = sum(len(calls) for calls in self.call_graph.functions.values())
        
        # Find most called functions
        call_counts = {
            func: len(callers)
            for func, callers in self.call_graph.callers.items()
        }
        most_called = sorted(call_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Find most complex functions (calls many others)
        complexity = {
            func: len(calls)
            for func, calls in self.call_graph.functions.items()
        }
        most_complex = sorted(complexity.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            'total_functions': total_functions,
            'total_calls': total_calls,
            'avg_calls_per_function': total_calls / total_functions if total_functions > 0 else 0,
            'most_called': [{'name': name, 'call_count': count} for name, count in most_called],
            'most_complex': [{'name': name, 'complexity': count} for name, count in most_complex],
            'total_files': len(set(loc['file'] for loc in self.call_graph.function_locations.values()))
        }

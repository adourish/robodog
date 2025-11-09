#!/usr/bin/env python3
"""
Agent Context Builder
Efficiently builds context for agent loop using code map
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class AgentContextBuilder:
    """Build minimal, focused context for agent tasks"""
    
    def __init__(self, code_mapper, file_service):
        self.code_mapper = code_mapper
        self.file_service = file_service
        self.max_context_tokens = 4000  # Conservative limit
        self.max_files = 10
    
    def build_context(self, task: Dict[str, Any], 
                     include_patterns: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Build focused context for a task
        
        Args:
            task: Task dictionary with 'desc' and optional 'include'
            include_patterns: Additional file patterns to include
        
        Returns:
            Dictionary with context information
        """
        task_desc = task.get('desc', '')
        task_include = task.get('include')
        
        # Combine patterns
        patterns = []
        if task_include:
            patterns.append(task_include.get('pattern', '*'))
        if include_patterns:
            patterns.extend(include_patterns)
        
        # Get relevant files from code map
        context_info = self.code_mapper.get_context_for_task(
            task_desc,
            include_patterns=patterns if patterns else None
        )
        
        # Build context with token budget
        context = {
            'task': task_desc,
            'files': [],
            'total_tokens': 0,
            'keywords': context_info['keywords'],
            'truncated': False
        }
        
        # Add files in order of relevance
        for file_path, info in context_info['relevant_files'].items():
            if len(context['files']) >= self.max_files:
                context['truncated'] = True
                break
            
            # Get file content
            file_content = self._load_file_content(file_path, info['summary'])
            if not file_content:
                continue
            
            # Estimate tokens (rough: 1 token ≈ 4 chars)
            estimated_tokens = len(file_content) // 4
            
            # Check budget
            if context['total_tokens'] + estimated_tokens > self.max_context_tokens:
                context['truncated'] = True
                break
            
            # Add to context
            context['files'].append({
                'path': file_path,
                'score': info['score'],
                'content': file_content,
                'tokens': estimated_tokens,
                'summary': info['summary']
            })
            context['total_tokens'] += estimated_tokens
        
        logger.info(f"Built context: {len(context['files'])} files, {context['total_tokens']} tokens")
        return context
    
    def _load_file_content(self, file_path: str, summary: Dict[str, Any]) -> Optional[str]:
        """Load file content, optionally filtering to relevant sections"""
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            
            content = path.read_text(encoding='utf-8')
            
            # For very large files, extract only relevant sections
            if summary['lines'] > 500:
                content = self._extract_relevant_sections(content, summary)
            
            return content
        
        except Exception as e:
            logger.warning(f"Failed to load {file_path}: {e}")
            return None
    
    def _extract_relevant_sections(self, content: str, summary: Dict[str, Any]) -> str:
        """Extract only relevant sections from large files"""
        lines = content.splitlines()
        
        # Include file header (imports, module docstring)
        header_lines = min(50, len(lines))
        sections = ['\n'.join(lines[:header_lines])]
        sections.append('\n# ... (file truncated for context) ...\n')
        
        # Include class/function signatures (not full implementations)
        file_map = self.code_mapper.file_maps.get(summary['path'])
        if file_map:
            for cls in file_map.classes[:3]:  # Top 3 classes
                # Get class definition and method signatures
                class_lines = lines[cls.line_start-1:min(cls.line_start+10, len(lines))]
                sections.append('\n'.join(class_lines))
                sections.append('    # ... (methods omitted) ...\n')
            
            for func in file_map.functions[:5]:  # Top 5 functions
                # Get function signature
                func_lines = lines[func.line_start-1:min(func.line_start+5, len(lines))]
                sections.append('\n'.join(func_lines))
                sections.append('    # ... (implementation omitted) ...\n')
        
        return '\n'.join(sections)
    
    def build_minimal_context(self, task_desc: str, max_files: int = 3) -> str:
        """
        Build minimal context string for a task (for small prompts)
        
        Args:
            task_desc: Task description
            max_files: Maximum number of files to include
        
        Returns:
            Formatted context string
        """
        context_info = self.code_mapper.get_context_for_task(task_desc)
        
        sections = [f"# Context for: {task_desc}\n"]
        
        # Add file summaries (not full content)
        for i, (file_path, info) in enumerate(list(context_info['relevant_files'].items())[:max_files]):
            summary = info['summary']
            sections.append(f"\n## File {i+1}: {Path(file_path).name}")
            sections.append(f"Path: {file_path}")
            sections.append(f"Lines: {summary['lines']}")
            
            if summary['classes']:
                sections.append(f"Classes: {', '.join(summary['classes'][:5])}")
            
            if summary['functions']:
                sections.append(f"Functions: {', '.join(summary['functions'][:5])}")
            
            if summary['docstring']:
                sections.append(f"Description: {summary['docstring'][:100]}...")
        
        return '\n'.join(sections)
    
    def get_definition_context(self, name: str) -> Optional[str]:
        """
        Get context for a specific class or function
        
        Args:
            name: Name of class or function
        
        Returns:
            Code snippet with definition
        """
        results = self.code_mapper.find_definition(name)
        if not results:
            return None
        
        # Get first result
        result = results[0]
        file_path = result['file']
        line_start = result['line_start']
        line_end = result.get('line_end', line_start + 20)
        
        try:
            content = Path(file_path).read_text(encoding='utf-8')
            lines = content.splitlines()
            
            # Get definition with some context
            start = max(0, line_start - 5)
            end = min(len(lines), line_end + 5)
            
            snippet = '\n'.join(lines[start:end])
            
            return f"""# {result['type']}: {name}
# File: {file_path}:{line_start}

{snippet}
"""
        except Exception as e:
            logger.warning(f"Failed to get definition context: {e}")
            return None
    
    def get_dependency_context(self, module: str) -> Dict[str, Any]:
        """
        Get context about a module's usage
        
        Args:
            module: Module name
        
        Returns:
            Dictionary with usage information
        """
        files = self.code_mapper.find_usages(module)
        
        return {
            'module': module,
            'used_in': files,
            'usage_count': len(files)
        }
    
    def estimate_context_size(self, task: Dict[str, Any]) -> Dict[str, int]:
        """
        Estimate context size without loading files
        
        Args:
            task: Task dictionary
        
        Returns:
            Dictionary with estimates
        """
        task_desc = task.get('desc', '')
        context_info = self.code_mapper.get_context_for_task(task_desc)
        
        estimates = {
            'relevant_files': len(context_info['relevant_files']),
            'estimated_tokens': 0,
            'estimated_chars': 0
        }
        
        for file_path, info in context_info['relevant_files'].items():
            summary = info['summary']
            file_map = self.code_mapper.file_maps.get(file_path)
            
            if file_map:
                # Rough estimate: 1 line ≈ 40 chars ≈ 10 tokens
                estimates['estimated_chars'] += file_map.size
                estimates['estimated_tokens'] += file_map.lines * 10
        
        return estimates


def create_focused_prompt(task: Dict[str, Any], context: Dict[str, Any]) -> str:
    """
    Create a focused prompt for LLM with minimal context
    
    Args:
        task: Task dictionary
        context: Context from AgentContextBuilder
    
    Returns:
        Formatted prompt string
    """
    sections = []
    
    # Task description
    sections.append(f"# Task: {task.get('desc', '')}\n")
    
    # Context summary
    sections.append(f"## Context")
    sections.append(f"Keywords: {', '.join(context['keywords'])}")
    sections.append(f"Relevant files: {len(context['files'])}")
    sections.append(f"Total tokens: {context['total_tokens']}\n")
    
    # File contents
    sections.append("## Relevant Code\n")
    for file_info in context['files']:
        sections.append(f"### {Path(file_info['path']).name}")
        sections.append(f"```{file_info['summary']['language']}")
        sections.append(file_info['content'])
        sections.append("```\n")
    
    # Instructions
    sections.append("## Instructions")
    sections.append("Implement the required changes based on the task description.")
    sections.append("Focus only on the relevant files shown above.")
    sections.append("Provide clear, working code that follows best practices.\n")
    
    return '\n'.join(sections)


# Example usage
if __name__ == "__main__":
    from code_map import CodeMapper
    
    # Initialize
    mapper = CodeMapper(roots=["."])
    mapper.scan_codebase()
    
    # Create context builder
    builder = AgentContextBuilder(mapper, None)
    
    # Build context for task
    task = {'desc': 'Implement user authentication'}
    context = builder.build_context(task)
    
    print(f"Context built:")
    print(f"  Files: {len(context['files'])}")
    print(f"  Tokens: {context['total_tokens']}")
    print(f"  Keywords: {context['keywords']}")
    
    # Create prompt
    prompt = create_focused_prompt(task, context)
    print(f"\nPrompt length: {len(prompt)} chars")

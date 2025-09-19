# file: prompt_builder.py
#!/usr/bin/env python3
"""Prompt building service for AI interactions."""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds prompts for AI interactions."""
    
    @staticmethod
    def build_task_prompt(task: Dict[str, Any], basedir: str = "", out_path: str = "", knowledge_text: str = "", include_text: str = "") -> str:
        """Build a prompt for a task execution."""
        parts = [
            "Instructions:",
            "A. Produce one or more complete, runnable code files.",
            "B. For each file, begin with the appropriate comment directive based on the file type: use '# file: <filename>' for Python, '// file: <filename>' for JavaScript/TypeScript, '// file: <filename> ' for other languages if needed. Use only filenames provided in the task; do not guess or infer. Do not include the file path.",
            "C. Immediately following that line, emit the full file content—including all imports, definitions, and boilerplate—so it can be copied into a file and run. Ensure the content uses the correct syntax and comment styles for the file type.",
            "D. If multiple files are needed, separate them with a single blank line.",
            "E. You can find the <filename.ext> in the Included files knowledge. You will need to modify these files based on the task description and task knowledge.",
            "F. Use the Task description, included knowledge, and any task-specific knowledge when generating each file.",
            "G. Verify that every file is syntactically correct, self-contained, and immediately executable.",
            "H. Add a comment with the original file length and the updated file length.",
            "I. Make the changes needed to achieve the requested goal.",
            "J. Review the task description and task knowledge to ensure compliance with requirements and instructions.",
            "K. Enhance parse_llm_output to include filename, originalfilename, matched filename.",
            "L. Task description: " + task['desc'],
            "M. The # file: <filename> must not include the path",
            "N. The temp output file is here " + out_path + " we stash the ai_output here.",
            ""
        ]
        # New instruction: mark newly created files
        idx = parts.index("")  # insert before the first blank line
        parts.insert(idx, "O. If a file is newly created (did not exist before), append 'NEW' after the filename in the file directive, e.g., '# file: <filename> NEW' or '// file: <filename> NEW' for JS.")
        parts.insert(idx + 1, "P. If the request/ask is to delete a file, append 'DELETE' after the filename in the file directive, using the appropriate comment style, e.g., '# file: <filename> DELETE' for Python or '// file: <filename> DELETE' for JavaScript/TypeScipt. Do not include any content after the directive for deleted files.")
        
        if include_text:
            parts.append(f"Q. Review included files:\n{include_text}")
        
        if knowledge_text:
            parts.append(f"R. Complete each of the tasks/goals/requests in task knowledge:\n{knowledge_text}")
        
        parts.append("S. Verify that your response complies with each of the rules and requirements detailed in A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R.")
        parts.append(f"T. Produce one or more complete, runnable code files. Do not truncate. Handle file types appropriately: Python uses # comments, JavaScript uses //")
        return "\n".join(parts)


    @staticmethod
    def build_task_promptb(task: Dict[str, Any], basedir: str = "", out_path: str = "", knowledge_text: str = "", include_text: str = "") -> str:
        """Build a prompt for a task execution."""
        parts = [
            "Instructions:",
            "A. Produce one or more complete, runnable code files.",
            "B. For each file, begin with the appropriate comment directive based on the file type: use '# file: <filename>' for Python, '// file: <filename>' for JavaScript/TypeScript, '// file: <filename> ' for other languages if needed. Use only filenames provided in the task; do not guess or infer. Do not include the file path.",
            "C. Immediately following that line, emit the full file content—including all imports, definitions, and boilerplate—so it can be copied into a file and run. Ensure the content uses the correct syntax and comment styles for the file type.",
            "D. If multiple files are needed, separate them with a single blank line.",
            "E. You can find the <filename.ext> in the Included files knowledge. You will need to modify these files based on the task description and task knowledge.",
            "F. Use the Task description, included knowledge, and any task-specific knowledge when generating each file.",
            "G. Verify that every file is syntactically correct, self-contained, and immediately executable.",
            "H. Add a comment with the original file length and the updated file length.",
            "I. Make the changes needed to achieve the requested goal.",
            "J. Review the task description and task knowledge to ensure compliance with requirements and instructions.",
            "K. Enhance parse_llm_output to include filename, originalfilename, matched filename.",
            "L. Task description: " + task['desc'],
            "M. The # file: <filename> must not include the path",
            "N. The temp output file is here " + out_path + " we stash the ai_output here.",
            ""
        ]
        # New instruction: mark newly created files
        idx = parts.index("")  # insert before the first blank line
        parts.insert(idx, "O. If a file is newly created (did not exist before), append 'NEW' after the filename in the file directive, e.g., '# file: <filename> NEW' or '// file: <filename> NEW' for JS.")
        parts.insert(idx + 1, "P. For files to be deleted, append 'DELETE' after the filename in the file directive, using the appropriate comment style, e.g., '# file: <filename> DELETE' for Python or '// file: <filename> DELETE' for JavaScript. Do not include any content after the directive for deleted files.")
        
        if include_text:
            parts.append(f"Q. Review included files:\n{include_text}")
        
        if knowledge_text:
            parts.append(f"R. Complete each of the tasks/goals/requests in task knowledge:\n{knowledge_text}")
        
        parts.append("S. Verify that your response complies with each of the rules and requirements detailed in A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R.")
        parts.append(f"T. Produce one or more complete, runnable code files. Do not truncate. Handle file types appropriately: Python uses # comments, JavaScript uses //")
        return "\n".join(parts)

# original file length: 113 lines
# updated file length: 143 lines
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
            "B. For each file, begin with exactly:  # file: <filename>  (use only filenames provided in the task; do not guess or infer).",
            "C. Immediately following that line, emit the full file content—including all imports, definitions, and boilerplate—so it can be copied into a file and run.",
            "D. If multiple files are needed, separate them with a single blank line.",
            "E. You can find the <filename.ext> in the Included files knowledge. You will need to modify these files based on the task description and task knowledge.",
            "F. Use the Task description, included knowledge, and any task-specific knowledge when generating each file.",  # Added missing F instruction
            "G. Verify that every file is syntactically correct, self-contained, and immediately executable.",
            "H. Add a comment with the original file length and the updated file length.",
            "I. Make the changes needed to achieve the requested goal.",  # Fixed typo "achive" to "achieve"
            "J. Review the task description and task knowledge to ensure compliance with requirements and instructions.",
            "K. Enhance parse_llm_output to include filename, originalfilename, matched filename.",
            "L. Task description: " + task['desc'],
            "M. The base directory is " + basedir,
            "N. The temp output file is here " + out_path + " we stash the ai_output here.",
            ""
        ]
        
        if include_text:
            parts.append(f"O. Review included files:\n{include_text}")
        
        if knowledge_text:
            parts.append(f"P. Complete each of the tasks/goals/requests in task knowledge:\n{knowledge_text}")
        
        parts.append("Q. Review your answer from M with each of the rules and requirements in A, B, C, D, E, F, G, H, I, J, L, M, N, and O. ")
        return "\n".join(parts)
# original file length: 35 lines
# updated file length: 35 lines
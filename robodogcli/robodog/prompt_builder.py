# file: prompt_builder.py
#!/usr/bin/env python3
"""Prompt building service for AI interactions."""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Builds prompts for AI interactions.
    Note: Enforced file directive syntax: All outputs use '# <file/Command>: <filename> <NEW/UPDATE/COPY/DELETE>' format
    for all file types. Prefix always uses "#" for simplicity across all languages.
    """

    @staticmethod
    def build_task_prompt(
        task: Dict[str, Any],
        basedir: str = "",
        out_path: str = "",
        knowledge_text: str = "",
        include_text: str = "",
        diff: bool = False
    ) -> str:
        """Build a prompt for a task execution (with relative paths for NEW files). Enhanced with unified diff support."""
        if diff:
            return PromptBuilder._build_diff_task_prompt(task, basedir, out_path, knowledge_text, include_text)
        else:
            return PromptBuilder._build_full_file_task_prompt(task, basedir, out_path, knowledge_text, include_text)

    @staticmethod
    def _build_full_file_task_prompt(
        task: Dict[str, Any],
        basedir: str = "",
        out_path: str = "",
        knowledge_text: str = "",
        include_text: str = ""
    ) -> str:
        """Build a prompt for full file output (original behavior)."""
        parts = [
            "Instructions:",
            "A. Produce one or more complete, runnable code files.",
            "B. For each file, begin with the consistent directive format '# file: <filename> <NEW/UPDATE/COPY/DELETE>' using '#' prefix for all file types (Python, JS/TS, SQL, C/C++, Java, PHP, Go, etc.). Use only filenames provided in the task; do not guess or infer. Do not include the file path for existing files.",
            "C. Immediately following that line, emit the full file content—including all imports, definitions, and boilerplate—so it can be copied into a file and run. Ensure the content uses the correct syntax and comment styles for the file type.",
            "D. If multiple files are needed, separate them with a single blank line.",
            "E. You can find the <filename.ext> in the Included files knowledge. You will need to modify these files based on the task description and task knowledge.",
            "F. Use the Task description, included knowledge, and any task-specific knowledge when generating each file.",
            "G. Verify that every file is syntactically correct, self-contained, and immediately executable.",
            "H. Verify the original file length and the updated file length. ensure that no content was dropped.",
            "I. Make the changes needed to achieve the requested goal.",
            "J. Review the task description and task knowledge to ensure compliance with requirements and instructions.",
            "K. Enhance parse_llm_output to include filename, originalfilename, matched filename.",
            "L. Task description: " + task.get("desc", ""),
            "M. The # file: <filename> must not include the path for updates.",
            "N. The temp output file is here " + out_path + " we stash the ai_output here.",
            ""
        ]
        
        idx = parts.index("")
        parts.insert(
            idx,
            "O. If a file is newly created (did not exist before), append 'NEW' after the directive and include its path *relative to the task's base directory*. "
            "Example: '# file: subdir/new_module.py NEW'."
        )
        
        parts.insert(idx + 1,
            "P. If the request/ask is to delete a file, append 'DELETE' after the filename in the file directive, using the appropriate comment style, "
            "e.g., '# file: <filename> DELETE' for Python or '// file: <filename> DELETE' for JavaScript/TypeScript. "
            "Do not include any content after the directive for deleted files. IMPORTANT: When the task involves reviewing folder structure or marking/deleting files, "
            "always use the DELETE tag for files to be removed, and ensure no code content follows the directive."
        )
        
        parts.insert(idx + 2,
            "Q. Before generating code, always generate or update a 'plan.md' file using the specialized planning prompt (build_plan_prompt). "
            "This plan should outline high-level summary, key changes, and next steps. . "
            "Use 'NEW' if creating or 'UPDATE' if modifying plan.md."
        )

        parts.insert(idx + 3,
            "R. For Salesforce tasks: Generate valid Apex classes (.cls) with proper structure (public class, methods with @AuraEnabled if needed). "
            "For metadata files (.object-meta.xml), ensure correct XML format compliant with Salesforce schema. Include examples in prompts for Apex syntax and XML structure. "
            "Validate syntax for .cls (e.g., public virtual class with constructors) and metadata (e.g., <CustomObject> root)."
        )

        if include_text:
            parts.append(f"S. Review included files:\n{include_text}")

        if knowledge_text:
            parts.append(f"T. Complete each of the tasks/goals/requests in task knowledge:\n{knowledge_text}")

        parts.append(
            "U. Verify that your response complies with each of the rules and requirements detailed in A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T."
        )
        parts.append(
            "V. Produce one or more complete, runnable code files. Do not truncate. Handle file types appropriately using the consistent '# <file/Command>: <filename> <action>' syntax "
            "for all files: always use '#' prefix (e.g., for Python, JS, etc.), overriding any type-specific variations. For deletion tasks, strictly follow P: use exact filenames, no content after directive. "
            "For new files, include the relative path as specified in O. Always reference the generated plan.md for structured, efficient execution. "
            "For Salesforce: Ensure Apex .cls files compile without errors; metadata XML must be schema-valid."
        )

        return "\n".join(parts)

    @staticmethod
    def _build_diff_task_prompt(
        task: Dict[str, Any],
        basedir: str = "",
        out_path: str = "",
        knowledge_text: str = "",
        include_text: str = ""
    ) -> str:
        """Build a prompt for unified diff output format."""
        parts = [
            "Instructions (Unified Diff Mode):",
            "A. Produce unified diff patches for existing files, or complete files for NEW/DELETE operations.",
            "B. For each file, begin with the consistent directive format '# file: <filename> <NEW/UPDATE/COPY/DELETE>' using '#' prefix for all file types.",
            "C. For UPDATE operations: After the directive, provide a unified diff (like `git diff` or `diff -u`) showing only the changes needed.",
            "D. For NEW operations: Provide the complete file content as normal after the directive.",
            "E. For DELETE operations: Only provide the directive line with DELETE flag, no content.",
            "F. For COPY operations: Provide the directive with source and destination information.",
            "G. Unified diff format should include proper headers (--- a/filename, +++ b/filename) and hunks (@@ lines).",
            "H. Use standard diff format: lines starting with '-' for deletions, '+' for additions, ' ' (space) for context.",
            "I. Include sufficient context lines (typically 3-7 lines) around changes for accurate patching.",
            "J. If multiple files are needed, separate them with a single blank line.",
            "K. You can find the <filename.ext> in the Included files knowledge. Analyze these files to generate precise diffs.",
            "L. Use the Task description, included knowledge, and any task-specific knowledge when generating diffs.",
            "M. Verify that your diffs are syntactically correct and will apply cleanly to the original files.",
            "N. Make only the minimal changes needed to achieve the requested goal - this is the key advantage of diff mode.",
            "O. Task description: " + task.get("desc", ""),
            "P. The # file: <filename> must not include the path for updates.",
            "Q. The temp output file is here " + out_path + " we stash the ai_output here.",
            ""
        ]

        idx = parts.index("")
        parts.insert(
            idx,
            "R. If a file is newly created (did not exist before), append 'NEW' after the directive and include its path *relative to the task's base directory*. "
            "Provide complete file content for NEW files, not diffs. Example: '# file: subdir/new_module.py NEW'."
        )

        parts.insert(idx + 1,
            "S. For DELETE operations, append 'DELETE' after the filename in the file directive. "
            "Do not include any content after the directive for deleted files."
        )

        parts.insert(idx + 2,
            "T. Before generating diffs, always generate or update a 'plan.md' file using the specialized planning prompt. "
            "Use 'NEW' if creating or 'UPDATE' if modifying plan.md."
        )

        parts.insert(idx + 3,
            "U. For Salesforce tasks: Generate valid unified diffs for Apex classes (.cls) and metadata files (.object-meta.xml). "
            "Ensure diffs maintain proper XML structure and Apex syntax."
        )

        if include_text:
            parts.append(f"V. Review included files for diff generation:\n{include_text}")

        if knowledge_text:
            parts.append(f"W. Complete each of the tasks/goals/requests in task knowledge:\n{knowledge_text}")

        parts.append(
            "X. Verify that your response complies with each of the rules and requirements detailed above."
        )

        parts.append(
            "Y. Produce unified diffs for existing files and complete files for NEW operations. Use minimal, targeted changes. "
            "Handle file types appropriately using the consistent '# file: <filename> <action>' syntax. "
            "For Salesforce: Ensure diff patches maintain schema compliance and syntax validity."
        )

        return "\n".join(parts)

    @staticmethod
    def build_plan_prompt(
        task: Dict[str, Any],
        basedir: str = "",
        out_path: str = "",
        knowledge_text: str = "",
        include_text: str = ""
    ) -> str:
        """Build a concise prompt specifically for generating or updating plan.md. Enhanced for better task execution of the changes."""
        parts = [
            "Generate a structured plan.md that outlines only the required high-level steps to implement the requested changes. Do not suggest performance or architectural optimizations.",
            "A. Output only the content for plan.md: Start with a high-level task summary based on the description.",
            "B. Analyze included files and knowledge to outline key changes to files/code structure. ",
            "C. List actionable next steps in numbered bullets",
            "E. Keep it focused, brief, and no file directives, no extra commentary. Aim for under 500 tokens.",
            "F. Use the task description, knowledge, and includes to inform a effective plan. ",
            "G. No performance tuning, code optimization, or best-practice editorializing—only list the files to change and the sequential steps needed.",
            # Added Salesforce-specific guidance for plans
            "H. For Salesforce tasks: Note specific files like .cls (Apex classes) and .object-meta.xml; outline metadata schema compliance and Apex syntax validation.",
            "Task Description: " + task.get("desc", ""),
            "Knowledge (knowledge_tokens: " + str(len(knowledge_text.split()) if knowledge_text else 0) + "): " + (knowledge_text or "None"),
            "Included Files Summary (include_tokens: " + str(len(include_text.split()) if include_text else 0) + "): " + (include_text or "None"),
            "Output Path: " + out_path + " (Estimate plan_tokens here for logging).",
            "End with the plan content only. Ensure the plan enhances overall task execution speed and efficiency."
        ]
        return "\n".join(parts)
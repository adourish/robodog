# file: todo.md

# Project Plan: Enhance parse_llm_output in ParseService
# This todo.md was generated on 2023-10-05 as part of planning mode only.
# Sequencing details: Tasks are grouped by parsing enhancement steps, with dependencies noted.
# Overview: This plan outlines the steps to enhance ParseService's parse_llm_output method to include filename, originalfilename, matchedfilename fields, using _file_service.resolve_path for smart matching, and adding a new_file indicator. All tasks start disabled to avoid accidental execution. Plan is in planning mode — no code changes yet.

[-][-] Review current parse_llm_output implementation in parse_service.py
  out: temp\out-parse_service_review.txt
  include: pattern=*robodogcli*robodog*parse_service.py recursive
  ```knowledge
  Details: Analyze the existing parse_llm_output method. Note current inputs (ai_out, base_dir) and outputs (list of dicts with filename, content, tokens). Identify where to add new fields: filename (existing), originalfilename (copy of filename), matchedfilename (via resolve_path). Ensure no breaking changes.
  ```

[-][-] Modify parse_llm_output to add originalfilename and matchedfilename fields
  out: temp\out-modify_parse_fields.txt
  include: pattern=*robodogcli*robodog*parse_service.py recursive
  ```knowledge
  Details: Update the method to copy filename to originalfilename. For matchedfilename, call self._file_service.resolve_path on filename (passed from TodoService). If no match, set matchedfilename to None and add a new_file boolean property explaining it might be a new file.
  Dependency: Must first have access to _file_service (inject via TodoService).
  ```

[-][-] Handle injection of _file_service into ParseService for resolve_path access
  out: temp\out-inject_file_service.txt
  include: pattern=*robodogcli*robodog*parse_service.py recursive
  ```knowledge
  Details: Since ParseService doesn't have _file_service, modify ParseService init to accept file_service param. Update TodoService calls to parse_llm_output to pass self._file_service. This allows smart matching in parse_llm_output.
  ```

[-][-] Test enhancement with sample LLM output
  out: temp\out-test_parse_output.txt
  include: pattern=*robodogcli*robodog*parse_service.py recursive
  ```knowledge
  Details: Create unit tests or manual checks with mock LLM output containing files. Verify matchedfilename matches via resolve_path, or new_file indicator when no match. Ensure output list includes all new fields without errors.
  Dependency: After modifications to parse_llm_output and file_service injection.
  ```

[-][-] Update calling code in TodoService to handle new parse_llm_output fields
  out: temp\out-update_calling_code.txt
  include: pattern=*robodogcli*robodog*todo.py recursive
  ```knowledge
  Details: Review _process_one, _process_manual_done, etc., to handle parsed_files with new fields (e.g., log matchedfilename or new_file status). No removal of existing logic.
  Dependency: After core parse_llm_output changes.
  ```

# file: parse_service.py

# This is a placeholder for the enhanced parse_service.py code.
# Original plan: Enhance parse_llm_output, but planning mode only — no code yet. Ignored per instructions. 

# file: todo.py

# This is a placeholder for any needed changes to todo.py for file_service injection.
# Original plan: Modifications for dependency on ParseService changes, but planning mode only — no code yet. Ignored per instructions.
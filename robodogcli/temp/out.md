# file: todo.md
# original file length: 0 lines
# updated file length: 45 lines
---
base: /path/to/robodogcli
---

- [-][-] Refactor base.py: Extract common utilities into separate service classes for better modularity
  include: pattern=*robodogcli*robodog*.py recursive
  out: base_refactored.py
  ```knowledge
  This task involves splitting the current BaseService and TaskBase classes into more granular services.
  Remove unused imports like Dict, Any from typing if not needed after refactoring.
  Ensure backward compatibility by maintaining the same interfaces.
  Update any references in other files that use BaseService properties.
  ```

- [-][-] Refactor cli.py: Separate command handling logic from main interaction loop
  include: pattern=*robodogcli*robodog*.py recursive
  out: cli_refactored.py
  ```knowledge
  Extract the command parsing and execution into a dedicated CommandHandler class.
  Move service initialization into a separate function for better organization.
  Reduce the complexity of the main() function by delegating setup to sub-functions.
  Update logging integration to use the new handler structure.
  ```

- [-][-] Refactor service.py: Break down the large RobodogService class into smaller, focused services
  include: pattern=*robodogcli*robodog*.py recursive
  out: service_refactored.py
  ```knowledge
  Split into separate classes like ModelManager, ConfigManager, and ApiClient.
  Move file operations to a dedicated FileOpsService.
  Keep the core ask method intact but delegate other responsibilities.
  Ensure all existing parameters and methods remain functional.
  ```

- [-][-] Refactor file_service.py: Optimize path resolution and file reading performance
  include: pattern=*robodogcli*robodog*.py recursive
  out: file_service_refactored.py
  ```knowledge
  Add caching for resolved paths to reduce repeated filesystem calls.
  Improve error handling for binary files and expand safe_read_file capabilities.
  Implement asynchronous file operations where possible using ThreadPoolExecutor.
  Update logging to include more granular debug information.
  ```

- [-][-] Refactor file_watcher.py: Implement more robust file change detection
  include: pattern=*robodogcli*robodog*.py recursive
  out: file_watcher_refactored.py
  ```knowledge
  Add support for watching multiple directories.
  Improve ignore mechanism to handle more complex cases.
  Use polling less frequently for better performance.
  Integrate better with the file_service for callbacks.
  ```

- [-][-] Refactor mcphandler.py: Modularize HTTP and raw MCP command handling
  include: pattern=*robodogcli*robodog*.py recursive
  out: mcphandler_refactored.py
  ```knowledge
  Separate HTTP request handling from raw MCP dispatch logic.
  Create dedicated classes like HttpHandler and McpDispatcher.
  Improve error responses and authentication checks.
  Ensure CORS and token validation remain secure.
  ```

- [-][-] Refactor models.py: Add validation schemas and improve data models
  include: pattern=*robodogcli*robodog*.py recursive
  out: models_refactored.py
  ```knowledge
  Extend BaseModel classes with additional validation rules.
  Add new models for tasks, configs, and responses as needed.
  Implement custom validators for common patterns.
  Keep TaskModel and Change models backward-compatible.
  ```

- [-][-] Refactor parse_service.py: Enhance LLM output parsing with more formats
  include: pattern=*robodogcli*robodog*.py recursive
  out: parse_service_refactored.py
  ```knowledge
  Add support for additional formats like CSV or custom structured text.
  Improve error handling and fallback mechanisms.
  Optimize parsing performance for larger outputs.
  Add methods for validating parsed content syntactically.
  ```

- [-][-] Refactor prompt_builder.py: Create template-based prompt building
  include: pattern=*robodogcli*robodog*.py recursive
  out: prompt_builder_refactored.py
  ```knowledge
  Implement a template system for different types of prompts.
  Add dynamic variable substitution for task-specific data.
  Separate static guide text into configurable templates.
  Maintain the current build_task_prompt method signature.
  ```

- [-][-] Refactor task_manager.py: Improve task state management and concurrency
  include: pattern=*robodogcli*robodog*.py recursive
  out: task_manager_refactored.py
  ```knowledge
  Add support for task dependencies and parallel execution where safe.
  Enhance task summary formatting with more metrics.
  Implement better error handling during task transitions.
  Integrate with threading for non-blocking operations.
  ```

- [-][-] Refactor task_parser.py: Add advanced task dependency resolution
  include: pattern=*robodogcli*robodog*.py recursive
  out: task_parser_refactored.py
  ```knowledge
  Implement dependency checking based on task descriptions.
  Add support for parsing nested sub-tasks.
  Improve front-matter base directory parsing.
  Cache parsed tasks for faster reloading.
  ```

- [-][-] Refactor todo.py: Implement user-defined scripts and custom task types
  include: pattern=*robodogcli*robodog*.py recursive
  out: todo_refactored.py
  ```knowledge
  Add custom task types beyond standard To Do/Doing/Done.
  Implement script execution for certain tasks.
  Enhance watch loop with user-definable callbacks.
  Improve base directory parsing and path resolution.
  Update token comparisons and completeness checks to be more flexible.
  ```
# file: todo.md
---
base: c:\projects\robodog
---

- [-][-] Identify and analyze the current robodog UI structure to determine where and how to integrate a new /todo command for generating todo.md project plans.
  - include pattern=*robodogcli*robodog*.py recursive
  - out: ui_analysis.md
```knowledge
This task involves inspecting the UI code to understand the command handling system, like how other slash commands are implemented in the robodogcli/robodog codebase. Focus on files like main.py or ui.py that handle user inputs and commands. The output should detail integration points, such as hooking into the command parser or UI event handlers.
```

- [-][-] Design the /todo command syntax and behavior, specifying how "something" translates into a structured todo.md plan with multiple tasks.
  - include pattern=*robodogcli*robodog*.py recursive
  - out: command_design.md
```knowledge
Design phase: Define the command as /todo <description>, where <description> is parsed to break into tasks, assign out files (e.g., code files to modify), and include knowledge blocks. Group tasks logically, such as UI changes, processing logic, and output formatting. Ensure it aligns with the todoh.py system for handling task status and flags.
```

- [-][-] Implement the UI handler for the /todo command, updating the robodog UI to accept and process the command input.
  - include pattern=*robodogcli*robodog*.py recursive
  - out: ui_handler.py
```knowledge
Modify UI files (like ui.py in robodogcli/robodog) to add a new method that listens for /todo commands. When parsed, trigger the plan generation, passing the description to a new service method. Ensure it integrates with existing todo.md loading/reloading logic in todo.py.
```

- [-][-] Develop the plan generation logic that takes user input from /todo and converts it into a structured todo.md format with tasks, includes, outs, and knowledge blocks.
  - include pattern=*robodogcli*robodog*.py recursive
  - out: plan_generator.py
```knowledge
Extend todo.py with a new method to generate the plan: parse the input description into multiple tasks based on grouping (e.g., split by keywords like 'design', 'implement'). For each task, auto-assign out files (like modifying existing code files), include the recursive pattern, and populate knowledge blocks with AI-suggested details. Output as a new todo.md or append to existing.
```

- [-][-] Test the /todo command integration by running sample inputs and verifying the generated todo.md matches the required format (disabled tasks, includes, outs, knowledge).
  - include pattern=*robodogcli*robodog*.py recursive
  - out: integration_test.py
```knowledge
Testing phase: Create unit tests or manual tests in robodogcli/robodog/test_ui.py to simulate /todo inputs. Validate that tasks are created with [-][-] status, appropriate includes, out files (e.g., pointing to code changes in rododogcli), and knowledge blocks contain relevant details based on include pattern matches.
```

- [-][-] Document and finalize the complete process for generating project plans via /todo, ensuring all tasks are disabled by default and follow the specified structure.
  - include pattern=*robodogcli*robodog*.py recursive
  - out: documentation.md
```knowledge
Final documentation: Summarize the steps, including code changes in files like todo.py for plan generation, UI integration in ui.py for command handling, and examples of /todo usage. Ensure the generated plans always use [-][-] or [x][x] for disabled tasks, with recursive includes on *robodogcli*robodog*.py patterns, and detailed knowledge blocks for each task's purpose.
```

# original file length: 0
# updated file length: 32
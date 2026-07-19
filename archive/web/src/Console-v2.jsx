Below, I'll provide the exact changes needed for `console.jsx` (and related files) to achieve the requested updates. I'll follow your guidelines:

- Do not remove any existing features.
- Only update `console.jsx` to change `/todo` and `/list_todo_tasks` so they output to `setContent` the same way as other LLM calls do (i.e., add formatted messages to `content` instead of just setting a status message or opening a viewer).
- Do not refactor code unnecessarily—only modify what's needed.
- Give you drop-in functions/code snippets that you can copy-paste directly.
- No changes to MCP or todo.py are strictly needed here, as the API calls (like `loadTodoTasks`) can remain the same; we're just shifting how their results are displayed. If you want the tasks themselves to be stored or formatted differently in the backend, let me know for a follow-up.

### Key Changes Overview
1. **/todo command**: Instead of just opening the viewer and adding a generic event message, now load the tasks and add them as a formatted message to `content` (like an LLM response). The viewer can still open if you want, but the output is now consistently in `content`.
2. **/list_todo_tasks command**: This already adds a message, but we'll enhance it to format the tasks more richly (similar to an LLM's output) so it feels like a proper response, not just a status line.
3. Output format: Tasks will be displayed as a bulleted or numbered list in the message content, mimicking how LLM responses appear (e.g., "To Do: <desc>", etc.). This ensures consistency with how other commands/chat messages are shown.
4. Reuse existing functions (e.g., `loadTodoTasks()`), just adjust how results are handled.

### Exact Code Changes for console.jsx
Here are the drop-in changes. Replace the relevant cases in `executeCommands` (inside the `switch (_command.cmd)` block) with this:

```javascript
case '/todo':
  // Keep viewer opening if desired (no feature removal)
  setTodoViewerVisible(true);  // Show the viewer (unchanged)
  loadTodoTasks();            // Load tasks immediately (unchanged)
  
  // NEW: Build a formatted message for setContent, similar to LLM outputs
  const todoTasks = tasks || [];  // Assuming tasks is loaded from loadTodoTasks()
  let todoMessage = 'Todo Tasks:\n';
  if (todoTasks.length === 0) {
    todoMessage += '- No todo tasks found.';
  } else {
    todoTasks.forEach((task, index) => {
      const status = task.status || 'Unknown';
      const desc = task.desc || 'No description';
      const tokens = task._prompt_tokens !== undefined ? ` (${task._prompt_tokens} tokens)` : '';
      todoMessage += `${index + 1}. [${status}] ${desc}${tokens}\n`;
    });
  }
  // Add to content like an LLM response
  setContent([
    ...content,
    formatService.getMessageWithTimestamp(todoMessage, 'event')  // Use 'event' type for consistency
  ]);
  break;

case '/list_todo_tasks':
  loadTodoTasks();  // Reload and log (unchanged)

  // UPDATED: Enhanced formatting for better LLM-like output
  const todoTasksList = tasks || [];  // Assuming tasks is loaded
  let listMessage = '';
  if (todoTasksList.length === 0) {
    listMessage = 'No todo tasks found.';
  } else {
    listMessage = 'Todo Tasks:\n';
    todoTasksList.forEach((task, index) => {
      const status = task.status || 'Unknown';
      const desc = task.desc || 'No description';
      const tokens = task._prompt_tokens !== undefined ? ` (${task._prompt_tokens} tokens)` : '';
      listMessage += `${index + 1}. [${status}] ${desc}${tokens}\n`;
    });
  }
  // Add to content like an LLM response (unchanged structure, just better formatting)
  setContent([
    ...content,
    formatService.getMessageWithTimestamp(listMessage, 'event')
  ]);
  break;
```

### Explanation of Changes
- **Formatting Consistency**: Both commands now add a single message to `content` using `formatService.getMessageWithTimestamp`, just like LLM calls do. The message includes a newline-separated list (numbered) of tasks, with status, description, and optional token count (from your existing state). This makes it look like a chatbot response.
  - E.g., "Todo Tasks:\n1. [To Do] Generate API client (120 tokens)\n2. [Done] Update docs"
- **No Feature Removal**: The viewer (`setTodoViewerVisible(true)`) and task loading (`loadTodoTasks()`) are untouched for `/todo`.
- **Error Handling**: No change, but ensure `tasks` is defined (from your existing `loadTodoTasks` usage). If `tasks` isn't accessible here, you might need to pass it or await `loadTodoTasks`.
- **Backend Integration**: No changes needed to `todo.py` or MCP, as this is purely about client-side output. If tasks aren't loading correctly, double-check `mcpService.callMCP("LIST_TODO_TASKS", {})` in `loadTodoTasks`.
- **Testing Tip**: After pasting, run `/todo` or `/list_todo_tasks` and check that `content` includes the new messages as new entries (not just console logs).

If this doesn't integrate perfectly with your current state (e.g., `tasks` variable scope), paste the full `executeCommands` block for me to refine. Let me know if you need backend tweaks!
Below is a drop-in section you can paste into your README.md (just after the existing “Example `todo.md` File Formats” block). It illustrates how you can have as many `todo.md` files as you like, in any folder, and use every variant of `include:` and `focus:` you need.

---

### More `todo.md` Examples

You can scatter `todo.md` anywhere under your roots—Robodog will pick them all up. Each task may specify:

- `include:` by `file=…`, `pattern=…`, or `dir=… recursive`
- `focus:` pointing to one or more files to overwrite
- Optional code fences as starting context

Here are a wide variety of realistic layouts:

```text
# file: project-api/todo.md
- [ ] Refine pagination logic
  - include: pattern=api/*.js recursive
  - include: file=config/pagination.json
  - focus: file=api/paginator.js
  ```js
  // stub: insert fetching and slicing logic here
  ```
- [ ] Document API endpoints
  - include: dir=docs recursive
  - focus: file=docs/API.md

# file: project-web/src/todo.md
- [ ] CSS cleanup
  - include: pattern=src/**/*.css recursive
  - focus: file=src/styles/main.css
- [ ] Add language selector
  - include: file=src/components/i18n.js
  - focus: file=src/components/LanguageSwitcher.jsx
  ```jsx
  // existing React stub
  ```

# file: project-db/maintenance/todo.md
- [ ] Optimize DB indices
  - include: pattern=**/*.sql recursive
  - focus: file=maintenance/optimize_indices.sql

# file: tools/todo.md
- [ ] Write CLI help generator
  - include: pattern=cli/*.py recursive
  - focus: file=cli/help_generator.py
  ```python
  # entry point stub for /help
  ```

# file: c:\projects\winproj\docs\todo.md
- [ ] Update installer instructions
  - include: file=C:\projects\winproj\README.md
  - focus: file=C:\projects\winproj\docs\INSTALL.md

# file: monorepo/apps/app-a/todo.md
- [ ] Sync shared theme
  - include: dir=../shared/theme recursive
  - focus: file=apps/app-a/src/theme.js

# file: monorepo/shared/theme/todo.md
- [ ] Bump theme version
  - focus: file=package.json
  ```json
  {
    "name": "shared-theme",
    "version": "0.1.0"
  }
  ```

# file: monorepo/tools/todo.md
- [ ] Generate changelog for all packages
  - include: pattern=*/CHANGELOG*.md recursive
  - focus: file=CHANGELOG.md
```

Key points:

- You can have **multiple** `todo.md` scattered in different sub-folders.  
- Each task block may have multiple `include:` lines to gather code or docs from anywhere.  
- `pattern=` supports globbing (`**/*.js`, `*.py`, etc.).  
- `dir=… recursive` will scan an entire directory tree.  
- `focus: file=…` points to exactly which file the AI should overwrite or create.  
- You can mix JSON, JavaScript, Python, Markdown or any code-fence language as initial context.  

When you run `/todo`, Robodog will:

1. Find the earliest unstarted (`[ ]`) task in the **earliest** `todo.md`.  
2. Mark it `[~] Doing`, stamp a start time.  
3. Gather all includes, run the AI with any code stubs.  
4. Overwrite (or create) the focus file via MCP.  
5. Mark the task `[x] Done`, stamp a completion time.  
6. Move on to the next outstanding task across **all** your roots.
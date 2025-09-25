# file: plan.md NEW
# Plan for Fixing Missing-File Read Errors

## High-level Summary  
Ensure robust handling of FileNotFoundError across file operations so missing files no longer crash the CLI.

## Key Changes  
- FileService.safe_read_file: add `except FileNotFoundError` to return `""` and log a warning.  
- FileService.search_files/find_matching_file: skip paths that don’t exist before attempting reads.  
- ParseService._enhance_parsed_object: if original file missing, set `original_content=""` and proceed without diff.  
- TodoService._gather_include_knowledge: wrap `svc.include` calls in try/catch to ignore missing files.  
- Add tests simulating missing FormInstanceTriggerHandler.cls and BundleInstanceTrigger.trigger to verify error is logged, not raised.

## Next Steps  
1. Modify `safe_read_file` to catch `FileNotFoundError` and return empty content.  
2. In `search_files` and `find_matching_file`, filter out non-existent `Path`s before safe_read calls.  
3. Update `ParseService` to default `orig=""` when safe_read returns `""`, skip diff generation.  
4. Wrap include/spec resolution in `TodoService` and `RobodogService.include` with existence checks.  
5. Write unit and integration tests for missing-file scenarios; add CI guard.  
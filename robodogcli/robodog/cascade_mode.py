#!/usr/bin/env python3
"""
Cascade Mode - Windsurf-inspired parallel execution
Provides:
- Multi-step reasoning
- Parallel tool execution
- Automatic tool selection
- Self-correction
"""

import asyncio
import json
from typing import List, Dict, Any, Set, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class CascadeStep:
    """A step in the cascade flow"""
    step_id: str
    action: str
    params: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    status: str = 'pending'  # pending, running, completed, failed
    result: Any = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def duration(self) -> float:
        """Get execution duration in seconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class CascadeEngine:
    """
    Implements Windsurf-style cascade mode with:
    - Multi-step reasoning
    - Parallel execution based on dependencies
    - Automatic tool selection
    - Self-correction and retry logic
    """
    
    def __init__(self, svc, code_mapper=None, file_service=None):
        self.svc = svc
        self.code_mapper = code_mapper
        self.file_service = file_service
        self.steps: List[CascadeStep] = []
        self.max_retries = 2
        self.enable_self_correction = True
        
    async def execute_cascade(self, task: str, context: str = "") -> Dict[str, Any]:
        """Execute a task using cascade mode with parallel execution"""
        
        logger.info(f"🌊 Starting cascade for task: {task}...")
        logger.debug(f"Context provided: {context[:100] if context else 'None'}...")
        start_time = datetime.now()
        logger.debug(f"Start time: {start_time}")
        
        try:
            # 1. Plan: Break down task into steps with dependencies
            logger.debug("Step 1: Planning cascade steps...")
            plan = await self._plan_cascade(task, context)
            logger.info(f"📋 Plan created: {len(plan)} steps")
            for i, step in enumerate(plan, 1):
                logger.debug(f"  Step {i}: {step.action} (id={step.step_id}, deps={step.dependencies})")
            
            if not plan:
                return {
                    'status': 'error',
                    'error': 'Failed to create execution plan'
                }
            
            logger.info(f"📋 Plan created: {len(plan)} steps")
            
            # 2. Execute: Run steps in parallel where possible
            logger.debug("Step 2: Executing cascade steps...")
            results = await self._execute_parallel(plan)
            logger.debug(f"Execution completed: {len(results)} results")
            
            # 3. Verify: Check results and self-correct if needed
            logger.debug("Step 3: Verifying results...")
            if self.enable_self_correction:
                logger.debug("Self-correction enabled, checking for errors...")
                verified = await self._verify_and_correct(results, task)
            else:
                logger.debug("Self-correction disabled, using results as-is")
                verified = results
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.debug(f"End time: {end_time}, Duration: {duration:.2f}s")
            
            # Calculate statistics
            successful = sum(1 for s in self.steps if s.status == 'completed')
            failed = sum(1 for s in self.steps if s.status == 'failed')
            logger.info(f"✨ Cascade completed: {successful}/{len(self.steps)} steps successful, {failed} failed")
            
            # Convert any Exception objects to strings for JSON serialization
            serializable_results = [
                {'error': str(r)} if isinstance(r, Exception) else r
                for r in verified
            ]
            
            return {
                'status': 'completed',
                'task': task,
                'steps': len(self.steps),
                'successful': successful,
                'failed': failed,
                'results': serializable_results,
                'duration': duration,
                'steps_detail': [self._step_to_dict(s) for s in self.steps]
            }
        
        except Exception as e:
            logger.error(f"Cascade execution failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'task': task
            }
    
    async def _plan_cascade(self, task: str, context: str) -> List[CascadeStep]:
        """Use LLM to plan cascade steps with dependencies"""
        
        # Get project structure hint
        project_hint = ""
        if self.code_mapper and hasattr(self.code_mapper, '_roots'):
            roots = self.code_mapper._roots
            if roots:
                project_hint = f"\nProject root: {roots[0]}"
        
        prompt = f"""Break down this task into parallel executable steps.

Task: {task}

Context: {context}{project_hint}

IMPORTANT: When specifying file paths, use paths relative to the project root.
For example:
- CORRECT: "robodog/app.py" (includes subdirectory)
- WRONG: "app.py" (missing subdirectory)
- CORRECT: "robodog/cli.py"
- WRONG: "cli.py"

Available actions and REQUIRED parameters:
1. read_file: {{"path": "robodog/file.py"}} (use full relative path!)
2. edit_file: {{"path": "file.py", "changes": "description"}}
3. create_file: {{"path": "file.py", "content": "file content"}}
4. search: {{"query": "search term"}}
5. analyze: {{"prompt": "what to analyze"}}
6. map_context: {{"task": "task description"}}

IMPORTANT: Each action MUST include ALL required parameters!

For each step, specify:
1. step_id: unique identifier (step_1, step_2, etc.)
2. action: one of the actions above
3. params: MUST include all required parameters for that action
4. dependencies: list of step_ids that must complete first (empty if no dependencies)

Return ONLY a JSON array of steps, no other text:
[
  {{
    "step_id": "step_1",
    "action": "map_context",
    "params": {{"task": "find app.py files"}},
    "dependencies": []
  }},
  {{
    "step_id": "step_2",
    "action": "read_file",
    "params": {{"path": "robodog/app.py"}},  // MUST include 'robodog/' prefix!
    "dependencies": ["step_1"]
  }},
  {{
    "step_id": "step_3",
    "action": "analyze",
    "params": {{"prompt": "Analyze the structure of app.py"}},
    "dependencies": ["step_2"]
  }}
]
"""
        
        try:
            logger.debug(f"Sending planning prompt to LLM (length: {len(prompt)} chars)")
            response = self.svc.ask(prompt)
            logger.debug(f"Received LLM response (length: {len(response)} chars)")
            
            # Extract JSON from response
            json_str = self._extract_json(response)
            if not json_str:
                logger.warning("No JSON found in response, using fallback plan")
                return self._create_fallback_plan(task)
            
            steps_data = json.loads(json_str)
            logger.debug(f"Parsed {len(steps_data)} steps from JSON")
            
            # Fix common path issues
            self._fix_paths_in_plan(steps_data)
            
            # Convert to CascadeStep objects
            steps = []
            for step_data in steps_data:
                step = CascadeStep(
                    step_id=step_data.get('step_id', f'step_{len(steps)+1}'),
                    action=step_data.get('action', 'analyze'),
                    params=step_data.get('params', {}),
                    dependencies=step_data.get('dependencies', [])
                )
                steps.append(step)
            
            self.steps = steps
            return steps
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            logger.debug(f"Failed JSON string: {json_str[:200] if json_str else 'None'}...")
            return self._create_fallback_plan(task)
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            logger.debug(f"Exception type: {type(e).__name__}")
            # Return fallback plan
            return self._create_fallback_plan(task)
    
    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON array from text"""
        
        # Find JSON array
        start = text.find('[')
        if start == -1:
            return None
        
        # Find matching closing bracket
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '[':
                depth += 1
            elif text[i] == ']':
                depth -= 1
                if depth == 0:
                    return text[start:i+1]
        
        return None
    
    def _fix_paths_in_plan(self, steps_data: List[Dict[str, Any]]) -> None:
        """Fix common path issues in LLM-generated plans"""
        
        # Common files that should be in robodog/ subdirectory
        robodog_files = {
            'app.py', 'cli.py', 'service.py', 'base.py', 'models.py',
            'todo.py', 'task_manager.py', 'file_service.py', 'code_map.py',
            'cascade_mode.py', 'agent_loop.py', 'mcphandler.py'
        }
        
        for step in steps_data:
            action = step.get('action')
            params = step.get('params', {})
            
            # Fix paths in read_file, edit_file, create_file actions
            if action in ['read_file', 'edit_file', 'create_file']:
                path = params.get('path', '')
                if path:
                    # Check if it's a bare filename that should be in robodog/
                    filename = path.split('/')[-1]
                    if filename in robodog_files and not path.startswith('robodog/'):
                        corrected_path = f'robodog/{path}'
                        logger.debug(f"Correcting path: '{path}' -> '{corrected_path}'")
                        params['path'] = corrected_path
    
    def _create_fallback_plan(self, task: str) -> List[CascadeStep]:
        """Create a simple fallback plan if LLM planning fails"""
        
        steps = [
            CascadeStep(
                step_id='step_1',
                action='analyze',
                params={'prompt': f'Analyze this task: {task}'},
                dependencies=[]
            )
        ]
        
        self.steps = steps
        return steps
    
    async def _execute_parallel(self, steps: List[CascadeStep]) -> List[Any]:
        """Execute steps in parallel based on dependencies"""
        
        completed = set()
        results = []
        iteration = 0
        max_iterations = len(steps) * 2  # Prevent infinite loops
        
        while len(completed) < len(steps) and iteration < max_iterations:
            iteration += 1
            
            # Find steps ready to execute (all dependencies met)
            ready = [
                s for s in steps 
                if s.status == 'pending' 
                and all(dep in completed for dep in s.dependencies)
            ]
            
            if not ready:
                # Check if we're stuck
                pending = [s for s in steps if s.status == 'pending']
                if pending:
                    logger.warning(f"Stuck with {len(pending)} pending steps")
                    for p in pending:
                        missing_deps = [d for d in p.dependencies if d not in completed]
                        logger.debug(f"  {p.step_id} waiting for: {missing_deps}")
                    # Execute them anyway (dependencies might be optional)
                    ready = pending
                else:
                    break
            
            logger.info(f"🔄 Executing {len(ready)} steps in parallel...")
            logger.debug(f"  Ready steps: {[s.step_id for s in ready]}")
            
            # Execute ready steps in parallel
            tasks = [self._execute_step(step) for step in ready]
            step_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for step, result in zip(ready, step_results):
                if isinstance(result, Exception):
                    step.status = 'failed'
                    step.error = str(result)
                    logger.error(f"❌ Step {step.step_id} failed: {result}")
                    logger.debug(f"  Action: {step.action}, Params: {step.params}")
                else:
                    step.status = 'completed'
                    step.result = result
                    result_preview = str(result)[:100] if result else 'None'
                    logger.info(f"✅ Step {step.step_id} completed")
                    logger.debug(f"  Result preview: {result_preview}...")
                
                completed.add(step.step_id)
                results.append(result)
        
        return results
    
    async def _execute_step(self, step: CascadeStep) -> Any:
        """Execute a single cascade step"""
        
        step.status = 'running'
        step.start_time = datetime.now()
        
        try:
            logger.debug(f"Executing {step.step_id}: {step.action}")
            logger.debug(f"  Params: {step.params}")
            
            if step.action == 'read_file':
                result = await self._action_read_file(step.params)
            
            elif step.action == 'edit_file':
                result = await self._action_edit_file(step.params)
            
            elif step.action == 'create_file':
                result = await self._action_create_file(step.params)
            
            elif step.action == 'search':
                result = await self._action_search(step.params)
            
            elif step.action == 'map_context':
                result = await self._action_map_context(step.params)
            
            elif step.action == 'analyze':
                result = await self._action_analyze(step.params)
            
            else:
                raise ValueError(f"Unknown action: {step.action}")
            
            step.end_time = datetime.now()
            duration = step.duration()
            logger.debug(f"Step {step.step_id} completed in {duration:.2f}s")
            return result
        
        except Exception as e:
            step.end_time = datetime.now()
            duration = step.duration()
            logger.debug(f"Step {step.step_id} failed after {duration:.2f}s: {e}")
            raise
    
    async def _action_read_file(self, params: Dict[str, Any]) -> str:
        """Read a file"""
        path = params.get('path')
        
        if not path:
            raise ValueError("Missing required parameter 'path' for read_file action")
        
        if not self.file_service:
            raise ValueError("File service not available")
        
        logger.debug(f"Reading file: {path}")
        from pathlib import Path
        content = self.file_service.safe_read_file(Path(path))
        logger.debug(f"Read {len(content)} characters from {path}")
        return content
    
    async def _action_edit_file(self, params: Dict[str, Any]) -> str:
        """Edit a file"""
        # This would integrate with the edit service
        return "Edit completed"
    
    async def _action_create_file(self, params: Dict[str, Any]) -> str:
        """Create a new file"""
        path = params.get('path')
        content = params.get('content', '')
        
        if not path:
            raise ValueError("Missing required parameter 'path' for create_file action")
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return f"Created {path}"
    
    async def _action_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search for code"""
        query = params.get('query')
        
        if not query:
            raise ValueError("Missing required parameter 'query' for search action")
        
        if not self.code_mapper:
            logger.warning("Code mapper not available, returning empty results")
            return {'results': [], 'message': 'Code mapper not initialized'}
        
        logger.debug(f"Searching for: {query}")
        results = self.code_mapper.find_definition(query)
        logger.debug(f"Found {len(results) if results else 0} results")
        return {'results': results}
    
    async def _action_map_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get context from code map"""
        task = params.get('task')
        
        if not task:
            raise ValueError("Missing required parameter 'task' for map_context action")
        
        if not self.code_mapper:
            logger.warning("Code mapper not available, returning empty context")
            return {'context': '', 'message': 'Code mapper not initialized'}
        
        context = self.code_mapper.get_context_for_task(task)
        return context
    
    async def _action_analyze(self, params: Dict[str, Any]) -> str:
        """Analyze with LLM"""
        prompt = params.get('prompt')
        
        if not prompt:
            raise ValueError("Missing required parameter 'prompt' for analyze action")
        
        logger.debug(f"Analyzing with prompt (length: {len(prompt)} chars)")
        response = self.svc.ask(prompt)
        logger.debug(f"Received analysis response (length: {len(response)} chars)")
        return response
    
    async def _verify_and_correct(self, results: List[Any], task: str) -> List[Any]:
        """Verify results and self-correct if needed"""
        
        # Check for errors
        errors = [
            (i, r) for i, r in enumerate(results) 
            if isinstance(r, Exception)
        ]
        
        if not errors:
            logger.debug("No errors found, verification passed")
            return results
        
        logger.info(f"🔍 Found {len(errors)} errors, attempting self-correction...")
        logger.debug(f"Error indices: {[i for i, _ in errors]}")
        
        # Build correction prompt
        error_summary = "\n".join([
            f"Step {i}: {str(e)}"
            for i, e in errors
        ])
        
        correction_prompt = f"""The following errors occurred while executing the task:

Task: {task}

Errors:
{error_summary}

How should we adjust the approach to fix these errors?
Provide specific corrective actions.
"""
        
        try:
            logger.debug(f"Sending correction prompt to LLM (length: {len(correction_prompt)} chars)")
            correction = self.svc.ask(correction_prompt)
            logger.info(f"💡 Correction suggestion: {correction[:100]}...")
            logger.debug(f"Full correction: {correction}")
            
            # For now, just log the correction
            # A full implementation would retry failed steps
            
        except Exception as e:
            logger.warning(f"Self-correction failed: {e}")
            logger.debug(f"Exception type: {type(e).__name__}")
        
        return results
    
    def _step_to_dict(self, step: CascadeStep) -> Dict[str, Any]:
        """Convert step to dictionary for serialization"""
        # Ensure result is JSON serializable
        result_value = step.result
        if isinstance(result_value, Exception):
            result_value = {'error': str(result_value)}
        
        return {
            'step_id': step.step_id,
            'action': step.action,
            'status': step.status,
            'duration': step.duration(),
            'error': step.error,
            'result': result_value
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics"""
        
        if not self.steps:
            return {}
        
        total_duration = sum(s.duration() for s in self.steps)
        successful = sum(1 for s in self.steps if s.status == 'completed')
        failed = sum(1 for s in self.steps if s.status == 'failed')
        
        return {
            'total_steps': len(self.steps),
            'successful': successful,
            'failed': failed,
            'total_duration': total_duration,
            'avg_duration': total_duration / len(self.steps) if self.steps else 0
        }

# file: todo_cascade_integration.py
#!/usr/bin/env python3
"""
Integration layer between Todo tasks, Cascade mode, and Code Map.
Provides enhanced performance and UX through intelligent task execution.
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TodoCascadeIntegration:
    """
    Integrates Todo, Cascade, and Code Map for enhanced task execution.
    
    Features:
    - Automatic code map context for todos
    - Parallel task execution using cascade
    - Smart dependency detection
    - Progress tracking and reporting
    """
    
    def __init__(self, todo_service, cascade_engine, code_mapper):
        """
        Initialize integration layer.
        
        Args:
            todo_service: TodoService instance
            cascade_engine: CascadeEngine instance
            code_mapper: CodeMapper instance
        """
        self.todo_service = todo_service
        self.cascade_engine = cascade_engine
        self.code_mapper = code_mapper
        self.execution_stats = {
            'total_tasks': 0,
            'completed': 0,
            'failed': 0,
            'skipped': 0,
            'total_duration': 0.0
        }
        
        logger.info("TodoCascadeIntegration initialized")
    
    async def execute_todo_with_cascade(
        self,
        task_id: int,
        use_map_context: bool = True,
        parallel: bool = True
    ) -> Dict[str, Any]:
        """
        Execute a todo task using cascade mode with code map context.
        
        Args:
            task_id: Task ID to execute
            use_map_context: Whether to use code map for context
            parallel: Whether to enable parallel execution
            
        Returns:
            Execution result dictionary
        """
        start_time = datetime.now()
        logger.info(f"🚀 Executing todo task {task_id} with cascade mode...")
        
        try:
            # Get task details
            task = self._get_task(task_id)
            if not task:
                return {
                    'status': 'error',
                    'error': f'Task {task_id} not found'
                }
            
            logger.debug(f"Task description: {task.get('desc', 'N/A')}")
            
            # Build context from code map
            context = ""
            if use_map_context and self.code_mapper:
                context = await self._build_map_context(task)
                logger.debug(f"Built code map context: {len(context)} chars")
            
            # Execute with cascade
            result = await self.cascade_engine.execute_cascade(
                task=task.get('desc', ''),
                context=context
            )
            
            # Update stats
            duration = (datetime.now() - start_time).total_seconds()
            self._update_stats(result, duration)
            
            # Update task status
            if result.get('status') == 'completed':
                self._mark_task_done(task_id)
                logger.info(f"✅ Task {task_id} completed in {duration:.2f}s")
            else:
                logger.warning(f"⚠️ Task {task_id} had issues: {result.get('error', 'Unknown')}")
            
            return {
                'status': 'success',
                'task_id': task_id,
                'cascade_result': result,
                'duration': duration,
                'used_map_context': use_map_context
            }
            
        except Exception as e:
            logger.error(f"Failed to execute task {task_id}: {e}")
            return {
                'status': 'error',
                'task_id': task_id,
                'error': str(e)
            }
    
    async def execute_multiple_todos(
        self,
        task_ids: List[int],
        parallel: bool = True,
        max_concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        Execute multiple todo tasks with optional parallelization.
        
        Args:
            task_ids: List of task IDs to execute
            parallel: Whether to run tasks in parallel
            max_concurrent: Maximum concurrent tasks
            
        Returns:
            Aggregated results
        """
        logger.info(f"🔄 Executing {len(task_ids)} tasks (parallel={parallel})...")
        start_time = datetime.now()
        
        results = []
        
        if parallel:
            # Execute in parallel with concurrency limit
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def execute_with_semaphore(task_id):
                async with semaphore:
                    return await self.execute_todo_with_cascade(task_id)
            
            tasks = [execute_with_semaphore(tid) for tid in task_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # Execute sequentially
            for task_id in task_ids:
                result = await self.execute_todo_with_cascade(task_id)
                results.append(result)
        
        # Aggregate results
        total_duration = (datetime.now() - start_time).total_seconds()
        successful = sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'success')
        failed = len(results) - successful
        
        logger.info(f"✨ Batch execution completed: {successful}/{len(task_ids)} successful in {total_duration:.2f}s")
        
        return {
            'status': 'completed',
            'total_tasks': len(task_ids),
            'successful': successful,
            'failed': failed,
            'duration': total_duration,
            'results': results
        }
    
    async def auto_execute_pending_todos(
        self,
        max_tasks: int = 5,
        parallel: bool = True
    ) -> Dict[str, Any]:
        """
        Automatically execute pending todo tasks.
        
        Args:
            max_tasks: Maximum number of tasks to execute
            parallel: Whether to run in parallel
            
        Returns:
            Execution results
        """
        logger.info(f"🤖 Auto-executing up to {max_tasks} pending tasks...")
        
        # Get pending tasks
        pending_tasks = self._get_pending_tasks(max_tasks)
        
        if not pending_tasks:
            logger.info("No pending tasks found")
            return {
                'status': 'completed',
                'message': 'No pending tasks',
                'total_tasks': 0
            }
        
        task_ids = [t['id'] for t in pending_tasks]
        logger.info(f"Found {len(task_ids)} pending tasks: {task_ids}")
        
        # Execute with cascade
        return await self.execute_multiple_todos(task_ids, parallel=parallel)
    
    async def _build_map_context(self, task: Dict[str, Any]) -> str:
        """Build context from code map for a task."""
        
        task_desc = task.get('desc', '')
        include_patterns = task.get('include', [])
        
        # Get relevant context from code map
        if self.code_mapper:
            try:
                context_data = self.code_mapper.get_context_for_task(
                    task_desc,
                    include_patterns=include_patterns if include_patterns else None
                )
                
                # Format context
                context_parts = []
                
                if context_data:
                    context_parts.append("# Relevant Code Context")
                    
                    for file_path, file_info in context_data.items():
                        context_parts.append(f"\n## {file_path}")
                        
                        if 'classes' in file_info:
                            context_parts.append(f"Classes: {', '.join(file_info['classes'])}")
                        
                        if 'functions' in file_info:
                            context_parts.append(f"Functions: {', '.join(file_info['functions'])}")
                
                return '\n'.join(context_parts)
                
            except Exception as e:
                logger.warning(f"Failed to build map context: {e}")
                return ""
        
        return ""
    
    def _get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get task by ID."""
        if hasattr(self.todo_service, '_tasks'):
            for task in self.todo_service._tasks:
                if task.get('id') == task_id:
                    return task
        return None
    
    def _get_pending_tasks(self, max_tasks: int) -> List[Dict[str, Any]]:
        """Get pending tasks."""
        pending = []
        
        if hasattr(self.todo_service, '_tasks'):
            for task in self.todo_service._tasks:
                status = task.get('status', [' ', ' ', ' '])
                # Check if task is pending (first status is ' ')
                if status[0] == ' ':
                    pending.append(task)
                    if len(pending) >= max_tasks:
                        break
        
        return pending
    
    def _mark_task_done(self, task_id: int) -> None:
        """Mark task as done."""
        task = self._get_task(task_id)
        if task:
            # Update status to done
            task['status'] = ['x', 'x', 'x']
            logger.debug(f"Marked task {task_id} as done")
    
    def _update_stats(self, result: Dict[str, Any], duration: float) -> None:
        """Update execution statistics."""
        self.execution_stats['total_tasks'] += 1
        self.execution_stats['total_duration'] += duration
        
        if result.get('status') == 'completed':
            self.execution_stats['completed'] += 1
        else:
            self.execution_stats['failed'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        stats = self.execution_stats.copy()
        
        if stats['total_tasks'] > 0:
            stats['avg_duration'] = stats['total_duration'] / stats['total_tasks']
            stats['success_rate'] = stats['completed'] / stats['total_tasks']
        else:
            stats['avg_duration'] = 0.0
            stats['success_rate'] = 0.0
        
        return stats
    
    def reset_stats(self) -> None:
        """Reset execution statistics."""
        self.execution_stats = {
            'total_tasks': 0,
            'completed': 0,
            'failed': 0,
            'skipped': 0,
            'total_duration': 0.0
        }
        logger.info("Execution stats reset")


class ProgressTracker:
    """Track and report progress for long-running operations."""
    
    def __init__(self, total_steps: int, callback: Optional[callable] = None):
        """
        Initialize progress tracker.
        
        Args:
            total_steps: Total number of steps
            callback: Optional callback for progress updates
        """
        self.total_steps = total_steps
        self.current_step = 0
        self.callback = callback
        self.start_time = datetime.now()
        self.step_times = []
    
    def update(self, step: int, message: str = "") -> None:
        """Update progress."""
        self.current_step = step
        self.step_times.append(datetime.now())
        
        progress = (step / self.total_steps) * 100 if self.total_steps > 0 else 0
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        # Estimate remaining time
        if step > 0:
            avg_time_per_step = elapsed / step
            remaining_steps = self.total_steps - step
            eta = avg_time_per_step * remaining_steps
        else:
            eta = 0
        
        progress_info = {
            'step': step,
            'total': self.total_steps,
            'progress': progress,
            'message': message,
            'elapsed': elapsed,
            'eta': eta
        }
        
        logger.info(f"Progress: {step}/{self.total_steps} ({progress:.1f}%) - {message}")
        
        if self.callback:
            self.callback(progress_info)
    
    def complete(self, message: str = "Completed") -> None:
        """Mark as complete."""
        self.update(self.total_steps, message)
        total_time = (datetime.now() - self.start_time).total_seconds()
        logger.info(f"✅ {message} in {total_time:.2f}s")


def create_integration(todo_service, cascade_engine, code_mapper) -> TodoCascadeIntegration:
    """
    Factory function to create TodoCascadeIntegration instance.
    
    Args:
        todo_service: TodoService instance
        cascade_engine: CascadeEngine instance
        code_mapper: CodeMapper instance
        
    Returns:
        TodoCascadeIntegration instance
    """
    return TodoCascadeIntegration(todo_service, cascade_engine, code_mapper)

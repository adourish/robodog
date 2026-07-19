# file: agent_loop.py
#!/usr/bin/env python3
"""
Agentic game loop for incremental LLM task execution.
Breaks large tasks into small chunks and processes them iteratively.
"""

# CRITICAL IMPORTS - DO NOT REMOVE OR MODIFY
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
import json
# END CRITICAL IMPORTS

logger = logging.getLogger(__name__)

# Import enhancement methods
try:
    from agent_loop_enhanced import AgentLoopEnhancements
except ImportError:
    # Fallback if enhancements not available
    class AgentLoopEnhancements:
        """Stub class for when enhancements are not available."""
        pass

# Import context builder for code map integration
try:
    from agent_context import AgentContextBuilder
except ImportError:
    AgentContextBuilder = None
    logger.warning("AgentContextBuilder not available - code map context disabled")


class AgentState:
    """Tracks the state of the agentic loop execution."""
    
    def __init__(self, task: Dict[str, Any]):
        self.task = task
        self.subtasks: List[Dict[str, Any]] = []
        self.completed_subtasks: List[Dict[str, Any]] = []
        self.failed_subtasks: List[Dict[str, Any]] = []
        self.current_subtask: Optional[Dict[str, Any]] = None
        self.iteration = 0
        self.max_iterations = 50  # Increased for smaller chunks
        self.total_tokens_used = 0
        self.files_modified: List[str] = []
        self.start_time = datetime.now()
        
        # Enhanced tracking
        self.quality_scores: List[float] = []  # Track quality of each output
        self.reflection_results: List[Dict[str, Any]] = []  # Self-reflection logs
        self.micro_steps: List[Dict[str, Any]] = []  # Fine-grained progress
        self.avg_quality = 0.0
        self.refinement_count = 0  # How many times we refined output
        
    def add_subtask(self, subtask: Dict[str, Any]):
        """Add a new subtask to the queue."""
        self.subtasks.append(subtask)
        
    def next_subtask(self) -> Optional[Dict[str, Any]]:
        """Get the next subtask to execute."""
        if self.subtasks:
            self.current_subtask = self.subtasks.pop(0)
            self.iteration += 1
            return self.current_subtask
        return None
    
    def mark_complete(self, result: Dict[str, Any], quality_score: float = 0.0):
        """Mark current subtask as completed with quality score."""
        if self.current_subtask:
            self.current_subtask['result'] = result
            self.current_subtask['completed_at'] = datetime.now().isoformat()
            self.current_subtask['quality_score'] = quality_score
            self.completed_subtasks.append(self.current_subtask)
            self.quality_scores.append(quality_score)
            self.avg_quality = sum(self.quality_scores) / len(self.quality_scores)
            self.current_subtask = None
            
    def mark_failed(self, error: str):
        """Mark current subtask as failed."""
        if self.current_subtask:
            self.current_subtask['error'] = error
            self.current_subtask['failed_at'] = datetime.now().isoformat()
            self.failed_subtasks.append(self.current_subtask)
            self.current_subtask = None
    
    def log_micro_step(self, step_name: str, details: Dict[str, Any]):
        """Log a micro-step for fine-grained progress tracking."""
        self.micro_steps.append({
            'step': step_name,
            'timestamp': datetime.now().isoformat(),
            'iteration': self.iteration,
            'details': details
        })
    
    def add_reflection(self, reflection: Dict[str, Any]):
        """Record a self-reflection result."""
        self.reflection_results.append({
            'timestamp': datetime.now().isoformat(),
            'iteration': self.iteration,
            **reflection
        })
            
    def should_continue(self) -> bool:
        """Check if the loop should continue."""
        if self.iteration >= self.max_iterations:
            logger.warning(f"Max iterations ({self.max_iterations}) reached")
            return False
        if not self.subtasks:
            return False
        return True
    
    def get_summary(self) -> Dict[str, Any]:
        """Get execution summary."""
        duration = (datetime.now() - self.start_time).total_seconds()
        return {
            'total_iterations': self.iteration,
            'completed': len(self.completed_subtasks),
            'failed': len(self.failed_subtasks),
            'pending': len(self.subtasks),
            'duration_seconds': duration,
            'total_tokens': self.total_tokens_used,
            'files_modified': self.files_modified,
        }


class AgentLoop(AgentLoopEnhancements):
    """
    Agentic game loop that breaks tasks into small chunks and executes them iteratively.
    Enhanced with self-reflection, adaptive chunking, and iterative refinement.
    """
    
    def __init__(self, svc, file_service, prompt_builder, parser, code_mapper=None):
        self.svc = svc
        self.file_service = file_service
        self.prompt_builder = prompt_builder
        self.parser = parser
        self.code_mapper = code_mapper
        
        # Initialize context builder if code mapper available
        self.context_builder = None
        if code_mapper and AgentContextBuilder:
            self.context_builder = AgentContextBuilder(code_mapper, file_service)
            logger.info("Code map context builder initialized")
        
        # Adaptive chunking configuration
        self.min_chunk_size = 1  # Minimum files per chunk
        self.max_chunk_size = 3  # Maximum files per chunk
        self.target_tokens_per_chunk = 2000  # Target token count
        self.quality_threshold = 0.7  # Minimum acceptable quality
        self.enable_reflection = True  # Enable self-reflection
        self.enable_refinement = True  # Enable iterative refinement
        
    def execute(
        self,
        task: Dict[str, Any],
        base_folder: str,
        include_files: List[str],
        knowledge_text: str,
        plan_content: str
    ) -> Tuple[bool, List[Dict[str, Any]], AgentState]:
        """
        Execute task using agentic loop.
        
        Returns:
            Tuple of (success, parsed_files, agent_state)
        """
        logger.info("=" * 70, extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"🤖 STARTING AGENTIC LOOP", extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"Task: {task['desc']}", extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"Files to process: {len(include_files)}", extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"Base folder: {base_folder}", extra={'log_color': 'HIGHLIGHT'})
        logger.info("=" * 70, extra={'log_color': 'HIGHLIGHT'})
        
        # Initialize state
        logger.info("Initializing agent state...", extra={'log_color': 'HIGHLIGHT'})
        state = AgentState(task)
        logger.info(f"Max iterations: {state.max_iterations}", extra={'log_color': 'HIGHLIGHT'})
        
        # Step 1: Decompose task into subtasks
        logger.info("\n" + "─" * 70, extra={'log_color': 'HIGHLIGHT'})
        logger.info("PHASE 1: TASK DECOMPOSITION", extra={'log_color': 'HIGHLIGHT'})
        logger.info("─" * 70, extra={'log_color': 'HIGHLIGHT'})
        
        subtasks = self._decompose_task(task, include_files, plan_content)
        for subtask in subtasks:
            state.add_subtask(subtask)
            
        logger.info(f"✅ Decomposed into {len(subtasks)} subtasks:", extra={'log_color': 'PERCENT'})
        for i, st in enumerate(subtasks, 1):
            logger.info(f"  {i}. {st['description']} ({len(st.get('target_files', []))} files)", 
                       extra={'log_color': 'PERCENT'})
        
        all_results = []
        
        # Step 2: Execute subtasks in loop
        logger.info("\n" + "─" * 70, extra={'log_color': 'HIGHLIGHT'})
        logger.info("PHASE 2: ITERATIVE EXECUTION", extra={'log_color': 'HIGHLIGHT'})
        logger.info("─" * 70, extra={'log_color': 'HIGHLIGHT'})
        
        while state.should_continue():
            subtask = state.next_subtask()
            if not subtask:
                logger.info("No more subtasks to process", extra={'log_color': 'HIGHLIGHT'})
                break
            
            logger.info("\n" + "┌" + "─" * 68 + "┐", extra={'log_color': 'HIGHLIGHT'})
            logger.info(f"│ 🔄 ITERATION {state.iteration}/{state.max_iterations}".ljust(69) + "│", 
                       extra={'log_color': 'HIGHLIGHT'})
            logger.info(f"│ Task: {subtask['description'][:60]}".ljust(69) + "│", 
                       extra={'log_color': 'HIGHLIGHT'})
            logger.info(f"│ Files: {len(subtask.get('target_files', []))}".ljust(69) + "│", 
                       extra={'log_color': 'HIGHLIGHT'})
            logger.info("└" + "─" * 68 + "┘", extra={'log_color': 'HIGHLIGHT'})
            
            try:
                # Micro-step: Start execution
                state.log_micro_step('execute_start', {'subtask': subtask['description']})
                
                # Execute subtask
                result = self._execute_subtask(
                    subtask,
                    task,
                    base_folder,
                    knowledge_text,
                    plan_content,
                    state
                )
                
                # Micro-step: Execution complete
                state.log_micro_step('execute_complete', {
                    'files_generated': len(result.get('parsed_files', []))
                })
                
                # Self-reflection on output quality
                reflection = self._reflect_on_output(subtask, result, state)
                state.add_reflection(reflection)
                
                quality_score = reflection.get('quality_score', 0.8)
                should_refine = reflection.get('should_refine', False)
                
                # Refinement if quality is low
                if should_refine and self.enable_refinement:
                    logger.info(f"🔧 Quality below threshold ({quality_score:.2f}), refining...", 
                               extra={'log_color': 'DELTA'})
                    result = self._refine_output(subtask, result, reflection, state)
                    
                    # Re-evaluate after refinement
                    reflection = self._reflect_on_output(subtask, result, state)
                    quality_score = reflection.get('quality_score', 0.8)
                    logger.info(f"✨ Refined quality: {quality_score:.2f}", 
                               extra={'log_color': 'PERCENT'})
                
                # Validate result
                if self._validate_result(result, subtask):
                    state.mark_complete(result, quality_score)
                    all_results.extend(result.get('parsed_files', []))
                    state.files_modified.extend(result.get('files_modified', []))
                    logger.info(f"✅ Subtask completed: {subtask['description']} (Q:{quality_score:.2f})", 
                               extra={'log_color': 'PERCENT'})
                else:
                    # Retry logic
                    if subtask.get('retry_count', 0) < 2:
                        subtask['retry_count'] = subtask.get('retry_count', 0) + 1
                        state.add_subtask(subtask)  # Re-queue
                        logger.warning(f"⚠️ Subtask validation failed, retrying: {subtask['description']}", 
                                     extra={'log_color': 'DELTA'})
                    else:
                        state.mark_failed("Validation failed after retries")
                        logger.error(f"❌ Subtask failed: {subtask['description']}", 
                                   extra={'log_color': 'DELTA'})
                        
            except Exception as e:
                logger.exception(f"Error executing subtask: {e}", extra={'log_color': 'DELTA'})
                state.mark_failed(str(e))
                
        # Step 3: Summary
        logger.info("\n" + "─" * 70, extra={'log_color': 'HIGHLIGHT'})
        logger.info("PHASE 3: SUMMARY & RESULTS", extra={'log_color': 'HIGHLIGHT'})
        logger.info("─" * 70, extra={'log_color': 'HIGHLIGHT'})
        
        summary = state.get_summary()
        
        logger.info(f"🏁 Agentic loop completed!", extra={'log_color': 'PERCENT'})
        logger.info(f"", extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"📊 Statistics:", extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"  ✅ Succeeded: {summary['completed']}", extra={'log_color': 'PERCENT'})
        logger.info(f"  ❌ Failed: {summary['failed']}", extra={'log_color': 'DELTA' if summary['failed'] > 0 else 'PERCENT'})
        logger.info(f"  ⏱️  Duration: {summary['duration_seconds']:.1f}s", extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"  🔄 Iterations: {summary['total_iterations']}", extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"  💰 Total tokens: {summary['total_tokens']:,}", extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"  📁 Files modified: {len(summary['files_modified'])}", extra={'log_color': 'HIGHLIGHT'})
        
        if hasattr(state, 'avg_quality') and state.avg_quality > 0:
            logger.info(f"  ⭐ Average quality: {state.avg_quality:.2f}", extra={'log_color': 'PERCENT'})
        if hasattr(state, 'refinement_count') and state.refinement_count > 0:
            logger.info(f"  🔧 Refinements: {state.refinement_count}", extra={'log_color': 'HIGHLIGHT'})
        if hasattr(state, 'micro_steps'):
            logger.info(f"  📝 Micro-steps logged: {len(state.micro_steps)}", extra={'log_color': 'HIGHLIGHT'})
        
        if summary['files_modified']:
            logger.info(f"\n📁 Modified files:", extra={'log_color': 'HIGHLIGHT'})
            for f in summary['files_modified'][:10]:
                logger.info(f"  • {f}", extra={'log_color': 'HIGHLIGHT'})
            if len(summary['files_modified']) > 10:
                logger.info(f"  ... and {len(summary['files_modified']) - 10} more", 
                           extra={'log_color': 'HIGHLIGHT'})
        
        logger.info("=" * 70, extra={'log_color': 'HIGHLIGHT'})
        
        success = summary['failed'] == 0 and summary['completed'] > 0
        return success, all_results, state
    
    def _decompose_task(
        self,
        task: Dict[str, Any],
        include_files: List[str],
        plan_content: str
    ) -> List[Dict[str, Any]]:
        """
        Decompose main task into smaller subtasks using adaptive chunking.
        
        Strategy:
        1. Use adaptive chunking based on file size and complexity
        2. Create subtasks with optimal token counts
        3. Extract action-based subtasks from plan
        4. Order by priority and dependencies
        """
        subtasks = []
        
        # Use adaptive chunking for better granularity
        if hasattr(self, '_adaptive_chunk_files'):
            # Create temporary state for chunking
            from agent_loop import AgentState
            temp_state = AgentState(task)
            file_chunks = self._adaptive_chunk_files(include_files, temp_state)
            
            for idx, chunk in enumerate(file_chunks):
                chunk_names = [Path(f).name for f in chunk]
                if len(chunk) == 1:
                    desc = f'Process {chunk_names[0]}'
                else:
                    desc = f'Process {len(chunk)} files: {", ".join(chunk_names[:2])}{"..." if len(chunk) > 2 else ""}'
                
                subtasks.append({
                    'id': f'subtask_{idx}',
                    'description': desc,
                    'target_files': chunk,
                    'type': 'adaptive_chunk',
                    'priority': 1,
                })
        else:
            # Fallback to simple strategy
            if len(include_files) <= 3:
                # Small number - process individually
                for idx, file_path in enumerate(include_files):
                    subtasks.append({
                        'id': f'subtask_{idx}',
                        'description': f'Process {Path(file_path).name}',
                        'target_files': [file_path],
                        'type': 'single_file',
                        'priority': 1,
                    })
            else:
                # Many files - group by directory
                file_groups = self._group_files(include_files)
                for idx, (group_name, files) in enumerate(file_groups.items()):
                    subtasks.append({
                        'id': f'subtask_{idx}',
                        'description': f'Process {group_name} ({len(files)} files)',
                        'target_files': files,
                        'type': 'file_group',
                        'priority': 1,
                    })
        
        # Strategy 2: Extract specific actions from plan
        if plan_content:
            action_subtasks = self._extract_actions_from_plan(plan_content)
            subtasks.extend(action_subtasks)
        
        # Sort by priority
        subtasks.sort(key=lambda x: x.get('priority', 999))
        
        return subtasks
    
    def _group_files(self, files: List[str]) -> Dict[str, List[str]]:
        """Group files by directory or module."""
        groups = {}
        for file_path in files:
            path = Path(file_path)
            # Group by parent directory
            group_key = path.parent.name or 'root'
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(file_path)
        return groups
    
    def _extract_actions_from_plan(self, plan_content: str) -> List[Dict[str, Any]]:
        """Extract actionable subtasks from plan content."""
        subtasks = []
        
        # Look for numbered steps or bullet points
        lines = plan_content.split('\n')
        for idx, line in enumerate(lines):
            line = line.strip()
            # Match patterns like "1. ", "- ", "* ", "Step 1:", etc.
            if any(line.startswith(prefix) for prefix in ['1.', '2.', '3.', '4.', '5.', '- ', '* ', 'Step ']):
                # Extract action description
                action = line.lstrip('0123456789.-*• ').strip()
                if len(action) > 10:  # Meaningful action
                    subtasks.append({
                        'id': f'action_{idx}',
                        'description': action[:100],  # Truncate long descriptions
                        'target_files': [],  # Will be determined during execution
                        'type': 'plan_action',
                        'priority': 2,
                        'source_line': idx,
                    })
        
        return subtasks
    
    def _execute_subtask(
        self,
        subtask: Dict[str, Any],
        task: Dict[str, Any],
        base_folder: str,
        knowledge_text: str,
        plan_content: str,
        state: AgentState
    ) -> Dict[str, Any]:
        """Execute a single subtask."""
        
        # Build focused prompt for this subtask
        prompt = self._build_subtask_prompt(
            subtask,
            task,
            knowledge_text,
            plan_content,
            state
        )
        
        # Track tokens
        prompt_tokens = len(prompt.split())
        state.total_tokens_used += prompt_tokens
        
        logger.debug(f"Subtask prompt: {prompt_tokens} tokens")
        
        # Call LLM
        response = self.svc.ask(prompt)
        
        if not response:
            raise Exception("Empty LLM response")
        
        # Track response tokens
        response_tokens = len(response.split())
        state.total_tokens_used += response_tokens
        
        # Parse response
        parsed_files = self.parser.parse_llm_output(
            response,
            base_dir=base_folder,
            file_service=self.file_service,
            ai_out_path=None,
            task=task,
            svc=self.svc
        )
        
        return {
            'parsed_files': parsed_files,
            'response': response,
            'prompt_tokens': prompt_tokens,
            'response_tokens': response_tokens,
            'files_modified': [f.get('filename', '') for f in parsed_files],
        }
    
    def _build_subtask_prompt(
        self,
        subtask: Dict[str, Any],
        task: Dict[str, Any],
        knowledge_text: str,
        plan_content: str,
        state: AgentState
    ) -> str:
        """Build a focused prompt for a specific subtask with code map context."""
        
        focused_context = ""
        
        # Try to use code map context builder for targeted context
        if self.context_builder:
            try:
                # Build minimal context for this specific subtask
                subtask_desc = subtask.get('description', '')
                minimal_context = self.context_builder.build_minimal_context(
                    subtask_desc, 
                    max_files=3
                )
                focused_context = minimal_context
                logger.info(f"Using code map context for subtask: {subtask_desc[:50]}")
            except Exception as e:
                logger.warning(f"Failed to build code map context: {e}")
                # Fall back to manual file loading
                focused_context = self._load_target_files_manually(subtask)
        else:
            # Fall back to manual file loading
            focused_context = self._load_target_files_manually(subtask)
        
        # Build prompt
        prompt = f"""# Task: {task['desc']}

## Current Subtask
{subtask['description']}

## Context
Iteration: {state.iteration}/{state.max_iterations}
Completed subtasks: {len(state.completed_subtasks)}
Files already modified: {', '.join(state.files_modified[:5])}

## Plan Summary
{plan_content[:500]}...

## Knowledge
{knowledge_text[:300]}...

{focused_context}

## Instructions
Focus ONLY on: {subtask['description']}
Generate code changes for the specified files only.
Use the format: # file: <filename> followed by the code.
Keep changes minimal and focused.
Provide working, tested code that follows best practices.
"""
        
        return prompt
    
    def _load_target_files_manually(self, subtask: Dict[str, Any]) -> str:
        """Fallback method to load target files manually when code map not available."""
        target_files = subtask.get('target_files', [])
        focused_context = ""
        
        if target_files:
            focused_context = "# Relevant Files:\n"
            for file_path in target_files[:3]:  # Limit to 3 files per subtask
                try:
                    content = self.file_service.safe_read_file(Path(file_path))
                    focused_context += f"\n## {file_path}\n```\n{content}\n```\n"
                except Exception as e:
                    logger.warning(f"Could not read {file_path}: {e}")
        
        return focused_context
    
    def _validate_result(
        self,
        result: Dict[str, Any],
        subtask: Dict[str, Any]
    ) -> bool:
        """Validate that subtask result is acceptable."""
        
        # Check if we got parsed files
        parsed_files = result.get('parsed_files', [])
        if not parsed_files:
            logger.warning("No parsed files in result")
            return False
        
        # Check if files match expected targets
        target_files = subtask.get('target_files', [])
        if target_files:
            result_files = [f.get('filename', '') for f in parsed_files]
            # At least one target file should be present
            if not any(Path(rf).name in [Path(tf).name for tf in target_files] for rf in result_files):
                logger.warning(f"Result files {result_files} don't match targets {target_files}")
                return False
        
        # Check for errors in parsed content
        for pf in parsed_files:
            if pf.get('error'):
                logger.warning(f"Parse error in {pf.get('filename')}: {pf.get('error')}")
                return False
        
        return True


def enable_agent_loop(todo_service, enable: bool = True):
    """
    Enable or disable agentic loop for a TodoService instance.
    
    Usage:
        enable_agent_loop(todo_service, True)
    """
    if enable:
        # Get code_mapper from service if available
        code_mapper = getattr(todo_service._svc, 'code_mapper', None)
        
        agent_loop = AgentLoop(
            svc=todo_service._svc,
            file_service=todo_service._file_service,
            prompt_builder=todo_service._prompt_builder,
            parser=todo_service.parser,
            code_mapper=code_mapper
        )
        todo_service._agent_loop = agent_loop
        
        if code_mapper:
            logger.info("🤖 Agentic loop enabled with code map context", extra={'log_color': 'HIGHLIGHT'})
        else:
            logger.info("🤖 Agentic loop enabled", extra={'log_color': 'HIGHLIGHT'})
    else:
        todo_service._agent_loop = None
        logger.info("Agentic loop disabled")

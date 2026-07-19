# file: agent_loop_enhanced.py
"""
Enhanced methods for the agentic loop with self-reflection and adaptive chunking.
These methods extend the base AgentLoop class.
"""

import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class AgentLoopEnhancements:
    """Mixin class with enhanced agentic capabilities."""
    
    def _reflect_on_output(self, subtask: Dict[str, Any], result: Dict[str, Any], state) -> Dict[str, Any]:
        """
        Self-reflect on the quality of the output.
        Returns a reflection dict with quality_score and suggestions.
        """
        logger.info(f"🔍 Starting self-reflection for: {subtask['description']}", 
                   extra={'log_color': 'HIGHLIGHT'})
        
        if not self.enable_reflection:
            logger.info("Self-reflection disabled, using default quality score", 
                       extra={'log_color': 'DELTA'})
            return {'quality_score': 0.8, 'suggestions': [], 'should_refine': False}
        
        state.log_micro_step('reflection_start', {'subtask': subtask['description']})
        
        # Build reflection prompt
        logger.info("Building reflection prompt...", extra={'log_color': 'HIGHLIGHT'})
        reflection_prompt = self._build_reflection_prompt(subtask, result)
        logger.info(f"Reflection prompt: {len(reflection_prompt.split())} tokens", 
                   extra={'log_color': 'HIGHLIGHT'})
        
        try:
            # Ask LLM to evaluate its own work
            logger.info("Asking LLM to evaluate its own work...", extra={'log_color': 'HIGHLIGHT'})
            reflection_response = self.svc.ask(reflection_prompt)
            logger.info(f"Received reflection response: {len(reflection_response.split())} tokens", 
                       extra={'log_color': 'HIGHLIGHT'})
            
            # Parse reflection
            logger.info("Parsing reflection response...", extra={'log_color': 'HIGHLIGHT'})
            reflection = self._parse_reflection(reflection_response)
            
            state.log_micro_step('reflection_complete', {
                'quality_score': reflection['quality_score'],
                'suggestions_count': len(reflection['suggestions'])
            })
            
            logger.info(f"✅ Self-reflection complete: Quality={reflection['quality_score']:.2f}, "
                       f"Completeness={'Yes' if reflection['completeness'] else 'No'}, "
                       f"Correctness={'Yes' if reflection['correctness'] else 'No'}, "
                       f"Suggestions={len(reflection['suggestions'])}", 
                       extra={'log_color': 'PERCENT'})
            
            if reflection['suggestions']:
                logger.info(f"Suggestions for improvement:", extra={'log_color': 'HIGHLIGHT'})
                for i, suggestion in enumerate(reflection['suggestions'][:3], 1):
                    logger.info(f"  {i}. {suggestion}", extra={'log_color': 'HIGHLIGHT'})
            
            return reflection
            
        except Exception as e:
            logger.warning(f"❌ Reflection failed: {e}", extra={'log_color': 'DELTA'})
            return {'quality_score': 0.7, 'suggestions': [], 'should_refine': False}
    
    def _build_reflection_prompt(self, subtask: Dict[str, Any], result: Dict[str, Any]) -> str:
        """Build prompt for self-reflection."""
        parsed_files = result.get('parsed_files', [])
        file_summaries = []
        
        for pf in parsed_files[:3]:  # Limit to first 3 files
            filename = pf.get('filename', 'unknown')
            content = pf.get('content', '')
            lines = len(content.split('\n'))
            file_summaries.append(f"- {filename} ({lines} lines)")
        
        prompt = f"""# Self-Reflection Task

You just completed this subtask:
**{subtask['description']}**

Output generated:
{chr(10).join(file_summaries)}

Please evaluate your own work on a scale of 0.0 to 1.0:

1. **Quality Score** (0.0-1.0): How well does the output meet the requirements?
2. **Completeness**: Are all necessary changes included?
3. **Correctness**: Is the code syntactically correct and logical?
4. **Suggestions**: What could be improved?

Respond in this format:
QUALITY_SCORE: 0.85
COMPLETENESS: yes/no
CORRECTNESS: yes/no
SUGGESTIONS:
- Suggestion 1
- Suggestion 2

Be honest and critical. If quality < 0.7, suggest refinements.
"""
        return prompt
    
    def _parse_reflection(self, reflection_text: str) -> Dict[str, Any]:
        """Parse LLM's self-reflection response."""
        lines = reflection_text.strip().split('\n')
        
        quality_score = 0.8  # Default
        completeness = True
        correctness = True
        suggestions = []
        
        in_suggestions = False
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('QUALITY_SCORE:'):
                try:
                    quality_score = float(line.split(':', 1)[1].strip())
                except:
                    pass
            elif line.startswith('COMPLETENESS:'):
                completeness = 'yes' in line.lower()
            elif line.startswith('CORRECTNESS:'):
                correctness = 'yes' in line.lower()
            elif line.startswith('SUGGESTIONS:'):
                in_suggestions = True
            elif in_suggestions and line.startswith('-'):
                suggestions.append(line.lstrip('- ').strip())
        
        should_refine = quality_score < self.quality_threshold or not completeness or not correctness
        
        return {
            'quality_score': quality_score,
            'completeness': completeness,
            'correctness': correctness,
            'suggestions': suggestions,
            'should_refine': should_refine
        }
    
    def _refine_output(
        self,
        subtask: Dict[str, Any],
        result: Dict[str, Any],
        reflection: Dict[str, Any],
        state
    ) -> Dict[str, Any]:
        """
        Refine the output based on reflection suggestions.
        """
        logger.info(f"🔧 Starting refinement for: {subtask['description']}", 
                   extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"Original quality: {reflection['quality_score']:.2f}", 
                   extra={'log_color': 'HIGHLIGHT'})
        
        if not self.enable_refinement:
            logger.info("Refinement disabled, using original output", 
                       extra={'log_color': 'DELTA'})
            return result
        
        state.log_micro_step('refinement_start', {
            'original_quality': reflection['quality_score'],
            'suggestions': len(reflection['suggestions'])
        })
        
        logger.info(f"Applying {len(reflection['suggestions'])} suggestions:", 
                   extra={'log_color': 'HIGHLIGHT'})
        for i, suggestion in enumerate(reflection['suggestions'][:3], 1):
            logger.info(f"  {i}. {suggestion}", extra={'log_color': 'HIGHLIGHT'})
        
        # Build refinement prompt
        logger.info("Building refinement prompt...", extra={'log_color': 'HIGHLIGHT'})
        refinement_prompt = self._build_refinement_prompt(subtask, result, reflection)
        logger.info(f"Refinement prompt: {len(refinement_prompt.split())} tokens", 
                   extra={'log_color': 'HIGHLIGHT'})
        
        try:
            # Get refined output
            logger.info("Asking LLM to refine output...", extra={'log_color': 'HIGHLIGHT'})
            refined_response = self.svc.ask(refinement_prompt)
            logger.info(f"Received refined response: {len(refined_response.split())} tokens", 
                       extra={'log_color': 'HIGHLIGHT'})
            
            # Parse refined output
            logger.info("Parsing refined output...", extra={'log_color': 'HIGHLIGHT'})
            refined_files = self.parser.parse_llm_output(
                refined_response,
                base_dir=subtask.get('base_folder', '.'),
                file_service=self.file_service,
                ai_out_path=None,
                task=state.task,
                svc=self.svc
            )
            logger.info(f"Parsed {len(refined_files)} files from refined output", 
                       extra={'log_color': 'HIGHLIGHT'})
            
            refined_result = {
                'parsed_files': refined_files,
                'response': refined_response,
                'prompt_tokens': len(refinement_prompt.split()),
                'response_tokens': len(refined_response.split()),
                'files_modified': [f.get('filename', '') for f in refined_files],
                'refinement_iteration': result.get('refinement_iteration', 0) + 1
            }
            
            state.refinement_count += 1
            state.log_micro_step('refinement_complete', {
                'refinement_iteration': refined_result['refinement_iteration']
            })
            
            logger.info(f"✅ Refinement complete (iteration {refined_result['refinement_iteration']})", 
                       extra={'log_color': 'PERCENT'})
            logger.info(f"Files modified: {', '.join([f.get('filename', 'unknown') for f in refined_files[:3]])}", 
                       extra={'log_color': 'PERCENT'})
            
            return refined_result
            
        except Exception as e:
            logger.warning(f"❌ Refinement failed: {e}, using original output", 
                          extra={'log_color': 'DELTA'})
            return result
    
    def _build_refinement_prompt(
        self,
        subtask: Dict[str, Any],
        result: Dict[str, Any],
        reflection: Dict[str, Any]
    ) -> str:
        """Build prompt for refining output."""
        suggestions_text = '\n'.join(f"- {s}" for s in reflection['suggestions'])
        
        original_output = result.get('response', '')[:1000]  # First 1000 chars
        
        prompt = f"""# Refinement Task

Original subtask: {subtask['description']}

Your previous output had quality score: {reflection['quality_score']:.2f}

Issues identified:
{suggestions_text}

Original output (preview):
```
{original_output}
...
```

Please provide an improved version that addresses these issues.
Focus on:
1. Fixing any identified problems
2. Improving code quality
3. Ensuring completeness

Generate the refined code now.
"""
        return prompt
    
    def _adaptive_chunk_files(self, files: List[str], state) -> List[List[str]]:
        """
        Adaptively chunk files based on size and complexity.
        Returns list of file groups.
        """
        logger.info(f"📦 Starting adaptive chunking for {len(files)} files", 
                   extra={'log_color': 'HIGHLIGHT'})
        logger.info(f"Target: {self.target_tokens_per_chunk} tokens/chunk, "
                   f"Max: {self.max_chunk_size} files/chunk", 
                   extra={'log_color': 'HIGHLIGHT'})
        
        state.log_micro_step('adaptive_chunking_start', {'total_files': len(files)})
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for idx, file_path in enumerate(files, 1):
            try:
                # Estimate file complexity
                content = self.file_service.safe_read_file(file_path)
                file_tokens = len(content.split())
                complexity = self._estimate_complexity(file_path)
                
                logger.info(f"  [{idx}/{len(files)}] {Path(file_path).name}: "
                           f"{file_tokens} tokens, complexity={complexity:.2f}", 
                           extra={'log_color': 'HIGHLIGHT'})
                
                # Decide if we should start a new chunk
                would_exceed = current_tokens + file_tokens > self.target_tokens_per_chunk
                chunk_at_max = len(current_chunk) >= self.max_chunk_size
                
                if current_chunk and (would_exceed or chunk_at_max):
                    # Start new chunk
                    logger.info(f"  → Creating chunk {len(chunks)+1} with {len(current_chunk)} files "
                               f"({current_tokens} tokens)", 
                               extra={'log_color': 'PERCENT'})
                    chunks.append(current_chunk)
                    current_chunk = [file_path]
                    current_tokens = file_tokens
                else:
                    # Add to current chunk
                    current_chunk.append(file_path)
                    current_tokens += file_tokens
                    
            except Exception as e:
                logger.warning(f"Could not read {file_path} for chunking: {e}", 
                              extra={'log_color': 'DELTA'})
                current_chunk.append(file_path)
        
        # Add remaining chunk
        if current_chunk:
            logger.info(f"  → Creating final chunk {len(chunks)+1} with {len(current_chunk)} files "
                       f"({current_tokens} tokens)", 
                       extra={'log_color': 'PERCENT'})
            chunks.append(current_chunk)
        
        state.log_micro_step('adaptive_chunking_complete', {
            'chunks_created': len(chunks),
            'avg_chunk_size': sum(len(c) for c in chunks) / len(chunks) if chunks else 0
        })
        
        logger.info(f"✅ Adaptive chunking complete: {len(files)} files → {len(chunks)} chunks", 
                   extra={'log_color': 'PERCENT'})
        for i, chunk in enumerate(chunks, 1):
            chunk_names = [Path(f).name for f in chunk]
            logger.info(f"  Chunk {i}: {', '.join(chunk_names)}", 
                       extra={'log_color': 'PERCENT'})
        
        return chunks
    
    def _estimate_complexity(self, file_path: str) -> float:
        """
        Estimate complexity of a file (0.0 = simple, 1.0 = complex).
        """
        try:
            content = self.file_service.safe_read_file(file_path)
            
            # Complexity indicators
            lines = len(content.split('\n'))
            functions = content.count('def ') + content.count('function ')
            classes = content.count('class ')
            imports = content.count('import ')
            
            # Normalize to 0-1 scale
            complexity = min(1.0, (
                (lines / 500) * 0.3 +
                (functions / 20) * 0.3 +
                (classes / 10) * 0.2 +
                (imports / 30) * 0.2
            ))
            
            return complexity
            
        except Exception:
            return 0.5  # Default medium complexity

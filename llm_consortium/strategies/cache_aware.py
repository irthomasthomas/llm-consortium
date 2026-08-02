"""
Cache-Aware Consortium Strategy

For DeepSeek API (and similar providers with context caching), this strategy
serializes the first instance of each model to establish a cache prefix, then
launches remaining instances in parallel to benefit from cache hits.

DeepSeek context caching:
- Cache is persisted at request boundaries (when a request completes)
- Also at fixed token intervals (~128 tokens) for long inputs
- Subsequent requests with matching prefixes hit cache (90% cost reduction)
- Even 0.1s delay between requests can trigger cache hits

Strategy:
1. Group model instances by model_id
2. Launch instance 0 of each model first
3. Wait for completion (or first token in streaming mode)
4. Launch remaining instances in parallel to benefit from cache
"""

import concurrent.futures
import logging
import time
from typing import List, Dict, Any, Optional

from .base import ConsortiumStrategy

logger = logging.getLogger(__name__)


class CacheAwareStrategy(ConsortiumStrategy):
    """
    Optimizes model execution order for maximum prompt cache hits.
    
    Strategy params:
        cache_delay: float - Delay in seconds between first and subsequent instances (default: 0.5)
        cache_mode: str - 'completion' (wait for full response) or 'streaming' (wait for first token)
        per_model_serial: bool - Serialize first call per model (default: True)
        max_cache_wait: float - Maximum time to wait for cache in seconds (default: 10)
    """
    
    def __init__(self, orchestrator, params=None):
        super().__init__(orchestrator, params)
        self.cache_delay = float(self.params.get('cache_delay', 0.5))
        self.cache_mode = self.params.get('cache_mode', 'completion')
        self.per_model_serial = self.params.get('per_model_serial', True)
        self.max_cache_wait = float(self.params.get('max_cache_wait', 10))
        
        # Track which models have had their first instance complete
        self._cache_established: set = set()
        # Track first instance results for each model
        self._first_instance_results: Dict[str, Dict[str, Any]] = {}
        
        logger.debug(
            f"CacheAwareStrategy initialized: delay={self.cache_delay}s, "
            f"mode={self.cache_mode}, per_model_serial={self.per_model_serial}"
        )
    
    def initialize_state(self):
        """Reset cache tracking for new orchestration run."""
        self._cache_established.clear()
        self._first_instance_results.clear()
    
    def select_models(self, available_models: Dict[str, int], current_prompt: str, iteration: int) -> Dict[str, int]:
        """Select all available models (same as default)."""
        return available_models.copy()
    
    def process_responses(self, successful_responses: List[Dict[str, Any]], iteration: int) -> List[Dict[str, Any]]:
        """Pass through all responses unmodified."""
        return successful_responses
    
    def prepare_iteration_prompt(self, model_id: str, instance: int, original_prompt: str, iteration: int) -> str:
        """
        Cache-optimized prompt: static content first, dynamic guidance last.
        This ensures the prefix (iteration history) is stable for cache hits.
        """
        if not self.orchestrator.iteration_history:
            return original_prompt
        
        prev_synth = self.orchestrator.iteration_history[-1].get("synthesis", {}).get("synthesis", "")
        
        guidance = f"""Iteration Guidance:
Please improve upon the previous iteration based on this synthesis:
{prev_synth}"""
        
        if getattr(self.orchestrator, 'manual_context', False):
            # Cache-optimized layout: Static content (original prompt) first,
            # dynamic iteration guidance last
            return f"Original Context/Prompt: {original_prompt}\n---\n{guidance}"
        else:
            return guidance
    
    def get_instance_system_prompt(self, model: str, instance: int, default_prompt: Optional[str]) -> Optional[str]:
        """
        Ensure all instances of the same model get identical system prompts
        for maximum cache hit potential.
        """
        return default_prompt


def execute_cache_aware_responses(
    orchestrator,
    prompt: str,
    models: Dict[str, int],
    iteration: int,
    get_response_fn
) -> List[Dict[str, Any]]:
    """
    Execute model responses with cache-aware scheduling.
    
    For each model with multiple instances:
    1. Launch instance 0 first (establish cache)
    2. Wait for cache delay
    3. Launch remaining instances in parallel
    
    Different models can run their first instances in parallel.
    """
    strategy = orchestrator.strategy
    cache_delay = getattr(strategy, 'cache_delay', 0.5)
    cache_mode = getattr(strategy, 'cache_mode', 'completion')
    per_model_serial = getattr(strategy, 'per_model_serial', True)
    
    if not per_model_serial:
        # Fall back to default parallel execution
        return _execute_all_parallel(orchestrator, prompt, models, iteration, get_response_fn)
    
    # Step 1: Group instances by model
    model_instances = {}
    for model_id, count in models.items():
        model_instances[model_id] = list(range(count))
    
    # Step 2: Identify first instances and remaining instances per model
    first_instances = []
    remaining_instances = []
    
    for model_id, instances in model_instances.items():
        if instances:
            first_instances.append((model_id, instances[0]))
            for inst in instances[1:]:
                remaining_instances.append((model_id, inst))
    
    logger.info(
        f"Cache-aware execution: {len(first_instances)} first instances, "
        f"{len(remaining_instances)} cache-benefiting instances"
    )
    
    # Step 3: Launch all first instances in parallel
    first_responses = {}
    first_start = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(first_instances) or 1, 10)) as executor:
        future_to_model = {}
        for model_id, instance in first_instances:
            task = (model_id, prompt, instance, iteration)
            future = executor.submit(get_response_fn, *task)
            future_to_model[future] = (model_id, instance)
        
        for future in concurrent.futures.as_completed(future_to_model):
            model_id, instance = future_to_model[future]
            try:
                result = future.result()
                first_responses[(model_id, instance)] = result
                logger.debug(f"First instance {model_id}/{instance} completed")
            except Exception as e:
                first_responses[(model_id, instance)] = {
                    "model": model_id,
                    "instance": instance,
                    "error": str(e)
                }
    
    first_elapsed = time.time() - first_start
    logger.info(f"First instances completed in {first_elapsed:.2f}s")
    
    # Step 4: Wait for cache persistence if there are remaining instances
    if remaining_instances:
        wait_time = cache_delay
        if cache_mode == 'streaming':
            # If using streaming, we could have waited less
            wait_time = min(wait_time, 0.5)
        
        logger.debug(f"Waiting {wait_time}s for cache persistence...")
        time.sleep(wait_time)
    
    # Step 5: Launch remaining instances in parallel
    remaining_responses = {}
    
    if remaining_instances:
        remaining_start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(remaining_instances) or 1, 10)) as executor:
            future_to_model = {}
            for model_id, instance in remaining_instances:
                task = (model_id, prompt, instance, iteration)
                future = executor.submit(get_response_fn, *task)
                future_to_model[future] = (model_id, instance)
            
            for future in concurrent.futures.as_completed(future_to_model):
                model_id, instance = future_to_model[future]
                try:
                    result = future.result()
                    remaining_responses[(model_id, instance)] = result
                except Exception as e:
                    remaining_responses[(model_id, instance)] = {
                        "model": model_id,
                        "instance": instance,
                        "error": str(e)
                    }
        
        remaining_elapsed = time.time() - remaining_start
        logger.info(f"Remaining instances completed in {remaining_elapsed:.2f}s (with cache)")
    
    # Step 6: Combine all responses
    all_responses = list(first_responses.values()) + list(remaining_responses.values())
    return all_responses


def _execute_all_parallel(orchestrator, prompt, models, iteration, get_response_fn):
    """Fallback: execute all model instances in parallel."""
    tasks = []
    for model_id, count in models.items():
        for instance in range(count):
            tasks.append((model_id, prompt, instance, iteration))
    
    responses = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tasks) or 1, 10)) as executor:
        future_to_task = {executor.submit(get_response_fn, *task): task for task in tasks}
        for future in concurrent.futures.as_completed(future_to_task):
            try:
                responses.append(future.result())
            except Exception as e:
                task = future_to_task[future]
                responses.append({
                    "model": task[0],
                    "instance": task[2],
                    "error": str(e)
                })
    return responses

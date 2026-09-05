import concurrent.futures
import json
import logging
import re
import uuid
import pathlib
from typing import List, Dict, Any, Optional

import llm

from .strategies.factory import create_strategy
from .strategies.cache_aware import execute_cache_aware_responses
from .strategies.cache_max import execute_cache_max_responses
from .db import (
    log_response,
    save_consortium_run,
    save_consortium_member,
    save_arbiter_decision,
    update_consortium_run,
)
from .embeddings.service import EmbeddingService, create_embedding_service
from .geometry import GeometricConfidenceCalculator
from .models import ConsortiumConfig

logger = logging.getLogger(__name__)

def _read_prompt_file(filename: str) -> str:
    try:
        file_path = pathlib.Path(__file__).parent / filename
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error reading {filename} file: {e}")
        return ""

def _read_system_prompt() -> str:
    return _read_prompt_file("system_prompt.xml")

def _read_arbiter_prompt() -> str:
    return _read_prompt_file("arbiter_prompt.xml")

def _read_iteration_prompt() -> str:
    return _read_prompt_file("iteration_prompt.xml")

def _read_rank_prompt() -> str:
    return _read_prompt_file("rank_prompt.xml")

def _read_arbiter_system_prompt() -> str:
    return _read_prompt_file("arbiter_system.xml")


def _read_arbiter_system_xml_prompt() -> str:
    return _read_prompt_file("arbiter_system_xml.xml")

def _read_rank_system_prompt() -> str:
    return _read_prompt_file("rank_system.xml")

def _read_rank_cot_system_prompt() -> str:
    return _read_prompt_file("rank_cot_system.xml")

def _read_rank_cot_prompt() -> str:
    return _read_prompt_file("rank_cot_prompt.xml")

def _active_responses(parsed: Dict[str, Any], iteration: int) -> List[Dict[str, Any]]:
    """Responses associated with a decision (used for geometry enrichment)."""
    return parsed.get("_responses_for_geometry", []) or []


class IterationContext:
    def __init__(self, synthesis: Dict[str, Any], model_responses: List[Dict[str, Any]]):
        self.synthesis = synthesis
        self.model_responses = model_responses

class ConsortiumOrchestrator:
    def __init__(self, config: ConsortiumConfig, config_name: Optional[str] = None):
        self.config = config
        self.config_name = config_name
        self.models = config.models
        self.system_prompt = config.system_prompt
        self.confidence_threshold = config.confidence_threshold
        self.max_iterations = config.max_iterations
        self.minimum_iterations = config.minimum_iterations
        self.arbiter = config.arbiter
        self.judging_method = config.judging_method
        self.strategy = create_strategy(config.strategy, self, config.strategy_params)
        self.manual_context = config.manual_context
        # Arbiter instructions are delivered via the system channel (one stable
        # contract per run) unless disabled for judges without a system role.
        self.arbiter_system_enabled = (config.strategy_params or {}).get("arbiter_system_prompt", True)
        self.arbiter_system_prompt = (
            self._load_arbiter_system_prompt(self.judging_method)
            if self.arbiter_system_enabled else None
        )
        self.iteration_history = []
        self._conversation_history = ""
        self.consortium_id = None
        self._embedding_service: Optional[EmbeddingService] = None

        # Conversation management - persist across turns
        self.model_conversations: dict = {}  # Key: f"{model_name}_{instance_id}"
        self.arbiter_conversation = None

    def get_embedding_service(self) -> EmbeddingService:
        if self._embedding_service is None:
            self._embedding_service = create_embedding_service(self.config)
        return self._embedding_service

    def _get_model_conversation(self, model_name: str, instance_id: int):
        """Get or create a conversation for a specific model instance."""
        if self.manual_context:
            return None
        key = f"{model_name}_{instance_id}"
        if key not in self.model_conversations:
            try:
                model = llm.get_model(model_name)
                self.model_conversations[key] = model.conversation()
                logger.debug(f"Created new conversation for {key}")
            except Exception as e:
                logger.error(f"Failed to create conversation for {model_name} instance {instance_id}: {e}")
                return None
        return self.model_conversations[key]

    def _get_arbiter_conversation(self):
        """Get or create a conversation for the arbiter."""
        if self.manual_context:
            return None
        if self.arbiter_conversation is None:
            try:
                model = llm.get_model(self.arbiter)
                self.arbiter_conversation = model.conversation()
                logger.debug(f"Created new conversation for arbiter {self.arbiter}")
            except Exception as e:
                logger.error(f"Failed to create conversation for arbiter {self.arbiter}: {e}")
                return None
        return self.arbiter_conversation

    def reset_model_conversations(self) -> None:
        """Reset all stored model conversations."""
        self.model_conversations.clear()
        logger.info("All model conversations reset.")

    def reset_arbiter_conversation(self) -> None:
        """Reset the stored arbiter conversation."""
        self.arbiter_conversation = None
        logger.info("Arbiter conversation reset.")

    def _final_status(self, synthesis_dict: Dict[str, Any]) -> str:
        """Terminal status for the run row. Explicit failure statuses set on
        config during the loop (model_failure / embedding_failure) win."""
        if self.config.status and self.config.status not in ("running", None):
            return self.config.status
        if not self.iteration_history:
            return "model_failure"
        if not synthesis_dict.get("synthesis"):
            return "empty_synthesis"
        if synthesis_dict.get("parse_success") is False:
            return "arbiter_parse_failure"
        return "success"

    def orchestrate(self, prompt: str, conversation_history: Optional[str] = None, consortium_id: Optional[str] = None) -> Dict[str, Any]:
        """Main entry point for orchestration - chooses method based on config."""
        self.consortium_id = consortium_id or str(uuid.uuid4())
        
        if self.manual_context:
            return self._orchestrate_manual(prompt, conversation_history, self.consortium_id)
        else:
            return self._orchestrate_automatic(prompt, conversation_history, self.consortium_id)

    def _orchestrate_manual(self, prompt: str, conversation_history: Optional[str] = None, consortium_id: Optional[str] = None) -> Dict[str, Any]:
        self.iteration_history = []
        self._conversation_history = conversation_history or ""
        
        self.strategy.initialize_state()
        
        save_consortium_run(
            run_id=str(consortium_id),
            strategy=getattr(self.config, 'strategy', None) or "default",
            judging_method=self.judging_method,
            confidence_threshold=self.confidence_threshold,
            max_iterations=self.max_iterations,
            iteration_count=0,
            final_confidence=0.0,
            user_prompt=prompt,
            config_name=self.config_name,
            category=self.config.category,
            expected_agreement=self.config.expected_agreement,
            status="running"
        )
        
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"Starting iteration {iteration}")
            
            available_models = self.models
            selected_models = self.strategy.select_models(available_models, prompt, iteration)
            
            model_responses = self._get_model_responses_manual(prompt, selected_models, iteration)
            model_responses = self.strategy.process_responses(model_responses, iteration)
            
            valid_responses = [r for r in model_responses if r.get('error') is None]
            if not valid_responses:
                logger.error("No valid responses from models in this iteration.")
                self.config.status = "embedding_failure" if getattr(self.config, 'embedding_backend', None) else "model_failure"
                break
            
            synthesis_result = self._synthesize_responses_manual(prompt, valid_responses, self.iteration_history, iteration)
            
            iteration_data = {
                "iteration": iteration,
                "selected_models": selected_models,
                "model_responses": model_responses,
                "synthesis": synthesis_result
            }
            self.iteration_history.append(iteration_data)
            
            context = IterationContext(synthesis=synthesis_result, model_responses=model_responses)
            self.strategy.update_state(context)
            
            # Check convergence: break if arbiter is confident and not requesting iteration
            # Unless synthesis was deferred (skip_intermediate_synthesis mode)
            synth_text = synthesis_result.get('synthesis', '')
            is_deferred = synth_text in ('', '[DEFERRED]')
            parse_ok = synthesis_result.get('parse_success', True)
            if parse_ok and not synthesis_result.get('needs_iteration', False) and iteration >= self.minimum_iterations:
                if (synthesis_result.get('confidence') or 0.0) >= self.confidence_threshold:
                    if is_deferred and iteration < self.max_iterations:
                        logger.info(f"Arbiter confident but synthesis deferred at iteration {iteration}, continuing for final synthesis")
                    else:
                        logger.info(f"Conversation converged at iteration {iteration} with confidence {synthesis_result.get('confidence')}")
                        break
        
        synthesis_dict = self.iteration_history[-1].get("synthesis", {}) if self.iteration_history else {}
        final_result = {
            "synthesis": synthesis_dict,
            "iterations": self.iteration_history,
            "metadata": {
                "total_iterations": len(self.iteration_history),
                "consortium_id": consortium_id,
                "config": self.config.to_dict()
            },
            "original_prompt": prompt
        }

        update_consortium_run(
            run_id=str(consortium_id),
            iteration_count=len(self.iteration_history),
            final_confidence=float(synthesis_dict.get("confidence", 0.0) or 0.0),
            status=self._final_status(synthesis_dict)
        )
        
        return final_result

    def _get_model_responses_manual(self, prompt: str, models: Dict[str, int], iteration: int) -> List[Dict[str, Any]]:
        # Auto-detect multi-instance models and use cache-aware execution
        # This is automatic for ALL strategies when multiple instances of the same model exist
        if self._has_multi_instance_models(models):
            # Use strategy's cache_delay if available, else default 0.5s
            cache_delay = getattr(self.strategy, 'cache_delay', 0.5)
            logger.info(f"Cache-aware execution (auto, delay={cache_delay}s) for {len(models)} models")
            executor_fn = execute_cache_max_responses if getattr(self.strategy, 'prewarm_arbiter', False) else execute_cache_aware_responses
            return executor_fn(
                self, prompt, models, iteration,
                self._get_single_model_response_manual
            )
        
        tasks = []
        for model_id, count in models.items():
            for i in range(count):
                tasks.append((model_id, prompt, i, iteration))
        
        responses = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tasks) or 1, 10)) as executor:
            future_to_task = {executor.submit(self._get_single_model_response_manual, *task): task for task in tasks}
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

    def _get_single_model_response_manual(self, model_id: str, prompt: str, instance: int, iteration: int) -> Dict[str, Any]:
        try:
            model = llm.get_model(model_id)
            
            # Get the strategy-modified system prompt for this specific model instance
            instance_system_prompt = self.strategy.get_instance_system_prompt(
                model_id, instance, self.system_prompt
            )
            
            full_prompt = ""
            if instance_system_prompt:
                full_prompt += f"System: {instance_system_prompt}\n\n"
            if self._conversation_history:
                full_prompt += f"{self._conversation_history}\n\n"
            
            # Delegate prompt formulation entirely to strategy to maximize cache hits
            strategy_prompt = self.strategy.prepare_iteration_prompt(model_id, instance, prompt, iteration)
            full_prompt += strategy_prompt
            response = model.prompt(full_prompt, system=instance_system_prompt)
            text = response.text()
            
            confidence = 0.5
            conf_match = re.search(r"<confidence>([\d.]+)</confidence>", text)
            if conf_match:
                try:
                    val = float(conf_match.group(1))
                    confidence = val / 100 if val > 1 else val
                except:
                    pass
            
            result = {
                "model": model_id,
                "instance": instance,
                "response": text,
                "confidence": confidence,
                "id": uuid.uuid4().int % 1000000,
                "response_id": str(getattr(response, 'id', uuid.uuid4())),
            }
            
            if hasattr(response, 'id') and self.consortium_id:
                log_response(response, model_id, str(self.consortium_id))
                role_label = self._member_role_label({"model": model_id, "instance": instance}) or None
                save_consortium_member(
                    str(self.consortium_id), str(response.id), model_id, iteration, instance,
                    strategy_role=role_label,
                )
            
            return result
        except Exception as e:
            logger.error(f"Error calling model {model_id}: {e}")
            return {"model": model_id, "instance": instance, "error": str(e)}

    def _orchestrate_automatic(self, prompt: str, conversation_history: Optional[str] = None, consortium_id: Optional[str] = None) -> Dict[str, Any]:
        self.iteration_history = []
        
        self.strategy.initialize_state()
        
        save_consortium_run(
            run_id=str(consortium_id),
            strategy=getattr(self.config, 'strategy', None) or "default",
            judging_method=self.judging_method,
            confidence_threshold=self.confidence_threshold,
            max_iterations=self.max_iterations,
            iteration_count=0,
            final_confidence=0.0,
            user_prompt=prompt,
            config_name=self.config_name,
            category=self.config.category,
            expected_agreement=self.config.expected_agreement,
            status="running"
        )
        
        model_tasks = []
        for model_id, count in self.models.items():
            for i in range(count):
                # Get the strategy-modified system prompt for this specific model instance
                instance_system_prompt = self.strategy.get_instance_system_prompt(
                    model_id, i, self.system_prompt
                )
                # Use persistent conversation object for multi-turn support
                conversation = self._get_model_conversation(model_id, i)
                if conversation is None:
                    model_obj = llm.get_model(model_id)
                    conversation = model_obj.conversation()
                model_tasks.append({
                    "model_id": model_id,
                    "instance": i,
                    "conversation": conversation,
                    "system_prompt": instance_system_prompt
                })
        
        # Store conversation history for first-iteration context injection
        if conversation_history:
            self._conversation_history = conversation_history

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"Starting iteration {iteration}")
            
            # Count real instances per model so multi-instance cache-aware serialization kicks in
            available_models: Dict[str, int] = {}
            for task in model_tasks:
                available_models[task["model_id"]] = available_models.get(task["model_id"], 0) + 1
            selected_models = self.strategy.select_models(available_models, prompt, iteration)
            
            responses = self._get_model_responses_automatic(prompt, model_tasks, selected_models, iteration)
            responses = self.strategy.process_responses(responses, iteration)
            
            valid_responses = [r for r in responses if r.get('error') is None]
            if not valid_responses:
                logger.error("No valid responses from models in this iteration.")
                self.config.status = "embedding_failure" if getattr(self.config, 'embedding_backend', None) else "model_failure"
                break
            
            synthesis_result = self._synthesize_responses_automatic(prompt, valid_responses, self.iteration_history, iteration)
            
            iteration_data = {
                "iteration": iteration,
                "selected_models": selected_models,
                "model_responses": responses,
                "synthesis": synthesis_result
            }
            self.iteration_history.append(iteration_data)
            
            context = IterationContext(synthesis=synthesis_result, model_responses=responses)
            self.strategy.update_state(context)
            
            # Check convergence: break if arbiter is confident and not requesting iteration
            # Unless synthesis was deferred (skip_intermediate_synthesis mode)
            synth_text = synthesis_result.get('synthesis', '')
            is_deferred = synth_text in ('', '[DEFERRED]')
            parse_ok = synthesis_result.get('parse_success', True)
            if parse_ok and not synthesis_result.get('needs_iteration', False) and iteration >= self.minimum_iterations:
                if (synthesis_result.get('confidence') or 0.0) >= self.confidence_threshold:
                    if is_deferred and iteration < self.max_iterations:
                        logger.info(f"Arbiter confident but synthesis deferred at iteration {iteration}, continuing for final synthesis")
                    else:
                        logger.info(f"Conversation converged at iteration {iteration} with confidence {synthesis_result.get('confidence')}")
                        break

        synthesis_dict = self.iteration_history[-1].get("synthesis", {}) if self.iteration_history else {}
        final_result = {
            "synthesis": synthesis_dict,
            "iterations": self.iteration_history,
            "metadata": {
                "total_iterations": len(self.iteration_history),
                "consortium_id": consortium_id,
                "config": self.config.to_dict()
            },
            "original_prompt": prompt
        }

        update_consortium_run(
            run_id=str(consortium_id),
            iteration_count=len(self.iteration_history),
            final_confidence=float(synthesis_dict.get("confidence", 0.0) or 0.0),
            status=self._final_status(synthesis_dict)
        )
        
        return final_result

    def _get_model_responses_automatic(self, prompt: str, tasks: List[Dict[str, Any]], 
                                     selected_models: Dict[str, int], iteration_idx: int) -> List[Dict[str, Any]]:
        responses = []
        active_tasks = [t for t in tasks if t["model_id"] in selected_models]
        
        # Auto-detect multi-instance models and use cache-aware execution
        if self._has_multi_instance_models(selected_models):
            cache_delay = getattr(self.strategy, 'cache_delay', 0.5)
            logger.info(f"Cache-aware execution (auto, delay={cache_delay}s)")
            def _auto_response_fn(model_id, prompt, instance, iteration):
                task = next((t for t in active_tasks if t["model_id"] == model_id and t["instance"] == instance), None)
                if task is None:
                    task = {"model_id": model_id, "instance": instance, "conversation": None, "system_prompt": None}
                iter_prompt = self.strategy.prepare_iteration_prompt(model_id, instance, prompt, iteration)
                return self._get_single_response_automatic(task, iter_prompt, iteration)
            
            executor_fn = execute_cache_max_responses if getattr(self.strategy, 'prewarm_arbiter', False) else execute_cache_aware_responses
            return executor_fn(
                self, prompt, selected_models, iteration_idx,
                _auto_response_fn
            )
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(active_tasks) or 1, 10)) as executor:
            future_to_task = {}
            for task in active_tasks:
                 # Always delegate so iteration 1 and >1 share the same cached prefix
                 iter_prompt = self.strategy.prepare_iteration_prompt(
                     task["model_id"], task["instance"], prompt, iteration_idx
                 )

                 future = executor.submit(self._get_single_response_automatic, task, iter_prompt, iteration_idx)
                 future_to_task[future] = task

            for future in concurrent.futures.as_completed(future_to_task):
                try:
                    responses.append(future.result())
                except Exception as e:
                    task = future_to_task[future]
                    responses.append({
                        "model": task["model_id"],
                        "instance": task["instance"],
                        "error": str(e)
                    })
        return responses

    def _get_single_response_automatic(self, task: Dict[str, Any], prompt: str, iteration: int) -> Dict[str, Any]:
        try:
            model_id = task["model_id"]
            conversation = task["conversation"]
            instance_system_prompt = task.get("system_prompt")
            
            # Inject conversation history on first iteration for multi-turn context
            full_prompt = prompt
            if iteration == 1 and hasattr(self, '_conversation_history') and self._conversation_history:
                full_prompt = f"""<conversation_history>
{self._conversation_history}
</conversation_history>

{prompt}"""
            
            response = conversation.prompt(full_prompt, system=instance_system_prompt)
            text = response.text()
            
            rid = hash(f"{model_id}_{task['instance']}_{iteration}") % 1000

            result = {
                "model": model_id,
                "instance": task["instance"],
                "response": text,
                "confidence": 0.5,
                "id": rid,
                "response_id": str(getattr(response, 'id', rid)),
            }
            
            if hasattr(response, 'id') and self.consortium_id:
                log_response(response, model_id, str(self.consortium_id))
                role_label = self._member_role_label({"model": model_id, "instance": task["instance"]}) or None
                save_consortium_member(
                    str(self.consortium_id), str(response.id), model_id, iteration, task["instance"],
                    strategy_role=role_label,
                )

            return result
        except Exception as e:
            logger.error(f"Automatic response error for {task['model_id']}: {e}")
            raise

    def _has_multi_instance_models(self, models: Dict[str, int]) -> bool:
        """Check if any model has more than 1 instance configured."""
        return any(count > 1 for count in models.values())

    @staticmethod
    def _load_arbiter_system_prompt(judging_method: str) -> str:
        """Load the judge instructions for the configured judging method."""
        if judging_method == "rank":
            return _read_rank_system_prompt() or _read_arbiter_system_prompt()
        if judging_method == "rank-cot":
            return _read_rank_cot_system_prompt() or _read_arbiter_system_prompt()
        if judging_method == "xml":
            return _read_arbiter_system_xml_prompt() or _read_arbiter_system_prompt()
        return _read_arbiter_system_prompt()

    def _resolve_arbiter_sys_prompt(self) -> Optional[str]:
        """System prompt for the arbiter call: strategy hook override (e.g.
        cache_max serves the member system prompt for byte-identical prefix
        caching) or the file-based arbiter instructions."""
        hook = getattr(self.strategy, "get_arbiter_system_prompt", None)
        if callable(hook):
            return hook(default=self.arbiter_system_prompt)
        return self.arbiter_system_prompt

    def _member_role_label(self, response: Dict[str, Any]) -> str:
        """Short strategy role label for a member, shown to the arbiter so it
        judges role-conformant behaviour fairly."""
        try:
            model = response.get("model", "")
            instance = response.get("instance", 0)
            assigned = getattr(self.strategy, "iteration_state", {}).get("assigned_roles", {})
            modifier = assigned.get(f"{model}-{instance}")
            if not modifier:
                return ""
            # first non-empty line after the override header
            for line in modifier.splitlines():
                line = line.strip().strip("[]")
                if line and "COGNITIVE ROLE OVERRIDE" not in line and "DIVERGENCE MATRIX" not in line:
                    return line[:80]
        except Exception:
            pass
        return ""

    def _synthesize_responses_manual(self, prompt: str, responses: List[Dict[str, Any]], 
                                   history: List[Dict[str, Any]], iteration: int) -> Dict[str, Any]:
        if not self.arbiter:
             return {
                 "synthesis": responses[0].get("response", ""),
                 "confidence": 1.0,
                 "analysis": "No arbiter defined, using first model response.",
                 "dissent": "",
                 "needs_iteration": False,
                 "refinement_areas": [],
                  "ranking": [r.get("id") for r in responses],
                  "geometric_confidence": 0.0,
                  "centroid_vector": None,
                  "parse_success": True,
             }

        arbiter_prompt = self._prepare_arbiter_prompt(prompt, responses, history, iteration=iteration)
        arbiter_model = llm.get_model(self.arbiter)

        parsed, raw_text, response, retried = self._synthesize_with_retry(
            arbiter_model, arbiter_prompt, responses,
            is_final_iteration=iteration >= getattr(self, "max_iterations", 3),
        )
        if retried:
            parsed["repair_retried"] = True
        log_response(response, self.arbiter, self.consortium_id)
        if hasattr(response, 'id') and self.consortium_id:
            save_consortium_member(str(self.consortium_id), str(response.id), 'arbiter', iteration, 0)
        self._persist_decision(response, parsed, iteration, raw_text, responses)
        return parsed

    def _synthesize_responses_automatic(self, prompt: str, valid_responses: List[Dict[str, Any]], 
                                      history: List[Dict[str, Any]], iteration: int) -> Dict[str, Any]:
        if not self.arbiter:
             return {
                 "synthesis": valid_responses[0].get("response", ""),
                 "confidence": 1.0,
                 "analysis": "No arbiter defined",
                 "needs_iteration": False,
                  "ranking": [r.get("id") for r in valid_responses],
                  "geometric_confidence": 0.0,
                  "centroid_vector": None,
                  "parse_success": True,
             }

        arbiter_model = llm.get_model(self.arbiter)
        arbiter_conversation = self._get_arbiter_conversation()
        if arbiter_conversation is None:
            arbiter_conversation = arbiter_model.conversation()

        arbiter_prompt = self._prepare_arbiter_prompt(prompt, valid_responses, history, iteration=iteration)
        parsed, raw_text, response, retried = self._synthesize_with_retry(
            arbiter_model, arbiter_prompt, valid_responses, conversation=arbiter_conversation,
            is_final_iteration=iteration >= getattr(self, "max_iterations", 3),
        )
        if retried:
            parsed["repair_retried"] = True
        log_response(response, self.arbiter, self.consortium_id)
        if hasattr(response, 'id') and self.consortium_id:
            save_consortium_member(str(self.consortium_id), str(response.id), 'arbiter', iteration, 0)
        self._persist_decision(response, parsed, iteration, raw_text, valid_responses)
        return parsed

    def _enrich_with_geometry(self, parsed_result: Dict[str, Any], responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        embeddings = [response.get("embedding") for response in responses if response.get("embedding") is not None]
        if not embeddings:
            parsed_result.setdefault("geometric_confidence", 0.0)
            parsed_result.setdefault("centroid_vector", None)
            return parsed_result

        confidence, centroid = GeometricConfidenceCalculator.compute(embeddings)
        parsed_result["geometric_confidence"] = confidence
        parsed_result["centroid_vector"] = centroid.tolist()
        parsed_result["outlier_indices"] = GeometricConfidenceCalculator.detect_outliers(embeddings)
        return parsed_result

    def _prepare_arbiter_prompt(self, prompt: str, responses: List[Dict[str, Any]], 
                               history: List[Dict[str, Any]], iteration: int = 1) -> str:
        formatted_responses = ""
        for i, r in enumerate(responses):
            rid = r.get("id", i)
            model_name = r.get("model", "unknown")
            response_text = r.get("response", "")
            role_label = self._member_role_label(r)
            formatted_responses += f"--- RESPONSE {rid} (Model: {model_name}"
            if role_label:
                formatted_responses += f" | Role: {role_label}"
            formatted_responses += f") ---\n"
            formatted_responses += response_text + "\n\n"

        formatted_history = ""
        for item in history:
            itr = item.get("iteration", "?")
            prev_synthesis = item.get("synthesis", {}).get("synthesis", "")
            formatted_history += f"Iteration {itr} synthesis:\n"
            formatted_history += prev_synthesis + "\n\n"

        # Determine if this is a forced-final iteration (last allowed iteration)
        is_final_iteration = iteration >= getattr(self, "max_iterations", 3)

        # Determine if we should skip synthesis for this intermediate iteration
        skip_synthesis = (
            getattr(getattr(self, 'config', None), 'skip_intermediate_synthesis', False)
            and not is_final_iteration
        )

        # --- Select the appropriate prompt template (data only; judge
        # instructions live in the system prompt, see _resolve_arbiter_sys_prompt) ---
        jm = getattr(self, 'judging_method', 'default')
        if jm == 'rank-cot':
            template = _read_rank_cot_prompt() or _read_arbiter_prompt()
        elif jm == 'rank':
            template = _read_rank_prompt() or _read_arbiter_prompt()
        else:
            template = _read_arbiter_prompt()

        if not template:
            template = "Original prompt: {original_prompt}\nModel responses:\n{formatted_responses}\nIteration history:\n{formatted_history}\nAnalyze the responses and provide a synthesis."

        # CacheMax: static prefix first (identical to member/iteration prompt prefix
        # and to the pre-warm request), dynamic responses LAST. This maximizes
        # prefix-cache hits for same-model arbiters and for pre-warmed arbiters.
        if getattr(self.strategy, 'arbiter_shared_prefix', False) and getattr(self, 'judging_method', 'default') != 'rank-cot':
            static_prefix = self.strategy.get_arbiter_prefix(prompt)
            if skip_synthesis:
                dynamic_suffix = self._build_skip_synthesis_suffix(
                    formatted_responses, formatted_history, responses
                )
            else:
                dynamic_suffix = (
                    "\n\n<model_responses>\n"
                    + formatted_responses
                    + "\n</model_responses>\n\n<iteration_history>\n"
                    + formatted_history
                    + "\n</iteration_history>\n\n"
                )
                if getattr(self, "arbiter_system_enabled", True):
                    if getattr(self, "judging_method", "default") == "xml":
                        dynamic_suffix += "Analyze the responses and reply with the <synthesis_output> block."
                    else:
                        dynamic_suffix += "Analyze the responses and reply with the JSON decision object."
                else:
                    if getattr(self, "judging_method", "default") == "xml":
                        dynamic_suffix += (
                            "Analyze the responses, then reply ONLY with the <synthesis_output> block "
                            "specified in your instructions."
                        )
                    else:
                        dynamic_suffix += (
                            "Analyze the responses, then reply ONLY with the JSON decision object "
                            "specified in your instructions."
                        )
            return static_prefix + dynamic_suffix

        # Build the formatted prompt
        formatted_prompt = template.format(
            original_prompt=prompt,
            formatted_responses=formatted_responses,
            formatted_history=formatted_history,
            user_instructions=self.system_prompt or ""
        )

        # Inject skip-synthesis instructions if applicable
        if skip_synthesis:
            skip_instruction = self._build_skip_synthesis_instruction(responses)
            formatted_prompt += "\n\n" + skip_instruction

        # Legacy inline mode (arbiter_system_prompt disabled): deliver judge
        # instructions in the user turn like the pre-split templates did.
        if not getattr(self, "arbiter_system_enabled", True):
            legacy_instructions = self._load_arbiter_system_prompt(getattr(self, 'judging_method', 'default'))
            if legacy_instructions:
                formatted_prompt += "\n\n" + legacy_instructions

        return formatted_prompt

    def _build_skip_synthesis_instruction(self, responses: List[Dict[str, Any]]) -> str:
        """Build the instruction block telling the arbiter to skip synthesis and provide evaluation + guidance."""
        per_model = getattr(self.config, 'per_model_guidance', True)

        guidance_json = (
            '\nFormat "model_guidance" as {"model-name_instance": "feedback"}.'
            if per_model else ''
        )
        return f"""**IMPORTANT - INTERMEDIATE EVALUATION MODE:**
This is an intermediate iteration. Do NOT produce a full "synthesis" value.
Instead, focus on:
1. Evaluating each response against the criteria.
2. Providing specific guidance for how each model should improve.
3. Set "needs_iteration": true if improvement is needed.
4. Set "synthesis" to "[DEFERRED]".
5. You may still set "needs_iteration": false with a real synthesis if you are already confident.{guidance_json}"""

    def _build_skip_synthesis_suffix(self, formatted_responses: str, formatted_history: str,
                                     responses: List[Dict[str, Any]]) -> str:
        """Build the CacheMax-style suffix for skip-synthesis mode."""
        suffix = (
            "\n\n<model_responses>\n"
            + formatted_responses
            + "\n</model_responses>\n\n<iteration_history>\n"
            + formatted_history
            + "\n</iteration_history>\n\n"
        )
        if getattr(self.config, 'per_model_guidance', True):
            suffix += (
                "This is an INTERMEDIATE iteration. Evaluate the responses and provide per-model guidance.\n"
                "Reply ONLY with the JSON decision object; set \"synthesis\" to \"[DEFERRED]\" and "
                "include \"model_guidance\" keyed by \"model-name_instance\"."
            )
        else:
            suffix += (
                "This is an INTERMEDIATE iteration. Evaluate and provide guidance.\n"
                "Reply ONLY with the JSON decision object; set \"synthesis\" to \"[DEFERRED]\"."
            )
        return suffix


    # ------------------------------------------------------------------
    # Arbiter invocation (JSON contract, schema-aware, one repair retry)
    # ------------------------------------------------------------------
    def _arbiter_json_schema(self) -> Optional[dict]:
        if self.judging_method == "xml":
            return None
        if self.judging_method == "rank":
            return self.RANK_JSON_SCHEMA
        if self.judging_method == "rank-cot":
            return self.RANK_COT_JSON_SCHEMA
        return self.ARBITER_JSON_SCHEMA

    def _call_arbiter(self, model, prompt: str, conversation=None):
        """Call the arbiter; pass schema= when the backend supports it."""
        schema = self._arbiter_json_schema()
        kwargs = {"schema": schema} if schema and getattr(model, "supports_schema", False) else {}
        if conversation is not None:
            return conversation.prompt(prompt, system=self._resolve_arbiter_sys_prompt(), stream=False, **kwargs)
        return model.prompt(prompt, system=self._resolve_arbiter_sys_prompt(), stream=False, **kwargs)

    def _parse_arbiter_call(self, raw_text: str, responses, judging_method: Optional[str] = None) -> Dict[str, Any]:
        jm = judging_method or self.judging_method
        if jm == "xml":
            return self._parse_arbiter_xml_response(raw_text, responses)
        if jm == "rank":
            return self._parse_rank_response(raw_text, responses)
        if jm == "rank-cot":
            return self._parse_rank_cot_response(raw_text, responses)
        return self._parse_arbiter_response(raw_text, responses=responses)

    def _degraded_acceptance(self, parsed: Dict[str, Any], missing: List[str], raw_text: str) -> Dict[str, Any]:
        """Accept an envelope-incomplete arbiter reply whose synthesis content
        is usable. Only used on the final iteration, after the repair retry."""
        return {
            "synthesis": parsed["degraded_synthesis"],
            "confidence": None,
            "analysis": f"Accepted degraded arbiter reply (missing: {', '.join(missing)}); one repair retry already attempted.",
            "dissent": "",
            "needs_iteration": False,
            "refinement_areas": [],
            "ranking": [],
            "chosen_response_id": None,
            "parse_success": True,
            "degraded": True,
            "missing_fields": missing,
            "model_guidance": {},
            "raw_arbiter_response": raw_text,
        }

    def _synthesize_with_retry(self, model, prompt: str, responses, conversation=None, is_final_iteration: bool = False):
        """One arbiter call + at most one repair retry when the reply violates
        the JSON contract. On the final iteration, if the retry still lacks the
        envelope fields but carries a usable synthesis, accept it degraded
        rather than discarding the arbiter's answer. Returns
        (parsed, raw_text, response_obj, retried)."""
        response = self._call_arbiter(model, prompt, conversation)
        raw_text = response.text()
        try:
            parsed = self._parse_arbiter_call(raw_text, responses)
        except Exception as e:
            parsed = self._fallback_decision(raw_text, str(e))

        if parsed.get("parse_success"):
            return parsed, raw_text, response, False

        detail = parsed.get("analysis", "unknown reason").replace("Parse failure: ", "")
        missing = parsed.get("missing_fields") or []
        logger.warning(
            "Arbiter reply violated the JSON contract (%s); sending one targeted repair request.",
            detail,
        )
        specifics = ""
        if missing:
            specifics = " Required fields are missing: " + ", ".join(f'"{m}"' for m in missing) + "."
        jm = getattr(self, "judging_method", "default")
        if jm == "xml":
            format_fix = (
                " Reply ONLY with the <synthesis_output> block: <analysis>, <dissent>, <synthesis>,"
                " <confidence>, <refinement_areas>, <needs_iteration>, <ranking> with <rank position=\"1\">ID</rank> entries."
                " The <synthesis> body must be the final answer to the original prompt itself —"
                " it must not mention, compare, or review the candidate responses, their IDs, models, or rankings."
            )
        else:
            format_fix = (
                ' "synthesis" must be a single JSON string (serialize any structured answer into it), "confidence" a number 0.0-1.0,'
                ' "ranking" the full list of response IDs as integers, "needs_iteration" a boolean.'
                " The \"synthesis\" string must be the final answer to the original prompt itself —"
                " it must not mention, compare, or review the candidate responses, their IDs, models, or rankings."
                " Reply ONLY with the complete JSON decision object. No prose, no Markdown fences."
            )
        repair_prompt = (
            prompt
            + "\n\nYour previous reply did not use the required format (" + detail + ")."
            + specifics
            + format_fix
        )
        try:
            response2 = self._call_arbiter(model, repair_prompt, conversation)
            raw2 = response2.text()
            try:
                parsed2 = self._parse_arbiter_call(raw2, responses)
            except Exception as e:
                parsed2 = self._fallback_decision(raw2, str(e))
            if parsed2.get("parse_success"):
                return parsed2, raw2, response2, True
            if is_final_iteration:
                for cand, cand_raw in ((parsed2, raw2), (parsed, raw_text)):
                    if cand.get("degraded_synthesis"):
                        logger.warning(
                            "Final-iteration arbiter reply still incomplete; accepting degraded synthesis (missing: %s).",
                            ", ".join(cand.get("missing_fields") or []),
                        )
                        return self._degraded_acceptance(cand, cand.get("missing_fields") or ["envelope"], cand_raw), cand_raw, response2, True
            return parsed2, raw2, response2, True
        except Exception as e:
            logger.error("Arbiter repair retry failed: %s", e)
            if is_final_iteration and parsed.get("degraded_synthesis"):
                return self._degraded_acceptance(parsed, parsed.get("missing_fields") or ["envelope"], raw_text), raw_text, response, True
            return parsed, raw_text, response, True

    def _persist_decision(self, response_obj, parsed: Dict[str, Any], iteration: int, raw_text: str, responses) -> None:
        parsed = self._enrich_with_geometry(parsed, responses)
        parsed.setdefault("raw_arbiter_response", raw_text)
        if hasattr(response_obj, "id") and self.consortium_id:
            save_arbiter_decision(
                str(self.consortium_id),
                iteration,
                str(response_obj.id),
                parsed,
                self.judging_method,
                geometric_confidence=parsed.get("geometric_confidence"),
                centroid_vector=parsed.get("centroid_vector"),
            )

    # ------------------------------------------------------------------
    # JSON arbiter contract
    # ------------------------------------------------------------------
    ARBITER_JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis": {"type": "string"},
            "dissent": {"type": "string"},
            "synthesis": {"type": "string"},
            "confidence": {"type": "number"},
            "refinement_areas": {"type": "array", "items": {"type": "string"}},
            "needs_iteration": {"type": "boolean"},
            "ranking": {"type": "array", "items": {"type": "integer"}},
            "model_guidance": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["synthesis", "confidence", "needs_iteration", "ranking"],
        "additionalProperties": False,
    }
    RANK_JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string"},
            "ranking": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["ranking"],
        "additionalProperties": False,
    }
    RANK_COT_JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "evaluation": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "strengths": {"type": "string"},
                        "weaknesses": {"type": "string"},
                    },
                    "required": ["id"],
                    "additionalProperties": False,
                },
            },
            "analysis": {"type": "string"},
            "dissent": {"type": "string"},
            "synthesis": {"type": "string"},
            "confidence": {"type": "number"},
            "refinement_areas": {"type": "array", "items": {"type": "string"}},
            "needs_iteration": {"type": "boolean"},
            "ranking": {"type": "array", "items": {"type": "integer"}},
            "model_guidance": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["synthesis", "confidence", "needs_iteration", "ranking"],
        "additionalProperties": False,
    }

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """Pull the first JSON object out of a response, tolerating fences,
        prose wrappers, and trailing garbage."""
        if not text:
            return None
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        candidates = []
        if fenced:
            candidates.append(fenced.group(1))
        # find outermost braces
        start = text.find("{")
        if start != -1:
            depth = 0
            for i, ch in enumerate(text[start:], start=start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start:i + 1])
                        break
        candidates.append(text)
        for c in candidates:
            c = c.strip()
            if not c.startswith("{"):
                continue
            try:
                obj = json.loads(c)
                if isinstance(obj, dict):
                    return obj
            except (json.JSONDecodeError, ValueError):
                continue
        # Last resort: salvage a reply truncated mid-JSON (backend output cap).
        for c in candidates:
            c = c.strip()
            start = c.find("{")
            if start == -1:
                continue
            repaired = ConsortiumOrchestrator._salvage_truncated_json(c[start:])
            if repaired is None:
                continue
            try:
                obj = json.loads(repaired)
                if isinstance(obj, dict):
                    logger.warning("Arbiter reply was truncated; salvaged a partial JSON object.")
                    return obj
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    @staticmethod
    def _scan_json_state(src: str):
        """Single pass over src returning (stack, in_string, escaped)."""
        stack = []
        in_str = False
        esc = False
        for ch in src:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
        return stack, in_str, esc

    @classmethod
    def _salvage_truncated_json(cls, src: str) -> Optional[str]:
        """Close an unterminated JSON document: balance quotes/brackets and
        drop a dangling partial member. Returns a candidate string or None."""

        def close(base: str) -> Optional[str]:
            stack, in_str, esc = cls._scan_json_state(base)
            patched = base
            if in_str:
                if esc and patched.endswith("\\"):
                    patched = patched[:-1]
                patched += '"'
                stack, _, _ = cls._scan_json_state(patched)
            for ch in reversed(stack):
                patched = patched.rstrip()
                if patched.endswith(","):
                    patched = patched[:-1].rstrip()
                patched += "}" if ch == "{" else "]"
            return patched

        if not src:
            return None
        candidates = [close(src)]
        # Variant: drop a dangling `,"partial-key` member before closing.
        trimmed = re.sub(r',\s*"(?:[^"\\]|\\.)*$|,\s*"[^"]*"?$', "", src.rstrip())
        if trimmed != src:
            candidates.append(close(trimmed))
        for cand in candidates:
            if not cand:
                continue
            try:
                json.loads(cand)
                return cand
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    def _finalize_decision(self, obj: dict, responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Normalize a parsed JSON decision dict into the canonical shape and
        resolve ranking -> chosen_response_id."""
        raw_synth = obj.get("synthesis")
        if isinstance(raw_synth, (dict, list)):
            # Task-format bleed-through: the arbiter nested the answer object
            # under "synthesis". Serialize it so the user still gets it.
            synthesis = json.dumps(raw_synth, ensure_ascii=False, indent=2)
        else:
            synthesis = str(raw_synth or "")
        conf_raw = obj.get("confidence")
        try:
            confidence = float(conf_raw) if conf_raw is not None else None
            if confidence is not None:
                if confidence > 1.0:
                    confidence = confidence / 100.0
                confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = None

        ranking: List[int] = []
        raw_ranking = obj.get("ranking")
        if raw_ranking:
            for entry in raw_ranking:
                try:
                    ranking.append(int(entry))
                except (TypeError, ValueError):
                    continue

        needs_it = obj.get("needs_iteration")
        needs_iteration = bool(needs_it) if isinstance(needs_it, bool) else str(needs_it).strip().lower() == "true"

        refinement = obj.get("refinement_areas") or []
        if isinstance(refinement, str):
            refinement = [a.strip() for a in re.split(r"[\n;]|,\s(?=[A-Z])", refinement) if a.strip()]

        result = {
            "synthesis": synthesis,
            "confidence": confidence,
            "analysis": str(obj.get("analysis") or ""),
            "dissent": str(obj.get("dissent") or ""),
            "needs_iteration": needs_iteration,
            "refinement_areas": refinement,
            "ranking": ranking,
            "chosen_response_id": None,
            "parse_success": True,
        }

        if ranking and responses is not None:
            top_id = ranking[0]
            top = next((r for r in responses if r.get("id") == top_id), None)
            if top:
                result["chosen_response_id"] = top.get("response_id")

        guidance = obj.get("model_guidance")
        if isinstance(guidance, dict):
            result["model_guidance"] = {str(k): str(v) for k, v in guidance.items()}
        else:
            result["model_guidance"] = {}

        evaluation = obj.get("evaluation")
        result["evaluation"] = evaluation if isinstance(evaluation, list) else []

        return result

    @staticmethod
    def _fallback_decision(text: str, reason: str, missing_fields: Optional[List[str]] = None,
                           degraded_synthesis: Optional[str] = None) -> Dict[str, Any]:
        """Raw-fallback decision shape. Never handed to the user as-is: callers
        retry once, may accept it degraded on the final iteration, or substitute
        the best member response downstream."""
        out = {
            "synthesis": text,
            "confidence": None,
            "analysis": f"Parse failure: {reason}",
            "dissent": "",
            "needs_iteration": False,
            "refinement_areas": [],
            "ranking": [],
            "chosen_response_id": None,
            "parse_success": False,
            "model_guidance": {},
            "raw_arbiter_response": text,
        }
        if missing_fields:
            out["missing_fields"] = missing_fields
        if degraded_synthesis:
            out["degraded_synthesis"] = degraded_synthesis
        return out

    # Strong signals: any ONE indicates judge meta-commentary.
    _META_LEAK_STRONG_CI = [
        r"\bResponse\s+\d{1,6}\b",
        r"\bresponse\s+IDs?\b",
        r"\bmodel responses?\b",
        r"\bcandidate responses?\b",
    ]
    # Shout-case judge headers ("VERDICT", "WINNER"): matched case-sensitively
    # so ordinary prose using lowercase "winner" is never rejected.
    _META_LEAK_UPPER = [
        r"\bVERDICT\b",
        r"\bWINNER\b",
        r"\bSTRENGTHS\b",
        r"\bWEAKNESSES\b",
        r"\bRESPONSE\s+\d+\b",
    ]
    # Weak/ambiguous signals: require TWO OR MORE distinct hits.
    _META_LEAK_WEAK_CI = [
        r"\bconsortium\b",
        r"\ball (?:three|responses|of the responses)\b",
        r"\bthe three responses\b",
        r"\bsynthes(?:is|es) of the\b",
    ]

    def _detect_meta_leak(self, synthesis: str) -> Optional[str]:
        """Return a short reason string when the 'synthesis' text looks like
        judge meta-commentary about the member responses rather than an
        answer to the original prompt. Only strong signals count; we never
        reject normal prose."""
        if not synthesis:
            return None
        text = synthesis[:4000]
        hits = []
        for pat in self._META_LEAK_STRONG_CI:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                hits.append(m.group(0))
        for pat in self._META_LEAK_UPPER:
            m = re.search(pat, text)
            if m:
                hits.append(m.group(0))
        if hits:
            return "synthesis contains arbiter meta-commentary (" + ", ".join(sorted(set(hits))[:3]) + ")"
        weak_hits = []
        for pat in self._META_LEAK_WEAK_CI:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                weak_hits.append(m.group(0))
        if len(set(weak_hits)) >= 2:
            return "synthesis contains arbiter meta-commentary (" + ", ".join(sorted(set(weak_hits))[:3]) + ")"
        return None

    def _parse_arbiter_xml_response(self, text: str, responses: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Parse the legacy <synthesis_output> tag contract. Returns the
        canonical decision shape; parse_success=False triggers the repair
        retry, and on final iteration a usable <synthesis> can be accepted
        degraded (via degraded_synthesis) without the envelope fields."""
        sections = {
            "synthesis": r"<synthesis>([\s\S]*?)</synthesis>",
            "confidence": r"<confidence>\s*([\d.]+)\s*</confidence>",
            "analysis": r"<analysis>([\s\S]*?)</analysis>",
            "dissent": r"<dissent>([\s\S]*?)</dissent>",
            "needs_iteration": r"<needs_iteration>(true|false)</needs_iteration>",
            "refinement_areas": r"<refinement_areas>([\s\S]*?)</refinement_areas>",
            "ranking": r"<ranking>([\s\S]*?)</ranking>",
        }
        result = {
            "synthesis": text,
            "confidence": None,
            "analysis": "",
            "dissent":  "",
            "needs_iteration": False,
            "refinement_areas": [],
            "ranking": [],
            "chosen_response_id": None,
            "parse_success": False,
            "model_guidance": {},
            "raw_arbiter_response": text,
        }
        found_any = False
        for key, pattern in sections.items():
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            found_any = True
            extracted_text = match.group(1).strip()
            if key == "confidence":
                try:
                    value = float(extracted_text)
                    result[key] = value / 100 if value > 1 else value
                except (ValueError, TypeError):
                    logger.warning("Could not parse confidence value: %s", extracted_text)
            elif key == "needs_iteration":
                result[key] = extracted_text.lower() == "true"
            elif key == "refinement_areas":
                result[key] = [a.strip() for a in re.split(r"\s*<area>\s*|\s*</area>\s*", extracted_text) if a.strip()]
            elif key == "ranking":
                ranked_ids_str = re.findall(r'<rank position="\d+">(\d+)</rank>', extracted_text, re.IGNORECASE)
                if not ranked_ids_str:
                    ranked_ids_str = re.findall(r"(\d+)", extracted_text)
                if ranked_ids_str:
                    ranked_ids = [int(x) for x in ranked_ids_str]
                    result["ranking"] = ranked_ids
                    if responses is not None:
                        top_id = ranked_ids[0]
                        top_response = next((r for r in responses if r.get("id") == top_id), None)
                        if top_response:
                            result["chosen_response_id"] = top_response.get("response_id")
            else:
                result[key] = extracted_text

        if not found_any:
            return self._fallback_decision(text, "no <synthesis_output> tags found in arbiter reply")
        # Envelope completeness: synthesis + ranking are mandatory.
        has_synth = bool(result.get("synthesis")) and result["synthesis"] != text
        missing = []
        if not has_synth:
            missing.append("synthesis")
        if not result["ranking"]:
            missing.append("ranking")
        if missing:
            reason = "XML reply missing required tags: " + ", ".join(f"<{m}>" for m in missing)
            degraded = result["synthesis"] if has_synth else None
            return self._fallback_decision(text, reason, missing_fields=missing, degraded_synthesis=degraded)
        leak = self._detect_meta_leak(result["synthesis"])
        if leak:
            fb = self._fallback_decision(text, leak)
            fb["ranking"] = result["ranking"]
            fb["chosen_response_id"] = result["chosen_response_id"]
            return fb
        result["parse_success"] = True
        return result

    def _parse_arbiter_response(self, text: str, is_final_iteration: bool = False, responses: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        obj = self._extract_json(text)
        if obj is None:
            return self._fallback_decision(text, "no JSON object found in arbiter reply")
        missing = []
        synth = obj.get("synthesis")
        if not synth:
            missing.append("synthesis")
        if not isinstance(obj.get("ranking"), list) or not obj.get("ranking"):
            missing.append("ranking")
        type_note = ""
        if synth is not None and not isinstance(synth, str):
            type_note = ';"synthesis" must be a JSON string, not a nested object/array'
        if missing:
            reason = "JSON missing required fields: " + ", ".join(f'"{m}"' for m in missing)
            reason += type_note
            degraded = None
            if synth:
                degraded = json.dumps(synth, ensure_ascii=False, indent=2) if isinstance(synth, (dict, list)) else str(synth)
                if degraded.strip() in ("", "[DEFERRED]"):
                    degraded = None
            return self._fallback_decision(text, reason, missing_fields=missing or ["synthesis_type"], degraded_synthesis=degraded)
        decision = self._finalize_decision(obj, responses)
        leak = self._detect_meta_leak(decision["synthesis"])
        if leak:
            fb = self._fallback_decision(text, leak)
            fb["ranking"] = decision["ranking"]
            fb["chosen_response_id"] = decision["chosen_response_id"]
            return fb
        return decision

    def _parse_rank_response(self, text: str, responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        obj = self._extract_json(text)
        if obj is None or not obj.get("ranking"):
            raise ValueError("Could not parse arbiter ranking from JSON reply.")
        decision = self._finalize_decision(obj, responses)
        ranked_ids = decision["ranking"]
        top_id = ranked_ids[0]
        top_response = next((r for r in responses if r.get("id") == top_id), None)
        if not top_response:
            raise ValueError(f"Top-ranked response ID {top_id} not found.")
        return {
            "synthesis": top_response.get("response", ""),
            "confidence": decision["confidence"] if decision["confidence"] is not None else 1.0,
            "analysis": f"Top: #{top_id} ({top_response.get('model', 'unknown')}). Reasoning: {decision['analysis'][:400]}",
            "dissent": "",
            "needs_iteration": False,
            "refinement_areas": [],
            "ranking": ranked_ids,
            "chosen_response_id": top_response.get("response_id"),
            "parse_success": True,
        }

    def _parse_rank_cot_response(self, text: str, responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        obj = self._extract_json(text)
        if obj is None or not obj.get("ranking"):
            return self._fallback_decision(text, "no ranking in rank-cot JSON")
        return self._finalize_decision(obj, responses)



def create_consortium(models: Any, arbiter: Optional[str] = None,
                     confidence_threshold: float = 0.8, max_iterations: int = 3,
                     minimum_iterations: int = 1, system_prompt: Optional[str] = None,
                     judging_method: str = "default", manual_context: bool = False,
                     strategy: str = "default", strategy_params: Optional[Dict[str, Any]] = None,
                     config_name: Optional[str] = None,
                     embedding_backend: Optional[str] = None,
                     embedding_model: Optional[str] = None,
                     skip_intermediate_synthesis: bool = False,
                     per_model_guidance: bool = True) -> ConsortiumOrchestrator:
    """Convenience constructor used by tests and external callers."""
    from .models import parse_models

    model_dict = models
    if isinstance(models, list):
        model_dict = parse_models(models, 1)

    config = ConsortiumConfig(
        models=model_dict,
        arbiter=arbiter,
        confidence_threshold=confidence_threshold,
        max_iterations=max_iterations,
        minimum_iterations=minimum_iterations,
        system_prompt=system_prompt,
        judging_method=judging_method,
        manual_context=manual_context,
        strategy=strategy,
        strategy_params=strategy_params,
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        skip_intermediate_synthesis=skip_intermediate_synthesis,
        per_model_guidance=per_model_guidance,
    )
    return ConsortiumOrchestrator(config, config_name=config_name)

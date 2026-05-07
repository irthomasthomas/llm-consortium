import concurrent.futures
import logging
import re
import uuid
import json
import time
import pathlib
from typing import List, Dict, Any, Optional

import llm

from .strategies.factory import create_strategy
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
            
            if not synthesis_result.get('needs_iteration', False) and iteration >= self.minimum_iterations:
                if synthesis_result.get('confidence', 0) >= self.confidence_threshold:
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
            status=self.config.status if self.config.status != "running" else ("empty_synthesis" if not synthesis_dict.get("synthesis") else "success")
        )
        
        return final_result

    def _get_model_responses_manual(self, prompt: str, models: Dict[str, int], iteration: int) -> List[Dict[str, Any]]:
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
                save_consortium_member(str(self.consortium_id), str(response.id), model_id, iteration, instance)
            
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
            
            available_models = {task["model_id"]: 1 for task in model_tasks}
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
            
            if not synthesis_result.get('needs_iteration', False) and iteration >= self.minimum_iterations:
                if synthesis_result.get('confidence', 0) >= self.confidence_threshold:
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
            status=self.config.status if self.config.status != "running" else ("empty_synthesis" if not synthesis_dict.get("synthesis") else "success")
        )
        
        return final_result

    def _get_model_responses_automatic(self, prompt: str, tasks: List[Dict[str, Any]], 
                                     selected_models: Dict[str, int], iteration_idx: int) -> List[Dict[str, Any]]:
        responses = []
        active_tasks = [t for t in tasks if t["model_id"] in selected_models]
        
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
                save_consortium_member(str(self.consortium_id), str(response.id), model_id, iteration, task["instance"])

            return result
        except Exception as e:
            logger.error(f"Automatic response error for {task['model_id']}: {e}")
            raise

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
             }

        arbiter_prompt = self._prepare_arbiter_prompt(prompt, responses, history)
        arbiter_model = llm.get_model(self.arbiter)
        
        response = arbiter_model.prompt(arbiter_prompt, stream=False)
        raw_arbiter_text = response.text()
        log_response(response, self.arbiter, self.consortium_id)
        
        if hasattr(response, 'id') and self.consortium_id:
            save_consortium_member(str(self.consortium_id), str(response.id), 'arbiter', iteration, 0)

        try:
            if self.judging_method == 'rank':
                parsed_result = self._parse_rank_response(raw_arbiter_text, responses)
            else:
                parsed_result = self._parse_arbiter_response(raw_arbiter_text, responses=responses)
            
            parsed_result = self._enrich_with_geometry(parsed_result, responses)
            parsed_result['raw_arbiter_response'] = raw_arbiter_text
            
            if hasattr(response, 'id') and self.consortium_id:
                save_arbiter_decision(
                    str(self.consortium_id),
                    iteration,
                    str(response.id),
                    parsed_result,
                    self.judging_method,
                    geometric_confidence=parsed_result.get('geometric_confidence'),
                    centroid_vector=parsed_result.get('centroid_vector'),
                )
            
            return parsed_result
        except Exception as e:
            logger.error(f"Error parsing arbiter response: {e}")
            return {
                "synthesis": raw_arbiter_text,
                "confidence": 0.0,
                "analysis": "Parsing failed - see raw response",
                "dissent": "",
                "needs_iteration": False,
                "refinement_areas": [],
                "geometric_confidence": 0.0,
                "centroid_vector": None,
                "raw_arbiter_response": raw_arbiter_text
            }

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
             }

        arbiter_model = llm.get_model(self.arbiter)
        arbiter_conversation = self._get_arbiter_conversation()
        if arbiter_conversation is None:
            arbiter_conversation = arbiter_model.conversation()
        
        arbiter_prompt = self._prepare_arbiter_prompt(prompt, valid_responses, history)
        
        arbiter_response = arbiter_conversation.prompt(arbiter_prompt, stream=False)
        raw_arbiter_text = arbiter_response.text()
        log_response(arbiter_response, self.arbiter, self.consortium_id)
        
        if hasattr(arbiter_response, 'id') and self.consortium_id:
            save_consortium_member(str(self.consortium_id), str(arbiter_response.id), 'arbiter', iteration, 0)

        try:
            if self.judging_method == 'rank':
                parsed_result = self._parse_rank_response(raw_arbiter_text, valid_responses)
            else:
                parsed_result = self._parse_arbiter_response(raw_arbiter_text, responses=valid_responses)
            
            parsed_result = self._enrich_with_geometry(parsed_result, valid_responses)
            parsed_result['raw_arbiter_response'] = raw_arbiter_text
            
            if hasattr(arbiter_response, 'id') and self.consortium_id:
                save_arbiter_decision(
                    str(self.consortium_id),
                    iteration,
                    str(arbiter_response.id),
                    parsed_result,
                    self.judging_method,
                    geometric_confidence=parsed_result.get('geometric_confidence'),
                    centroid_vector=parsed_result.get('centroid_vector'),
                )
            
            return parsed_result
        except Exception as e:
            logger.error(f"Error parsing arbiter response: {e}")
            return {
                "synthesis": raw_arbiter_text,
                "confidence": 0.0,
                "analysis": "Parsing failed - see raw response",
                "dissent": "",
                "needs_iteration": False,
                "refinement_areas": [],
                "geometric_confidence": 0.0,
                "centroid_vector": None,
                "raw_arbiter_response": raw_arbiter_text
            }

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
                               history: List[Dict[str, Any]]) -> str:
        formatted_responses = ""
        for i, r in enumerate(responses):
            rid = r.get("id", i)
            model_name = r.get("model", "unknown")
            response_text = r.get("response", "")
            formatted_responses += f"--- RESPONSE {rid} (Model: {model_name}) ---\\n"
            formatted_responses += response_text + "\\n\\n"

        formatted_history = ""
        for item in history:
            itr = item.get("iteration", "?")
            prev_synthesis = item.get("synthesis", {}).get("synthesis", "")
            formatted_history += f"Iteration {itr} synthesis:\\n"
            formatted_history += prev_synthesis + "\\n\\n"

        template = _read_arbiter_prompt()
        if not template:
            template = "Original prompt: {original_prompt}\\nModel responses:\\n{formatted_responses}\\nIteration history:\\n{formatted_history}\\nAnalyze the responses and provide a synthesis."

        return template.format(
            original_prompt=prompt,
            formatted_responses=formatted_responses,
            formatted_history=formatted_history,
            user_instructions=self.system_prompt or ""
        )

    def _parse_arbiter_response(self, text: str, is_final_iteration: bool = False, responses: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        sections = {
            "synthesis": r"<synthesis>([\s\S]*?)</synthesis>",
            "confidence": r"<confidence>\s*([\d.]+)\s*</confidence>",
            "analysis": r"<analysis>([\s\S]*?)</analysis>",
            "dissent": r"<dissent>([\s\S]*?)</dissent>",
            "needs_iteration": r"<needs_iteration>(true|false)</needs_iteration>",
            "refinement_areas": r"<refinement_areas>([\s\S]*?)</refinement_areas>",
            "ranking": r"<ranking>([\s\S]*?)</ranking>"
        }

        result = {
            "synthesis": text,
            "confidence": 0.0,
            "analysis": "",
            "dissent": "",
            "needs_iteration": False,
            "refinement_areas": [],
            "ranking": [],
            "chosen_response_id": None
        }

        for key, pattern in sections.items():
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                extracted_text = match.group(1).strip()
                if key == "confidence":
                    try:
                        value = float(extracted_text)
                        result[key] = value / 100 if value > 1 else value
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse confidence value: {extracted_text}")
                elif key == "needs_iteration":
                    result[key] = extracted_text.lower() == "true"
                elif key == "refinement_areas":
                    result[key] = [area.strip() for area in re.split(r'\s*<area>\s*|\s*</area>\s*', extracted_text) if area.strip()]
                elif key == "ranking":
                    ranked_ids_str = re.findall(r'<rank position="\d+">(\d+)</rank>', extracted_text, re.IGNORECASE)
                    if ranked_ids_str:
                        ranked_ids = [int(id_str) for id_str in ranked_ids_str]
                        result["ranking"] = ranked_ids
                        
                        if responses is not None and ranked_ids:
                            top_id = ranked_ids[0]
                            top_response = next((r for r in responses if r.get('id') == top_id), None)
                            if top_response:
                                result["chosen_response_id"] = top_response.get('response_id')
                else:
                    result[key] = extracted_text

        return result

    def _parse_rank_response(self, text: str, responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        ranking_match = re.search(r"<ranking>([\s\S]*?)</ranking>", text, re.IGNORECASE | re.DOTALL)
        if not ranking_match:
            raise ValueError("Could not find a <ranking> tag.")
        ranked_ids_str = re.findall(r'<rank position="\d+">(\d+)</rank>', ranking_match.group(1), re.IGNORECASE)
        if not ranked_ids_str:
            raise ValueError("Found <ranking> tag, but no valid <rank> tags inside.")
        ranked_ids = [int(id_str) for id_str in ranked_ids_str]
        top_id = ranked_ids[0]
        top_response = next((r for r in responses if r.get('id') == top_id), None)
        if not top_response:
            raise ValueError(f"Top-ranked response ID {top_id} not found.")
        
        return {
            "synthesis": top_response.get('response', ''), 
            "confidence": 1.0,
            "analysis": f"Top: #{top_id} ({top_response.get('model', 'unknown')}). Ranking: {ranked_ids}",
            "dissent": "", 
            "needs_iteration": False, 
            "refinement_areas": [], 
            "ranking": ranked_ids,
            "chosen_response_id": top_response.get('response_id')
        }

def create_consortium(models: Any, arbiter: Optional[str] = None, 
                     confidence_threshold: float = 0.8, max_iterations: int = 3,
                     minimum_iterations: int = 1, system_prompt: Optional[str] = None,
                     judging_method: str = "default", manual_context: bool = False,
                     strategy: str = "default", strategy_params: Optional[Dict[str, Any]] = None,
                     config_name: Optional[str] = None,
                     embedding_backend: Optional[str] = None,
                     embedding_model: Optional[str] = None) -> ConsortiumOrchestrator:
    
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
        embedding_model=embedding_model
    )
    return ConsortiumOrchestrator(config, config_name=config_name)

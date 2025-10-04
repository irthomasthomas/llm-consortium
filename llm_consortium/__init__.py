import click
import json
import llm
from llm.cli import load_conversation, resolve_alias_options  # Import from llm.cli instead of llm
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging
import sys
import re
import os
import pathlib
import sqlite_utils
from .conversation_manager import ConversationManager, ConsortiumResponse
from pydantic import BaseModel
import time  # added import for time
import concurrent.futures  # Add concurrent.futures for parallel processing
import threading  # Add threading for thread-local storage
import secrets
import uuid  # Add uuid import


# Read system prompt from file
def _read_system_prompt() -> str:
    try:
        file_path = pathlib.Path(__file__).parent / "system_prompt.txt"
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error reading system prompt file: {e}")
        return ""

def _read_arbiter_prompt() -> str:
    try:
        file_path = pathlib.Path(__file__).parent / "arbiter_prompt.xml"
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error reading arbiter prompt file: {e}")
        return ""

def _read_iteration_prompt() -> str:
    try:
        file_path = pathlib.Path(__file__).parent / "iteration_prompt.txt"
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error reading iteration prompt file: {e}")
        return ""


def _read_pick_one_prompt() -> str:
    try:
        file_path = pathlib.Path(__file__).parent / "pick_one_prompt.xml"
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error reading pick_one_prompt.xml file: {e}")
        return ""

def _read_rank_prompt() -> str:
    try:
        file_path = pathlib.Path(__file__).parent / "rank_prompt.xml"
        with open(file_path, "r") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error reading rank_prompt.xml file: {e}")
        return ""

DEFAULT_SYSTEM_PROMPT = _read_system_prompt()

def user_dir() -> pathlib.Path:
    """Get or create user directory for storing application data."""
    path = pathlib.Path(click.get_app_dir("io.datasette.llm"))
    return path

def logs_db_path() -> pathlib.Path:
    """Get path to logs database."""
    return user_dir() / "logs.db"

def setup_logging() -> None:
    """Configure logging to write to both file and console."""
    log_path = user_dir() / "consortium.log"

    # Create a formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler with ERROR level
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(str(log_path))
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.ERROR)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

# Replace existing logging setup with new setup
setup_logging()
logger = logging.getLogger(__name__)
logger.debug("llm_karpathy_consortium module is being imported")

class DatabaseConnection:
    _thread_local = threading.local()

    @classmethod
    def get_connection(cls) -> sqlite_utils.Database:
        """Get thread-local database connection to ensure thread safety."""
        if not hasattr(cls._thread_local, 'db'):
            cls._thread_local.db = sqlite_utils.Database(logs_db_path())
        return cls._thread_local.db

def _get_finish_reason(response_json: Dict[str, Any]) -> Optional[str]:
    """Helper function to extract finish reason from various API response formats."""
    if not isinstance(response_json, dict):
        return None
    # List of possible keys for finish reason (case-insensitive)
    reason_keys = ['finish_reason', 'finishReason', 'stop_reason']

    # Convert response to lowercase for case-insensitive matching
    lower_response = {k.lower(): v for k, v in response_json.items()}

    # Check each possible key
    for key in reason_keys:
        value = lower_response.get(key.lower())
        if value:
            return str(value).lower()

    return None

def log_response(response, model):
    """Log model response to database and log file."""
    try:
        db = DatabaseConnection.get_connection()
        response.log_to_db(db)
        logger.debug(f"Response from {model} logged to database")

        # Check for truncation in various formats
        if response.response_json:
            finish_reason = _get_finish_reason(response.response_json)
            truncation_indicators = ['length', 'max_tokens', 'max_token']

            if finish_reason and any(indicator in finish_reason for indicator in truncation_indicators):
                logger.warning(f"Response from {model} truncated. Reason: {finish_reason}")

    except Exception as e:
        logger.error(f"Error logging to database: {e}")

class IterationContext:
    def __init__(self, synthesis: Dict[str, Any], model_responses: List[Dict[str, Any]]):
        self.synthesis = synthesis
        self.model_responses = model_responses

class ConsortiumConfig(BaseModel):
    models: Dict[str, int]  # Maps model names to instance counts
    system_prompt: Optional[str] = None
    confidence_threshold: float = 0.8
    max_iterations: int = 3
    minimum_iterations: int = 1
    arbiter: Optional[str] = None
    judging_method: str = "default"

    def to_dict(self):
        return self.model_dump()

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

class ConsortiumOrchestrator:
    def __init__(self, config: ConsortiumConfig):
        self.models = config.models
        self.system_prompt = config.system_prompt
        self.confidence_threshold = config.confidence_threshold
        self.max_iterations = config.max_iterations
        self.minimum_iterations = config.minimum_iterations
        self.arbiter = config.arbiter or "gemini-2.0-flash"
        self.judging_method = config.judging_method
        self.iteration_history: List[IterationContext] = []
        self.consortium_id: Optional[str] = None
        # Conversation management
        self.model_conversations: Dict[str, llm.Conversation] = {}  # Key: f"{model_name}_{instance_id}"
        self.arbiter_conversation: Optional[llm.Conversation] = None

    def _get_model_conversation(self, model_name: str, instance_id: int) -> Optional[llm.Conversation]:
        """Get or create a conversation for a specific model instance with error handling."""
        key = f"{model_name}_{instance_id}"
        if key not in self.model_conversations:
            try:
                model = llm.get_model(model_name)
                self.model_conversations[key] = model.conversation()
                logger.debug(f"Created new conversation for {key}")
            except Exception as e:
                logger.error(f"Failed to create conversation for model {model_name} instance {instance_id}: {e}")
                return None
        return self.model_conversations[key]

    def _get_arbiter_conversation(self) -> Optional[llm.Conversation]:
        """Get or create a conversation for the arbiter with error handling."""
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

    def orchestrate(self, prompt: str, conversation_history: str = "", consortium_id: Optional[str] = None) -> Dict[str, Any]:
        self.consortium_id = consortium_id
        iteration_count = 0
        final_result = None
        original_prompt = prompt
        raw_arbiter_response_final = "" # Store the final raw response

        # Construct the prompt including history, system prompt, and original user prompt
        full_prompt_parts = []
        if conversation_history:
            # Append history if provided
            full_prompt_parts.append(conversation_history.strip())

        # Add system prompt if it exists
        if self.system_prompt:
            system_wrapper = f"[SYSTEM INSTRUCTIONS]\n{self.system_prompt}\n[/SYSTEM INSTRUCTIONS]"
            full_prompt_parts.append(system_wrapper)

        # Add the latest user prompt for this turn
        full_prompt_parts.append(f"Human: {original_prompt}")

        combined_prompt = "\n\n".join(full_prompt_parts)

        current_prompt = f"""<prompt>
    <instruction>{combined_prompt}</instruction>
</prompt>"""

        # For non-iterative methods, run only once
        if hasattr(self, "judging_method") and self.judging_method != "default":
            self.max_iterations = 1

        while iteration_count < self.max_iterations or iteration_count < self.minimum_iterations:
            iteration_count += 1
            logger.debug(f"Starting iteration {iteration_count}")

            # Get responses from all models using the current prompt
            model_responses = self._get_model_responses(current_prompt)
            # Add a unique ID to each response for the arbiter to reference
            for i, r in enumerate(model_responses, 1):
                r['id'] = i

            # Have arbiter synthesize and evaluate responses
            synthesis_result = self._synthesize_responses(original_prompt, model_responses)
            # Store the raw response text from this iteration
            raw_arbiter_response_final = synthesis_result.get("raw_arbiter_response", "")


            # Defensively check if synthesis_result is not None before proceeding
            if synthesis_result is not None:
                 # Ensure synthesis has the required keys to avoid KeyError
                if "confidence" not in synthesis_result:
                    synthesis_result["confidence"] = 0.0
                    logger.warning("Missing 'confidence' in synthesis, using default value 0.0")

                # Store iteration context
                self.iteration_history.append(IterationContext(synthesis_result, model_responses))

                if synthesis_result["confidence"] >= self.confidence_threshold and iteration_count >= self.minimum_iterations:
                    final_result = synthesis_result
                    break

                # Prepare for next iteration if needed
                current_prompt = self._construct_iteration_prompt(original_prompt, synthesis_result)
            else:
                # Handle the unexpected case where synthesis_result is None
                logger.error("Synthesis result was None, breaking iteration.")
                # Use the last valid synthesis if available, otherwise create a fallback
                if self.iteration_history:
                    final_result = self.iteration_history[-1].synthesis
                else:
                    final_result = {
                        "synthesis": "Error: Failed to get synthesis.", "confidence": 0.0,
                         "analysis": "Consortium failed.", "dissent": "", "needs_iteration": False,
                         "refinement_areas": [], "raw_arbiter_response": raw_arbiter_response_final
                    }
                break


        if final_result is None:
             # If loop finished without meeting threshold, use the last synthesis_result
            final_result = synthesis_result if synthesis_result is not None else {
                 "synthesis": "Error: No final synthesis.", "confidence": 0.0,
                 "analysis":"Consortium finished iterations.", "dissent": "", "needs_iteration": False,
                 "refinement_areas": [], "raw_arbiter_response": raw_arbiter_response_final
            }


        return {
            "original_prompt": original_prompt,
            # Storing all model responses might be verbose, consider adjusting if needed
            "model_responses_final_iteration": model_responses,
            "synthesis": final_result, # This now includes raw_arbiter_response
            "metadata": {
                "models_used": self.models,
                "arbiter": self.arbiter,
                "timestamp": datetime.utcnow().isoformat(),
                "iteration_count": iteration_count
            }
        }

    def _get_model_responses(self, prompt: str) -> List[Dict[str, Any]]:
        responses = []
        first_prompt_sent = False
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            for model, count in self.models.items():
                for instance in range(count):
                    # If this is the first prompt, mark it and submit immediately
                    if not first_prompt_sent:
                        futures.append(
                            executor.submit(self._get_model_response, model, prompt, instance, self.consortium_id)
                        )
                        first_prompt_sent = True
                    else:
                        futures.append(
                            executor.submit(self._get_model_response, model, prompt, instance, self.consortium_id)
                        )

            # Gather all results as they complete
            for future in concurrent.futures.as_completed(futures):
                responses.append(future.result())

        return responses

    def _get_model_response(self, model: str, prompt: str, instance: int, consortium_id: Optional[str] = None) -> Dict[str, Any]:
        # Generate a unique UUID for this specific prompt
        prompt_uuid = str(uuid.uuid4())
        
        if model == 'test-model':
            response = llm.Response.fake()
            response._set_content('test response')
        else:
            logger.debug(f"Getting response from model: {model} instance {instance + 1} with UUID: {prompt_uuid}")
            attempts = 0
            max_retries = 3

            # Generate a unique key for this model instance
            instance_key = f"{model}-{instance}"

            while attempts < max_retries:
                try:
                    # Use conversation for the prompt with instance-specific key
                    conversation = self._get_model_conversation(model, instance + 1)  # Pass 1-based instance ID
                    if conversation is None:
                        return {"model": model, "instance": instance + 1, "error": "Failed to initialize model conversation.", "uuid": prompt_uuid}

                    xml_prompt = f"""<prompt>
        <uuid>{prompt_uuid}</uuid>
        <instruction>{prompt}</instruction>
    </prompt>"""

                    # Use the conversation object for the prompt, applying alias options
                    alias_opts = resolve_alias_options(model)
                    if alias_opts and alias_opts.get("options"):
                        response = conversation.prompt(xml_prompt, stream=False, **alias_opts["options"])
                    else:
                        response = conversation.prompt(xml_prompt, stream=False)

                    text = response.text()
                    log_response(response, f"{model}-{instance + 1}")
                    return {
                        "model": model,
                        "instance": instance + 1,
                        "response": text,
                        "confidence": self._extract_confidence(text),
                        "uuid": prompt_uuid,  # Include UUID in response
                    }
                except Exception as e:
                    # Check if the error is a rate-limit error
                    if "RateLimitError" in str(e):
                        attempts += 1
                        wait_time = 2 ** attempts  # exponential backoff
                        logger.warning(f"Rate limit encountered for {model}, retrying in {wait_time} seconds... (attempt {attempts})")
                        time.sleep(wait_time)
                    else:
                        logger.exception(f"Error getting response from {model} instance {instance + 1}")
                        return {"model": model, "instance": instance + 1, "error": str(e), "uuid": prompt_uuid}
            return {"model": model, "instance": instance + 1, "error": "Rate limit exceeded after retries.", "uuid": prompt_uuid}

    def _parse_confidence_value(self, text: str, default: float = 0.0) -> float:
        """Helper method to parse confidence values consistently."""
        # Try to find XML confidence tag, now handling multi-line and whitespace better
        xml_match = re.search(r"<confidence>\s*(0?\.?\d+|1\.0|\d+)\s*</confidence>", text, re.IGNORECASE | re.DOTALL)
        if xml_match:
            try:
                value = float(xml_match.group(1).strip())
                return value / 100 if value > 1 else value
            except ValueError:
                pass

        # Fallback to plain text parsing
        for line in text.lower().split("\n"):
            if "confidence:" in line or "confidence level:" in line:
                try:
                    nums = re.findall(r"(\d*\.?\d+)%?", line)
                    if nums:
                        num = float(nums[0])
                        return num / 100 if num > 1 else num
                except (IndexError, ValueError):
                    pass

        return default

    def _extract_confidence(self, text: str) -> float:
        return self._parse_confidence_value(text)

    def _construct_iteration_prompt(self, original_prompt: str, last_synthesis: Dict[str, Any]) -> str:
        """Construct the prompt for the next iteration."""
        # Use the iteration prompt template from file instead of a hardcoded string
        iteration_prompt_template = _read_iteration_prompt()

        # If template exists, use it with formatting, otherwise fall back to previous implementation
        if iteration_prompt_template:
            # Include the user_instructions parameter from the system_prompt
            user_instructions = self.system_prompt or ""

            # Ensure all required keys exist in last_synthesis to prevent KeyError
            formatted_synthesis = {
                "synthesis": last_synthesis.get("synthesis", ""),
                "confidence": last_synthesis.get("confidence", 0.0),
                "analysis": last_synthesis.get("analysis", ""),
                "dissent": last_synthesis.get("dissent", ""),
                "needs_iteration": last_synthesis.get("needs_iteration", True),
                "refinement_areas": last_synthesis.get("refinement_areas", [])
            }

            # Check if the template requires refinement_areas
            if "{refinement_areas}" in iteration_prompt_template:
                try:
                    return iteration_prompt_template.format(
                        original_prompt=original_prompt,
                        previous_synthesis=json.dumps(formatted_synthesis, indent=2),
                        user_instructions=user_instructions,
                        refinement_areas="\n".join(formatted_synthesis["refinement_areas"])
                    )
                except KeyError:
                    # Fallback if format fails
                    return f"""Refining response for original prompt:
{original_prompt}

Arbiter feedback from previous attempt:
{json.dumps(formatted_synthesis, indent=2)}

Please improve your response based on this feedback."""
            else:
                try:
                    return iteration_prompt_template.format(
                        original_prompt=original_prompt,
                        previous_synthesis=json.dumps(formatted_synthesis, indent=2),
                        user_instructions=user_instructions
                    )
                except KeyError:
                    # Fallback if format fails
                    return f"""Refining response for original prompt:
{original_prompt}

Arbiter feedback from previous attempt:
{json.dumps(formatted_synthesis, indent=2)}

Please improve your response based on this feedback."""
        else:
            # Fallback to previous hardcoded prompt
            return f"""Refining response for original prompt:
{original_prompt}

Arbiter feedback from previous attempt:
{json.dumps(last_synthesis, indent=2)}

Please improve your response based on this feedback."""

    def _format_iteration_history(self) -> str:
        history = []
        for i, iteration in enumerate(self.iteration_history, start=1):
            model_responses = "\n".join(
                f"<model_response>{r['model']}: {r.get('response', 'Error')}</model_response>"
                for r in iteration.model_responses
            )

            history.append(f"""<iteration>
            <iteration_number>{i}</iteration_number>
            <model_responses>
                {model_responses}
            </model_responses>
            <synthesis>{iteration.synthesis.get('synthesis','Error')}</synthesis>
            <confidence>{iteration.synthesis.get('confidence',0.0)}</confidence>
            <refinement_areas>
                {self._format_refinement_areas(iteration.synthesis.get('refinement_areas', []))}
            </refinement_areas>
        </iteration>""")
        return "\n".join(history) if history else "<no_previous_iterations>No previous iterations available.</no_previous_iterations>"

    def _format_refinement_areas(self, areas: List[str]) -> str:
        return "\n                ".join(f"<area>{area}</area>" for area in areas)
    def _format_responses(self, responses: List[Dict[str, Any]]) -> str:
        formatted = []
        for r in responses:
            formatted.append(f"""<model_response>
            <id>{r["id"]}</id>
            <model>{r['model']}</model>
            <instance>{r.get('instance', 1)}</instance>
            <confidence>{r.get('confidence', 'N/A')}</confidence>
            <response>{r.get('response', 'Error: ' + r.get('error', 'Unknown error'))}</response>
        </model_response>""")
        return "\n".join(formatted)

    def _synthesize_responses(self, original_prompt: str, responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        logger.debug("Synthesizing responses using arbiter conversation")
        
        formatted_history = self._format_iteration_history()
        formatted_responses = self._format_responses(responses)

        user_instructions = self.system_prompt or ""

        # Choose prompt template based on judging method
        if hasattr(self, 'judging_method') and self.judging_method == 'pick-one':
            arbiter_prompt_template = _read_pick_one_prompt()
        elif hasattr(self, 'judging_method') and self.judging_method == 'rank':
            arbiter_prompt_template = _read_rank_prompt()
        else:
            arbiter_prompt_template = _read_arbiter_prompt()

        arbiter_prompt = arbiter_prompt_template.format(
            original_prompt=original_prompt,
            formatted_responses=formatted_responses,
            formatted_history=formatted_history,
            user_instructions=user_instructions
        )

        # Use conversation for the arbiter prompt
        arbiter_conversation = self._get_arbiter_conversation()
        if arbiter_conversation is None:
            logger.error("Failed to initialize arbiter conversation.")
            return {
                "synthesis": "Error: Arbiter unavailable.", "confidence": 0.0,
                "analysis": "Failed to initialize arbiter conversation.", "dissent": "",
                "needs_iteration": False, "refinement_areas": [],
                "raw_arbiter_response": "Error initializing arbiter conversation."
            }

        # Apply alias options to arbiter prompt
        alias_opts = resolve_alias_options(self.arbiter)
        if alias_opts and alias_opts.get("options"):
            arbiter_response = arbiter_conversation.prompt(arbiter_prompt, stream=False, **alias_opts["options"])
        else:
            arbiter_response = arbiter_conversation.prompt(arbiter_prompt, stream=False)
        raw_arbiter_text = arbiter_response.text()
        log_response(arbiter_response, self.arbiter)

        try:
            # Choose parser based on judging method
            if hasattr(self, 'judging_method') and self.judging_method == 'pick-one':
                parsed_result = self._parse_pick_one_response(raw_arbiter_text, responses)
            elif hasattr(self, 'judging_method') and self.judging_method == 'rank':
                parsed_result = self._parse_rank_response(raw_arbiter_text, responses)
            else:
                parsed_result = self._parse_arbiter_response(raw_arbiter_text)
            
            # Add raw response to the parsed result
            parsed_result['raw_arbiter_response'] = raw_arbiter_text
            return parsed_result
        except Exception as e:
            logger.error(f"Error parsing arbiter response: {e}")
            # Return fallback dict INCLUDING raw response
            return {
                "synthesis": raw_arbiter_text, # Fallback synthesis is raw text
                "confidence": 0.0,
                "analysis": "Parsing failed - see raw response",
                "dissent": "",
                "needs_iteration": False,
                "refinement_areas": [],
                "raw_arbiter_response": raw_arbiter_text # Ensure raw is included here
            }

    
    def _parse_arbiter_response(self, text: str, is_final_iteration: bool = False) -> Dict[str, Any]:
        """Parse arbiter response with special handling for final iteration."""
        sections = {
            "synthesis": r"<synthesis>([\s\S]*?)</synthesis>",
            "confidence": r"<confidence>\s*([\d.]+)\s*</confidence>",
            "analysis": r"<analysis>([\s\S]*?)</analysis>",
            "dissent": r"<dissent>([\s\S]*?)</dissent>",
            "needs_iteration": r"<needs_iteration>(true|false)</needs_iteration>",
            "refinement_areas": r"<refinement_areas>([\s\S]*?)</refinement_areas>"
        }

        # Initialize with default values to avoid KeyError
        result = {
            "synthesis": text,  # Use the full text as fallback synthesis
            "confidence": 0.0,   # Default confidence
            "analysis": "",
            "dissent": "",
            "needs_iteration": False,
            "refinement_areas": []
            # raw_arbiter_response is added in _synthesize_responses
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
                        # Keep default value if conversion fails
                        logger.warning(f"Could not parse confidence value: {extracted_text}")
                elif key == "needs_iteration":
                    result[key] = extracted_text.lower() == "true"
                elif key == "refinement_areas":
                    # Parse refinement areas, splitting by newline and filtering empty
                    result[key] = [area.strip() for area in re.split(r'\s*<area>\s*|\s*</area>\s*', extracted_text) if area.strip()]

                else:
                    result[key] = extracted_text # Store the clean extracted text

        # No special handling for is_final_iteration needed here anymore,
        # the synthesis field should contain the clean text if parsed correctly.

        # *** FIX: Explicitly return the result dictionary ***
        return result

    def _parse_pick_one_response(self, text: str, responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse arbiter response for pick-one method."""
        match = re.search(r"<response_id>\s*(\d+)\s*</response_id>", text, re.IGNORECASE)
        if not match:
            raise ValueError("Could not find a valid <response_id> tag.")
        chosen_id = int(match.group(1))
        chosen_response = next((r for r in responses if r.get('id') == chosen_id), None)
        if not chosen_response:
            raise ValueError(f"Arbiter chose response ID {chosen_id}, but this ID was not found.")
        return {
            "synthesis": chosen_response['response'], "confidence": 1.0,
            "analysis": f"Arbiter selected response #{chosen_id} from model '{chosen_response['model']}'.",
            "dissent": "", "needs_iteration": False, "refinement_areas": [], "chosen_id": chosen_id
        }

    def _parse_rank_response(self, text: str, responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse arbiter response for rank method."""
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
            "synthesis": top_response['response'], "confidence": 1.0,
            "analysis": f"Arbiter ranked all responses. Top choice is #{top_id} from '{top_response['model']}'. Full ranking: {ranked_ids}",
            "dissent": "", "needs_iteration": False, "refinement_areas": [], "ranking": ranked_ids
        }


def parse_models(models: List[str], count: int) -> Dict[str, int]:
    """Parse models and counts from CLI arguments into a dictionary."""
    model_dict = {}

    for item in models:
        # Basic split, can be enhanced later if needed
        if ':' in item:
             parts = item.split(':', 1)
             model_name = parts[0]
             try:
                 model_count = int(parts[1])
             except ValueError:
                 raise ValueError(f"Invalid count for model {model_name}: {parts[1]}")
             model_dict[model_name] = model_count
        else:
             model_dict[item] = count # Use default count if not specified

    return model_dict

def read_stdin_if_not_tty() -> Optional[str]:
    """Read from stdin if it's not a terminal."""
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return None

class ConsortiumModel(llm.Model):
    can_stream = False # Synchronous execution only for now

    class Options(llm.Options):
        confidence_threshold: Optional[float] = None
        max_iterations: Optional[int] = None
        system_prompt: Optional[str] = None  # Add support for system prompt as an option

    def __init__(self, model_id: str, config: ConsortiumConfig):
        self.model_id = model_id
        self.config = config
        self._orchestrator = None  # Lazy initialization

    def __str__(self):
        return f"Consortium Model: {self.model_id}"

    def get_orchestrator(self):
        if self._orchestrator is None:
            try:
                self._orchestrator = ConsortiumOrchestrator(self.config)
            except Exception as e:
                raise llm.ModelError(f"Failed to initialize consortium: {e}")
        return self._orchestrator

    def execute(self, prompt, stream, response, conversation):
        consortium_id = secrets.token_hex(8)
        """Execute the consortium synchronously"""
        try:
            # Extract conversation history from the conversation object directly
            conversation_history = ""
            if conversation and hasattr(conversation, 'responses') and conversation.responses:
                logger.info(f"Processing conversation with {len(conversation.responses)} previous exchanges")
                history_parts = []
                for resp in conversation.responses:
                    # Handle prompt format
                    human_prompt = "[prompt unavailable]"
                    if hasattr(resp, 'prompt') and resp.prompt:
                        if hasattr(resp.prompt, 'prompt'):
                            human_prompt = resp.prompt.prompt
                        else:
                            human_prompt = str(resp.prompt)

                    # Handle response text format
                    assistant_response = "[response unavailable]"
                    if hasattr(resp, 'text') and callable(resp.text):
                        assistant_response = resp.text()
                    elif hasattr(resp, 'response') and resp.response:
                        assistant_response = resp.response

                    # Format the history exchange
                    history_parts.append(f"Human: {human_prompt}")
                    history_parts.append(f"Assistant: {assistant_response}")

                if history_parts:
                    conversation_history = "\n\n".join(history_parts)
                    logger.info(f"Successfully formatted {len(history_parts)//2} exchanges from conversation history")

            # Check if a system prompt was provided via --system option
            if hasattr(prompt, 'system') and prompt.system:
                # Create a copy of the config with the updated system prompt
                updated_config = ConsortiumConfig(**self.config.to_dict())
                updated_config.system_prompt = prompt.system
                # Create a new orchestrator with the updated config
                orchestrator = ConsortiumOrchestrator(updated_config)
                result = orchestrator.orchestrate(prompt.prompt, conversation_history=conversation_history, consortium_id=consortium_id)
            else:
                # Use the default orchestrator with the original config
                result = self.get_orchestrator().orchestrate(prompt.prompt, conversation_history=conversation_history, consortium_id=consortium_id)

            # --- BEGIN REVISED FALLBACK LOGIC ---
            # Check result details from orchestrate
            final_synthesis_data = result.get("synthesis", {}) # This dict contains parsed fields and raw_arbiter_response
            raw_arbiter_response = final_synthesis_data.get("raw_arbiter_response", "")
            parsed_synthesis = final_synthesis_data.get("synthesis", "") # This is the parsed <synthesis> content
            analysis_text = final_synthesis_data.get("analysis", "")

            # Determine if parsing failed or synthesis is insufficient
            # Check 1: Explicit parsing failure message
            # Check 2: Parsed synthesis is empty, but raw response is not (likely missing <synthesis> tag)
            # Check 3: Parsed synthesis is exactly the raw response (parser fallback returned raw) AND no explicit success analysis
            is_fallback = ("Parsing failed" in analysis_text) or \
                          (not parsed_synthesis and raw_arbiter_response) or \
                          (parsed_synthesis == raw_arbiter_response and raw_arbiter_response) # Simpler check: If parsed == raw and raw is not empty, it's likely the fallback.

            if is_fallback:
                 final_output_text = raw_arbiter_response if raw_arbiter_response else "Error: Arbiter response unavailable or empty."
                 logger.warning("Arbiter response parsing failed or synthesis missing/empty. Returning raw arbiter response for logging.")
            else:
                 # Parsing seemed successful, return the clean synthesis
                 final_output_text = parsed_synthesis

            # Store the full result JSON in the response object for logging (existing code)
            response.response_json = result # Ensure this is still done before returning
            # Return the determined final text (clean synthesis or raw fallback)
            return final_output_text
            # --- END REVISED FALLBACK LOGIC ---

        except Exception as e:
            logger.exception(f"Consortium execution failed: {e}")
            raise llm.ModelError(f"Consortium execution failed: {e}")

def _get_consortium_configs() -> Dict[str, ConsortiumConfig]:
    """Fetch saved consortium configurations from the database."""
    db = DatabaseConnection.get_connection()

    db.execute("""
        CREATE TABLE IF NOT EXISTS consortium_configs (
            name TEXT PRIMARY KEY,
            config TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    configs = {}
    for row in db["consortium_configs"].rows:
        config_name = row["name"]
        try:
            config_data = json.loads(row["config"])
            configs[config_name] = ConsortiumConfig.from_dict(config_data)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
             logger.error(f"Error loading config for '{config_name}': {e}. Skipping.")
    return configs

def _save_consortium_config(name: str, config: ConsortiumConfig) -> None:
    """Save a consortium configuration to the database."""
    db = DatabaseConnection.get_connection()
    db.execute("""
        CREATE TABLE IF NOT EXISTS consortium_configs (
            name TEXT PRIMARY KEY,
            config TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db["consortium_configs"].insert(
        {"name": name, "config": json.dumps(config.to_dict())}, replace=True
    )

from click_default_group import DefaultGroup
class DefaultToRunGroup(DefaultGroup):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set 'run' as the default command
        self.default_cmd_name = 'run'
        self.ignore_unknown_options = True

    def get_command(self, ctx, cmd_name):
        # Try to get the command normally
        rv = super().get_command(ctx, cmd_name)
        if rv is not None:
            return rv
        # If command not found, check if it's an option for the default command
        # Also handle cases where the command might be misinterpreted as an option
        if cmd_name is None or cmd_name.startswith('-'):
            # Check if 'run' is a valid command in the current context
             run_cmd = super().get_command(ctx, self.default_cmd_name)
             if run_cmd:
                 return run_cmd
        return None

    def resolve_command(self, ctx, args):
        # If no command name detected, assume default command 'run'
        try:
            # Peek at the first arg without consuming it
            first_arg = args[0] if args else None
            # If the first arg isn't a known command and doesn't look like an option,
            # or if there are no args, prepend the default command name.
            if first_arg is None or (not first_arg.startswith('-') and super().get_command(ctx, first_arg) is None):
                 # Check if 'run' is actually registered before prepending
                 if super().get_command(ctx, self.default_cmd_name) is not None:
                     args.insert(0, self.default_cmd_name)
        except IndexError:
             # No arguments, definitely use default
             if super().get_command(ctx, self.default_cmd_name) is not None:
                 args = [self.default_cmd_name]

        return super().resolve_command(ctx, args)


def create_consortium(
    models: list[str],
    confidence_threshold: float = 0.8,
    max_iterations: int = 3,
    min_iterations: int = 1,
    arbiter: Optional[str] = None,
    judging_method: str = "default",
    system_prompt: Optional[str] = None,
    default_count: int = 1,
    raw: bool = False,
) -> ConsortiumOrchestrator:
    """
    Create and return a ConsortiumOrchestrator with a simplified API.
    - models: list of model names. To specify instance counts, use the format "model:count".
    - system_prompt: if not provided, DEFAULT_SYSTEM_PROMPT is used.
    """
    model_dict = parse_models(models, default_count) # Use parse_models here
    config = ConsortiumConfig(
        models=model_dict,
        system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
        confidence_threshold=confidence_threshold,
        max_iterations=max_iterations,
        minimum_iterations=min_iterations,
        arbiter=arbiter,
               judging_method=judging_method,
            )
    return ConsortiumOrchestrator(config=config)

@llm.hookimpl
def register_commands(cli):
    @cli.group(cls=DefaultToRunGroup)
    @click.pass_context
    def consortium(ctx):
        """Commands for managing and running model consortiums"""
        pass

    @consortium.command(name="run")
    @click.argument("prompt", required=False)
    @click.option(
        "-m",
        "--model", "models",  # store values in 'models'
        multiple=True,
        help="Model to include, use format 'model:count' or 'model' for default count. Multiple allowed.",
        default=[], # Default to empty list, require at least one model
    )
    @click.option(
        "-n",
        "--count",
        type=int,
        default=1,
        help="Default number of instances (if count not specified per model)",
    )
    @click.option(
        "--arbiter",
        help="Model to use as arbiter",
        default="claude-3-opus-20240229"
    )
    @click.option(
        "--confidence-threshold",
        type=float,
        help="Minimum confidence threshold (0.0-1.0)",
        default=0.8
    )
    @click.option(
        "--max-iterations",
        type=int,
        help="Maximum number of iteration rounds",
        default=3
    )
    @click.option(
        "--min-iterations",
        type=int,
        help="Minimum number of iterations to perform",
        default=1
    )
    @click.option(
        "--system",
        help="System prompt text or path to system prompt file.",
    )
    @click.option(
        "--output",
        type=click.Path(dir_okay=False, writable=True, path_type=pathlib.Path), # Use pathlib
        help="Save full results (JSON) to this file path.",
    )
    @click.option(
        "--stdin/--no-stdin", "read_from_stdin", # More descriptive name
        default=True, # Default changed to True
        help="Read prompt text from stdin if no prompt argument is given.",
    )
    @click.option(
        "--raw",
        is_flag=True,
        default=False,
        help="Output the raw, unparsed response from the final arbiter call instead of the clean synthesis.",
    )
    @click.option(
        "--judging-method",
        type=click.Choice(["default", "pick-one", "rank"], case_sensitive=False),
        default="default",
        help="Judging method for the arbiter (default, pick-one, rank)."
    )
    def run_command(prompt, models, count, arbiter, confidence_threshold, max_iterations,
                   min_iterations, system, output, read_from_stdin, raw, judging_method):
        """Run prompt through a dynamically defined consortium of models."""
        # Check if models list is empty
        if not models:
            # Provide default models if none are specified
            models = ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "gpt-4", "gemini-pro"]
            logger.info(f"No models specified, using default set: {', '.join(models)}")


        # Handle prompt input (argument vs stdin)
        if not prompt and read_from_stdin:
            prompt_from_stdin = read_stdin_if_not_tty()
            if prompt_from_stdin:
                prompt = prompt_from_stdin
            else:
                 # If stdin is not a tty but empty, or no prompt arg given & stdin disabled
                 if not sys.stdin.isatty():
                     logger.warning("Reading from stdin enabled, but stdin was empty.")
                 # Raise error only if no prompt was given via arg and stdin reading failed/disabled
                 if not prompt: # Check again if prompt was somehow set
                    raise click.UsageError("No prompt provided via argument or stdin.")
        elif not prompt and not read_from_stdin:
             raise click.UsageError("No prompt provided via argument and stdin reading is disabled.")


        # Parse models and counts
        try:
            model_dict = parse_models(models, count)
        except ValueError as e:
            raise click.ClickException(str(e))

        # Handle system prompt (text or file path)
        system_prompt_content = None
        if system:
             system_path = pathlib.Path(system)
             if system_path.is_file():
                 try:
                     system_prompt_content = system_path.read_text().strip()
                     logger.info(f"Loaded system prompt from file: {system}")
                 except Exception as e:
                     raise click.ClickException(f"Error reading system prompt file '{system}': {e}")
             else:
                 system_prompt_content = system # Use as literal string
                 logger.info("Using provided system prompt text.")
        else:
            system_prompt_content = DEFAULT_SYSTEM_PROMPT # Use default if nothing provided
            logger.info("Using default system prompt.")


        # Convert percentage confidence to decimal if needed
        if confidence_threshold > 1.0:
             if confidence_threshold <= 100.0:
                 confidence_threshold /= 100.0
             else:
                 raise click.UsageError("Confidence threshold must be between 0.0 and 1.0 (or 0 and 100).")
        elif confidence_threshold < 0.0:
             raise click.UsageError("Confidence threshold must be non-negative.")

        logger.info(f"Starting consortium run with {len(model_dict)} models.")
        logger.debug(f"Models: {', '.join(f'{k}:{v}' for k, v in model_dict.items())}")
        logger.debug(f"Arbiter model: {arbiter}")
        logger.debug(f"Confidence: {confidence_threshold}, Max Iter: {max_iterations}, Min Iter: {min_iterations}")

        orchestrator = ConsortiumOrchestrator(
            config=ConsortiumConfig(
               models=model_dict,
               system_prompt=system_prompt_content,
               confidence_threshold=confidence_threshold,
               max_iterations=max_iterations,
               minimum_iterations=min_iterations,
                arbiter=arbiter,
               judging_method=judging_method,
            )
        )

        try:
            result = orchestrator.orchestrate(prompt, consortium_id=consortium_id)

            # Output full result to JSON file if requested
            if output:
                try:
                    with output.open('w') as f:
                        json.dump(result, f, indent=2)
                    logger.info(f"Full results saved to {output}")
                except Exception as e:
                    click.ClickException(f"Error saving results to '{output}': {e}")


            # *** FIX: Conditional output based on --raw flag ***
            final_synthesis_data = result.get("synthesis", {})

            if raw:
                 # Output the raw arbiter response text
                 raw_text = final_synthesis_data.get("raw_arbiter_response", "Error: Raw arbiter response unavailable")
                 click.echo(raw_text)
            else:
                 # Output the clean synthesis text
                 clean_text = final_synthesis_data.get("synthesis", "Error: Clean synthesis unavailable")
                 click.echo(clean_text)

            # Optional: Log other parts like analysis/dissent if needed for debugging, but don't echo by default
            # logger.debug(f"Analysis: {final_synthesis_data.get('analysis', '')}")
            # logger.debug(f"Dissent: {final_synthesis_data.get('dissent', '')}")

        except Exception as e:
            logger.exception("Error during consortium run execution")
            raise click.ClickException(f"Consortium run failed: {e}")


    # Register consortium management commands group
    @consortium.command(name="save")
    @click.argument("name")
    @click.option(
        "-m",
        "--model", "models",
        multiple=True,
        help="Model to include (format 'model:count' or 'model'). Multiple allowed.",
        required=True,
    )
    @click.option(
        "-n",
        "--count",
        type=int,
        default=1,
        help="Default number of instances (if count not specified per model)",
    )
    @click.option(
        "--arbiter",
        help="Model to use as arbiter",
        required=True
    )
    @click.option(
        "--confidence-threshold",
        type=float,
        help="Minimum confidence threshold (0.0-1.0)",
        default=0.8
    )
    @click.option(
        "--max-iterations",
        type=int,
        help="Maximum number of iteration rounds",
        default=3
    )
    @click.option(
        "--min-iterations",
        type=int,
        help="Minimum number of iterations to perform",
        default=1
    )
    @click.option(
        "--system",
        help="System prompt text or path to system prompt file.",
    )
    @click.option(
        "--judging-method",
        type=click.Choice(["default", "pick-one", "rank"], case_sensitive=False),
        default="default",
        help="Judging method for the arbiter (default, pick-one, rank)."
    )
    def save_command(name, models, count, arbiter, confidence_threshold, max_iterations,
                     min_iterations, system, judging_method):
        """Save a consortium configuration to be used as a model."""
        try:
            model_dict = parse_models(models, count)
        except ValueError as e:
            raise click.ClickException(str(e))

        # Handle system prompt (text or file path) - similar to run_command
        system_prompt_content = None
        if system:
             system_path = pathlib.Path(system)
             if system_path.is_file():
                 try:
                     system_prompt_content = system_path.read_text().strip()
                 except Exception as e:
                     raise click.ClickException(f"Error reading system prompt file '{system}': {e}")
             else:
                 system_prompt_content = system
        # No default system prompt when saving? Or use DEFAULT_SYSTEM_PROMPT? Let's assume None if not provided.

        # Validate confidence threshold
        if confidence_threshold > 1.0:
             if confidence_threshold <= 100.0:
                 confidence_threshold /= 100.0
             else:
                 raise click.UsageError("Confidence threshold must be between 0.0 and 1.0 (or 0 and 100).")
        elif confidence_threshold < 0.0:
             raise click.UsageError("Confidence threshold must be non-negative.")


        config = ConsortiumConfig(
            models=model_dict,
            arbiter=arbiter,
            confidence_threshold=confidence_threshold,
            max_iterations=max_iterations,
            minimum_iterations=min_iterations,
            system_prompt=system_prompt_content,
            judging_method=judging_method,
        )
        try:
            _save_consortium_config(name, config)
            click.echo(f"Consortium configuration '{name}' saved.")
            click.echo(f"You can now use it like: llm -m {name} \"Your prompt here\"")
        except Exception as e:
             raise click.ClickException(f"Error saving consortium '{name}': {e}")


    @consortium.command(name="list")
    def list_command():
        """List all saved consortium configurations."""
        try:
            configs = _get_consortium_configs()
        except Exception as e:
             raise click.ClickException(f"Error reading consortium configurations: {e}")

        if not configs:
            click.echo("No saved consortiums found.")
            return

        click.echo("Available saved consortiums:\n")
        for name, config in configs.items():
            click.echo(f"Name: {name}")
            click.echo(f"  Models: {', '.join(f'{k}:{v}' for k, v in config.models.items())}")
            click.echo(f"  Arbiter: {config.arbiter}")
            click.echo(f"  Confidence Threshold: {config.confidence_threshold}")
            click.echo(f"  Max Iterations: {config.max_iterations}")
            click.echo(f"  Min Iterations: {config.minimum_iterations}")
            system_prompt_display = config.system_prompt
            if system_prompt_display and len(system_prompt_display) > 60:
                 system_prompt_display = system_prompt_display[:57] + "..."
            click.echo(f"  System Prompt: {system_prompt_display or 'Default'}")
            click.echo(f"  Judging Method: {config.judging_method}")
            click.echo("") # Empty line between consortiums


    @consortium.command(name="remove")
    @click.argument("name")
    def remove_command(name):
        """Remove a saved consortium configuration."""
        db = DatabaseConnection.get_connection()
        # Ensure table exists before trying to delete
        db.execute("""
        CREATE TABLE IF NOT EXISTS consortium_configs (
            name TEXT PRIMARY KEY,
            config TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        try:
            # Check if it exists before deleting
            count = db["consortium_configs"].count_where("name = ?", [name])
            if count == 0:
                 raise click.ClickException(f"Consortium with name '{name}' not found.")
            db["consortium_configs"].delete(name)
            click.echo(f"Consortium configuration '{name}' removed.")
        except Exception as e:
             # Catch potential database errors beyond NotFoundError
             raise click.ClickException(f"Error removing consortium '{name}': {e}")


@llm.hookimpl
def register_models(register):
    logger.debug("Registering saved consortium models")
    
    # Register the dummy model for testing
    try:
        dummy_model = DummyModel()
        register(dummy_model, aliases=["dummy"])
        logger.debug("Registered dummy model for testing")
    except Exception as e:
        logger.error(f"Failed to register dummy model: {e}")
    
    try:
        configs = _get_consortium_configs()
        for name, config in configs.items():
            try:
                # Ensure config is valid before registering
                if not config.models or not config.arbiter:
                     logger.warning(f"Skipping registration of invalid consortium '{name}': Missing models or arbiter.")
                     continue
                model_instance = ConsortiumModel(name, config)
                register(model_instance, aliases=[name]) # Use list for aliases
                logger.debug(f"Registered consortium model: {name}")
            except Exception as e:
                logger.error(f"Failed to register consortium model '{name}': {e}")
    except Exception as e:
        logger.error(f"Failed to load or register consortium configurations: {e}")


# Keep this class definition for potential future hook implementations
class KarpathyConsortiumPlugin:
    @staticmethod
    @llm.hookimpl
    def register_commands(cli):
        # This hook is technically handled by the register_commands function above,
        # but keeping the class structure might be useful.
        logger.debug("KarpathyConsortiumPlugin.register_commands hook called (via function)")
        pass # Function above does the work


logger.debug("llm_consortium module finished loading")

# Define __all__ for explicit exports if this were a larger package
__all__ = [
    'KarpathyConsortiumPlugin', 'ConsortiumModel', 'ConsortiumConfig',
    'ConsortiumOrchestrator', 'create_consortium', 'register_commands',
    'register_models', 'log_response', 'DatabaseConnection', 'logs_db_path',
    'user_dir'
]

__version__ = "0.3.2" # Incremented version number

class DummyModel(llm.Model):
    model_id = "dummy"
    can_stream = True
    
    def execute(self, prompt, stream, response, conversation):
        # Simple dummy model that echoes back the prompt with a prefix
        message = f"DUMMY ECHO: {prompt.prompt}"
        if stream:
            yield message
        else:
            return message

# Test the dummy model
if __name__ == "__main__":
    import tempfile
    import os
    
    # Create a temporary directory for the test
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["LLM_USER_PATH"] = tmpdir
        
        # Register the dummy model
        from llm.plugins import pm
        
        class DummyPlugin:
            __name__ = "DummyPlugin"
            
            @llm.hookimpl
            def register_models(self, register):
                register(DummyModel())
        
        pm.register(DummyPlugin(), name="dummy-plugin")
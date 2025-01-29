import click
import json
import llm
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging
import sys
import re
import os
import pathlib
import sqlite_utils
from pydantic import BaseModel

# Todo:
# "finish_reason": "length"
# "finish_reason": "max_tokens"
# "stop_reason": "max_tokens",
# "finishReason": "MAX_TOKENS"
# "finishReason": "length"
# response.response_json
# Todo: setup continuation models: claude, deepseek etc.

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

DEFAULT_SYSTEM_PROMPT = _read_system_prompt()

def user_dir() -> pathlib.Path:
    """Get or create user directory for storing application data."""
    llm_user_path = os.environ.get("LLM_USER_PATH")
    if llm_user_path:
        path = pathlib.Path(llm_user_path)
    else:
        path = pathlib.Path(click.get_app_dir("io.datasette.llm"))
    path.mkdir(exist_ok=True, parents=True)
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
    _instance: Optional['DatabaseConnection'] = None

    def __init__(self):
        self.db = sqlite_utils.Database(logs_db_path())

    @classmethod
    def get_connection(cls) -> sqlite_utils.Database:
        """Get singleton database connection."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance.db

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

async def log_response(response, model):
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
    models: List[str]
    system_prompt: Optional[str] = None
    confidence_threshold: float = 0.8
    max_iterations: int = 3
    arbiter: Optional[str] = None

    def to_dict(self):
        return self.model_dump()

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

class ConsortiumOrchestrator:
    def __init__(self, config: ConsortiumConfig):
        self.models = config.models
        self.system_prompt = config.system_prompt or DEFAULT_SYSTEM_PROMPT
        self.confidence_threshold = config.confidence_threshold
        self.max_iterations = config.max_iterations
        self.arbiter = config.arbiter or "claude-3-opus-20240229"
        self.iteration_history: List[IterationContext] = []


    async def orchestrate(self, prompt: str) -> Dict[str, Any]:
        iteration_count = 0
        final_result = None
        original_prompt = prompt
        current_prompt = f"""<prompt>
    <instruction>{prompt}</instruction>
</prompt>"""

        while iteration_count < self.max_iterations:
            iteration_count += 1
            logger.debug(f"Starting iteration {iteration_count}")

            # Get responses from all models using the current prompt
            model_responses = await self._get_model_responses(current_prompt)

            # Have arbiter synthesize and evaluate responses
            synthesis = await self._synthesize_responses(original_prompt, model_responses)

            # Store iteration context
            self.iteration_history.append(IterationContext(synthesis, model_responses))

            if synthesis["confidence"] >= self.confidence_threshold:
                final_result = synthesis
                break

            # Prepare for next iteration if needed
            current_prompt = self._construct_iteration_prompt(original_prompt, synthesis)

        if final_result is None:
            final_result = synthesis

        return {
            "original_prompt": original_prompt,
            "model_responses": model_responses,
            "synthesis": final_result,
            "metadata": {
                "models_used": self.models,
                "arbiter": self.arbiter,
                "timestamp": datetime.utcnow().isoformat(),
                "iteration_count": iteration_count
            }
        }

    async def _get_model_responses(self, prompt: str) -> List[Dict[str, Any]]:
        tasks = [self._get_model_response(model, prompt) for model in self.models]
        return await asyncio.gather(*tasks)

    async def _get_model_response(self, model: str, prompt: str) -> Dict[str, Any]:
        logger.debug(f"Getting response from model: {model}")
        try:
            xml_prompt = f"""<prompt>
    <instruction>{prompt}</instruction>
</prompt>"""
            response = llm.get_model(model).prompt(xml_prompt, system=self.system_prompt)
            text = response.text()
            asyncio.create_task(log_response(response, model))

            return {
                "model": model,
                "response": text,
                "confidence": self._extract_confidence(text),
            }
        except Exception as e:
            logger.exception(f"Error getting response from {model}")
            return {"model": model, "error": str(e)}

    def _parse_confidence_value(self, text: str, default: float = 0.5) -> float:
        """Helper method to parse confidence values consistently."""
        # Try to find XML confidence tag, now handling multi-line and whitespace better
        xml_match = re.search(r"<confidence>\s*(0?\.\d+|1\.0|\d+)\s*</confidence>", text, re.IGNORECASE | re.DOTALL)
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
        iteration_prompt_template = _read_iteration_prompt()
        iteration_history = self._format_iteration_history()

        # Create the formatted prompt directly
        return f"""Refining response for original prompt:
{original_prompt}

Previous synthesis results:
{json.dumps(last_synthesis, indent=2)}

Previous iteration history:
{iteration_history}

Please provide an improved response that addresses any issues identified in the previous iterations."""

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
            <synthesis>{iteration.synthesis['synthesis']}</synthesis>
            <confidence>{iteration.synthesis['confidence']}</confidence>
            <refinement_areas>
                {self._format_refinement_areas(iteration.synthesis['refinement_areas'])}
            </refinement_areas>
        </iteration>""")
        return "\n".join(history) if history else "<no_previous_iterations>No previous iterations available.</no_previous_iterations>"

    def _format_refinement_areas(self, areas: List[str]) -> str:
        return "\n                ".join(f"<area>{area}</area>" for area in areas)

    def _format_responses(self, responses: List[Dict[str, Any]]) -> str:
        formatted = []
        for r in responses:
            formatted.append(f"""<model_response>
            <model>{r['model']}</model>
            <confidence>{r.get('confidence', 'N/A')}</confidence>
            <response>{r.get('response', 'Error: ' + r.get('error', 'Unknown error'))}</response>
        </model_response>""")
        return "\n".join(formatted)

    async def _synthesize_responses(self, original_prompt: str, responses: List[Dict[str, Any]]) -> Dict[str, Any]:
        logger.debug("Synthesizing responses")
        arbiter = llm.get_model(self.arbiter)

        formatted_history = self._format_iteration_history()
        formatted_responses = self._format_responses(responses)

        # Load and format the arbiter prompt template
        arbiter_prompt_template = _read_arbiter_prompt()
        arbiter_prompt = arbiter_prompt_template.format(
            original_prompt=original_prompt,
            formatted_responses=formatted_responses,
            formatted_history=formatted_history
        )

        arbiter_response = arbiter.prompt(arbiter_prompt)
        asyncio.create_task(log_response(arbiter_response, arbiter))

        # Print raw arbiter response
        click.echo("\nArbiter Response:\n")
        click.echo(arbiter_response.text())
        click.echo("\n---\n")


        try:
            return self._parse_arbiter_response(arbiter_response.text())
        except Exception as e:
            logger.error(f"Error parsing arbiter response: {e}")
            return {
                "synthesis": arbiter_response.text(),
                "confidence": 0.5,
                "analysis": "Parsing failed - see raw response",
                "dissent": "",
                "needs_iteration": False,
                "refinement_areas": []
            }

    def _parse_arbiter_response(self, text: str) -> Dict[str, Any]:
        sections = {
            "synthesis": r"<synthesis>([\s\S]*?)</synthesis>",
            "confidence": r"<confidence>\s*([\d.]+)\s*</confidence>",
            "analysis": r"<analysis>([\s\S]*?)</analysis>",
            "dissent": r"<dissent>([\s\S]*?)</dissent>",
            "needs_iteration": r"<needs_iteration>(true|false)</needs_iteration>",
            "refinement_areas": r"<refinement_areas>([\s\S]*?)</refinement_areas>"
        }

        result = {}
        for key, pattern in sections.items():
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                if key == "confidence":
                    try:
                        value = float(match.group(1).strip())
                        result[key] = value / 100 if value > 1 else value
                    except (ValueError, TypeError):
                        result[key] = 0.5
                elif key == "needs_iteration":
                    result[key] = match.group(1).lower() == "true"
                elif key == "refinement_areas":
                    result[key] = [area.strip() for area in match.group(1).split("\n") if area.strip()]
                else:
                    result[key] = "" if key != "confidence" else 0.5

        return result

# Add this helper function before the register_commands
def read_stdin_if_not_tty() -> Optional[str]:
    """Read from stdin if it's not a terminal."""
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return None

class ConsortiumModel(llm.Model):
    can_stream = False

    class Options(llm.Options):
        confidence_threshold: Optional[float] = None
        max_iterations: Optional[int] = None

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
        """Execute method that handles the async orchestration internally"""
        try:
            # Run the async orchestration synchronously
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(self.get_orchestrator().orchestrate(prompt.prompt))
            response.response_json = result
            return result["synthesis"]["synthesis"]

        except Exception as e:
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
        config_data = json.loads(row["config"])
        configs[config_name] = ConsortiumConfig.from_dict(config_data)
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
        if cmd_name.startswith('-'):
            return super().get_command(ctx, self.default_cmd_name)
        return None

    def resolve_command(self, ctx, args):
        # Handle the case where no command is provided
        if not args:
            args = [self.default_cmd_name]
        return super().resolve_command(ctx, args)

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
        "--models",
        multiple=True,
        help="Models to include in consortium (can specify multiple)",
        default=[
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "gpt-4",
            "gemini-pro"
        ],
    )
    @click.option(
        "--arbiter",
        help="Model to use as arbiter",
        default="claude-3-opus-20240229"
    )
    @click.option(
        "--confidence-threshold",
        type=float,
        help="Minimum confidence threshold",
        default=0.8
    )
    @click.option(
        "--max-iterations",
        type=int,
        help="Maximum number of iteration rounds",
        default=3
    )
    @click.option(
        "--system",
        help="System prompt to use",
    )
    @click.option(
        "--output",
        type=click.Path(dir_okay=False, writable=True),
        help="Save full results to this JSON file",
    )
    @click.option(
        "--stdin/--no-stdin",
        default=True,
        help="Read additional input from stdin and append to prompt",
    )
    @click.option(
        "--raw",
        is_flag=True,
        default=True,
        help="Output raw response from arbiter model",
    )
    def run_command(prompt, models, arbiter, confidence_threshold, max_iterations,
                   system, output, stdin, raw):
        """Run prompt through a consortium of models and synthesize results."""
        # If no prompt is provided, read from stdin
        if not prompt and stdin:
            prompt = read_stdin_if_not_tty()
            if not prompt:
                raise click.UsageError("No prompt provided and no input from stdin")

        # Convert percentage to decimal if needed
        if confidence_threshold > 1.0:
            confidence_threshold /= 100.0

        if stdin:
            stdin_content = read_stdin_if_not_tty()
            if stdin_content:
                prompt = f"{prompt}\n\n{stdin_content}"

        logger.info(f"Starting consortium with {len(models)} models")
        logger.debug(f"Models: {', '.join(models)}")
        logger.debug(f"Arbiter model: {arbiter}")

        orchestrator = ConsortiumOrchestrator(
            config=ConsortiumConfig(
               models=list(models),
               system_prompt=system,
               confidence_threshold=confidence_threshold,
               max_iterations=max_iterations,
               arbiter=arbiter,
            )
        )

        try:
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(orchestrator.orchestrate(prompt))

            if output:
                with open(output, 'w') as f:
                    json.dump(result, f, indent=2)
                logger.info(f"Results saved to {output}")

            click.echo("\nSynthesized response:\n")
            click.echo(result["synthesis"]["synthesis"])

            click.echo(f"\nConfidence: {result['synthesis']['confidence']}")

            click.echo("\nAnalysis:")
            click.echo(result["synthesis"]["analysis"])

            if result["synthesis"]["dissent"]:
                click.echo("\nNotable dissenting views:")
                click.echo(result["synthesis"]["dissent"])

            click.echo(f"\nNumber of iterations: {result['metadata']['iteration_count']}")
            if raw:
                click.echo("\nIndividual model responses:")
                for response in result["model_responses"]:
                    click.echo(f"\nModel: {response['model']}")
                    click.echo(f"Confidence: {response.get('confidence', 'N/A')}")
                    click.echo(f"Response: {response.get('response', 'Error: ' + response.get('error', 'Unknown error'))}")

        except Exception as e:
            logger.exception("Error in consortium command")
            raise click.ClickException(str(e))

    # Register consortium management commands group
    @consortium.command(name="save")
    @click.argument("name")
    @click.option(
        "-m",
        "--models",
        multiple=True,
        help="Models to include in consortium (can specify multiple)",
        required=True,
    )
    @click.option(
        "--arbiter",
        help="Model to use as arbiter",
        required=True
    )
    @click.option(
        "--confidence-threshold",
        type=float,
        help="Minimum confidence threshold",
        default=0.8
    )
    @click.option(
        "--max-iterations",
        type=int,
        help="Maximum number of iteration rounds",
        default=3
    )
    @click.option(
        "--system",
        help="System prompt to use",
    )
    def save_command(name, models, arbiter, confidence_threshold, max_iterations, system):
        """Save a consortium configuration."""
        config = ConsortiumConfig(
            models=models,
            arbiter=arbiter,
            confidence_threshold=confidence_threshold,
            max_iterations=max_iterations,
            system_prompt=system,
        )
        _save_consortium_config(name, config)
        click.echo(f"Consortium configuration '{name}' saved.")
        click.echo("Options: --option confidence_threshold=0.9 --option stream_individual_responses=true")

    @consortium.command(name="list")
    def list_command():
        """List all saved consortiums."""
        db = DatabaseConnection.get_connection()

        db.execute("""
        CREATE TABLE IF NOT EXISTS consortium_configs (
            name TEXT PRIMARY KEY,
            config TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        consortiums = list(db["consortium_configs"].rows)
        if not consortiums:
            click.echo("No consortiums found.")
            return

        click.echo("Available consortiums:")
        for row in consortiums:
            click.echo(f"- {row['name']}")

    @consortium.command(name="show")
    @click.argument("name")
    def show_command(name):
        """Show details of a saved consortium."""
        db = DatabaseConnection.get_connection()

        db.execute("""
        CREATE TABLE IF NOT EXISTS consortium_configs (
            name TEXT PRIMARY KEY,
            config TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        try:
            consortium_config = db["consortium_configs"].get(name)
            if not consortium_config:
               raise click.ClickException(f"Consortium with name '{name}' not found.")

            config_data = json.loads(consortium_config['config'])
            config = ConsortiumConfig.from_dict(config_data)

            click.echo(f"Consortium: {name}")
            click.echo(f"  Models: {', '.join(config.models)}")
            click.echo(f"  Arbiter: {config.arbiter}")
            click.echo(f"  Confidence Threshold: {config.confidence_threshold}")
            click.echo(f"  Max Iterations: {config.max_iterations}")
            if config.system_prompt:
                click.echo(f"  System Prompt: {config.system_prompt}")
        except sqlite_utils.db.NotFoundError:
            raise click.ClickException(f"Consortium with name '{name}' not found.")

    @consortium.command(name="remove")
    @click.argument("name")
    def remove_command(name):
        """Remove a saved consortium."""
        db = DatabaseConnection.get_connection()
        db.execute("""
        CREATE TABLE IF NOT EXISTS consortium_configs (
            name TEXT PRIMARY KEY,
            config TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        try:
            db["consortium_configs"].delete(name)
            click.echo(f"Consortium '{name}' removed.")
        except sqlite_utils.db.NotFoundError:
            raise click.ClickException(f"Consortium with name '{name}' not found.")

@llm.hookimpl
def register_models(register):
    logger.debug("KarpathyConsortiumPlugin.register_commands called")
    try:
        for name, config in _get_consortium_configs().items():
            try:
                model = ConsortiumModel(name, config)
                register(model, aliases=(name,))
            except Exception as e:
                logger.error(f"Failed to register consortium '{name}': {e}")
    except Exception as e:
        logger.error(f"Failed to load consortium configurations: {e}")

class KarpathyConsortiumPlugin:
    @staticmethod
    @llm.hookimpl
    def register_commands(cli):
        logger.debug("KarpathyConsortiumPlugin.register_commands called")

logger.debug("llm_karpathy_consortium module finished loading")

__all__ = ['KarpathyConsortiumPlugin', 'log_response', 'DatabaseConnection', 'logs_db_path', 'user_dir', 'ConsortiumModel']

__version__ = "0.3.1"
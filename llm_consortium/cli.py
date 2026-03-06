import click
import json
import logging
import pathlib
import llm

from .db import DatabaseConnection
from .visualization import generate_run_visualization
from .models import ConsortiumConfig, parse_models, _save_consortium_config, _get_consortium_configs
from .strategies.factory import list_available_strategies

logger = logging.getLogger(__name__)


def _parse_strategy_params(strategy_params_list):
    strategy_params = {}
    for param in strategy_params_list:
        if '=' in param:
            key, value = param.split('=', 1)
            key = key.strip()
            value = value.strip()

            if key in strategy_params:
                existing_value = strategy_params[key]
                if isinstance(existing_value, list):
                    existing_value.append(value)
                else:
                    strategy_params[key] = [existing_value, value]
            else:
                strategy_params[key] = value
        else:
            strategy_params[param.strip()] = True

    return strategy_params

@llm.hookimpl
def register_commands(cli):
    @cli.group()
    @click.pass_context
    def consortium(ctx):
        """Commands for managing and running model consortiums"""
        pass

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
        default=3,
        help="Maximum iterations for convergence"
    )
    @click.option(
        "--min-iterations",
        type=int,
        default=1,
        help="Minimum iterations before convergence"
    )
    @click.option(
        "--system", "system_prompt_content",
        help="System prompt for consortium members"
    )
    @click.option(
        "--judging-method",
        type=click.Choice(["default", "rank"], case_sensitive=False),
        default="default",
        help="Judging method for the arbiter (default=synthesis, rank)."
    )
    @click.option(
        "--manual-context/--auto-context",
        default=False,
        help="Use manual context construction"
    )
    @click.option(
        "--strategy",
        help="Strategy to use (e.g., voting, elimination, role).",
        default="default"
    )
    @click.option(
        "--embedding-backend",
        type=click.Choice(["openai", "sentence-transformers", "chutes"], case_sensitive=False),
        default=None,
        help="Embedding backend (openai, sentence-transformers, chutes)."
    )
    @click.option(
        "--embedding-model",
        default=None,
        help="Specific embedding model name."
    )
    @click.option(
        "--clustering-algorithm",
        type=click.Choice(["dbscan", "hdbscan", "tropical"], case_sensitive=False),
        default=None,
        help="Semantic clustering algorithm to use."
    )
    @click.option(
        "--cluster-eps",
        type=float,
        default=0.5,
        help="DBSCAN epsilon parameter."
    )
    @click.option(
        "--cluster-min-samples",
        type=int,
        default=2,
        help="Minimum points required to form a semantic cluster."
    )
    @click.option(
        "--strategy-param", "strategy_params_list",
        multiple=True,
        help="Parameters for the strategy, format KEY=VALUE. Can be provided multiple times.",
    )
    def save_command(name, models, count, arbiter, confidence_threshold, max_iterations,
                     min_iterations, system_prompt_content, judging_method, manual_context, strategy,
                     embedding_backend, embedding_model, clustering_algorithm, cluster_eps, cluster_min_samples,
                     strategy_params_list):
        """Save a consortium configuration to be used as a model."""
        
        model_dict = parse_models(models, count)
        strategy_params = _parse_strategy_params(strategy_params_list)
        if clustering_algorithm:
            strategy_params["clustering_algorithm"] = clustering_algorithm.lower()
            strategy_params["eps"] = cluster_eps
            strategy_params["min_samples"] = cluster_min_samples

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
            strategy=strategy,
            strategy_params=strategy_params,
            embedding_backend=embedding_backend,
            embedding_model=embedding_model,
            manual_context=manual_context
        )
        try:
            _save_consortium_config(name, config)
            click.echo(f"Consortium configuration '{name}' saved.")
            click.echo(f"You can now use it like: llm -m {name} \"Your prompt here\"")
        except Exception as e:
             raise click.ClickException(f"Error saving consortium '{name}': {e}")

    @consortium.command(name="strategies")
    def strategies_command():
        """List available consortium strategies and what they do."""
        strategies = list_available_strategies()
        if not strategies:
            click.echo("No consortium strategies are registered.")
            return

        click.echo("Available consortium strategies:\n")
        for name, metadata in strategies.items():
            click.echo(f"Name: {name}")
            click.echo(f"  Class: {metadata['class_name']}")
            click.echo(f"  Description: {metadata['description']}")
            click.echo("")


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
            click.echo(f"  Context Mode: {'Manual' if config.manual_context else 'Automatic'}")
            click.echo("")


    @consortium.command(name="remove")
    @click.argument("name")
    def remove_command(name):
        """Remove a saved consortium configuration."""
        db = DatabaseConnection.get_connection()
        try:
            count = db["consortium_configs"].count_where("name = ?", [name])
            if count == 0:
                 raise click.ClickException(f"Consortium with name '{name}' not found.")
            db["consortium_configs"].delete(name)
            click.echo(f"Consortium configuration '{name}' removed.")
        except Exception as e:
             raise click.ClickException(f"Error removing consortium '{name}': {e}")

    @consortium.command(name="runs")
    @click.option("--limit", type=int, default=10, help="Maximum number of runs to show")
    @click.option("--since", help="Show runs since date (YYYY-MM-DD)")
    def runs_command(limit, since):
        """List recent consortium executions"""
        db = DatabaseConnection.get_connection()
        if "consortium_runs" not in db.table_names():
            click.echo("No consortium runs found.")
            return

        query = "SELECT * FROM consortium_runs"
        params = []
        if since:
            query += " WHERE created_at >= ?"
            params.append(since)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        runs = list(db.query(query, params))
        if not runs:
            click.echo("No recent consortium executions found.")
            return

        click.echo(f"\nRecent Consortium Runs (up to {limit}):\n")
        for run in runs:
            click.echo(f"ID: {run['id']}")
            click.echo(f"  Created: {run['created_at']}")
            click.echo(f"  Strategy: {run['strategy']} | Judging Method: {run['judging_method']}")
            click.echo(f"  Iterations: {run['iteration_count']}/{run.get('max_iterations', '?')} | Final Confidence: {run['final_confidence']}")
            prompt = run.get('user_prompt', '')
            if prompt and len(prompt) > 80:
                prompt = prompt[:77] + "..."
            click.echo(f"  Prompt: {prompt}")
            click.echo("")

    @consortium.command(name="export-training")
    @click.argument("output", type=click.Path(dir_okay=False, writable=True, path_type=pathlib.Path))
    @click.option("--since", help="Export evaluations since date (YYYY-MM-DD)")
    @click.option("--model", "model_filter", help="Filter by specific model")
    @click.option("--min-confidence", type=float, help="Minimum confidence threshold")
    def export_training_command(output, since, model_filter, min_confidence):
        """Export evaluations as training data (JSONL format)"""
        click.echo("This command is temporarily disabled as we refactor storage to use a relational schema.")

    @consortium.command(name="run-info")
    @click.argument("consortium_id")
    @click.option("--json-output", is_flag=True, help="Output as JSON")
    def run_info_command(consortium_id, json_output):
        """Show detailed execution trace for a consortium run"""
        db = DatabaseConnection.get_connection()
        
        runs = list(db.query("SELECT * FROM consortium_runs WHERE id = ?", [consortium_id]))
        if not runs:
            raise click.ClickException(f"Consortium run '{consortium_id}' not found.")
            
        run_data = runs[0]
        
        members = list(db.query(
            "SELECT cm.*, r.model, r.response FROM consortium_members cm "
            "JOIN responses r ON cm.response_id = r.id "
            "WHERE cm.run_id = ? ORDER BY cm.iteration, cm.member_index", 
            [consortium_id]
        ))
        
        decisions = list(db.query(
            "SELECT ad.*, r.response as full_response FROM arbiter_decisions ad "
            "JOIN responses r ON ad.response_id = r.id "
            "WHERE ad.run_id = ? ORDER BY ad.iteration", 
            [consortium_id]
        ))

        if json_output:
            output = {
                "run": dict(run_data),
                "members": [dict(m) for m in members],
                "decisions": [dict(d) for d in decisions]
            }
            click.echo(json.dumps(output, indent=2))
            return

        click.echo(f"\n=== Consortium Run Info ===")
        click.echo(f"ID: {run_data['id']}")
        click.echo(f"Prompt: {run_data.get('user_prompt')}")
        click.echo(f"Details: {run_data['strategy']} strategy, {run_data['judging_method']} judging")
        
        for iteration in range(1, run_data.get('max_iterations', 0) + 1):
            iter_members = [m for m in members if m['iteration'] == iteration]
            iter_decision = next((d for d in decisions if d['iteration'] == iteration), None)
            
            if not iter_members and not iter_decision:
                continue
                
            click.echo(f"\n--- Iteration {iteration} ---")
            
            for member in iter_members:
                if member['role'] != 'arbiter':
                    model_display = member.get('model', 'Unknown Model')
                    click.echo(f"  Member [{model_display}] (ID: {member['response_id']}):")
                    content = member.get('response', '')
                    if content and len(content) > 100:
                        content = content[:97] + "..."
                    click.echo(f"    {content}")
            
            if iter_decision:
                click.echo(f"\n  Arbiter Decision (Confidence: {iter_decision.get('confidence')}, Geometric: {iter_decision.get('geometric_confidence')}):")
                click.echo(f"    Synthesis: {iter_decision.get('synthesis')}")
                if iter_decision.get('refinement_areas') and iter_decision.get('refinement_areas') != '[]':
                    click.echo(f"    Refinement: {iter_decision.get('refinement_areas')}")

    @consortium.command(name="visualize-run")
    @click.argument("run_id")
    @click.argument("output", required=False, type=click.Path(dir_okay=False, path_type=pathlib.Path))
    def visualize_run_command(run_id, output):
        """Export a run embedding visualization to HTML."""
        figure = generate_run_visualization(run_id)
        output_path = output or pathlib.Path(f"{run_id}.html")
        if hasattr(figure, "write_html"):
            figure.write_html(str(output_path))
        else:
            raise click.ClickException("Visualization backend does not support HTML export")
        click.echo(f"Visualization exported to {output_path}")

    @consortium.command(name="list-traces")
    @click.option("--limit", type=int, default=10, help="Maximum number of traces to show")
    def list_traces_command(limit):
        """List recent trace IDs (Delegates to 'runs' internally since traces are now linked to runs)"""
        click.echo("Traces are now stored contextually within Consortium Runs.")
        runs_command.callback(limit=limit, since=None)

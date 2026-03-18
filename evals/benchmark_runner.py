#!/usr/bin/env python3
"""
Benchmark Script for Semantic Filtering Validation (Phase 1.1)
Executes a suite of prompts against both default and semantic strategies.
"""
import argparse
import json
import logging
import time
import concurrent.futures
import multiprocessing
from pathlib import Path

from llm_consortium import create_consortium

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("benchmark_runner")


def run_strategy(strategy_name, prompt_data, models, str_params=None, arbiter=None, embedding_backend=None, embedding_model=None):
    prompt_text = prompt_data.get("prompt", "")
    category = prompt_data.get("category", "unknown")
    expected_agreement = prompt_data.get("expected_agreement", 0.5)

    orch = create_consortium(
        models=models,
        confidence_threshold=0.8,
        max_iterations=3,
        minimum_iterations=1,
        arbiter=arbiter if arbiter else (list(models.keys())[0] if isinstance(models, dict) else models[0]),
        strategy=strategy_name,
        strategy_params=str_params or {},
        embedding_backend=embedding_backend if strategy_name == "semantic" else None,
        embedding_model=embedding_model if strategy_name == "semantic" else None
    )
    # Inject metadata for db logging
    orch.config.category = category
    orch.config.expected_agreement = expected_agreement

    start_t = time.time()
    result = orch.orchestrate(prompt_text)
    elapsed = time.time() - start_t

    synthesis = result.get("synthesis", {})
    return {
        "status": orch.config.status,
        "elapsed_seconds": elapsed,
        "total_iterations": result.get("metadata", {}).get("total_iterations", 0),
        "arbiter_confidence": synthesis.get("confidence", 0.0),
        "geometric_confidence": synthesis.get("geometric_confidence", 0.0),
        "synthesis": synthesis.get("synthesis", ""),
        "consortium_id": result.get("metadata", {}).get("consortium_id"),
        "error": synthesis.get("error"),
    }


def _run_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", required=True, help="Path to JSON file containing prompts")
    parser.add_argument("--output", default="benchmark_results.json", help="Output JSON path")
    parser.add_argument("--models", help="Comma-separated list of model:count (e.g. gpt-4o:3)")
    parser.add_argument("--arbiter", help="Arbiter model name (e.g. gpt-4o)")
    parser.add_argument("--embedding-backend", default="sentence-transformers", help="Embedding backend string")
    parser.add_argument("--embedding-model", default=None, help="Embedding model string")
    args = parser.parse_args()

    # Parse models
    models_config = {}
    for m in args.models.split(","):
        if ":" in m:
            name, count = m.split(":")
            models_config[name] = int(count)
        else:
            models_config[m] = 1

    try:
        with open(args.prompts, "r") as f:
            prompts = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load prompts: {e}")
        return

    results = []
    
    max_workers = min(5, multiprocessing.cpu_count())
    logger.info(f"Running benchmarks with {max_workers} concurrent parallel workers")

    def process_prompt(p_data, i):
        logger.info(f"Starting prompt {i+1}/{len(prompts)}: {p_data.get('category')}...")
        
        res_default = run_strategy(
            "default", p_data, models_config,
            arbiter=args.arbiter,
            embedding_backend=args.embedding_backend,
            embedding_model=args.embedding_model
        )
        
        res_semantic = run_strategy(
            "semantic", 
            p_data, 
            models_config, 
            str_params={"clustering_algorithm": "dbscan", "eps": 0.5, "min_samples": 2},
            arbiter=args.arbiter,
            embedding_backend=args.embedding_backend,
            embedding_model=args.embedding_model
        )
        
        return {
            "prompt_index": i,
            "prompt_text": p_data.get("prompt"),
            "category": p_data.get("category"),
            "expected_agreement": p_data.get("expected_agreement"),
            "notes": p_data.get("notes", ""),
            "runs": {
                "default": res_default,
                "semantic": res_semantic
            }
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_prompt, p_data, i): i for i, p_data in enumerate(prompts)}
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"Error executing prompt: {e}")

    # Summary Output
    default_failures = sum(1 for r in results if r["runs"]["default"]["status"] != "success")
    semantic_failures = sum(1 for r in results if r["runs"]["semantic"]["status"] != "success")
    
    print("\n--- BENCHMARK SUMMARY ---")
    print(f"Total Prompts Run: {len(results)}")
    print(f"Default Failures: {default_failures}")
    print(f"Semantic Failures: {semantic_failures}")
    
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved results to {args.output}")

def main():
    _run_main()

if __name__ == "__main__":
    main()

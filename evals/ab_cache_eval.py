#!/usr/bin/env python3
"""Live A/B eval: cache_aware vs cache_max on DeepSeek (prefix caching).

Runs the same long static-prefix workload through both strategies and
measures provider-reported cache telemetry (prompt_cache_hit_tokens) plus
wall-clock latency. DeepSeek charges ~10x less for cached prompt tokens,
so hit-rate deltas translate directly to cost deltas.

Usage:
    python evals/ab_cache_eval.py [--model deepseek-v4-flash] [--rounds 3]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_consortium.models import ConsortiumConfig
from llm_consortium.orchestrator import ConsortiumOrchestrator
from llm_consortium.strategies.cache_max import CacheMaxStrategy

# Long shared prefix: gives the prefix cache something substantial to hold.
# (DeepSeek caches in ~128-token blocks; short prompts yield nothing.)
SHARED_CONTEXT = (
    "You are analyzing a distributed systems design document. "
    + ("The system uses Raft consensus with leader leases, quorum reads, "
       "partition-tolerant writes, vector clocks for causality tracking, "
       "and a gossip-based membership protocol with SWIM failure detection. " * 40)
)

QUESTIONS = [
    "What is the primary consistency trade-off in this design?",
    "How does the failure detector interact with leader election?",
    "Where can read staleness occur, and how is it bounded?",
]


def run_strategy(strategy: str, model: str, question: str) -> dict:
    config = ConsortiumConfig(
        models={model: 2},          # 2 instances -> multi-instance serialization path
        arbiter=model,              # same-model arbiter: cache_max shares member prefix
        strategy=strategy,
        strategy_params={},
        max_iterations=1,
        minimum_iterations=1,
        confidence_threshold=1.1,   # stop after iteration 1
    )
    orch = ConsortiumOrchestrator(config)
    prompt = SHARED_CONTEXT + "\n\nQuestion: " + question
    t0 = time.time()
    result = orch.orchestrate(prompt)
    elapsed = time.time() - t0

    row = {
        "strategy": strategy,
        "question": question[:40],
        "elapsed_s": round(elapsed, 2),
        "confidence": (result.get("synthesis") or {}).get("confidence"),
    }
    strat_obj = getattr(orch, "strategy", None)
    if isinstance(strat_obj, CacheMaxStrategy):
        row["prewarm_report"] = strat_obj.prewarm_report()
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--rounds", type=int, default=1)
    args = ap.parse_args()

    results = []
    for rnd in range(args.rounds):
        for strategy in ("cache_aware", "cache_max"):
            for q in QUESTIONS:
                print(f"[round {rnd+1}] {strategy}: {q[:40]}...", flush=True)
                try:
                    row = run_strategy(strategy, args.model, q)
                except Exception as e:
                    row = {"strategy": strategy, "question": q[:40], "error": str(e)}
                row["round"] = rnd + 1
                results.append(row)
                print("   ->", json.dumps({k: v for k, v in row.items()
                                            if k in ("elapsed_s", "confidence", "prewarm_report", "error")}), flush=True)

    out = Path("evals/ab_cache_results.json")
    out.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out}")

    ok = [r for r in results if "error" not in r]
    for strat in ("cache_aware", "cache_max"):
        rows = [r for r in ok if r["strategy"] == strat]
        if rows:
            avg = sum(r["elapsed_s"] for r in rows) / len(rows)
            print(f"{strat:12s} runs={len(rows)} avg_elapsed={avg:.1f}s")


if __name__ == "__main__":
    main()

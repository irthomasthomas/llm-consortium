#!/usr/bin/env python3
"""
Analysis Script for Semantic Filtering Validation (Phase 1.3)
Classifies outcomes and reports on semantic filtering vs default.
Recomputes clusters from saved embeddings to evaluate disagreement frequency.
"""
import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import DBSCAN

from llm_consortium.db import get_embedding_records_for_run

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("analyze_results")

def compute_clusters(records, eps=0.5, min_samples=2):
    """Recomputes DBSCAN clustering on saved embeddings."""
    if not records:
        return 0, {}
        
    embeddings = []
    vector_ids = []
    for r in records:
        if r.get("embedding_json"):
            try:
                vec = json.loads(r["embedding_json"])
                embeddings.append(vec)
                vector_ids.append(r["response_id"])
            except:
                pass
                
    if not embeddings:
        return 0, {}
        
    X = np.array(embeddings)
    clusterer = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean")
    labels = clusterer.fit_predict(X)
    
    unique_clusters = set(labels) - {-1}
    cluster_count = len(unique_clusters)
    
    return cluster_count, dict(zip(vector_ids, labels.tolist()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, help="Path to benchmark_results.json")
    parser.add_argument("--judgments", required=False, help="Path to judged_results.json")
    parser.add_argument("--output", default="analysis_report.json", help="Output JSON path")
    args = parser.parse_args()

    try:
        with open(args.results, "r") as f:
            results = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load results: {e}")
        return

    judgments = {}
    if args.judgments:
        try:
            with open(args.judgments, "r") as f:
                j_list = json.load(f)
                judgments = {j["prompt_index"]: j for j in j_list}
        except Exception as e:
            logger.error(f"Failed to load judgments: {e}")

    analysis = {
        "total_runs": len(results),
        "buckets": {
            "semantic_no_op": 0,
            "disagreement_same_synthesis": 0,
            "disagreement_diff_synthesis": 0,
            "one_side_failed": 0,
            "both_failed": 0
        },
        "by_category": defaultdict(lambda: {"total": 0, "semantic_wins": 0, "default_wins": 0, "ties": 0}),
        "by_expected_agreement": defaultdict(lambda: {"total": 0, "semantic_wins": 0, "default_wins": 0, "ties": 0}),
        "win_rates": {"semantic": 0, "default": 0, "tie": 0},
        "disagreement_frequency": 0,
        "operational_failures": {"default": 0, "semantic": 0},
        "geometric_confidence_deltas": []
    }

    for res in results:
        default = res["runs"]["default"]
        semantic = res["runs"]["semantic"]
        cat = res["category"]
        exp_ag = str(res["expected_agreement"])
        
        # Track failures
        d_fail = default["status"] != "success"
        s_fail = semantic["status"] != "success"
        
        if d_fail and s_fail:
            analysis["buckets"]["both_failed"] += 1
            analysis["operational_failures"]["default"] += 1
            analysis["operational_failures"]["semantic"] += 1
            continue
        elif d_fail or s_fail:
            analysis["buckets"]["one_side_failed"] += 1
            if d_fail: analysis["operational_failures"]["default"] += 1
            if s_fail: analysis["operational_failures"]["semantic"] += 1
            continue
            
        # Analyze clusters and disagreement
        semantic_cid = semantic.get("consortium_id")
        records = get_embedding_records_for_run(semantic_cid) if semantic_cid else []
        cluster_count, _ = compute_clusters(records)
        
        has_disagreement = cluster_count > 1
        if has_disagreement:
            analysis["disagreement_frequency"] += 1
            synthesis_match = default["synthesis"] == semantic["synthesis"]
            if synthesis_match:
                analysis["buckets"]["disagreement_same_synthesis"] += 1
            else:
                analysis["buckets"]["disagreement_diff_synthesis"] += 1
        else:
            analysis["buckets"]["semantic_no_op"] += 1
            
        # Track geometric confidence deltas
        delta = semantic.get("geometric_confidence", 0) - default.get("geometric_confidence", 0)
        analysis["geometric_confidence_deltas"].append(delta)

        # Process Judgments
        if res["prompt_index"] in judgments:
            j = judgments[res["prompt_index"]]
            winner = j["winner"]
            
            analysis["by_category"][cat]["total"] += 1
            analysis["by_expected_agreement"][exp_ag]["total"] += 1
            
            if winner == "semantic":
                analysis["win_rates"]["semantic"] += 1
                analysis["by_category"][cat]["semantic_wins"] += 1
                analysis["by_expected_agreement"][exp_ag]["semantic_wins"] += 1
            elif winner == "default":
                analysis["win_rates"]["default"] += 1
                analysis["by_category"][cat]["default_wins"] += 1
                analysis["by_expected_agreement"][exp_ag]["default_wins"] += 1
            else:
                analysis["win_rates"]["tie"] += 1
                analysis["by_category"][cat]["ties"] += 1
                analysis["by_expected_agreement"][exp_ag]["ties"] += 1

    # Convert defaultdicts to dicts for JSON
    analysis["by_category"] = dict(analysis["by_category"])
    analysis["by_expected_agreement"] = dict(analysis["by_expected_agreement"])
    
    with open(args.output, "w") as f:
        json.dump(analysis, f, indent=2)

    total_runs = analysis["total_runs"]
    buckets = analysis["buckets"]
    win_rates = analysis["win_rates"]
    by_category = analysis["by_category"]
    
    has_judgments = total_runs > 0 and (win_rates["semantic"] + win_rates["default"] + win_rates["tie"]) > 0
    total_judged = win_rates["semantic"] + win_rates["default"] + win_rates["tie"] if has_judgments else 0

    print("\n=== OUTCOME BUCKETS ===")
    for b_k, b_v in buckets.items():
        pct = (b_v / total_runs * 100) if total_runs else 0.0
        print(f"{b_k:<30} {b_v} ({pct:.1f}%)")

    if has_judgments:
        print("\n=== WIN RATES ===")
        semantic_pct = (win_rates['semantic'] / total_judged * 100) if total_judged else 0.0
        default_pct = (win_rates['default'] / total_judged * 100) if total_judged else 0.0
        tie_pct = (win_rates['tie'] / total_judged * 100) if total_judged else 0.0
        print(f"Semantic: {win_rates['semantic']}/{total_judged} ({semantic_pct:.1f}%)")
        print(f"Default:  {win_rates['default']}/{total_judged} ({default_pct:.1f}%)")
        print(f"Tie:      {win_rates['tie']}/{total_judged} ({tie_pct:.1f}%)")

        print("\n=== BY CATEGORY ===")
        print(f"{'Category':<15} {'Total':>5}  {'Semantic':>8}  {'Default':>7}  {'Tie':>3}")
        for cat, stats in by_category.items():
            print(f"{cat:<15} {stats['total']:>5}  {stats['semantic_wins']:>8}  {stats['default_wins']:>7}  {stats['ties']:>3}")

    deltas = analysis["geometric_confidence_deltas"]
    avg_delta = sum(deltas) / len(deltas) if deltas else 0.0
    print(f"\nAverage geometric confidence delta: {avg_delta:.4f}")

    dfreq = analysis["disagreement_frequency"]
    df_pct = (dfreq / total_runs * 100) if total_runs else 0.0
    print(f"Disagreement frequency: {dfreq} ({df_pct:.1f}%)")
            
if __name__ == "__main__":
    main()

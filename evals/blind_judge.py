#!/usr/bin/env python3
"""
Blind Judge Script for Semantic Filtering Validation (Phase 1.2)
Takes benchmark results and uses an LLM to evaluate the synthesis quality blindly.
"""
import argparse
import json
import logging
import random
import re
from pathlib import Path
from typing import Dict, Any

import llm

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("blind_judge")

JUDGE_PROMPT = """
You are an expert impartial judge evaluating the quality of two AI-generated syntheses based on a user prompt.

Original Prompt:
{prompt}

Synthesis A:
{synthesis_a}

Synthesis B:
{synthesis_b}

Compare the two syntheses and pick the winner.
Focus on correctness, completeness, clarity, and lack of hallucination.

Provide your evaluation in the following XML format:
<evaluation>
  <winner>[A, B, or TIE]</winner>
  <rationale>[Short explanation of why]</rationale>
  <confidence>[1-5 scale of how confident you are in this decision]</confidence>
</evaluation>
"""

def parse_evaluation(text: str) -> Dict[str, Any]:
    evaluation = {
        "winner": "ERROR",
        "rationale": "",
        "confidence": 0,
        "raw_text": text
    }
    
    winner_match = re.search(r"<winner>(.*?)</winner>", text, re.IGNORECASE | re.DOTALL)
    if winner_match:
        evaluation["winner"] = winner_match.group(1).strip().upper()
        
    rationale_match = re.search(r"<rationale>(.*?)</rationale>", text, re.IGNORECASE | re.DOTALL)
    if rationale_match:
        evaluation["rationale"] = rationale_match.group(1).strip()
        
    conf_match = re.search(r"<confidence>(.*?)</confidence>", text, re.IGNORECASE | re.DOTALL)
    if conf_match:
        try:
            evaluation["confidence"] = int(conf_match.group(1).strip())
        except ValueError:
            pass
            
    return evaluation

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to benchmark_results.json")
    parser.add_argument("--output", default="judged_results.json", help="Output JSON path")
    parser.add_argument("--judge-model", default="gpt-4o", help="Model to use as judge")
    parser.add_argument("--limit", type=int, help="Limit number of evaluations for testing")
    args = parser.parse_args()

    try:
        with open(args.input, "r") as f:
            results = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load input: {e}")
        return

    judge = llm.get_model(args.judge_model)
    judgments = []
    
    count = 0
    for res in results:
        if args.limit and count >= args.limit:
            break
            
        default_run = res["runs"]["default"]
        semantic_run = res["runs"]["semantic"]
        
        # Only evaluate if both succeeded and have non-empty syntheses
        if (default_run["status"] != "success" or semantic_run["status"] != "success" or
            not default_run["synthesis"] or not semantic_run["synthesis"]):
            continue
            
        count += 1
        logger.info(f"Evaluating prompt {res['prompt_index']}...")
        
        # Randomize A/B
        is_default_a = random.choice([True, False])
        
        if is_default_a:
            synthesis_a = default_run["synthesis"]
            synthesis_b = semantic_run["synthesis"]
        else:
            synthesis_a = semantic_run["synthesis"]
            synthesis_b = default_run["synthesis"]
            
        prompt = JUDGE_PROMPT.format(
            prompt=res["prompt_text"],
            synthesis_a=synthesis_a,
            synthesis_b=synthesis_b
        )
        
        try:
            response = judge.prompt(prompt)
            eval_text = response.text()
            
            parsed = parse_evaluation(eval_text)
            
            # Map back to default/semantic
            if parsed["winner"] == "A":
                actual_winner = "default" if is_default_a else "semantic"
            elif parsed["winner"] == "B":
                actual_winner = "semantic" if is_default_a else "default"
            else:
                actual_winner = "tie"
                
            judgments.append({
                "prompt_index": res["prompt_index"],
                "default_is_a": is_default_a,
                "winner": actual_winner,
                "rationale": parsed["rationale"],
                "confidence": parsed["confidence"],
                "raw_judge_output": parsed["raw_text"]
            })
            
        except Exception as e:
            logger.error(f"Failed to evaluate prompt {res['prompt_index']}: {e}")
            
    with open(args.output, "w") as f:
        json.dump(judgments, f, indent=2)
    logger.info(f"Saved {len(judgments)} judgments to {args.output}")

if __name__ == "__main__":
    main()

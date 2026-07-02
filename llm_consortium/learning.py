"""
Automated learning loop — mines consortium database for routing rules.
"""
import json, logging
from collections import defaultdict
from typing import Dict, List, Any
from .db import DatabaseConnection
from .classifier.regex_rules import classify_prompt

logger = logging.getLogger(__name__)

# Canonical model aliases (consortium DB has name evolution)
MODEL_ALIASES = {
    "glm-5": "glm-5", "glm-5.1": "glm-5", "glm-5-chutes": "glm-5",
    "openrouter/z-ai/glm-5": "glm-5",
    "deepseek-v4-pro": "deepseek-v4-pro", "deepseek-v4-pro-zen": "deepseek-v4-pro",
    "deepseek-v4-flash-zen": "deepseek-v4-flash",
    "qwen3.6-35b-a3b-or": "qwen3.6", "chutes/Qwen/Qwen3.6-27B-TEE": "qwen3.6",
    "openrouter/qwen/qwen3.5-397b-a17b": "qwen3.5-397b",
    "openrouter/qwen/qwen3.5-122b-a10b": "qwen3.5-122b",
    "openrouter/moonshotai/kimi-k2.5": "kimi-k2.5",
    "chutes/moonshotai/Kimi-K2.6-TEE": "kimi-k2.6",
    "openrouter/minimax/minimax-m2.5": "minimax-m2.5",
    "gpt-oss-120b-groq": "gpt-oss-120b",
    "gpt-4.1-copilot": "gpt-4.1",
    "mimo-v2.5-pro-zen": "mimo-v2.5",
}

def canonical_model(name: str) -> str:
    return MODEL_ALIASES.get(name, name)

def learn_from_history() -> Dict[str, Dict[str, Any]]:
    db = DatabaseConnection.get_connection()
    if "consortium_runs" not in db.table_names():
        return {}
    try:
        runs = list(db.query("""
            SELECT cr.id, cr.user_prompt, cr.strategy,
                   ad.chosen_response_id, ad.confidence
            FROM consortium_runs cr
            JOIN arbiter_decisions ad ON ad.run_id = cr.id
            WHERE ad.chosen_response_id IS NOT NULL
              AND cr.user_prompt IS NOT NULL
              AND length(cr.user_prompt) > 10
        """))
    except Exception as e:
        logger.error(f"Failed to query battle history: {e}")
        return {}
    logger.info(f"Analyzing {len(runs)} historical battles...")
    category_wins = defaultdict(lambda: defaultdict(int))
    category_appearances = defaultdict(lambda: defaultdict(int))
    category_battles = defaultdict(int)
    for run in runs:
        prompt = run["user_prompt"]
        classification = classify_prompt(prompt)
        category = classification["category"]
        category_battles[category] += 1
        try:
            members = list(db.query(
                "SELECT role, response_id FROM consortium_members WHERE run_id = ?",
                [run["id"]]
            ))
        except Exception:
            continue
        for member in members:
            model = canonical_model(member["role"])
            if model in ("arbiter", "dummy", "member", "healer-alpha", "hunter-alpha"):
                continue
            category_appearances[category][model] += 1
            if member["response_id"] == run["chosen_response_id"]:
                category_wins[category][model] += 1
    rules = {}
    for category in sorted(category_battles.keys()):
        appearances = category_appearances[category]
        wins = category_wins[category]
        model_stats = []
        for model, appear_count in appearances.items():
            win_count = wins.get(model, 0)
            win_rate = win_count / appear_count if appear_count > 0 else 0
            if appear_count >= 2:
                model_stats.append({"model": model, "wins": win_count,
                    "appearances": appear_count, "win_rate": round(win_rate, 3)})
        model_stats.sort(key=lambda x: (-x["win_rate"], -x["wins"]))
        selected = [m["model"] for m in model_stats if m["win_rate"] >= 0.20][:3]
        if selected:
            rules[category] = {"models": selected,
                "win_rates": {m["model"]: m["win_rate"] for m in model_stats[:5]},
                "total_battles": category_battles[category]}
    return rules

MIN_BATTLES_RELIABLE = 30  # Below this, recommendations are unreliable


def persist_rules(rules: Dict[str, Dict[str, Any]]) -> str:
    """Save learned routing rules to JSON file for use by classifier."""
    import json
    from pathlib import Path
    rules_path = Path.home() / ".config" / "io.datasette.llm" / "routing_rules.json"
    
    # Only persist categories with sufficient data
    reliable = {}
    for cat, data in rules.items():
        if data["total_battles"] >= MIN_BATTLES_RELIABLE:
            reliable[cat] = {
                "models": data["models"],
                "strategy": "pick_best" if cat != "reasoning" else "ring_ling",
            }
    
    if reliable:
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_text(json.dumps(reliable, indent=2))
        return f"Persisted {len(reliable)} categories to {rules_path}"
    return "No categories with sufficient data to persist"


def format_rules_report(rules: Dict[str, Dict[str, Any]]) -> str:
    lines = ["=" * 70, "ROUTING RULES FROM HISTORICAL BATTLES", "=" * 70, ""]
    for category in sorted(rules.keys()):
        data = rules[category]
        lines.append(f"  {category.upper()} ({data['total_battles']} battles)")
        lines.append(f"    Recommended: {', '.join(data['models'])}")
        lines.append(f"    Win rates:")
        for model, rate in sorted(data["win_rates"].items(), key=lambda x: -x[1]):
            marker = "★" if model in data["models"] else " "
            lines.append(f"      {marker} {model:35} {rate:.1%}")
        lines.append("")
    total = sum(d["total_battles"] for d in rules.values())
    lines.append(f"  Total battles analyzed: {total}")
    lines.append("")
    # Data quality assessment
    unreliable = [(c, d["total_battles"]) for c, d in rules.items() if d["total_battles"] < MIN_BATTLES_RELIABLE]
    if unreliable:
        lines.append(f"  WARNING: {len(unreliable)} categories have insufficient data (< {MIN_BATTLES_RELIABLE} battles):")
        for cat, count in sorted(unreliable, key=lambda x: x[1]):
            lines.append(f"    {cat}: {count} battles (unreliable)")
    lines.append("=" * 70)
    return "\n".join(lines)

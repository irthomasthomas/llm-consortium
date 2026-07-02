"""
Weighted regex task classifier — 80+ weighted patterns across 6 categories.
Ported from llm-router. No external dependencies. Deterministic. Fast.
"""
import re
from typing import Dict, List, Tuple

PATTERNS: Dict[str, List[Tuple[str, int]]] = {
    "coding": [
        (r'\b(code|coding|program|programming)\b', 3),
        (r'\b(function|method|class|variable)\b', 2),
        (r'\b(debug|fix|error|exception|stack ?trace)\b', 3),
        (r'\b(python|javascript|typescript|rust|go|java|c\+\+)\b', 3),
        (r'\b(sql|query|database|select|insert|join)\b', 2),
        (r'\b(api|endpoint|rest|graphql|http)\b', 2),
        (r'\b(react|vue|angular|django|flask|fastapi)\b', 3),
        (r'\b(docker|kubernetes|k8s|deploy)\b', 2),
        (r'\b(algorithm|sort|search|optimize|complexity)\b', 2),
        (r'\b(git|commit|merge|pull request|pr)\b', 1),
        (r'```', 4),
        (r'\b(regex|regular expression)\b', 3),
        (r'\b(html|css|json|xml|yaml)\b', 2),
        (r'\b(compile|build|make|cmake)\b', 2),
        (r'\b(unit test|pytest|jest|mocha)\b', 3),
    ],
    "math": [
        (r'\b(calculate|evaluate)\b', 3),
        (r'\bcompute\b', 1),
        (r'\b(solve|solution|equation)\b', 3),
        (r'\b(derivative|integral|differentiate)\b', 4),
        (r'\b(probability|statistics|statistical)\b', 3),
        (r'\b(prove|proof|theorem|lemma)\b', 4),
        (r'\b(matrix|vector|tensor|eigenvalue)\b', 3),
        (r'\b(geometr|algebra|trigonometr|calculu)s\b', 3),
        (r'\bprime number\b', 3),
        (r'\b(fibonacci|factorial|permutation|combination)\b', 3),
        (r'\d+\s*%\s*of\s*\d+', 5),
        (r'[\d]+\s*[%×÷\+\-\*\/]\s*[\d]+', 2),
        (r'\b(logarithm|exponent|square root)\b', 3),
        (r'\b(sin|cos|tan|cot|sec|csc)\b', 2),
    ],
    "reasoning": [
        (r'\b(analy[sz]e|analysis)\b', 3),
        (r'\b(compare|contrast|comparison)\b', 3),
        (r'\b(implications?|consequences?)\b', 2),
        (r'\b(pros?\s*(?:and|&)\s*cons?)\b', 4),
        (r'\b(logic|logical|deductive|inductive)\b', 3),
        (r'\b(puzzle|riddle|brain ?teaser)\b', 4),
        (r'\b(reasoning|step.by.step|think.through)\b', 3),
        (r'\b(trade.?offs?|advantages?|disadvantages?)\b', 2),
        (r'\b(hypothes|infer|deduce)\b', 3),
        (r'\b(strategy|strategic|tactical)\b', 2),
        (r'\b(ethical|moral|philosophical)\b', 3),
        (r'\b(decision|choose|select|pick)\b', 1),
        (r'\b(if.*then|therefore|thus|hence|consequently)\b', 2),
        (r'^\s*if\b.*\?', 3),
        (r'\b(all|some|none|every)\b.*\b(all|some|none|every)\b', 3),
    ],
    "creative": [
        (r'\b(write|wrote|written)\b.*\b(story|poem|song|script|essay)\b', 4),
        (r'\b(compose|create|generate|craft)\b.*\b(poem|story|song|character)\b', 4),
        (r'\b(imagine|describe|picture|envision)\b.*\b(scene|world|setting|character)\b', 4),
        (r'\b(brainstorm|ideate|generate ideas)\b', 3),
        (r'\b(creative|fiction|narrative|prose)\b', 3),
        (r'\b(dialogue|character|protagonist|antagonist)\b', 2),
        (r'\b(plot|setting|theme|metaphor|simile)\b', 2),
        (r'\b(haiku|sonnet|limerick|acrostic)\b', 4),
        (r'\bwrite\s+a\s+(poem|story|song|haiku|dialogue|letter)\b', 4),
    ],
    "sysadmin": [
        (r'^\s*(sudo|apt|pacman|yum|dnf|brew)\b', 4),
        (r'^\s*(systemctl|journalctl|service)\b', 4),
        (r'^\s*(docker|kubectl|helm)\b', 4),
        (r'^\s*(pip|npm|cargo|yarn|pnpm)\s+(install|remove|update)', 3),
        (r'^\s*(git\s+(clone|commit|push|pull|merge|rebase))\b', 3),
        (r'^\s*(ffmpeg|convert|imagemagick)\b', 3),
        (r'\b(mount|umount|fdisk|lsblk|blkid)\b', 3),
        (r'\b(iptables|ufw|firewall|nftables)\b', 4),
        (r'\b(sshd|nginx|apache|httpd|caddy)\b', 3),
        (r'\b(crontab|cron job|cron|systemd|timer|socket)\b', 3),
        (r'\b(set ?up|configure|install).{0,20}(backup|cron|schedule|deploy)\b', 3),
        (r'\b(network|interface|routing|dns|dhcp)\b', 2),
        (r'\b(permission|chmod|chown|chgrp|acl)\b', 3),
        (r'\b(bash|zsh|fish|shell)\s*(script|function|alias)', 3),
        (r'\b\./\S+\.sh\b', 3),
        (r'\b(environment variable|PATH|export|source)\b', 2),
    ],
    "factual": [
        (r'^\s*what (is|are|was|were)\b', 4),
        (r'^\s*who (is|are|was|were)\b', 4),
        (r'^\s*who (invented|discovered|created|made|built|founded)\b', 4),
        (r'^\s*when (did|was|were)\b', 4),
        (r'^\s*what year\b', 4),
        (r'^\s*where (is|are|was|were)\b', 4),
        (r'^\s*how (do|does|did|can|to)\b', 3),
        (r'\b(define|definition)\b', 3),
        (r'\b(explain|explanation)\b', 2),
        (r'\b(capital of|inventor of|discovered)\b', 4),
        (r'\b(history of|origin of|meaning of)\b', 3),
        (r'\b(list|name)\b.*\b(types of|kinds of|examples of)\b', 2),
    ],
}

CATEGORY_PRIORITY = ["coding", "math", "reasoning", "sysadmin", "creative", "factual"]

# Evidence-based routing rules from 738 historical consortium battles.
# Updated by learning.py - run llm consortium learn to refresh.
DEFAULT_ROUTING_RULES = {
    "coding":     {"models": ["glm-5.2-zen", "gemini-3-flash-zen"], "strategy": "pick_best"},
    "math":       {"models": ["openrouter/inception/mercury-2", "deepseek-v4-flash"], "strategy": "pick_best"},
    "reasoning":  {"models": ["gemini/gemini-2.5-pro", "cns-k2.6-n5-rank"], "strategy": "ring_ling"},
    "creative":   {"models": ["gpt-oss-120b-groq", "deepseek-v4-flash"], "strategy": "pick_best"},
    "factual":    {"models": ["deepseek-v4-flash", "gemini/gemini-2.5-flash"], "strategy": "fast"},
    "sysadmin":   {"models": ["glm-5", "deepseek-v4-pro"], "strategy": "pick_best"},
    "general":    {"models": ["ling-2.6-1t", "deepseek-v4-flash"], "strategy": "default"},
}

def classify_prompt(prompt: str) -> dict:
    prompt_lower = prompt.lower()
    scores = {}
    matched_patterns = {}
    for category, patterns in PATTERNS.items():
        total_score = 0
        matches = []
        for pattern, weight in patterns:
            if re.search(pattern, prompt_lower):
                total_score += weight
                matches.append(pattern)
        scores[category] = total_score
        if matches:
            matched_patterns[category] = matches
    max_score = max(scores.values()) if scores else 0
    if max_score == 0:
        return {"category": "general", "confidence": 0.0, "method": "weighted_patterns",
                "scores": scores, "matched_patterns": matched_patterns}
    best_score = max(scores.values())
    candidates = [c for c, s in scores.items() if s == best_score]
    if len(candidates) == 1:
        best_category = candidates[0]
    else:
        best_category = min(candidates, key=lambda c: CATEGORY_PRIORITY.index(c) if c in CATEGORY_PRIORITY else 99)
    sorted_scores = sorted(scores.values(), reverse=True)
    abs_confidence = min(best_score / 8.0, 1.0)
    if len(sorted_scores) > 1 and sorted_scores[1] > 0:
        rel_confidence = min(best_score / (best_score + sorted_scores[1]), 1.0)
    else:
        rel_confidence = min(best_score / 5.0, 1.0)
    confidence = min(abs_confidence, rel_confidence)
    return {"category": best_category, "confidence": round(confidence, 3), "method": "weighted_patterns",
            "scores": scores, "matched_patterns": matched_patterns}

def get_routing_decision(category: str) -> dict:
    """Get routing decision, checking learned rules first, then defaults."""
    import json as _json
    from pathlib import Path as _Path
    rules_path = _Path.home() / ".config" / "io.datasette.llm" / "routing_rules.json"
    if rules_path.exists():
        try:
            learned = _json.loads(rules_path.read_text())
            if category in learned:
                return learned[category]
        except Exception:
            pass
    return DEFAULT_ROUTING_RULES.get(category, DEFAULT_ROUTING_RULES["general"])

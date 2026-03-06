"""
Consortium Configuration Examples (cns-*)
==========================================

Python API examples demonstrating every strategy, judging method,
and configuration pattern. Each includes a realistic prompt to run.

Models used:
  - openrouter/moonshotai/kimi-k2.5
  - openrouter/minimax/minimax-m2.5
  - openrouter/z-ai/glm-5
  - gpt-4.1-copilot
  - openrouter/qwen/qwen3.5-122b-a10b
  - gpt-oss-120b-groq
  - openrouter/qwen/qwen3.5-397b-a17b
"""

from llm_consortium import create_consortium


# ============================================================================
# 1. DEFAULT STRATEGY
# ============================================================================

def cns_quick_answer():
    """Fast factual Q&A — 3 lightweight models, single iteration."""
    orch = create_consortium(
        models=["openrouter/minimax/minimax-m2.5", "gpt-4.1-copilot", "openrouter/qwen/qwen3.5-122b-a10b"],
        arbiter="gpt-oss-120b-groq",
        confidence_threshold=0.7,
        max_iterations=1,
        minimum_iterations=1,
        strategy="default",
    )
    return orch.orchestrate("What is the current population of Tokyo and how does it compare to Delhi?")


def cns_deep_research():
    """Multi-iteration deep analysis with high confidence bar."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
            "openrouter/z-ai/glm-5",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.92,
        max_iterations=5,
        minimum_iterations=2,
        strategy="default",
    )
    return orch.orchestrate(
        "Compare the transformer architecture with state-space models (Mamba, S4) "
        "for long-context sequence modeling. Cover theoretical foundations, "
        "computational complexity, empirical results on language modeling benchmarks, "
        "and practical deployment considerations."
    )


def cns_all_models():
    """Every model in the pool for maximum coverage."""
    orch = create_consortium(
        models={
            "openrouter/moonshotai/kimi-k2.5": 1,
            "openrouter/minimax/minimax-m2.5": 1,
            "openrouter/z-ai/glm-5": 1,
            "gpt-4.1-copilot": 1,
            "openrouter/qwen/qwen3.5-122b-a10b": 1,
            "gpt-oss-120b-groq": 1,
            "openrouter/qwen/qwen3.5-397b-a17b": 1,
        },
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.85,
        max_iterations=3,
        minimum_iterations=1,
        strategy="default",
    )
    return orch.orchestrate(
        "Design a rate limiting system for a multi-tenant SaaS API "
        "that handles 50,000 RPS. Cover token bucket vs sliding window algorithms, "
        "distributed coordination, tenant isolation, and graceful degradation."
    )


# ============================================================================
# 2. RANK JUDGING — Pick the best instead of synthesizing
# ============================================================================

def cns_rank_code_review():
    """Rank code review quality — pick the most useful review."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "gpt-4.1-copilot",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.85,
        max_iterations=2,
        minimum_iterations=1,
        judging_method="rank",
        strategy="default",
    )
    return orch.orchestrate("""Review this Python function for bugs, security issues, and improvements:

```python
def process_upload(file_path, user_id):
    import subprocess
    with open(file_path) as f:
        data = eval(f.read())
    subprocess.call(f"convert {file_path} /tmp/{user_id}_output.pdf", shell=True)
    db.execute(f"INSERT INTO uploads (user_id, data) VALUES ('{user_id}', '{data}')")
    return {"status": "ok", "path": f"/tmp/{user_id}_output.pdf"}
```""")


def cns_rank_factcheck():
    """Rank by factual accuracy — penalize hallucination."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/z-ai/glm-5",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
            "gpt-4.1-copilot",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.9,
        max_iterations=3,
        minimum_iterations=2,
        judging_method="rank",
        strategy="default",
    )
    return orch.orchestrate(
        "What were the specific terms of the Plaza Accord of 1985? "
        "Which countries signed it, what exchange rate targets were set, "
        "and what was the measurable impact on USD/JPY and USD/DEM over the following 2 years? "
        "Cite only verifiable facts."
    )


# ============================================================================
# 3. VOTING STRATEGY — Consensus-based
# ============================================================================

def cns_vote_strict():
    """Strict majority voting for math problems."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
            "gpt-4.1-copilot",
            "openrouter/z-ai/glm-5",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.9,
        max_iterations=3,
        minimum_iterations=1,
        strategy="voting",
        strategy_params={
            "similarity_threshold": 0.7,
            "require_majority": True,
            "fallback_to_all": True,
            "answer_length": 500,
        },
    )
    return orch.orchestrate(
        "A train leaves station A at 60 km/h. Another train leaves station B "
        "(300 km away) 30 minutes later at 90 km/h heading toward station A. "
        "At what distance from station A do they meet? Show your work."
    )


def cns_vote_binary():
    """Binary yes/no voting with all 7 models — maximum voter count."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/minimax/minimax-m2.5",
            "openrouter/z-ai/glm-5",
            "gpt-4.1-copilot",
            "openrouter/qwen/qwen3.5-122b-a10b",
            "gpt-oss-120b-groq",
            "openrouter/qwen/qwen3.5-397b-a17b",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.85,
        max_iterations=1,
        minimum_iterations=1,
        strategy="voting",
        strategy_params={
            "similarity_threshold": 0.8,
            "require_majority": True,
            "fallback_to_all": False,
            "answer_length": 50,
        },
    )
    return orch.orchestrate(
        "Is the following SQL query safe from injection attacks? Answer YES or NO, "
        "then explain briefly.\n\n"
        "query = f\"SELECT * FROM users WHERE id = {request.args.get('id')}\""
    )


def cns_vote_soft():
    """Soft consensus for open-ended creative suggestions."""
    orch = create_consortium(
        models=[
            "openrouter/minimax/minimax-m2.5",
            "openrouter/z-ai/glm-5",
            "gpt-4.1-copilot",
            "openrouter/qwen/qwen3.5-122b-a10b",
        ],
        arbiter="gpt-oss-120b-groq",
        confidence_threshold=0.75,
        max_iterations=2,
        minimum_iterations=1,
        strategy="voting",
        strategy_params={
            "similarity_threshold": 0.4,
            "require_majority": False,
            "fallback_to_all": True,
            "answer_length": 2000,
        },
    )
    return orch.orchestrate(
        "Suggest 3 names for a developer tool that combines git bisect with "
        "AI-powered root cause analysis. For each name, explain the reasoning."
    )


# ============================================================================
# 4. ELIMINATION STRATEGY — Progressive pruning
# ============================================================================

def cns_elim_tournament():
    """7-model tournament — eliminate 2 per round, keep top 2."""
    orch = create_consortium(
        models={
            "openrouter/moonshotai/kimi-k2.5": 1,
            "openrouter/minimax/minimax-m2.5": 1,
            "openrouter/z-ai/glm-5": 1,
            "gpt-4.1-copilot": 1,
            "openrouter/qwen/qwen3.5-122b-a10b": 1,
            "gpt-oss-120b-groq": 1,
            "openrouter/qwen/qwen3.5-397b-a17b": 1,
        },
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.88,
        max_iterations=5,
        minimum_iterations=3,
        judging_method="rank",
        strategy="elimination",
        strategy_params={
            "eliminate_count": 2,
            "keep_minimum": 2,
            "elimination_delay": 1,
        },
    )
    return orch.orchestrate(
        "Write a production-ready Python async context manager that implements "
        "a distributed lock using Redis with automatic renewal, deadlock detection, "
        "and graceful degradation when Redis is unavailable. Include type hints "
        "and comprehensive error handling."
    )


def cns_elim_gentle():
    """Gentle elimination — drop 1 per round, keep 3 minimum."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/z-ai/glm-5",
            "gpt-4.1-copilot",
            "openrouter/qwen/qwen3.5-122b-a10b",
            "gpt-oss-120b-groq",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.85,
        max_iterations=4,
        minimum_iterations=2,
        judging_method="rank",
        strategy="elimination",
        strategy_params={
            "eliminate_count": 1,
            "keep_minimum": 3,
            "elimination_delay": 1,
        },
    )
    return orch.orchestrate(
        "Design a database schema and query strategy for a social media feed "
        "that supports: posts, comments, likes, reposts, follow relationships, "
        "and a personalized timeline with 500M users. Cover indexing strategy, "
        "read/write patterns, and how to handle fan-out."
    )


def cns_elim_fraction():
    """Fractional elimination — cut 25% each round."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/minimax/minimax-m2.5",
            "openrouter/z-ai/glm-5",
            "gpt-4.1-copilot",
            "openrouter/qwen/qwen3.5-122b-a10b",
            "gpt-oss-120b-groq",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.85,
        max_iterations=4,
        minimum_iterations=2,
        judging_method="rank",
        strategy="elimination",
        strategy_params={
            "eliminate_fraction": 0.25,
            "keep_minimum": 2,
            "elimination_delay": 0,
        },
    )
    return orch.orchestrate(
        "Explain the CAP theorem with concrete examples of systems that choose "
        "different trade-offs (CP vs AP vs CA). For each, describe a failure "
        "scenario and how the system behaves. Include at least one common "
        "misconception about CAP."
    )


# ============================================================================
# 5. ROLE STRATEGY — Assigned cognitive perspectives
# ============================================================================

def cns_role_default():
    """Built-in roles: Generator, Devil's Advocate, Fact Checker."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.85,
        max_iterations=3,
        minimum_iterations=1,
        strategy="role",
    )
    return orch.orchestrate(
        "Should our startup migrate from a monolithic Django application to "
        "microservices? We have 12 engineers, 200k DAU, and the monolith "
        "deploys take 45 minutes. The main pain point is that teams block "
        "each other on releases."
    )


def cns_role_code_audit():
    """Security audit with specialized reviewer roles."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "gpt-4.1-copilot",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.88,
        max_iterations=3,
        minimum_iterations=2,
        strategy="role",
        strategy_params={
            "roles": [
                "The Security Auditor: Focus exclusively on security vulnerabilities — "
                "injection, auth bypass, data leaks, SSRF, race conditions. Assume all input is adversarial.",
                "The Performance Engineer: Analyze computational complexity, memory usage, "
                "I/O patterns, and scalability bottlenecks. Suggest concrete optimizations.",
                "The Correctness Prover: Verify logical correctness, edge cases, off-by-one errors, "
                "null handling, and type safety. Trace execution paths mentally.",
                "The Maintainability Reviewer: Assess readability, naming, abstraction level, "
                "test coverage gaps, and adherence to SOLID principles.",
            ],
        },
    )
    return orch.orchestrate("""Audit this authentication middleware:

```python
import jwt, hashlib, time
from functools import wraps
from flask import request, jsonify, g

SECRET = "my-secret-key-2024"

def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        try:
            payload = jwt.decode(token, SECRET, algorithms=["HS256"])
            g.user_id = payload['user_id']
            g.is_admin = payload.get('is_admin', False)
        except:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/admin/users/<user_id>', methods=['DELETE'])
@require_auth
def delete_user(user_id):
    if g.is_admin:
        db.execute(f"DELETE FROM users WHERE id = {user_id}")
        return jsonify({"deleted": user_id})
    return jsonify({"error": "forbidden"}), 403
```""")


def cns_role_debate():
    """Structured debate with explicit pro/con/pragmatic/historical roles."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
            "openrouter/z-ai/glm-5",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.8,
        max_iterations=4,
        minimum_iterations=2,
        strategy="role",
        strategy_params={
            "roles": [
                "The Proponent: Argue strongly in favor. Build the strongest case with evidence. "
                "Steel-man the position.",
                "The Opponent: Argue strongly against. Find every flaw, risk, and counterexample. "
                "Steel-man the opposing case.",
                "The Pragmatist: Ignore ideology. Focus on real-world feasibility, costs, "
                "second-order effects, and practical trade-offs.",
                "The Historian: Ground the discussion in precedent. What has been tried before? "
                "What were the outcomes? What does the evidence base say?",
            ],
        },
    )
    return orch.orchestrate(
        "Should the EU mandate that all AI models above 10^25 FLOPs of training compute "
        "undergo mandatory third-party safety audits before deployment? Consider innovation "
        "impact, safety benefits, enforcement feasibility, and global competitiveness."
    )


def cns_role_writing():
    """Editorial team for content creation."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/minimax/minimax-m2.5",
            "openrouter/z-ai/glm-5",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.82,
        max_iterations=3,
        minimum_iterations=2,
        strategy="role",
        strategy_params={
            "roles": [
                "The Drafter: Write the primary draft. Focus on flow, structure, and getting "
                "ideas on paper. Be bold and expressive.",
                "The Editor: Rewrite for clarity, concision, and audience. Cut fluff. Fix logic "
                "gaps. Make every sentence earn its place.",
                "The Fact-Checker and Style Guide: Verify all claims. Flag unsupported assertions. "
                "Ensure consistent tone and terminology.",
            ],
        },
    )
    return orch.orchestrate(
        "Write a 500-word blog post explaining WebAssembly to backend developers "
        "who have never used it. Cover what it is, why they should care, and "
        "one concrete use case (e.g., running user-uploaded Wasm plugins in a server). "
        "Tone: technical but approachable, no hype."
    )


def cns_role_dynamic():
    """More models than roles — extras get randomized personality matrices."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/minimax/minimax-m2.5",
            "openrouter/z-ai/glm-5",
            "gpt-4.1-copilot",
            "openrouter/qwen/qwen3.5-122b-a10b",
            "gpt-oss-120b-groq",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.85,
        max_iterations=3,
        minimum_iterations=1,
        strategy="role",
        strategy_params={"use_dynamic_personalities": "true"},
    )
    return orch.orchestrate(
        "What's the best way to implement real-time collaboration (like Google Docs) "
        "in a web application? Compare CRDTs vs OT, discuss infrastructure requirements, "
        "and recommend a tech stack for a team of 5 building an MVP."
    )


# ============================================================================
# 6. MULTIPLE INSTANCES — Self-consistency sampling
# ============================================================================

def cns_triple_qwen():
    """3 instances of Qwen 397b for self-consistency on math."""
    orch = create_consortium(
        models={"openrouter/qwen/qwen3.5-397b-a17b": 3},
        arbiter="gpt-oss-120b-groq",
        confidence_threshold=0.9,
        max_iterations=2,
        minimum_iterations=1,
        strategy="voting",
        strategy_params={
            "similarity_threshold": 0.6,
            "require_majority": True,
            "answer_length": 500,
        },
    )
    return orch.orchestrate(
        "Find all integer solutions to: x^3 + y^3 + z^3 = 42 where |x|, |y|, |z| < 10^6. "
        "Show your reasoning process."
    )


def cns_multi_instance():
    """Weighted model representation — heavyweights get 2 instances."""
    orch = create_consortium(
        models={
            "openrouter/qwen/qwen3.5-397b-a17b": 2,
            "openrouter/moonshotai/kimi-k2.5": 2,
            "gpt-4.1-copilot": 1,
            "openrouter/qwen/qwen3.5-122b-a10b": 1,
        },
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.85,
        max_iterations=3,
        minimum_iterations=1,
        strategy="default",
    )
    return orch.orchestrate(
        "Implement a B-tree in Rust with insert, delete, and range query operations. "
        "Support configurable branching factor. Include appropriate trait implementations."
    )


# ============================================================================
# 7. SYSTEM PROMPT CUSTOMIZATION
# ============================================================================

def cns_json_only():
    """Force structured JSON output from all members."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "gpt-4.1-copilot",
            "openrouter/qwen/qwen3.5-122b-a10b",
        ],
        arbiter="gpt-oss-120b-groq",
        confidence_threshold=0.85,
        max_iterations=2,
        minimum_iterations=1,
        strategy="default",
        system_prompt=(
            "You must respond ONLY with valid JSON. No markdown, no explanation, no prose. "
            "Your entire response must be parseable by json.loads(). "
            "Use the schema provided in the user prompt."
        ),
    )
    return orch.orchestrate(
        'Extract entities from this text and return as JSON with schema '
        '{"entities": [{"text": str, "type": "PERSON"|"ORG"|"LOCATION"|"DATE", "confidence": float}]}:\n\n'
        '"Tim Cook announced that Apple will open a new office in Ho Chi Minh City '
        'by Q3 2027, partnering with VinGroup on local manufacturing."'
    )


def cns_expert_python():
    """Python expert consortium with domain-specific system prompt."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "gpt-4.1-copilot",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.88,
        max_iterations=3,
        minimum_iterations=1,
        strategy="default",
        system_prompt=(
            "You are a senior Python engineer with deep expertise in Python 3.12+, "
            "type hints, async/await, and modern tooling (ruff, uv, pytest). "
            "Write production-quality code. Prefer stdlib solutions. "
            "No unnecessary dependencies. Always include type annotations. "
            "Handle errors explicitly."
        ),
    )
    return orch.orchestrate(
        "Write a Python module that implements a persistent task queue backed by SQLite. "
        "Support: enqueue, dequeue (with visibility timeout), ack, nack, dead-letter queue, "
        "and periodic cleanup of expired messages. Must be safe for multi-threaded access."
    )


# ============================================================================
# 8. MANUAL CONTEXT MODE
# ============================================================================

def cns_manual_ctx():
    """Manual context construction for cache-optimized workflows."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.85,
        max_iterations=3,
        minimum_iterations=1,
        strategy="default",
        manual_context=True,
    )
    # First turn
    result1 = orch.orchestrate(
        "Explain the difference between optimistic and pessimistic concurrency control."
    )
    # Second turn with conversation history
    result2 = orch.orchestrate(
        "Now show me how to implement optimistic locking in PostgreSQL with a retry loop.",
        conversation_history=(
            f"User: Explain the difference between optimistic and pessimistic concurrency control.\n"
            f"Assistant: {result1['synthesis']['synthesis']}"
        ),
    )
    return result2


# ============================================================================
# 9. DOMAIN-SPECIFIC COMBINED CONFIGURATIONS
# ============================================================================

def cns_legal_review():
    """Legal document analysis with adversarial counsel roles."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
            "openrouter/z-ai/glm-5",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.9,
        max_iterations=4,
        minimum_iterations=2,
        strategy="role",
        strategy_params={
            "roles": [
                "Party A's Counsel: Identify clauses favorable to Party A and risks to Party A. "
                "Suggest protective amendments.",
                "Party B's Counsel: Identify clauses favorable to Party B and risks to Party B. "
                "Suggest protective amendments.",
                "The Neutral Drafter: Propose balanced language that protects both parties equally. "
                "Focus on clarity and enforceability.",
                "The Compliance Officer: Check for regulatory compliance issues, missing required "
                "clauses, and jurisdictional concerns.",
            ],
        },
    )
    return orch.orchestrate(
        "Review this SaaS agreement clause:\n\n"
        '"Licensee grants Licensor a perpetual, irrevocable, worldwide license to use, '
        "modify, and distribute any data uploaded to the Service for the purpose of "
        "improving Licensor's products and services, including training machine learning "
        'models. This license survives termination of the Agreement."'
    )


def cns_incident_response():
    """Production incident analysis — elimination keeps best diagnosticians."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "gpt-4.1-copilot",
            "openrouter/qwen/qwen3.5-397b-a17b",
            "gpt-oss-120b-groq",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.85,
        max_iterations=3,
        minimum_iterations=2,
        judging_method="rank",
        strategy="elimination",
        strategy_params={
            "eliminate_count": 1,
            "keep_minimum": 2,
            "elimination_delay": 1,
        },
        system_prompt=(
            "You are a senior SRE analyzing a production incident. "
            "Focus on: 1) Root cause identification from the evidence provided. "
            "2) Immediate mitigation steps. 3) Preventive measures. "
            "Do NOT speculate beyond the evidence. If information is missing, "
            "say exactly what logs/metrics you need."
        ),
    )
    return orch.orchestrate(
        "Our payment service started returning 503s at 14:32 UTC. "
        "Key observations:\n"
        "- Postgres connection pool exhausted (max_connections=100, all in use)\n"
        "- No deployment in last 24h\n"
        "- Traffic is normal (2,000 RPM)\n"
        "- slow_query_log shows a new query pattern: SELECT * FROM transactions "
        "WHERE status='pending' AND created_at > now() - interval '30 days' (avg 12s)\n"
        "- The transactions table has 450M rows, index on (status) only\n"
        "- A cron job for monthly reporting was added last week\n\n"
        "What's the root cause and what should we do right now?"
    )


def cns_math_olympiad():
    """Self-consistency voting on competition math with duplicate instances."""
    orch = create_consortium(
        models={
            "openrouter/moonshotai/kimi-k2.5": 2,
            "openrouter/qwen/qwen3.5-397b-a17b": 2,
            "gpt-oss-120b-groq": 2,
            "gpt-4.1-copilot": 1,
        },
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.95,
        max_iterations=4,
        minimum_iterations=2,
        strategy="voting",
        strategy_params={
            "similarity_threshold": 0.8,
            "require_majority": True,
            "fallback_to_all": True,
            "answer_length": 100,
        },
        system_prompt=(
            "Solve step by step. Show all work. State the final numerical answer "
            "clearly on its own line prefixed with 'ANSWER: '. Double-check your arithmetic."
        ),
    )
    return orch.orchestrate(
        "Let f(x) = x^4 - 4x^3 + 6x^2 - 4x + 1. Find the sum of all real values "
        "of x for which f(f(x)) = 0."
    )


def cns_startup_pitch():
    """Business idea stress-test with VC/Customer/Operator/Competitor perspectives."""
    orch = create_consortium(
        models=[
            "openrouter/moonshotai/kimi-k2.5",
            "openrouter/minimax/minimax-m2.5",
            "gpt-4.1-copilot",
            "openrouter/z-ai/glm-5",
        ],
        arbiter="openrouter/qwen/qwen3.5-397b-a17b",
        confidence_threshold=0.8,
        max_iterations=3,
        minimum_iterations=2,
        strategy="role",
        strategy_params={
            "roles": [
                "The VC Partner: Evaluate market size, defensibility, team risk, and unit economics. "
                "Be skeptical. What's the failure mode?",
                "The Customer: Would you actually use this? What's your willingness to pay? "
                "What alternatives exist? Be brutally honest.",
                "The Operator: Can this actually be built and scaled? What are the operational "
                "nightmares? What's the hiring plan?",
                "The Competitor: How would an incumbent crush this? What moat could protect "
                "against fast-followers?",
            ],
        },
    )
    return orch.orchestrate(
        "Pitch: An AI-powered code review tool that integrates into GitHub PRs. "
        "It doesn't just lint — it understands your codebase's patterns, your team's "
        "conventions, and flags architectural regressions. $49/month per developer. "
        "Team of 3 engineers, pre-revenue, 200 beta users. "
        "Evaluate this startup idea."
    )


# ============================================================================
# Runner — pick one to execute
# ============================================================================

# Map of all examples for easy selection
ALL_EXAMPLES = {
    # Default strategy
    "cns-quick-answer": cns_quick_answer,
    "cns-deep-research": cns_deep_research,
    "cns-all-models": cns_all_models,
    # Rank judging
    "cns-rank-code-review": cns_rank_code_review,
    "cns-rank-factcheck": cns_rank_factcheck,
    # Voting
    "cns-vote-strict": cns_vote_strict,
    "cns-vote-binary": cns_vote_binary,
    "cns-vote-soft": cns_vote_soft,
    # Elimination
    "cns-elim-tournament": cns_elim_tournament,
    "cns-elim-gentle": cns_elim_gentle,
    "cns-elim-fraction": cns_elim_fraction,
    # Role
    "cns-role-default": cns_role_default,
    "cns-role-code-audit": cns_role_code_audit,
    "cns-role-debate": cns_role_debate,
    "cns-role-writing": cns_role_writing,
    "cns-role-dynamic": cns_role_dynamic,
    # Multi-instance
    "cns-triple-qwen": cns_triple_qwen,
    "cns-multi-instance": cns_multi_instance,
    # System prompt
    "cns-json-only": cns_json_only,
    "cns-expert-python": cns_expert_python,
    # Manual context
    "cns-manual-ctx": cns_manual_ctx,
    # Domain-specific
    "cns-legal-review": cns_legal_review,
    "cns-incident-response": cns_incident_response,
    "cns-math-olympiad": cns_math_olympiad,
    "cns-startup-pitch": cns_startup_pitch,
}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2 or sys.argv[1] == "--list":
        print("Available consortium examples:\n")
        for name, fn in ALL_EXAMPLES.items():
            doc = fn.__doc__ or ""
            print(f"  {name:30s} {doc.strip()}")
        print(f"\nUsage: python {sys.argv[0]} <example-name>")
        print(f"       python {sys.argv[0]} --list")
        sys.exit(0)

    name = sys.argv[1]
    if name not in ALL_EXAMPLES:
        print(f"Unknown example: {name}")
        print(f"Run with --list to see available examples.")
        sys.exit(1)

    print(f"Running: {name}")
    print("=" * 60)
    result = ALL_EXAMPLES[name]()
    print(f"\n{'=' * 60}")
    print(f"Synthesis:\n{result['synthesis']['synthesis'][:2000]}")
    print(f"\nConfidence: {result['synthesis']['confidence']}")
    print(f"Iterations: {result['metadata']['total_iterations']}")
    print(f"Consortium ID: {result['metadata']['consortium_id']}")

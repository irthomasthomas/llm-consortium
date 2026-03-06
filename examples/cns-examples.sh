#!/usr/bin/env bash
# =============================================================================
# Consortium Configuration Examples (cns-*)
# =============================================================================
# All configurations use these models:
#   - openrouter/moonshotai/kimi-k2.5       (strong reasoning)
#   - openrouter/minimax/minimax-m2.5        (general purpose)
#   - openrouter/z-ai/glm-5                 (Chinese-origin, balanced)
#   - gpt-4.1-copilot                        (coding/general, mid-range)
#   - openrouter/qwen/qwen3.5-122b-a10b     (MoE, efficient)
#   - gpt-oss-120b-groq                     (fast inference, large)
#   - openrouter/qwen/qwen3.5-397b-a17b     (MoE, largest)
#
# These examples demonstrate all strategies, judging methods, and parameter
# combinations. Each is a realistic use-case.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 1. DEFAULT STRATEGY — Basic configurations
# ---------------------------------------------------------------------------

# --- cns-quick-answer: Fast single-iteration lookup for factual questions ---
# Use case: simple Q&A where speed matters more than depth
llm consortium save cns-quick-answer \
  -m openrouter/minimax/minimax-m2.5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  --arbiter gpt-oss-120b-groq \
  --confidence-threshold 0.7 \
  --max-iterations 1 \
  --min-iterations 1 \
  --strategy default

# --- cns-deep-research: Multi-iteration deep analysis with high threshold ---
# Use case: complex research questions needing thorough synthesis
llm consortium save cns-deep-research \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  -m openrouter/z-ai/glm-5 \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.92 \
  --max-iterations 5 \
  --min-iterations 2 \
  --strategy default

# --- cns-all-models: Kitchen sink — every available model, maximum diversity ---
# Use case: critical decisions where you want maximum coverage
llm consortium save cns-all-models \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/minimax/minimax-m2.5 \
  -m openrouter/z-ai/glm-5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  -m gpt-oss-120b-groq \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 3 \
  --min-iterations 1 \
  --strategy default

# --- cns-budget: Minimum viable consortium — cheap and fast ---
# Use case: high-volume low-stakes queries (e.g. classification, tagging)
llm consortium save cns-budget \
  -m openrouter/minimax/minimax-m2.5 \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  --arbiter gpt-4.1-copilot \
  --confidence-threshold 0.65 \
  --max-iterations 1 \
  --min-iterations 1 \
  --strategy default

# --- cns-duo-heavyweight: Two big models, arbiter picks best ---
# Use case: when you want to compare the two strongest models head-to-head
llm consortium save cns-duo-heavyweight \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  --arbiter gpt-oss-120b-groq \
  --confidence-threshold 0.8 \
  --max-iterations 2 \
  --min-iterations 1 \
  --strategy default


# ---------------------------------------------------------------------------
# 2. RANK JUDGING METHOD — Pick-best rather than synthesize
# ---------------------------------------------------------------------------

# --- cns-rank-code-review: Rank responses for code quality assessment ---
# Use case: get multiple code review perspectives, pick the most accurate
llm consortium save cns-rank-code-review \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 2 \
  --min-iterations 1 \
  --judging-method rank \
  --strategy default

# --- cns-rank-factcheck: Rank for factual accuracy over eloquence ---
# Use case: verify claims where hallucination is the main risk
llm consortium save cns-rank-factcheck \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/z-ai/glm-5 \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  -m gpt-4.1-copilot \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.9 \
  --max-iterations 3 \
  --min-iterations 2 \
  --judging-method rank \
  --strategy default

# --- cns-rank-translation: Rank translations for natural fluency ---
# Use case: translate text and pick the most natural-sounding version
llm consortium save cns-rank-translation \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/z-ai/glm-5 \
  -m openrouter/minimax/minimax-m2.5 \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 2 \
  --min-iterations 1 \
  --judging-method rank \
  --strategy default


# ---------------------------------------------------------------------------
# 3. VOTING STRATEGY — Consensus-based selection
# ---------------------------------------------------------------------------

# --- cns-vote-strict: Strict majority required, high similarity bar ---
# Use case: math/logic problems where there's one right answer
llm consortium save cns-vote-strict \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  -m gpt-4.1-copilot \
  -m openrouter/z-ai/glm-5 \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.9 \
  --max-iterations 3 \
  --min-iterations 1 \
  --strategy voting \
  --strategy-param similarity_threshold=0.7 \
  --strategy-param require_majority=true \
  --strategy-param fallback_to_all=true \
  --strategy-param answer_length=500

# --- cns-vote-soft: Relaxed consensus for open-ended questions ---
# Use case: brainstorming, opinion aggregation, creative suggestions
llm consortium save cns-vote-soft \
  -m openrouter/minimax/minimax-m2.5 \
  -m openrouter/z-ai/glm-5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  --arbiter gpt-oss-120b-groq \
  --confidence-threshold 0.75 \
  --max-iterations 2 \
  --min-iterations 1 \
  --strategy voting \
  --strategy-param similarity_threshold=0.4 \
  --strategy-param require_majority=false \
  --strategy-param fallback_to_all=true \
  --strategy-param answer_length=2000

# --- cns-vote-binary: Short-answer voting for yes/no or A/B questions ---
# Use case: binary classification, go/no-go decisions
llm consortium save cns-vote-binary \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/minimax/minimax-m2.5 \
  -m openrouter/z-ai/glm-5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  -m gpt-oss-120b-groq \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 1 \
  --min-iterations 1 \
  --strategy voting \
  --strategy-param similarity_threshold=0.8 \
  --strategy-param require_majority=true \
  --strategy-param fallback_to_all=false \
  --strategy-param answer_length=50


# ---------------------------------------------------------------------------
# 4. ELIMINATION STRATEGY — Progressive model pruning
# ---------------------------------------------------------------------------

# --- cns-elim-tournament: Aggressive elimination tournament ---
# Use case: writing quality — eliminate weakest writers each round
llm consortium save cns-elim-tournament \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/minimax/minimax-m2.5 \
  -m openrouter/z-ai/glm-5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  -m gpt-oss-120b-groq \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.88 \
  --max-iterations 5 \
  --min-iterations 3 \
  --judging-method rank \
  --strategy elimination \
  --strategy-param eliminate_count=2 \
  --strategy-param keep_minimum=2 \
  --strategy-param elimination_delay=1

# --- cns-elim-gentle: Gradual elimination, keep most models ---
# Use case: technical analysis where you want diversity but prune noise
llm consortium save cns-elim-gentle \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/z-ai/glm-5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 4 \
  --min-iterations 2 \
  --judging-method rank \
  --strategy elimination \
  --strategy-param eliminate_count=1 \
  --strategy-param keep_minimum=3 \
  --strategy-param elimination_delay=1

# --- cns-elim-fraction: Eliminate by fraction rather than count ---
# Use case: scales better with variable model counts
llm consortium save cns-elim-fraction \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/minimax/minimax-m2.5 \
  -m openrouter/z-ai/glm-5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 4 \
  --min-iterations 2 \
  --judging-method rank \
  --strategy elimination \
  --strategy-param eliminate_fraction=0.25 \
  --strategy-param keep_minimum=2 \
  --strategy-param elimination_delay=0

# --- cns-elim-delayed: Extra warmup round before elimination starts ---
# Use case: complex questions where models need iteration context first
llm consortium save cns-elim-delayed \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/z-ai/glm-5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.88 \
  --max-iterations 5 \
  --min-iterations 3 \
  --judging-method rank \
  --strategy elimination \
  --strategy-param eliminate_count=1 \
  --strategy-param keep_minimum=2 \
  --strategy-param elimination_delay=2


# ---------------------------------------------------------------------------
# 5. ROLE STRATEGY — Assigned cognitive perspectives
# ---------------------------------------------------------------------------

# --- cns-role-default: Standard 3-role configuration (Generator, Devil's Advocate, Fact Checker) ---
# Use case: general problem-solving with built-in adversarial review
llm consortium save cns-role-default \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 3 \
  --min-iterations 1 \
  --strategy role

# --- cns-role-code-audit: Security-focused code review roles ---
# Use case: code review with security, performance, and correctness angles
llm consortium save cns-role-code-audit \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.88 \
  --max-iterations 3 \
  --min-iterations 2 \
  --strategy role \
  --strategy-param "roles=The Security Auditor: Focus exclusively on security vulnerabilities — injection, auth bypass, data leaks, SSRF, race conditions. Assume all input is adversarial." \
  --strategy-param "roles=The Performance Engineer: Analyze computational complexity, memory usage, I/O patterns, and scalability bottlenecks. Suggest concrete optimizations." \
  --strategy-param "roles=The Correctness Prover: Verify logical correctness, edge cases, off-by-one errors, null handling, and type safety. Trace execution paths mentally." \
  --strategy-param "roles=The Maintainability Reviewer: Assess readability, naming, abstraction level, test coverage gaps, and adherence to SOLID principles."

# --- cns-role-debate: Structured debate with opposing positions ---
# Use case: policy analysis, ethical dilemmas, design trade-offs
llm consortium save cns-role-debate \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  -m openrouter/z-ai/glm-5 \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.8 \
  --max-iterations 4 \
  --min-iterations 2 \
  --strategy role \
  --strategy-param "roles=The Proponent: Argue strongly in favor. Build the strongest possible case with evidence and reasoning. Steel-man the position." \
  --strategy-param "roles=The Opponent: Argue strongly against. Find every flaw, risk, and counterexample. Steel-man the opposing case." \
  --strategy-param "roles=The Pragmatist: Ignore ideology. Focus on real-world feasibility, implementation costs, second-order effects, and practical trade-offs." \
  --strategy-param "roles=The Historian: Ground the discussion in precedent. What has been tried before? What were the outcomes? What does the evidence base say?"

# --- cns-role-writing: Creative writing with editorial team roles ---
# Use case: drafting articles, blog posts, documentation
llm consortium save cns-role-writing \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/minimax/minimax-m2.5 \
  -m openrouter/z-ai/glm-5 \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.82 \
  --max-iterations 3 \
  --min-iterations 2 \
  --strategy role \
  --strategy-param "roles=The Drafter: Write the primary draft. Focus on flow, structure, and getting ideas on paper. Be bold and expressive." \
  --strategy-param "roles=The Editor: Rewrite for clarity, concision, and audience. Cut fluff. Fix logic gaps. Make every sentence earn its place." \
  --strategy-param "roles=The Fact-Checker and Style Guide: Verify all claims. Flag unsupported assertions. Ensure consistent tone and terminology."

# --- cns-role-dynamic: More models than roles — extras get random personalities ---
# Use case: maximum diversity with some structure + randomized perspectives
llm consortium save cns-role-dynamic \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/minimax/minimax-m2.5 \
  -m openrouter/z-ai/glm-5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 3 \
  --min-iterations 1 \
  --strategy role \
  --strategy-param use_dynamic_personalities=true


# ---------------------------------------------------------------------------
# 6. MULTIPLE INSTANCES PER MODEL
# ---------------------------------------------------------------------------

# --- cns-triple-qwen: 3x Qwen instances for self-consistency sampling ---
# Use case: math/reasoning where you want the same model to sample multiple paths
llm consortium save cns-triple-qwen \
  -m openrouter/qwen/qwen3.5-397b-a17b:3 \
  --arbiter gpt-oss-120b-groq \
  --confidence-threshold 0.9 \
  --max-iterations 2 \
  --min-iterations 1 \
  --strategy voting \
  --strategy-param similarity_threshold=0.6 \
  --strategy-param require_majority=true \
  --strategy-param answer_length=500

# --- cns-multi-instance: Mixed model counts — heavyweights x2, lightweights x1 ---
# Use case: weight heavier models by giving them more votes in the consortium
llm consortium save cns-multi-instance \
  -m openrouter/qwen/qwen3.5-397b-a17b:2 \
  -m openrouter/moonshotai/kimi-k2.5:2 \
  -m gpt-4.1-copilot:1 \
  -m openrouter/qwen/qwen3.5-122b-a10b:1 \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 3 \
  --min-iterations 1 \
  --strategy default


# ---------------------------------------------------------------------------
# 7. SYSTEM PROMPT CUSTOMIZATION
# ---------------------------------------------------------------------------

# --- cns-json-only: Force all members to respond in strict JSON ---
# Use case: structured data extraction, API-like outputs
llm consortium save cns-json-only \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  --arbiter gpt-oss-120b-groq \
  --confidence-threshold 0.85 \
  --max-iterations 2 \
  --min-iterations 1 \
  --strategy default \
  --system "You must respond ONLY with valid JSON. No markdown, no explanation, no prose. Your entire response must be parseable by json.loads(). Use the schema provided in the user prompt."

# --- cns-concise: Force brevity on all members ---
# Use case: quick answers, summaries, chat applications
llm consortium save cns-concise \
  -m openrouter/minimax/minimax-m2.5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  --arbiter gpt-oss-120b-groq \
  --confidence-threshold 0.75 \
  --max-iterations 1 \
  --min-iterations 1 \
  --strategy default \
  --system "Be extremely concise. Answer in 1-3 sentences maximum. No preamble, no caveats, no hedging. Get straight to the point."

# --- cns-expert-python: Python expert consortium ---
# Use case: Python coding assistance with domain expertise
llm consortium save cns-expert-python \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.88 \
  --max-iterations 3 \
  --min-iterations 1 \
  --strategy default \
  --system "You are a senior Python engineer with deep expertise in Python 3.12+, type hints, async/await, and modern tooling (ruff, uv, pytest). Write production-quality code. Prefer stdlib solutions. No unnecessary dependencies. Always include type annotations. Handle errors explicitly."


# ---------------------------------------------------------------------------
# 8. MANUAL CONTEXT MODE
# ---------------------------------------------------------------------------

# --- cns-manual-ctx: Manual context for cache-friendly long conversations ---
# Use case: multi-turn conversations where you want control over context
llm consortium save cns-manual-ctx \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 3 \
  --min-iterations 1 \
  --strategy default \
  --manual-context


# ---------------------------------------------------------------------------
# 9. COMBINED STRATEGIES — Realistic domain-specific configurations
# ---------------------------------------------------------------------------

# --- cns-legal-review: Legal document analysis with adversarial roles ---
# Use case: review contracts, identify risks, suggest amendments
llm consortium save cns-legal-review \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  -m openrouter/z-ai/glm-5 \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.9 \
  --max-iterations 4 \
  --min-iterations 2 \
  --strategy role \
  --strategy-param "roles=Party A's Counsel: Identify clauses favorable to Party A and risks to Party A. Suggest protective amendments." \
  --strategy-param "roles=Party B's Counsel: Identify clauses favorable to Party B and risks to Party B. Suggest protective amendments." \
  --strategy-param "roles=The Neutral Drafter: Propose balanced language that protects both parties equally. Focus on clarity and enforceability." \
  --strategy-param "roles=The Compliance Officer: Check for regulatory compliance issues, missing required clauses, and jurisdictional concerns."

# --- cns-medical-triage: Medical information with safety-focused voting ---
# Use case: health information where consensus matters for safety
llm consortium save cns-medical-triage \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  -m gpt-4.1-copilot \
  -m openrouter/z-ai/glm-5 \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.92 \
  --max-iterations 3 \
  --min-iterations 2 \
  --strategy voting \
  --strategy-param similarity_threshold=0.5 \
  --strategy-param require_majority=true \
  --strategy-param fallback_to_all=true \
  --strategy-param answer_length=3000 \
  --system "You are providing general health information (NOT medical advice). Always recommend consulting a healthcare professional. Cite established medical guidelines where possible. Err on the side of caution. Never minimize symptoms."

# --- cns-data-pipeline: Data engineering with elimination ---
# Use case: design ETL pipelines, eliminate weak suggestions
llm consortium save cns-data-pipeline \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  -m openrouter/qwen/qwen3.5-122b-a10b \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 4 \
  --min-iterations 2 \
  --judging-method rank \
  --strategy elimination \
  --strategy-param eliminate_count=1 \
  --strategy-param keep_minimum=2 \
  --strategy-param elimination_delay=1 \
  --system "You are a senior data engineer. Design for scale, idempotency, and observability. Prefer battle-tested tools (Airflow, dbt, Spark, Kafka). Consider data quality, schema evolution, and failure recovery in every design."

# --- cns-startup-pitch: Evaluate business ideas with diverse perspectives ---
# Use case: stress-test startup pitches, product ideas, go-to-market plans
llm consortium save cns-startup-pitch \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/minimax/minimax-m2.5 \
  -m gpt-4.1-copilot \
  -m openrouter/z-ai/glm-5 \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.8 \
  --max-iterations 3 \
  --min-iterations 2 \
  --strategy role \
  --strategy-param "roles=The VC Partner: Evaluate market size, defensibility, team risk, and unit economics. Be skeptical. What's the failure mode?" \
  --strategy-param "roles=The Customer: Would you actually use this? What's your willingness to pay? What alternatives exist? Be brutally honest." \
  --strategy-param "roles=The Operator: Can this actually be built and scaled? What are the operational nightmares? What's the hiring plan?" \
  --strategy-param "roles=The Competitor: How would an incumbent crush this? What moat could protect against fast-followers?"

# --- cns-incident-response: Production incident analysis ---
# Use case: RCA for outages, error log analysis, remediation planning
llm consortium save cns-incident-response \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m gpt-4.1-copilot \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 3 \
  --min-iterations 2 \
  --judging-method rank \
  --strategy elimination \
  --strategy-param eliminate_count=1 \
  --strategy-param keep_minimum=2 \
  --strategy-param elimination_delay=1 \
  --system "You are a senior SRE analyzing a production incident. Focus on: 1) Root cause identification from the evidence provided. 2) Immediate mitigation steps. 3) Preventive measures. Do NOT speculate beyond the evidence. If information is missing, say exactly what logs/metrics you need."

# --- cns-math-olympiad: Math competition problems with self-consistency ---
# Use case: competition math where correctness is binary
llm consortium save cns-math-olympiad \
  -m openrouter/moonshotai/kimi-k2.5:2 \
  -m openrouter/qwen/qwen3.5-397b-a17b:2 \
  -m gpt-oss-120b-groq:2 \
  -m gpt-4.1-copilot:1 \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.95 \
  --max-iterations 4 \
  --min-iterations 2 \
  --strategy voting \
  --strategy-param similarity_threshold=0.8 \
  --strategy-param require_majority=true \
  --strategy-param fallback_to_all=true \
  --strategy-param answer_length=100 \
  --system "Solve step by step. Show all work. State the final numerical answer clearly on its own line prefixed with 'ANSWER: '. Double-check your arithmetic."


# ---------------------------------------------------------------------------
# 10. EDGE CASES AND STRESS TESTS
# ---------------------------------------------------------------------------

# --- cns-single-model: Degenerate case — solo model with arbiter (is this useful?) ---
# Use case: testing, or when you only have one model but want structured output
# UX NOTE: The system allows this but it's odd — the arbiter "synthesizes" one response.
#          Should there be a minimum model count warning?
llm consortium save cns-single-model \
  -m gpt-4.1-copilot \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.7 \
  --max-iterations 1 \
  --min-iterations 1 \
  --strategy default

# --- cns-same-arbiter: Arbiter is also a consortium member ---
# Use case: when the best model should both contribute AND judge
# UX NOTE: No warning when arbiter is also a member. Is this intended? Could bias synthesis.
llm consortium save cns-same-arbiter \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.85 \
  --max-iterations 3 \
  --min-iterations 1 \
  --strategy default

# --- cns-high-min-iter: Minimum iterations equal to max ---
# Use case: force exactly N iterations regardless of confidence
# UX NOTE: Setting min == max forces exact iteration count. Useful but not documented.
llm consortium save cns-high-min-iter \
  -m openrouter/moonshotai/kimi-k2.5 \
  -m openrouter/qwen/qwen3.5-397b-a17b \
  -m gpt-oss-120b-groq \
  --arbiter openrouter/qwen/qwen3.5-397b-a17b \
  --confidence-threshold 0.99 \
  --max-iterations 3 \
  --min-iterations 3 \
  --strategy default

# --- cns-low-confidence: Very low threshold — accept first reasonable answer ---
# Use case: latency-sensitive applications where "good enough" is fine
llm consortium save cns-low-confidence \
  -m openrouter/minimax/minimax-m2.5 \
  -m gpt-4.1-copilot \
  --arbiter openrouter/qwen/qwen3.5-122b-a10b \
  --confidence-threshold 0.5 \
  --max-iterations 1 \
  --min-iterations 1 \
  --strategy default

echo ""
echo "========================================="
echo "  All cns-* configurations saved."
echo "  Run 'llm consortium list' to verify."
echo "========================================="

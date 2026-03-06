# UX Observations & Missing Functionality

Notes from creating 30+ consortium configurations across all strategies and modes.

---

## UX Issues Found

### 1. No validation that arbiter differs from members
**Severity**: Medium  
**Where**: `save` command and `create_consortium()`  
**Issue**: You can set `--arbiter openrouter/qwen/qwen3.5-397b-a17b` while also including that same model as a member (`-m openrouter/qwen/qwen3.5-397b-a17b`). There's no warning. This means the arbiter is judging its own output, which could bias synthesis.  
**Suggestion**: Warn (not block) when the arbiter is also a consortium member. Some users may want this intentionally, but most probably don't realize the implication.

### 2. Single-model consortium is silently accepted
**Severity**: Low  
**Where**: `save` command  
**Issue**: `llm consortium save cns-solo -m gpt-4.1-copilot --arbiter ...` works fine, but a 1-model consortium defeats the purpose — the arbiter just rephrases one response. No warning is shown.  
**Suggestion**: Warn when `len(models) < 2`. A consortium of one isn't really a consortium.

### 3. `--strategy-param` with `roles` is awkward on CLI
**Severity**: High (usability)  
**Where**: CLI `save` command  
**Issue**: Roles are lists of strings, but `--strategy-param` only supports `KEY=VALUE` format. To pass multiple roles you must repeat `--strategy-param "roles=The Security Auditor: ..."` multiple times. But looking at the parsing code:
```python
if '=' in param:
    k, v = param.split('=', 1)
    strategy_params[k.strip()] = v.strip()
```
This means each `roles=...` **overwrites** the previous one. Only the last role is saved!  
**Impact**: Role strategy via CLI is broken for custom roles unless the code handles list accumulation.  
**Fix needed**: Detect repeated keys and accumulate into a list, or use a syntax like `--strategy-param "roles=[role1, role2, ...]"`.

### 4. `eliminate_fraction` vs `eliminate_count` — no mutual exclusivity
**Severity**: Low  
**Where**: Elimination strategy  
**Issue**: You can set both `eliminate_count=2` and `eliminate_fraction=0.25`. The code appears to use `eliminate_count` if non-zero, ignoring fraction. This should be documented, or one should take precedence explicitly.

### 5. No way to list available strategies from CLI
**Severity**: Medium  
**Where**: CLI  
**Issue**: `--strategy` accepts any string. There's no `--help` hint showing valid strategies and no `llm consortium strategies` subcommand. A typo like `--strategy votting` fails silently at runtime.  
**Suggestion**: Add `llm consortium strategies` to list available strategies with descriptions.

### 6. No dry-run or validation mode
**Severity**: Medium  
**Where**: CLI / Python API  
**Issue**: There's no way to validate a configuration without running it. You can't check if models exist, if the arbiter is reachable, or if strategy params are valid until you actually orchestrate a prompt.  
**Suggestion**: Add `llm consortium validate <name>` or `--dry-run` flag.

### 7. No cost estimation
**Severity**: Medium  
**Where**: CLI / orchestrator  
**Issue**: Running 7 models for 5 iterations plus arbiter calls can be expensive. There's no way to estimate cost before running. The user has no visibility into how many tokens/API calls a configuration will make.  
**Suggestion**: Pre-run cost estimate based on model pricing and expected token counts.

### 8. Confidence threshold doesn't distinguish "confident wrong" from "confident right"
**Severity**: Low (design limitation)  
**Where**: Arbiter synthesis  
**Issue**: An arbiter can give 0.95 confidence on a wrong synthesis (all members hallucinated the same way). The confidence score reflects agreement, not correctness.  
**Suggestion**: Document this clearly. Consider adding a "self-consistency score" that measures diversity of reasoning paths, not just answer similarity.

### 9. `judging_method=rank` is required for elimination but not enforced
**Severity**: Medium  
**Where**: Elimination strategy  
**Issue**: Elimination strategy needs ranking data to decide which models to eliminate. If you use `judging_method=default`, the elimination strategy may not have ranking data and could fail silently or eliminate randomly.  
**Suggestion**: Auto-set or validate `judging_method=rank` when `strategy=elimination`.

### 10. No way to export/import configurations
**Severity**: Medium  
**Where**: CLI  
**Issue**: Configs are stored in SQLite. There's no `llm consortium export <name> > config.json` or `llm consortium import config.json`. Sharing configs between machines requires database manipulation.  
**Suggestion**: Add export/import as JSON or YAML.

### 11. No way to clone/duplicate a configuration
**Severity**: Low  
**Where**: CLI  
**Issue**: To create `cns-vote-strict-v2` as a variant of `cns-vote-strict`, you must retype the entire command. There's no `llm consortium clone cns-vote-strict cns-vote-strict-v2` or `llm consortium edit cns-vote-strict --max-iterations 5`.  
**Suggestion**: Add `clone` and `edit` subcommands.

### 12. `consortium list` output is not machine-readable
**Severity**: Low  
**Where**: CLI `list` command  
**Issue**: `llm consortium list` outputs human-readable text. There's no `--json` flag for programmatic use.  
**Suggestion**: Add `--json` to `list`, matching `llm` conventions.

### 13. No visibility into which models were eliminated
**Severity**: Medium  
**Where**: `run-info` command  
**Issue**: When using elimination strategy, the run-info output doesn't clearly show which models were eliminated at each iteration. You can infer from missing responses, but it should be explicit.  
**Suggestion**: Include elimination events in the iteration metadata.

### 14. No progress indicator during orchestration
**Severity**: Low (for interactive use)  
**Where**: CLI / orchestrator  
**Issue**: Long multi-iteration runs with many models can take minutes. There's no progress feedback (which iteration, which models are responding, etc.).  
**Suggestion**: Add a `--verbose` or `--progress` mode that streams status updates.

---

## Missing Functionality

### A. Strategy composition
Can't combine strategies (e.g., role assignment + voting + elimination). Each config gets exactly one strategy. A pipeline of strategies could be powerful.

### B. Model-specific system prompts via CLI
The Role strategy can assign per-model prompts, but there's no generic way to give different system prompts to different models outside of the role strategy. E.g., telling one model "focus on security" and another "focus on performance" without using the full role strategy machinery.

### C. Temperature/parameter control per model
No way to set `temperature`, `top_p`, or other model-specific parameters per consortium member. All models use whatever their defaults are. Higher temperature for diversity, lower for consistency — this is a natural consortium knob.

### D. Weighted model contributions
The only way to "weight" a model is to give it more instances. There's no explicit weight parameter that affects how the arbiter weighs responses.

### E. Conditional iteration
No way to express "iterate until models agree on X" or "stop if the answer contains Y". Convergence is purely confidence-based.

### F. Response caching / resumption
If a 5-iteration run fails at iteration 4 (e.g., rate limit), you lose everything. There's no checkpoint/resume mechanism.

### G. A/B testing configurations
No built-in way to run the same prompt through two different consortium configs and compare results.

### H. Streaming output
The orchestrator blocks until all models respond. For interactive use, streaming partial results would improve perceived latency.

---

## What Works Well

- **Strategy abstraction**: Adding new strategies is clean — just subclass `ConsortiumStrategy`.
- **Prompt engineering**: The arbiter/iteration prompts are well-crafted with structured XML output.
- **Model:count syntax**: `model:3` for multiple instances is intuitive.
- **Auto-scaling confidence**: Accepting 0-100 or 0-1 and auto-normalizing is user-friendly.
- **Rank judging method**: The truthfulness-focused ranking prompt is excellent for factual queries.
- **Role personalities**: The random personality matrix is a creative approach to forced diversity.

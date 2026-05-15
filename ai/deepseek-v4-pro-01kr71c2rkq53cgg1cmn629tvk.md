# LLM Consortium Codebase Review & Next Actions

## Project Summary
**LLM Consortium** (v0.8.0) is a well-architected plugin for Simon Willison's `llm` CLI tool that orchestrates multiple LLMs through structured consensus-building. It implements multiple strategies (default, voting, elimination, role, semantic, cache-aware), embedding-based clustering, and SQLite-backed tracing. The codebase is clean, with strong use of the Strategy pattern, factory functions, and proper separation of concerns.

---

## Critical / High Priority Actions

### 1. Complete Real-Provider Evaluation
The evaluation suite in `evals/` exists but hasn't been validated against real model providers. Both `TODO.md` and `NOTES-semantic-filtering.md` flag this as the key remaining validation step.

**Action:** Run `benchmark_runner.py` → `blind_judge.py` → `analyze_results.py` pipeline against real providers (OpenAI, Anthropic, Chutes) to establish whether semantic filtering actually improves answer quality over the default strategy.

```bash
python evals/benchmark_runner.py \
    --prompts evals/prompts.json \
    --models "gpt-4o:3,claude-3-5-sonnet:3" \
    --arbiter gpt-4o \
    --output evals/results.json
```

### 2. Add Configuration Validation Command
There's no way to validate a consortium configuration without running it. The UX observations doc flags this as a medium-severity gap.

**Action:** Implement `llm consortium validate <name>` that checks:
- Models exist and are reachable (lightweight connectivity check)
- Arbiter is reachable
- Strategy parameters are valid for the chosen strategy
- Model count ≥ 2 (warn if single-model)

### 3. Finish Streaming Arbiter
`TODO.md` lists streaming arbiter support as pending. The arbiter is often the bottleneck in multi-iteration runs.

**Action:** Implement streaming in `ConsortiumModel.execute()` so arbiter synthesis tokens appear incrementally rather than blocking until complete.

### 4. Fix Documented UX Issues
`cns-ux-observations.md` documents 15 issues. The most impactful unresolved ones:

| # | Issue | Severity | Action |
|---|-------|----------|--------|
| 1 | No validation when arbiter is also a member | Medium | Add warning in `save` command |
| 6 | No dry-run/validation mode | Medium | Implement `validate` subcommand |
| 7 | No cost estimation | Medium | Add pre-run token/cost estimate |
| 10 | No export/import configurations | Medium | Add `export`/`import` subcommands |
| 13 | Elimination visibility in run-info | Medium | Show eliminated models per iteration |

### 5. Resolve Code Duplication
The `consortium.py` file contains `_synthesize_responses_automatic()` and related methods that overlap significantly with `orchestrator.py`. This looks like a partial refactoring that wasn't completed.

**Action:** Determine if `consortium.py` is dead code or in-progress refactoring. If dead, remove it. If it's the intended replacement path, finish the migration and remove the duplicates from `orchestrator.py`.

---

## Medium Priority Actions

### 6. Add `--json` Flag to `consortium list`
The UX doc notes this as low severity but it's a quick win that enables programmatic config management.

### 7. Add Config Clone/Edit Commands
`llm consortium clone cns-vote-strict cns-vote-strict-v2` and `llm consortium edit cns-vote-strict --max-iterations 5` would significantly improve the iteration workflow when tuning configurations.

### 8. Progress Indicator During Orchestration
Multi-iteration runs with many models can take minutes with zero feedback. A simple `--verbose` mode showing iteration count, models responding, and confidence progression would improve UX dramatically.

### 9. Document Confidence Score Limitations
Both the UX doc (#8) and README acknowledge that arbiter confidence measures agreement, not correctness. This should be prominently documented to prevent misuse.

**Action:** Add a clear callout:
> ⚠️ Confidence scores reflect inter-model agreement, not verification of factual correctness. High confidence can occur when all models hallucinate the same way.

### 10. Cost Estimation
Users running 7 models × 5 iterations + arbiter calls have no visibility into API costs. A pre-run estimate (even approximate) would build trust.

---

## Low Priority / Nice to Have

### 11. Strategy Composition Pipeline
The UX doc notes this as missing. Users can't chain strategies (e.g., role assignment → voting → elimination). This would require a significant architectural change to support strategy pipelines rather than a single strategy.

### 12. Per-Model Temperature/Parameter Control
No way to set `temperature`, `top_p`, etc. per consortium member. This is a natural consortium knob (high temp for diversity, low for consistency) but requires extending the config schema and CLI.

### 13. HDBSCAN Optimization
`TODO.md` notes HDBSCAN parameter tuning for small sample sizes. The semantic strategy currently falls back to DBSCAN but the HDBSCAN path could be better for the N<10 typical consortium size.

### 14. Response Caching / Checkpointing
If a 5-iteration run fails at iteration 4 (rate limit), everything is lost. Checkpoint/resume would be valuable for expensive orchestration runs.

### 15. Revisit Visualization (with PCA)
`NOTES-semantic-filtering.md` explains why t-SNE was removed (mathematically invalid for N<10). PCA with proper bounding boxes could be a valid replacement for visualizing response drift across iterations.

---

## Architectural Observations

**Well-designed patterns:**
- Strategy ABC with `select_models()`, `process_responses()`, `update_state()` lifecycle
- Factory-based strategy creation with dynamic import fallback
- Clean embedding backend abstraction (OpenAI, SentenceTransformers, Chutes)
- Thread-safe DB connection with proper commit discipline
- Cache-aware execution for DeepSeek-style prompt caching

**Areas needing attention:**
- `ConsortiumModel.execute()` in `models.py` does too much: conversation history extraction, config patching, fallback logic, and result parsing. Consider extracting a `ResponseFormatter` or `ConversationAdapter` class
- Manual vs automatic context modes create near-duplicate code paths in the orchestrator (`_orchestrate_manual` vs `_orchestrate_automatic`, `_synthesize_responses_manual` vs `_synthesize_responses_automatic`)
- No visible test coverage information in the provided docs
- `consortium.py` appears to be a partially-refactored version of orchestrator logic

---

## Recommended Implementation Sequence

1. **This week:** Run real-provider evaluation, fix `consortium.py` duplication
2. **Next sprint:** Configuration validation + export/import commands  
3. **Following:** Streaming arbiter + progress indicator + `--json` list
4. **Later:** Cost estimation, confidence documentation, clone/edit commands
5. **Backlog:** Strategy composition, per-model parameters, HDBSCAN tuning, checkpointing

Release 2025.02.01
- Merge branch 'feature/n-species'
- Update to version 0.4: Add new features and update documentation
- cleanup: removed temporary database, script and log files
- Remove .artefacts from Git tracking and add to .gitignore
- Update cfr-example.md
- Implement asynchronous response logging and improve error handling
- Remove backup file for model consortium implementation
- feat: Integrate consortium model capabilities with logging and documentation updates

Release 2025.02.02
- Update to version 0.5:
  - Introduced the `model:count` syntax for specifying the number of instances for each model in the consortium (primarily for the Python API; the CLI uses `-m model -n count`).
  - Improved consortium configuration management to support instance counts.
  - Enhanced logging to track model instances and their responses more effectively.
  - **Performance Enhancement:** Implemented parallel processing for improved consortium execution speed.

Release 2025.02.23
- Update to version 0.7:
  - **New CLI Commands**: Added `leaderboard`, `runs`, `export-training`, and `run-info`.
  - **Consortium Strategy**: Implemented `VotingStrategy` for consensus-based selection and `EliminationStrategy` for adaptive model selection.
  - **Tracing & DB Logging**: Implemented a comprehensive prompt tracing system with SQLite database storage and CLI inspection. Refactored `EvaluationStore` using `sqlite-utils`.
  - **Context Management Improvements**: Refactored orchestration to explicitly support `manual` and `automatic` context modes, deprecating older conversation managers.
  - **Prompting Improvements**: Migrated internal prompt templates to XML formats (`system_prompt.xml`, `arbiter_prompt.xml`, `iteration_prompt.xml`, etc.) and refined rank-prompt criteria for truthfulness and reality grounding.
  - **Housekeeping**: Deprecated obsolete files and validation scripts, consolidated gitignores, aligned test suite with new API, and added token usage aggregation.

Release 2026.03.06 (Version 0.8.0)
- Semantic embedding and geometric consensus work:
  - Added embedding backend abstraction with strict interfaces for OpenAI, sentence-transformers, and Chutes `qwen3-embedding-8b` support (fails loudly on backend errors).
  - Added `SemanticClusteringStrategy` with DBSCAN, HDBSCAN fallback handling, and tropical centroid support.
  - Added persistence for response embeddings, consensus clusters, centroid vectors, and geometric confidence.
  - Demoted geometric confidence to observational telemetry (recorded in `arbiter_decisions` but not used for arbitration routing).
  - Added CLI/config support for `--embedding-backend`, `--embedding-model`, `--clustering-algorithm`, `--cluster-eps`, and `--cluster-min-samples`.
  - Removed unstable embedding visualizations and dummy fallback mechanisms following architectural review (see `NOTES-semantic-filtering.md`).
  - Added `llm consortium strategies` and fixed repeated `--strategy-param` accumulation for list-style parameters such as repeated role definitions.
  - Enforced `judging_method=rank` when `strategy=elimination`.
  - Fixed run summary persistence so `iteration_count` and `final_confidence` are updated after orchestration.
  - Validation status: full test suite passing locally; live Chutes embedding smoke test successful; real provider-backed answer-quality demonstration pending further evaluation.


## [Unreleased] - Cache Max Strategy & Code Cleanup

### Added
- **`cache_max` strategy**: Maximizes provider prefix-cache hits by using a static prefix (system prompt + original prompt) for all member and arbiter requests, with dynamic content appended as suffix. Includes arbiter pre-warming.
- **Parser-contract regression tests**: Comprehensive tests ensuring `_parse_arbiter_response` handles all prompt template variations correctly.
- **Live A/B eval harness** (`evals/ab_cache_eval.py`): Side-by-side comparison of cache strategies measuring provider-reported cache telemetry.
- **32 tests for cache_max strategy**: Coverage for pre-warming, prefix construction, and cache telemetry parsing.

### Fixed
- **Critical**: Missing `_read_rank_cot_prompt()` function caused `NameError` when using `rank-cot` judging method.
- **Cache_max**: Aligned arbiter prompt tags with `_parse_arbiter_response` expectations.
- **Cache_max**: Read cache telemetry from `response.json()` (llm API) instead of response attributes.
- **Cache_max**: Hardened prewarm logic and stopped learning-loop pollution from prewarm requests.
- **Studio**: React Studio now runs with npm on Python 3.14.
- **Code quality**: Resolved all 42 pyflakes issues — removed 14 unused imports, deleted dead `consortium.py` (112 lines), fixed 3 f-strings without placeholders.

### Changed
- Removed cache-block padding from cache_max strategy (simpler approach with better cache alignment).
- Removed VPS deploy/sync scripts from public repo.


## [Released 2026.08.12] - Enhanced Judge Modes

### Added
- **`rank-cot` judging method**: Combines ranking with chain-of-thought evaluation. The arbiter evaluates each response against structured criteria (truthfulness, accuracy, depth, completeness), provides per-model guidance, and selects the best response.
- **`skip_intermediate_synthesis`**: When enabled, the arbiter skips full synthesis during intermediate iterations and instead provides evaluation + per-model guidance. This saves tokens and focuses on improvement. A full synthesis is produced on the final iteration or when the arbiter is confident.
- **Per-model guidance**: The arbiter can now generate specific, actionable feedback for each consortium member model, which is fed back via the strategy's `prepare_iteration_prompt` in subsequent iterations.
- **`--no-per-model-guidance` CLI flag**: Disables per-model guidance when using skip-intermediate-synthesis (uses shared guidance instead).

### Changed
- `_prepare_arbiter_prompt` now accepts an `iteration` parameter to determine if this is a forced-final iteration.
- Iteration loops check for deferred synthesis (`[DEFERRED]`) and force one more iteration if needed.
- `arbiter_prompt.xml` includes optional `<model_guidance>` output section.
- Default strategy's `prepare_iteration_prompt` now uses per-model guidance when available.
- `ConsortiumConfig` normalizes `judging_method` to preserve dashes (e.g., `rank-cot`).

### New Files
- `llm_consortium/rank_cot_prompt.xml` - Prompt template for chain-of-thought ranking evaluation.
- `tests/test_enhanced_judge_modes.py` - 20 tests covering rank-cot parsing, model guidance parsing, skip-synthesis config, and normalization.

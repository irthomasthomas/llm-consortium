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
  - Added embedding backend abstraction with OpenAI, sentence-transformers, deterministic fallback embeddings, and Chutes `qwen3-embedding-8b` support.
  - Added `SemanticClusteringStrategy` with DBSCAN, HDBSCAN fallback handling, and tropical centroid support.
  - Integrated geometric confidence and centroid persistence into arbiter synthesis.
  - Added persistence for response embeddings, consensus clusters, centroid vectors, geometric confidence, and cached visualization JSON.
  - Added Plotly/t-SNE run visualization export via `llm consortium visualize-run`.
  - Added CLI/config support for `--embedding-backend`, `--embedding-model`, `--clustering-algorithm`, `--cluster-eps`, and `--cluster-min-samples`.
  - Added `llm consortium strategies` and fixed repeated `--strategy-param` accumulation for list-style parameters such as repeated role definitions.
  - Enforced `judging_method=rank` when `strategy=elimination`.
  - Fixed run summary persistence so `iteration_count` and `final_confidence` are updated after orchestration.
  - Fixed visualization persistence so exporting a run does not overwrite existing consortium run metadata.
  - Validation status: full test suite passing locally; live Chutes embedding smoke test successful; real provider-backed answer-quality comparison still pending.

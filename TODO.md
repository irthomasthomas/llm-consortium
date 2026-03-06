# TODO

## Completed
- [x] **Restore Strategy Implementations**: `VotingStrategy`, `EliminationStrategy`, and `SemanticClusteringStrategy` are fully integrated.
- [x] **Relational Schema**: Migrated to a robust relational schema for runs, members, and decisions.
- [x] **Packaging Update**: Bumped to v0.8.0, added optional extras for `embeddings`, `visualize`, and `dev`. (2026-03-06)
- [x] **CLI Enhancements**: Re-enabled `runs`, `run-info`, and added `visualize-run`.

## Pending / Future Work
- [ ] **Real Provider-Backed Comparison**: Conduct evaluations with real model providers to assess answer quality across strategies.
- [ ] **Streaming Arbiter**: Implement streaming support for the arbiter's synthesis response in `ConsortiumModel.execute`.
- [ ] **Automatic Strategy Parameter UI**: Improve CLI to better discover and validate strategy-specific parameters.
- [ ] **HDBSCAN Optimization**: Tune HDBSCAN parameters and fallback logic for better clustering on small sample sizes.

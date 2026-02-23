# TODO

## Restore Strategy Implementations

- **Context**: The `VotingStrategy` and `EliminationStrategy` classes are fully implemented in `llm_consortium/strategies/` and have verified tests. However, the current API entry point `create_consortium` inside `llm_consortium/__init__.py` no longer utilizes or accepts a `strategy` string.
- **Action Items**:
  1. Update `ConsortiumConfig` to accept a `strategy` parameter and `strategy_params`.
  2. Instantiate the corresponding strategy via the `StrategyFactory` inside `ConsortiumOrchestrator.__init__` or `create_consortium`.
  3. Re-wire `ConsortiumOrchestrator.orchestrate` to use the instantiated strategy's `select_models` and `process_responses` methods during iteration iterations instead of the hardcoded default behavior.
  4. Once restored, update `API.md` to reflect the available strategies (`voting`, `elimination`, `default`) and their configuration options.

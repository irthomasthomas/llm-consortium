# Context Pack: llm-consortium-main
**Generated**: 2026-03-05
**Branch**: experimental
**Head Commit**: Finalized Strategy Restoration

---

## Repository Purpose

LLM Consortium is a plugin for Simon Willison's `llm` CLI tool that implements **multi-model orchestration** with iterative refinement. It coordinates multiple LLMs to collaboratively solve problems through structured dialogue, evaluation, and arbitration.

**Core Philosophy**: "Coming up with a solution is harder than verifying one" - ask all models, then arbitrate consensus.

---

## Status: Refactor Complete

### Status Summary
The major refactor to extract logic into `models.py`, `orchestrator.py`, and `cli.py` is complete. The strategy system (`VotingStrategy`, `EliminationStrategy`, `RoleStrategy`) has been fully restored and integrated into the new architecture.

### Core Modules
- `llm_consortium/__init__.py` - Main entry point and plugin registration.
- `llm_consortium/db.py` - Database logic and relational schema.
- `llm_consortium/cli.py` - CLI commands (under `llm consortium`).
- `llm_consortium/models.py` - Pydantic configurations and `ConsortiumModel`.
- `llm_consortium/orchestrator.py` - Pure orchestration logic and `create_consortium` factory.
- `llm_consortium/strategies/` - Strategy pattern implementations.
- `tests/` - Updated test suite covering integration and strategies.

---

## Architecture Overview

```
llm_consortium/
├── __init__.py          # Main entry point (Consortium class)
├── cli.py               # NEW: CLI handling
├── models.py            # NEW: Data models
├── orchestrator.py      # NEW: Orchestration logic
├── consortium.py        # Core consortium logic
├── db.py                # Database operations (SQLite)
├── conversation_manager.py
├── evaluation_store.py
├── logger.py
├── tracing.py
├── strategies/          # Strategy pattern implementations
│   ├── base.py          # Abstract base
│   ├── default.py
│   ├── elimination.py   # EliminationStrategy
│   ├── voting.py        # VotingStrategy
│   ├── role.py          # RoleStrategy
│   └── factory.py       # Strategy factory
├── *.xml                # Prompt templates (arbiter, rank, iteration, system)
└── tests/
```

---

## Strategy System

| Strategy | Description |
|----------|-------------|
| DefaultStrategy | Basic response collection |
| VotingStrategy | Democratic voting among models |
| EliminationStrategy | Iteratively eliminate weakest responses |
| RoleStrategy | Assign roles to different models |

---

## Recent Commit History

| Commit | Description |
|--------|-------------|
| 6e6dcf2 | HEAD: Refactor DB logic into db.py, add storage tests |
| feaa2da | Migrate role strategy from recovery branch |
| af6a6c4 | Cleanup cruft, update docs, add TODO |
| ad1db89 | Improve rank prompt for truthfulness |
| c306122 | Align test suite (60/60 green) |
| 2ffcd64 | Merge VotingStrategy, EliminationStrategy |

---

## Key Technical Details

1. **Database**: SQLite-backed via db.py - stores all interactions
2. **Prompts**: XML templates for arbitration, ranking, iteration
3. **Model Instance Syntax**: model:count (e.g., gpt-4o:2 for 2 instances)
4. **Conversation Continuation**: -c / --cid flags like standard llm
5. **Confidence Thresholds**: Iterative refinement until threshold met

---

## TODO for Next Agent

1. **Verify Test Suite** - Ensure all integration and strategy tests are still green (last check was 60/60).
2. **Commit Changes** - Finalize the experimental branch work by committing the refactored modules.
3. **Documentation Review** - Ensure README and other documents align with the new Pydantic-based configuration.

---

## File References

- README.md: Installation, usage examples
- API.md: API documentation
- TODO.md: Outstanding tasks
- CHANGELOG.md: Version history
- examples/: Demo scripts for each strategy

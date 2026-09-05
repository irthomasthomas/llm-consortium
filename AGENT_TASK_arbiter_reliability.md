# AGENT TASK: llm-consortium — Arbiter Reliability & Run-Finalization Fixes

Repo: /home/thomas/Projects/llm/plugins/Utilities/llm-consortium/llm-consortium-main (branch: main)
This brief contains a completed forensic analysis. Trust the facts below — they were
verified against the live DBs and executing source on 2026-08-25. Do not re-derive them.

## CRITICAL ENVIRONMENT FACTS (verified)
- The `llm` CLI runs the REPO code, not a separate install: editable install finder
  `/home/thomas/.local/lib/python3.14/site-packages/__editable___llm_consortium_0_8_2_finder.py`
  maps `llm_consortium` -> this repo's `llm_consortium/` dir. Edits here take effect
  on next `llm` invocation; no reinstall needed.
- Ignore `/home/thomas/.local/lib/python3.13/site-packages/llm_consortium/` — stale Aug-2025
  copy, not on the import path (verify with: `cd /tmp && python -c "import llm_consortium; print(llm_consortium.__file__)"`).
- Logs: `/home/thomas/.config/io.datasette.llm/consortium_logs.db` (plugin tables)
  and `/home/thomas/.config/io.datasette.llm/logs.db` (final user-facing responses).
  Plugin log: `/home/thomas/.config/io.datasette.llm/consortium.log`.
- Reference failure run: id `d114fff4-b8f6-40b1-ab5f-e88c98bada9c`,
  config `cns-role-craft-glm-5.3-v-ox-alpha` (models ox-alpha + glm-5.2-coding,
  arbiter deepseek-v4-pro, strategy=role, threshold 0.90, max_iterations 2).
  Final user-facing response in logs.db: `01m0tzc5rdehzmhspmmc4z31yd`.

## ROOT CAUSES (verified, with file:line in llm_consortium/)

### 1. Arbiter ignores the XML output contract; parser silently degrades
- `arbiter_system.xml` demands a `<synthesis_output>` block with <synthesis>,
  <confidence>, <needs_iteration>, <ranking><rank position="1">ID</rank>…, etc.
- deepseek-v4-pro (a reasoning model) emitted 21k chars of native `reasoning` plus a
  pure-markdown "## Candidate Analysis" essay — zero tags. BOTH iterations.
- `orchestrator.py:_parse_arbiter_response()` (~line 859) defaults on no-match to
  `synthesis=<entire raw text>`, `confidence=0.0`, `needs_iteration=False`,
  `ranking=[]`, `chosen_response_id=None`. No error, no retry, no warning.
- Consequences for the reference run:
  a) confidence 0.0 < 0.90 threshold => convergence check never fires => both
     iterations burned (12.9 min, ~57k output tokens).
  b) `strategies/role.py:prepare_iteration_prompt()` embeds `iteration_history[-1]
     .synthesis.synthesis` into iteration-2 member prompts => members received the
     arbiter's judge-notes ("Response 650 is preferred...") as their "previous
     synthesis". glm wrote a self-referential errata reply instead of an answer.
  c) `models.py:execute()` (~lines 200-220) detects fallback (`parsed == raw`) and
     INTENTIONALLY returns the raw arbiter text => the user's final answer was the
     meta-analysis comparing members, never an actual answer.
- SYSTEMIC: 1,314/1,615 arbiter_decisions have empty ranking; 472 have confidence
  0.0; 434/995 `default`-judging runs ended final_confidence 0.0. `learning.py`
  (line ~63: `WHERE ad.chosen_response_id IS NOT NULL`) is starved of data by every
  default-method parse failure.

### 2. Run status never finalizes — "running" forever
- `models.py` line 41: `status: Optional[str] = None` (never set to "running").
- `orchestrator.py` lines 223 and 411 (both `_orchestrate_manual` and
  `_orchestrate_automatic`):
  `status=self.config.status if self.config.status != "running" else (...)`
  Since status is None, `None != "running"` is True => passes None =>
  `db.py:update_consortium_run()` (line ~170) takes the no-status branch and skips
  the UPDATE of status. iteration_count IS written (proves the update ran).
- DB evidence: 893 runs stuck 'running', 201 with NULL status, zero-ever 'success'
  from the default path. 19 'model_failure' rows exist only from the break path
  (orchestrator lines 179/367 assign config.status directly).

### 3. Arbiter is blind to strategy roles
- `_prepare_arbiter_prompt` does not include member role/system-prompt info, so with
  strategy=role the arbiter penalised glm-5.2-coding for "assuming a performance
  review was requested" — which is exactly what the Performance Engineer role
  mandated. Reference run iter-1 and iter-2 both did this.

## WORK TO DO (priority order)

### Fix A — Enforce/repair arbiter output contract
1. Preferred: structured output. `schemas` table already exists in consortium_logs.db;
   build a JSON schema for the decision (synthesis, confidence, needs_iteration,
   refinement_areas[], ranking[] as numeric IDs, analysis, dissent, model_guidance)
   and use llm's schema support for the arbiter call when the backend supports it.
2. Fallback for backends without schemas: one repair-retry. In
   `_synthesize_responses_*`, if parse result is the raw-fallback shape (no
   <synthesis> tag found / parsed == raw / no ranking), resend ONCE with an appended
   message: "Your previous reply did not use the required format. Reply ONLY with
   the <synthesis_output> block." Log both attempts.
3. Template hardening in `arbiter_system.xml`: drop the "Wrap your thought process
   inside <thinking> tags" instruction for reasoning arbiters (it conflicts with
   native reasoning channels and invites essays); put the output-format spec FIRST
   and last; state "Do not use Markdown headings in place of the XML tags."
   Consider a per-arbiter model check (e.g. options_json reasoning flag) to select
   the variant.
4. Add `parse_success: bool` to the parsed result and persist it in
   arbiter_decisions.decision_json.

### Fix B — status finalization
- In both orchestrate paths: `status=self.config.status or ("empty_synthesis" if not
  synthesis_dict.get("synthesis") else "success")` — or set
  `self.config.status = "running"` when the run starts. Ensure DB always ends
  success/empty_synthesis/model_failure/embedding_failure/aborted.

### Fix C — never propagate raw fallback text
- In `strategies/role.py:prepare_iteration_prompt()` (and the base strategy + any
  other strategy with the same pattern — check strategies/*.py) guard
  `prev_synth`: if it equals the raw fallback (parse_success False), substitute
  `[DEFERRED]` or the analysis/refinement_areas instead.
- In `models.py:execute()` fallback branch: return the best MEMBER response
  (ranking[0] if available else first valid response) rather than raw arbiter
  meta-analysis; keep the raw text in response_json for debugging.

### Fix D — arbiter sees strategy context
- `_prepare_arbiter_prompt`: include each member's assigned role label
  (strategy.get_instance_system_prompt / assigned_roles) in the formatted_responses
  section, e.g. `<response id="650" model="glm-5.2-coding" role="The Performance
  Engineer">`. Cheap, improves judging fairness for role/perspectives strategies.

### Fix E — distinguish missing vs low confidence
- Parser returns confidence=None when no <confidence> tag (instead of 0.0). Treat
  None as "parse failure -> repair path", 0.0 as genuine stated-low confidence.
  Keep `float(... or 0.0)` at persistence boundaries so DB stays NOT NULL.

### Fix F — maintenance CLI
- New `llm consortium runs --sweep [--dry-run]`: mark rows with status='running'
  older than N hours as 'aborted' (check last arbiter_decisions/responses timestamp
  for the run). Also a `--backfill-parse-success` that recomputes parse_success for
  historical decisions from decision_json/raw response.

### Fix G — logging polish (small)
- `save_consortium_member` stores MODEL NAME in the role column; store the strategy
  role label too (add a column or store "model|role" — prefer a new
  `strategy_role` column via migration in db.py's schema-bootstrap path).
- The repo has an old crash signature in consortium.log from a May worktree venv
  (`'ConsortiumOrchestrator' object has no attribute 'config'`) — that path is dead
  code now; ignore it, do NOT chase it.

## CONSTRAINTS
- Do not break `judging_method='rank'` or 'rank-cot' paths (`_parse_rank_response`
  raises on missing ranking — good pattern to reuse).
- CacheMax/arbiter_shared_prefix prompt layout must stay byte-stable for prefix
  caching: put any new instruction text in the SYSTEM prompt or the dynamic suffix,
  never before the static prefix (see comments in `_prepare_arbiter_prompt`).
- Tests live in tests/ (pytest). Run: `python -m pytest tests/ -x -q` from repo root.
  There is a Makefile and .venv; prefer `.venv/bin/python -m pytest` if deps live there.
- Member prompts embed `<documents>` XML for this workload; don't reformat member
  prompt bodies.

## ACCEPTANCE TESTS (write these)
1. Unit: `_parse_arbiter_response` on the actual raw markdown from decision_json of
   run d114fff4 iteration 1 (fetch it: `sqlite3 consortium_logs.db "select
   decision_json from arbiter_decisions where run_id='d114fff4-...' and iteration=1"`)
   must yield parse_success=False and trigger exactly one repair retry in the
   synthesizer (mock the arbiter model; second call returns valid XML).
2. Unit: orchestrate with mocked models + always-markdown arbiter => final run status
   in DB is 'success' (not 'running'), and the user-facing text is a MEMBER response,
   not the arbiter's notes.
3. Unit: iteration-2 member prompt contains NO arbiter meta text when parse failed.
4. DB integration: run a real small consortium twice (one clean, one forced-bad via
   monkeypatched arbiter) and assert statuses success/aborted semantics.
5. Sweep: `llm consortium runs --sweep --dry-run` on the real DB reports the 893+
   rows and would touch nothing else; `--execute` marks them 'aborted'.

## DELIVERABLE
- Working code + tests green + short SUMMARY of diffs. Optionally re-run the user's
  original consortium command as a smoke test (costs tokens — ask first).

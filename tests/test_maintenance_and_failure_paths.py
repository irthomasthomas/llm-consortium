"""Acceptance tests: DB status finalization, raw-fallback containment, sweep
CLI, and parse-success backfill."""
import json
import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from llm_consortium.cli import _sweep_stale_runs, _backfill_parse_success
from llm_consortium.db import DatabaseConnection, user_dir, save_consortium_run, update_consortium_run, save_arbiter_decision
from llm_consortium.orchestrator import create_consortium


def _mkdb(tmpdir):
    import threading
    DatabaseConnection._thread_local = threading.local()
    import llm_consortium.db as dbmod
    dbmod.user_dir = lambda: pathlib.Path(tmpdir)
    db = DatabaseConnection.get_connection()
    # minimal responses table for FK-joining sweep queries
    db.execute("""CREATE TABLE IF NOT EXISTS responses (
        id TEXT PRIMARY KEY, model TEXT, response TEXT, datetime_utc TEXT)""")
    db.conn.commit()
    return db


def _good_decision(ranking=(1, 2)):
    return {
        "synthesis": "final answer text",
        "confidence": 0.9,
        "analysis": "ok",
        "needs_iteration": False,
        "refinement_areas": [],
        "ranking": list(ranking),
        "parse_success": True,
    }


def _bad_decision(raw="## Candidate Analysis markdown essay"):
    return {
        "synthesis": raw,
        "confidence": None,
        "analysis": "Parse failure: no JSON object found",
        "needs_iteration": False,
        "refinement_areas": [],
        "ranking": [],
        "parse_success": False,
        "raw_arbiter_response": raw,
    }


class TestOrchestrateWithMarkdownArbiter(unittest.TestCase):
    """Acceptance test 2+3: always-markdown arbiter => status finalized,
    user-facing text is a MEMBER response, iteration-2 prompts clean."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = _mkdb(self.tmp)

    def _run(self, max_iterations=2):
        mock_member1, mock_member2, mock_arbiter = MagicMock(), MagicMock(), MagicMock()
        m1 = MagicMock(); m1.text.return_value = "MEMBER ONE ANSWER"; m1.id = "m1"
        mock_member1.prompt.return_value = m1
        m2 = MagicMock(); m2.text.return_value = "MEMBER TWO ANSWER"; m2.id = "m2"
        mock_member2.prompt.return_value = m2
        arb = MagicMock(); arb.id = "arb1"
        arb.text.return_value = "## Candidate Analysis\nResponse 650 is preferred..."  # always markdown
        mock_arbiter.prompt.return_value = arb

        def side_effect(mid):
            return {"member1": mock_member1, "member2": mock_member2,
                    "arbiter_model": mock_arbiter}.get(mid, MagicMock())
        orch = create_consortium(
            models=["member1:1", "member2:1"], arbiter="arbiter_model",
            confidence_threshold=0.9, max_iterations=max_iterations,
            minimum_iterations=1, manual_context=True, judging_method="default",
        )
        prompts_seen = []
        orig = orch._get_single_model_response_manual
        def spy(model_id, prompt, instance, iteration):
            prompts_seen.append(prompt)
            return orig(model_id, prompt, instance, iteration)
        orch._get_single_model_response_manual = spy
        with patch("llm_consortium.orchestrator.llm.get_model", side_effect=side_effect):
            result = orch.orchestrate("what is the answer?")
        return orch, result, prompts_seen, mock_arbiter

    def test_status_and_member_fallback(self):
        orch, result, prompts, mock_arbiter = self._run(max_iterations=2)
        db = DatabaseConnection.get_connection()
        rows = list(db["consortium_runs"].rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "arbiter_parse_failure")
        self.assertEqual(mock_arbiter.prompt.call_count, 4)  # 2 iters x 2 calls (retry)
        # user-facing text: ranking empty => first member response
        from llm_consortium.models import ConsortiumModel
        cm = ConsortiumModel.__new__(ConsortiumModel)
        text = cm._final_user_text(result)
        self.assertEqual(text, "MEMBER ONE ANSWER")

    def test_iteration2_prompts_have_no_meta(self):
        orch, result, prompts, _ = self._run(max_iterations=2)
        iter2 = prompts[2:]  # two members per iteration
        for p in iter2:
            self.assertNotIn("Candidate Analysis", p)
            self.assertNotIn("650", p)


class TestSweepCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = _mkdb(self.tmp)

    def test_sweep_marks_stale_only(self):
        save_consortium_run("stale1", "default", "default", 0.8, 3, 1, 0.5, "q", status="running")
        save_consortium_run("stale2", "default", "default", 0.8, 3, 1, 0.5, "q", status=None)
        save_consortium_run("fresh", "default", "default", 0.8, 3, 1, 0.5, "q", status="running")
        # backdate the stale ones
        self.db.conn.execute("UPDATE consortium_runs SET created_at = datetime('now','-2 days') WHERE id IN ('stale1','stale2')")
        self.db.conn.commit()
        _sweep_stale_runs(self.db, 6, dry_run=False)
        statuses = {r["id"]: r["status"] for r in self.db["consortium_runs"].rows}
        self.assertEqual(statuses["stale1"], "aborted")
        self.assertEqual(statuses["stale2"], "aborted")
        self.assertEqual(statuses["fresh"], "running")

    def test_dry_run_touches_nothing(self):
        save_consortium_run("s1", "default", "default", 0.8, 3, 1, 0.5, "q", status="running")
        self.db.conn.execute("UPDATE consortium_runs SET created_at = datetime('now','-2 days')")
        self.db.conn.commit()
        _sweep_stale_runs(self.db, 6, dry_run=True)
        row = list(self.db["consortium_runs"].rows)[0]
        self.assertEqual(row["status"], "running")


class TestBackfillParseSuccess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = _mkdb(self.tmp)

    def test_backfill(self):
        save_consortium_run("r1", "default", "default", 0.8, 3, 1, 0.9, "q", status="success")
        save_arbiter_decision("r1", 1, "resp1", _good_decision(), "default")
        save_arbiter_decision("r1", 2, "resp2", _bad_decision(), "default")
        # simulate legacy row without parse_success set
        self.db.conn.execute("UPDATE arbiter_decisions SET parse_success = NULL WHERE iteration=2")
        self.db.conn.commit()
        import click
        _backfill_parse_success(self.db, dry_run=False)
        vals = {r["iteration"]: r["parse_success"] for r in self.db["arbiter_decisions"].rows}
        self.assertEqual(vals[1], 1)
        self.assertEqual(vals[2], 0)


if __name__ == "__main__":
    unittest.main()

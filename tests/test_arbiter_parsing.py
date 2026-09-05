"""Tests for the JSON arbiter contract: parser, repair retry, and guards."""
import json
import unittest
import pathlib
from unittest.mock import MagicMock, patch

from llm_consortium import ConsortiumOrchestrator, ConsortiumConfig

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"
REAL_MARKDOWN_FAILURE = (FIXTURE_DIR / "arbiter_markdown_failure_iter1.txt").read_text()

VALID_DECISION = json.dumps({
    "analysis": "Compared the two candidates on correctness.",
    "dissent": "Model B disputed the framing.",
    "synthesis": "The synthesized answer for the user.",
    "confidence": 0.87,
    "refinement_areas": ["edge cases"],
    "needs_iteration": False,
    "ranking": [101, 202],
    "model_guidance": {"model-a_0": "add tests"},
})

RESPONSES = [
    {"model": "model-a", "instance": 0, "response": "Answer A text", "id": 101, "response_id": "r101"},
    {"model": "model-b", "instance": 0, "response": "Answer B text", "id": 202, "response_id": "r202"},
]


def make_orchestrator(**kw):
    config = ConsortiumConfig(
        models={"model-a": 1, "model-b": 1},
        confidence_threshold=0.8,
        max_iterations=2,
        arbiter="arbiter_model",
        **kw,
    )
    return ConsortiumOrchestrator(config=config)


class TestJsonParsing(unittest.TestCase):
    def setUp(self):
        self.orch = make_orchestrator()

    def test_valid_json_parses(self):
        r = self.orch._parse_arbiter_response(VALID_DECISION, responses=RESPONSES)
        self.assertTrue(r["parse_success"])
        self.assertEqual(r["synthesis"], "The synthesized answer for the user.")
        self.assertAlmostEqual(r["confidence"], 0.87)
        self.assertFalse(r["needs_iteration"])
        self.assertEqual(r["ranking"], [101, 202])
        self.assertEqual(r["chosen_response_id"], "r101")
        self.assertEqual(r["model_guidance"], {"model-a_0": "add tests"})

    def test_json_in_fences_and_prose(self):
        text = "Here is my decision:\n```json\n" + VALID_DECISION + "\n```\nDone."
        r = self.orch._parse_arbiter_response(text, responses=RESPONSES)
        self.assertTrue(r["parse_success"])

    def test_confidence_percent_normalized(self):
        obj = json.loads(VALID_DECISION)
        obj["confidence"] = 87
        r = self.orch._parse_arbiter_response(json.dumps(obj), responses=RESPONSES)
        self.assertAlmostEqual(r["confidence"], 0.87)

    def test_confidence_missing_is_none(self):
        obj = json.loads(VALID_DECISION)
        del obj["confidence"]
        r = self.orch._parse_arbiter_response(json.dumps(obj), responses=RESPONSES)
        self.assertTrue(r["parse_success"])
        self.assertIsNone(r["confidence"])

    def test_real_markdown_failure_is_detected(self):
        """The actual raw markdown from run d114fff4 iter 1 must be a parse
        failure (parse_success False, confidence None)."""
        r = self.orch._parse_arbiter_response(REAL_MARKDOWN_FAILURE, responses=RESPONSES)
        self.assertFalse(r["parse_success"])
        self.assertIsNone(r["confidence"])
        self.assertEqual(r["ranking"], [])

    def test_missing_ranking_is_failure(self):
        obj = json.loads(VALID_DECISION)
        del obj["ranking"]
        r = self.orch._parse_arbiter_response(json.dumps(obj), responses=RESPONSES)
        self.assertFalse(r["parse_success"])

    def test_empty_synthesis_is_failure(self):
        obj = json.loads(VALID_DECISION)
        obj["synthesis"] = ""
        r = self.orch._parse_arbiter_response(json.dumps(obj), responses=RESPONSES)
        self.assertFalse(r["parse_success"])

    def test_needs_iteration_string_coerced(self):
        obj = json.loads(VALID_DECISION)
        obj["needs_iteration"] = "true"
        r = self.orch._parse_arbiter_response(json.dumps(obj), responses=RESPONSES)
        self.assertTrue(r["parse_success"])
        self.assertTrue(r["needs_iteration"])


class TestRepairRetry(unittest.TestCase):
    def setUp(self):
        self.orch = make_orchestrator()
        self.model = MagicMock()

    def test_exactly_one_retry_on_bad_then_good(self):
        good = MagicMock()
        good.text.return_value = VALID_DECISION
        self.model.prompt.side_effect = [MagicMock(text=lambda: REAL_MARKDOWN_FAILURE), good]
        parsed, raw, resp, retried = self.orch._synthesize_with_retry(self.model, "PROMPT", RESPONSES)
        self.assertTrue(retried)
        self.assertTrue(parsed["parse_success"])
        self.assertEqual(self.model.prompt.call_count, 2)
        # retry prompt must carry the repair instruction
        second_call = self.model.prompt.call_args_list[1]
        self.assertIn("did not use the required format", second_call.args[0] if second_call.args else second_call.kwargs.get("prompt", ""))

    def test_no_retry_when_valid(self):
        self.model.prompt.return_value = MagicMock(text=lambda: VALID_DECISION)
        parsed, raw, resp, retried = self.orch._synthesize_with_retry(self.model, "PROMPT", RESPONSES)
        self.assertFalse(retried)
        self.assertEqual(self.model.prompt.call_count, 1)

    def test_no_second_retry_when_still_bad(self):
        self.model.prompt.return_value = MagicMock(text=lambda: REAL_MARKDOWN_FAILURE)
        parsed, raw, resp, retried = self.orch._synthesize_with_retry(self.model, "PROMPT", RESPONSES)
        self.assertTrue(retried)
        self.assertFalse(parsed["parse_success"])
        self.assertEqual(self.model.prompt.call_count, 2)

    def test_schema_passed_when_supported(self):
        self.model.supports_schema = True
        self.model.prompt.return_value = MagicMock(text=lambda: VALID_DECISION)
        self.orch._synthesize_with_retry(self.model, "PROMPT", RESPONSES)
        self.assertIsNotNone(self.model.prompt.call_args.kwargs.get("schema"))

    def test_schema_omitted_when_unsupported(self):
        self.model.supports_schema = False
        self.model.prompt.return_value = MagicMock(text=lambda: VALID_DECISION)
        self.orch._synthesize_with_retry(self.model, "PROMPT", RESPONSES)
        self.assertIsNone(self.model.prompt.call_args.kwargs.get("schema"))


class TestStatusFinalization(unittest.TestCase):
    def _with_history(self, orch):
        orch.iteration_history = [{"iteration": 1, "synthesis": {}}]
        return orch

    def test_success(self):
        orch = self._with_history(make_orchestrator())
        st = orch._final_status({"synthesis": "hello", "parse_success": True})
        self.assertEqual(st, "success")

    def test_parse_failure_status(self):
        orch = self._with_history(make_orchestrator())
        st = orch._final_status({"synthesis": "raw", "parse_success": False})
        self.assertEqual(st, "arbiter_parse_failure")

    def test_empty_synthesis(self):
        orch = self._with_history(make_orchestrator())
        st = orch._final_status({"synthesis": ""})
        self.assertEqual(st, "empty_synthesis")

    def test_no_iterations(self):
        orch = make_orchestrator()
        st = orch._final_status({})
        self.assertEqual(st, "model_failure")

    def test_explicit_failure_wins(self):
        orch = self._with_history(make_orchestrator())
        orch.config.status = "model_failure"
        st = orch._final_status({"synthesis": "x"})
        self.assertEqual(st, "model_failure")


class TestMemberPromptGuard(unittest.TestCase):
    def test_role_strategy_never_embeds_raw_fallback(self):
        from llm_consortium.strategies.role import RoleStrategy
        orch = make_orchestrator(strategy="role", manual_context=True)
        orch.iteration_history = [{
            "iteration": 1,
            "synthesis": {
                "synthesis": REAL_MARKDOWN_FAILURE,
                "parse_success": False,
                "analysis": "Parse failure: no JSON object found in arbiter reply",
                "refinement_areas": [],
            },
            "model_responses": [],
        }]
        prompt = orch.strategy.prepare_iteration_prompt("model-a", 0, "original question", 2)
        self.assertNotIn("Candidate Analysis", prompt)
        self.assertNotIn(REAL_MARKDOWN_FAILURE[:80], prompt)

    def test_role_strategy_nested_synth_fallback_shape(self):
        """Degraded/failed decision from the 2026-08-29 nested-synthesis runs:
        iteration prompts must never embed the raw arbiter reply."""
        from llm_consortium.strategies.role import RoleStrategy
        orch = make_orchestrator(strategy="role", manual_context=True)
        orch.iteration_history = [{
            "iteration": 1,
            "synthesis": {
                "synthesis": REAL_MARKDOWN_FAILURE,
                "parse_success": False,
                "analysis": 'Parse failure: JSON missing required fields: "ranking"',
                "missing_fields": ["ranking", "confidence"],
                "degraded_synthesis": '{"bugs": [...]}',
                "refinement_areas": [],
            },
            "model_responses": [],
        }]
        prompt = orch.strategy.prepare_iteration_prompt("model-a", 0, "original question", 2)
        self.assertNotIn(REAL_MARKDOWN_FAILURE[:80], prompt)

    def test_default_strategy_guard(self):
        orch = make_orchestrator(manual_context=True)
        orch.iteration_history = [{
            "iteration": 1,
            "synthesis": {
                "synthesis": REAL_MARKDOWN_FAILURE,
                "parse_success": False,
                "analysis": "Parse failure: no JSON",
                "refinement_areas": ["be concise"],
            },
            "model_responses": [],
        }]
        prompt = orch.strategy.prepare_iteration_prompt("model-a", 0, "original question", 2)
        self.assertNotIn(REAL_MARKDOWN_FAILURE[:80], prompt)
        self.assertIn("be concise", prompt)


class TestUserFacingText(unittest.TestCase):
    def test_parse_failure_returns_member_response(self):
        from llm_consortium.models import ConsortiumModel
        cfg = make_orchestrator().config
        cm = ConsortiumModel("test-consortium", cfg)
        result = {
            "synthesis": {"synthesis": REAL_MARKDOWN_FAILURE, "parse_success": False, "ranking": [202, 101]},
            "iterations": [{
                "iteration": 1,
                "model_responses": [
                    {"model": "model-a", "id": 101, "response": "Answer A text", "error": None},
                    {"model": "model-b", "id": 202, "response": "Answer B text", "error": None},
                ],
                "synthesis": {},
            }],
        }
        text = cm._final_user_text(result)
        self.assertEqual(text, "Answer B text")  # ranking[0] == 202

    def test_success_returns_synthesis(self):
        from llm_consortium.models import ConsortiumModel
        cfg = make_orchestrator().config
        cm = ConsortiumModel("test-consortium", cfg)
        result = {
            "synthesis": {"synthesis": "The final answer.", "parse_success": True, "ranking": [101]},
            "iterations": [{"iteration": 1, "model_responses": [
                {"model": "model-a", "id": 101, "response": "Answer A", "error": None}], "synthesis": {}}],
        }
        self.assertEqual(cm._final_user_text(result), "The final answer.")


class TestArbiterSeesRoles(unittest.TestCase):
    def test_role_label_in_prompt(self):
        orch = make_orchestrator(strategy="role")
        orch.strategy.initialize_state()
        orch.strategy.get_instance_system_prompt("model-a", 0, None)
        prompt = orch._prepare_arbiter_prompt("the question", [
            {"model": "model-a", "instance": 0, "response": "text", "id": 101},
        ], [], iteration=1)
        self.assertIn("Role:", prompt)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Regressions from 2026-08-29 runs 112a397d / cc0884d6 (ling-3.0-flash arbiter,
# role strategy, documents workload): the arbiter emitted the TASK's JSON
# answer nested under "synthesis" with no envelope fields, and iteration 2 was
# truncated mid-JSON by the output cap.
# ---------------------------------------------------------------------------
REAL_NESTED_SYNTH = (FIXTURE_DIR / "arbiter_nested_synth_iter1.json").read_text()
REAL_TRUNCATED = (FIXTURE_DIR / "arbiter_truncated_iter2.json").read_text()


class TestNestedSynthesisBleedThrough(unittest.TestCase):
    def setUp(self):
        self.orch = make_orchestrator()

    def test_nested_object_reported_as_missing_fields(self):
        r = self.orch._parse_arbiter_response(REAL_NESTED_SYNTH, responses=RESPONSES)
        self.assertFalse(r["parse_success"])
        self.assertIn("ranking", r.get("missing_fields", []))
        # the usable content is carried for degraded acceptance / member fallback
        self.assertIn("run_llama_bench", r["degraded_synthesis"])

    def test_valid_reply_with_dict_synthesis_is_stringified(self):
        obj = json.loads(VALID_DECISION)
        obj["synthesis"] = {"bugs": [{"id": 1, "title": "t"}]}
        r = self.orch._parse_arbiter_response(json.dumps(obj), responses=RESPONSES)
        self.assertTrue(r["parse_success"])
        self.assertIn('"bugs"', r["synthesis"])  # dict serialized to string
        self.assertIsInstance(r["synthesis"], str)


class TestTruncatedJsonSalvage(unittest.TestCase):
    def setUp(self):
        self.orch = make_orchestrator()

    def test_real_truncated_reply_is_salvaged(self):
        r = self.orch._parse_arbiter_response(REAL_TRUNCATED, responses=RESPONSES)
        # salvage recovers the object; envelope is still incomplete -> retry path
        self.assertFalse(r["parse_success"])
        self.assertIn("ranking", r.get("missing_fields", []))
        self.assertIn("run_llama_bench", r.get("degraded_synthesis") or "")

    def test_salvage_closes_brackets_and_strings(self):
        cases = [
            '{"synthesis": "abc',                                     # cut in string
            '{"analysis": "a", "synthesis": {"x": [1, 2',             # nested cut
            '{"analysis": "a", "synthesis": "s", "conf',              # dangling key
            '{"analysis": "a", "synthesis": "s", "confidence": 0.5',  # cut in number
        ]
        for c in cases:
            fixed = ConsortiumOrchestrator._salvage_truncated_json(c)
            self.assertIsNotNone(fixed, c)
            parsed = json.loads(fixed)
            self.assertIsInstance(parsed, dict, c)

    def test_complete_json_is_not_touched(self):
        fixed = ConsortiumOrchestrator._salvage_truncated_json(VALID_DECISION)
        self.assertEqual(json.loads(fixed), json.loads(VALID_DECISION))


class TestTargetedRepair(unittest.TestCase):
    def setUp(self):
        self.orch = make_orchestrator()
        self.model = MagicMock()

    def test_repair_prompt_names_the_missing_fields(self):
        good = MagicMock()
        good.text.return_value = VALID_DECISION
        self.model.prompt.side_effect = [
            MagicMock(text=lambda: REAL_NESTED_SYNTH), good
        ]
        self.orch._synthesize_with_retry(self.model, "PROMPT", RESPONSES)
        second = self.model.prompt.call_args_list[1]
        text_arg = second.args[0] if second.args else second.kwargs.get("prompt", "")
        self.assertIn("did not use the required format", text_arg)
        self.assertIn('"ranking"', text_arg)
        self.assertIn("serialize", text_arg)

    def test_final_iteration_accepts_degraded_after_failed_retry(self):
        # both attempts nest the task JSON under synthesis, like run 112a397d
        self.model.prompt.return_value = MagicMock(text=lambda: REAL_NESTED_SYNTH)
        parsed, raw, resp, retried = self.orch._synthesize_with_retry(
            self.model, "PROMPT", RESPONSES, is_final_iteration=True
        )
        self.assertTrue(retried)
        self.assertTrue(parsed["parse_success"])
        self.assertTrue(parsed["degraded"])
        self.assertIn("run_llama_bench", parsed["synthesis"])
        self.assertIsNone(parsed["confidence"])
        self.assertEqual(self.model.prompt.call_count, 2)

    def test_nonfinal_iteration_does_not_accept_degraded(self):
        self.model.prompt.return_value = MagicMock(text=lambda: REAL_NESTED_SYNTH)
        parsed, raw, resp, retried = self.orch._synthesize_with_retry(
            self.model, "PROMPT", RESPONSES, is_final_iteration=False
        )
        self.assertFalse(parsed["parse_success"])

    def test_degraded_acceptance_has_parse_success_true_for_status(self):
        orch = self._with_history(make_orchestrator())
        orch.config.max_iterations = 1
        self.model.prompt.return_value = MagicMock(text=lambda: REAL_NESTED_SYNTH)
        orch.arbiter = "arbiter_model"
        parsed, raw, resp, retried = orch._synthesize_with_retry(
            self.model, "PROMPT", RESPONSES, is_final_iteration=True
        )
        self.assertEqual(orch._final_status(parsed), "success")

    def _with_history(self, orch):
        orch.iteration_history = [{"iteration": 1, "synthesis": {}}]
        return orch


class TestNoneConfidenceConvergence(unittest.TestCase):
    def test_no_typeerror_when_confidence_missing(self):
        # parse_success=True + confidence=None previously raised TypeError
        # at the convergence check (None >= threshold).
        orch = make_orchestrator()
        orch.iteration_history = [{"iteration": 1, "synthesis": {
            "synthesis": "s", "parse_success": True, "confidence": None,
            "needs_iteration": False, "ranking": [101],
        }}]
        st = orch._final_status(orch.iteration_history[0]["synthesis"])
        self.assertEqual(st, "success")

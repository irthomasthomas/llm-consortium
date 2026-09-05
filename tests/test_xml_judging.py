"""Tests for the legacy XML <synthesis_output> judging method and the
meta-leak guard that keeps judge commentary out of user-facing output."""
import json
import unittest

from llm_consortium import ConsortiumOrchestrator, ConsortiumConfig

XML_VALID = """Some preamble the model shouldn't emit but might.
<synthesis_output>
<analysis>Compared the two candidates on correctness.</analysis>
<dissent>Model B disputed the framing.</dissent>
<synthesis>A pelican perched on a bollard beside a canal, drawn with exactly six visible feathers, is a strong replacement test because the count can be checked by eye.</synthesis>
<confidence>0.82</confidence>
<refinement_areas>edge cases</refinement_areas>
<needs_iteration>false</needs_iteration>
<ranking><rank position="1">101</rank><rank position="2">202</rank></ranking>
</synthesis_output>
"""

XML_META_LEAK = """<synthesis_output>
<analysis>Compared the two candidates on correctness.</analysis>
<dissent></dissent>
<synthesis>VERDICT SUMMARY: Response 101 is the strongest response, winning on verifiability. Response 202 covers automation better but is weaker overall. WINNER: Response 101.</synthesis>
<confidence>0.75</confidence>
<refinement_areas></refinement_areas>
<needs_iteration>false</needs_iteration>
<ranking><rank position="1">101</rank><rank position="2">202</rank></ranking>
</synthesis_output>
"""

XML_NO_TAGS = "## Candidate Analysis\
Response 101 is better because... (pure markdown essay)"

XML_MISSING_RANKING = """<synthesis_output>
<synthesis>A normal answer that never mentions any responses.</synthesis>
<confidence>0.7</confidence>
<needs_iteration>false</needs_iteration>
</synthesis_output>
"""

RESPONSES = [
    {"model": "model-a", "instance": 0, "response": "Answer A text", "id": 101, "response_id": "r101"},
    {"model": "model-b", "instance": 0, "response": "Answer B text", "id": 202, "response_id": "r202"},
]


def make_orchestrator(judging_method="default", **kw):
    config = ConsortiumConfig(
        models={"model-a": 1, "model-b": 1},
        confidence_threshold=0.8,
        max_iterations=2,
        arbiter="arbiter_model",
        judging_method=judging_method,
        **kw,
    )
    return ConsortiumOrchestrator(config=config)


class TestXmlJudgingMethod(unittest.TestCase):
    def setUp(self):
        self.orch = make_orchestrator(judging_method="xml")

    def test_valid_xml_parses(self):
        r = self.orch._parse_arbiter_xml_response(XML_VALID, responses=RESPONSES)
        self.assertTrue(r["parse_success"])
        self.assertEqual(r["ranking"], [101, 202])
        self.assertAlmostEqual(r["confidence"], 0.82)
        self.assertFalse(r["needs_iteration"])
        self.assertEqual(r["chosen_response_id"], "r101")
        self.assertIn("bollard", r["synthesis"])

    def test_dispatch_selects_xml_parser(self):
        r = self.orch._parse_arbiter_call(XML_VALID, RESPONSES)
        self.assertTrue(r["parse_success"])
        self.assertIn("bollard", r["synthesis"])

    def test_no_tags_is_parse_failure(self):
        r = self.orch._parse_arbiter_xml_response(XML_NO_TAGS, responses=RESPONSEs if False else RESPONSES)
        self.assertFalse(r["parse_success"])
        self.assertIn("synthesis_output", r["analysis"])

    def test_missing_ranking_is_failure(self):
        r = self.orch._parse_arbiter_xml_response(XML_MISSING_RANKING, responses=RESPONSES)
        self.assertFalse(r["parse_success"])
        self.assertIn("ranking", r["analysis"])

    def test_meta_leak_in_xml_is_rejected(self):
        r = self.orch._parse_arbiter_xml_response(XML_META_LEAK, responses=RESPONSES)
        self.assertFalse(r["parse_success"])
        self.assertIn("meta-commentary", r["analysis"])
        # ranking survives so the member-fallback can use it
        self.assertEqual(r["ranking"], [101, 202])

    def test_json_schema_is_none_for_xml(self):
        self.assertIsNone(self.orch._arbiter_json_schema())

    def test_system_prompt_is_xml_template(self):
        prompt = self.orch._load_arbiter_system_prompt("xml")
        self.assertIn("<synthesis_output>", prompt)
        self.assertIn("<ranking>", prompt)
        self.assertNotIn("reply with ONE JSON object", prompt)


class TestJsonMetaLeakGuard(unittest.TestCase):
    def setUp(self):
        self.orch = make_orchestrator(judging_method="default")

    def test_json_meta_leak_rejected(self):
        obj = json.loads(VALID_DECISION_JSON)
        obj["synthesis"] = "WINNER: Response 101. All three responses converge; Response 202 is third."
        r = self.orch._parse_arbiter_response(json.dumps(obj), responses=RESPONSES)
        self.assertFalse(r["parse_success"])
        self.assertIn("meta-commentary", r["analysis"])
        self.assertEqual(r["ranking"], [101, 202])

    def test_normal_synthesis_passes(self):
        r = self.orch._parse_arbiter_response(VALID_DECISION_JSON, responses=RESPONSES)
        self.assertTrue(r["parse_success"])
        self.assertIn("synthesized answer", r["synthesis"])


VALID_DECISION_JSON = json.dumps({
    "analysis": "Compared the two candidates on correctness.",
    "dissent": "Model B disputed the framing.",
    "synthesis": "The synthesized answer for the user.",
    "confidence": 0.87,
    "refinement_areas": ["edge cases"],
    "needs_iteration": False,
    "ranking": [101, 202],
    "model_guidance": {"model-a_0": "add tests"},
})


class TestMetaLeakDetectorUnit(unittest.TestCase):
    def setUp(self):
        self.orch = make_orchestrator()

    def test_verdict_summary_leaks(self):
        reason = self.orch._detect_meta_leak("VERDICT SUMMARY: all models agree")
        self.assertIsNotNone(reason)

    def test_response_mentions_leak(self):
        reason = self.orch._detect_meta_leak("Response 960 is best; response 299 close behind.")
        self.assertIsNotNone(reason)

    def test_plain_answer_no_leak(self):
        reason = self.orch._detect_meta_leak(
            "A good replacement test is an SVG field-guide plate with exactly 12 spokes "
            "and a crescent moon; every constraint is machine-checkable."
        )
        self.assertIsNone(reason)

    def test_word_winner_alone_in_normal_context(self):
        # "winner" in lowercase normal prose should not trip
        reason = self.orch._detect_meta_leak("The winner of the race drew a pelican.")
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()

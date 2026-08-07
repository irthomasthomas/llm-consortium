"""Tests for the CacheMaxStrategy and cache_max orchestrator integration."""

import threading
import time
from unittest.mock import Mock, MagicMock, patch

import pytest

from llm_consortium.strategies.cache_max import (
    CacheMaxStrategy,
    execute_cache_max_responses,
    ARBITER_STATIC_PREFIX,
)
from llm_consortium.strategies.factory import create_strategy, _strategy_registry


def make_orchestrator(arbiter="arbiter-model", system_prompt="Be helpful."):
    orch = Mock()
    orch.arbiter = arbiter
    orch.system_prompt = system_prompt
    orch.iteration_history = []
    orch.consortium_id = "test-consortium"
    return orch


class TestFactoryRegistration:
    def test_cache_max_in_registry(self):
        assert "cache_max" in _strategy_registry
        assert _strategy_registry["cache_max"] is CacheMaxStrategy

    def test_create_strategy_cache_max(self):
        orch = make_orchestrator()
        strategy = create_strategy("cache_max", orch, {})
        assert isinstance(strategy, CacheMaxStrategy)


class TestCacheMaxInit:
    def test_default_params(self):
        strategy = CacheMaxStrategy(make_orchestrator())
        assert strategy.prewarm_arbiter is True
        assert strategy.prewarm_max_tokens == 1
        assert strategy.arbiter_shared_prefix is True
        assert strategy.same_model_arbiter_prefix is True
        assert strategy._prewarm_sent is False

    def test_custom_params(self):
        params = {"prewarm_arbiter": False, "prewarm_max_tokens": 5}
        strategy = CacheMaxStrategy(make_orchestrator(), params)
        assert strategy.prewarm_arbiter is False
        assert strategy.prewarm_max_tokens == 5

    def test_initialize_state_resets_prewarm(self):
        strategy = CacheMaxStrategy(make_orchestrator())
        strategy._prewarm_sent = True
        strategy._prewarm_info = {"foo": "bar"}
        strategy.initialize_state()
        assert strategy._prewarm_sent is False
        assert strategy._prewarm_info == {}


class TestArbiterPrefix:
    def test_prefix_contains_prompt_not_system(self):
        """System prompt goes via the provider system= channel, never inline,
        so member and arbiter prefixes stay byte-identical."""
        strategy = CacheMaxStrategy(make_orchestrator(system_prompt="SYS"))
        prefix = strategy.get_arbiter_prefix("ORIGINAL")
        assert "ORIGINAL" in prefix
        assert "SYS" not in prefix

    def test_prefix_handles_none_system_prompt(self):
        strategy = CacheMaxStrategy(make_orchestrator(system_prompt=None))
        prefix = strategy.get_arbiter_prefix("ORIGINAL")
        assert "ORIGINAL" in prefix

    def test_prefix_identical_regardless_of_system_prompt(self):
        """Member and arbiter calls share the same user-prefix bytes even when
        the orchestrator system prompt differs at send time."""
        p1 = CacheMaxStrategy(make_orchestrator(system_prompt="SYS-A")).get_arbiter_prefix("X")
        p2 = CacheMaxStrategy(make_orchestrator(system_prompt="SYS-B")).get_arbiter_prefix("X")
        assert p1 == p2

    def test_arbiter_system_prompt_matches_orchestrator(self):
        orch = make_orchestrator(system_prompt="SYS")
        strategy = CacheMaxStrategy(orch)
        assert strategy.get_arbiter_system_prompt() == "SYS"


class TestIterationPrompt:
    def test_first_iteration_uses_canonical_prefix(self):
        strategy = CacheMaxStrategy(make_orchestrator())
        prompt = strategy.prepare_iteration_prompt("m1", 1, "ORIGINAL", 1)
        assert prompt == strategy.get_arbiter_prefix("ORIGINAL")

    def test_guidance_appended_last_for_cache(self):
        orch = make_orchestrator()
        orch.iteration_history = [{"synthesis": {"synthesis": "SYNTH_TEXT"}}]
        strategy = CacheMaxStrategy(orch)
        prompt = strategy.prepare_iteration_prompt("m1", 1, "ORIGINAL", 2)
        prefix = strategy.get_arbiter_prefix("ORIGINAL")
        # Static prefix first, dynamic guidance LAST (cache-friendly ordering)
        assert prompt.startswith(prefix)
        assert "SYNTH_TEXT" in prompt
        assert prompt.index("SYNTH_TEXT") > prompt.index("ORIGINAL")


class TestShouldPrewarm:
    def test_prewarms_different_model_arbiter(self):
        strategy = CacheMaxStrategy(make_orchestrator())
        assert strategy.should_prewarm("arbiter-model", ["member-a", "member-b"]) is True

    def test_skips_same_model_arbiter_by_default(self):
        strategy = CacheMaxStrategy(make_orchestrator())
        assert strategy.should_prewarm("member-a", ["member-a", "member-b"]) is False

    def test_prewarms_same_model_when_disabled(self):
        strategy = CacheMaxStrategy(
            make_orchestrator(), {"same_model_arbiter_prefix": False}
        )
        assert strategy.should_prewarm("member-a", ["member-a"]) is True

    def test_respects_master_switch(self):
        strategy = CacheMaxStrategy(make_orchestrator(), {"prewarm_arbiter": False})
        assert strategy.should_prewarm("arbiter-model", ["member-a"]) is False

    def test_respects_shared_prefix_switch(self):
        strategy = CacheMaxStrategy(make_orchestrator(), {"arbiter_shared_prefix": False})
        assert strategy.should_prewarm("arbiter-model", ["member-a"]) is False


class TestPrewarmCall:
    def test_prewarm_sends_exact_prefix_max_tokens_1(self):
        orch = make_orchestrator(arbiter="arbiter-model", system_prompt="SYS")
        strategy = CacheMaxStrategy(orch)
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "x"
        mock_response.id = "resp-1"
        mock_model.prompt.return_value = mock_response

        with patch("llm.get_model", return_value=mock_model):
            info = strategy.prewarm_arbiter_call("arbiter-model", "ORIGINAL")

        mock_model.prompt.assert_called_once_with(
            strategy.get_arbiter_prefix("ORIGINAL"), system="SYS", max_tokens=1
        )
        assert info["arbiter"] == "arbiter-model"
        assert info["prefix_chars"] == len(strategy.get_arbiter_prefix("ORIGINAL"))
        assert strategy._prewarm_sent is True

    def test_prewarm_only_fires_once(self):
        orch = make_orchestrator()
        strategy = CacheMaxStrategy(orch)
        mock_model = Mock()
        mock_model.prompt.return_value.text.return_value = "x"

        with patch("llm.get_model", return_value=mock_model):
            strategy.prewarm_arbiter_call("arbiter-model", "ORIGINAL")
            result = strategy.prewarm_arbiter_call("arbiter-model", "ORIGINAL")

        assert result is None
        assert mock_model.prompt.call_count == 1

    def test_prewarm_failure_is_caught_not_raised(self):
        orch = make_orchestrator()
        strategy = CacheMaxStrategy(orch)
        with patch("llm.get_model", side_effect=RuntimeError("boom")):
            info = strategy.prewarm_arbiter_call("arbiter-model", "ORIGINAL")
        assert "error" in info
        assert "boom" in info["error"]

    def test_start_prewarm_runs_in_background_thread(self):
        orch = make_orchestrator(arbiter="arbiter-model")
        strategy = CacheMaxStrategy(orch)
        mock_model = Mock()
        mock_model.prompt.return_value.text.return_value = "x"

        with patch("llm.get_model", return_value=mock_model):
            strategy.start_prewarm("ORIGINAL", ["member-a"])
            assert strategy._prewarm_thread is not None
            strategy._prewarm_thread.join(timeout=5)

        assert strategy._prewarm_sent is True
        assert strategy._prewarm_info.get("arbiter") == "arbiter-model"

    def test_start_prewarm_skips_same_model_arbiter(self):
        orch = make_orchestrator(arbiter="member-a")
        strategy = CacheMaxStrategy(orch)
        strategy.start_prewarm("ORIGINAL", ["member-a"])
        assert strategy._prewarm_thread is None
        assert strategy._prewarm_sent is False


class TestExecuteCacheMaxResponses:
    def test_delegates_and_triggers_prewarm(self):
        orch = make_orchestrator(arbiter="arbiter-model")
        strategy = CacheMaxStrategy(orch)
        orch.strategy = strategy
        models = {"member-a": 1, "member-b": 2}

        with patch.object(strategy, "start_prewarm") as mock_prewarm, \
             patch("llm_consortium.strategies.cache_max.execute_cache_aware_responses",
                   return_value={"ok": True}) as mock_exec:
            result = execute_cache_max_responses(orch, "PROMPT", models, 1, Mock())

        mock_prewarm.assert_called_once_with("PROMPT", ["member-a", "member-b"])
        mock_exec.assert_called_once()
        assert result == {"ok": True}

    def test_no_prewarm_without_arbiter(self):
        orch = make_orchestrator(arbiter=None)
        strategy = CacheMaxStrategy(orch)
        orch.strategy = strategy

        with patch.object(strategy, "start_prewarm") as mock_prewarm, \
             patch("llm_consortium.strategies.cache_max.execute_cache_aware_responses",
                   return_value={}) as mock_exec:
            execute_cache_max_responses(orch, "PROMPT", {"m": 1}, 1, Mock())

        mock_prewarm.assert_not_called()


class TestPrewarmConcurrency:
    def test_concurrent_start_prewarm_fires_exactly_once(self):
        """Race N threads on start_prewarm; the arbiter model must be
        prompted exactly once (the LLM-generated original had a TOCTOU race)."""
        orch = make_orchestrator(arbiter="arbiter-model")
        strategy = CacheMaxStrategy(orch)
        mock_model = Mock()
        mock_model.prompt.return_value.text.return_value = "x"

        with patch("llm.get_model", return_value=mock_model):
            threads = [
                threading.Thread(target=strategy.start_prewarm,
                                 args=("ORIGINAL", ["member-a"]))
                for _ in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)
            if strategy._prewarm_thread:
                strategy._prewarm_thread.join(timeout=5)

        assert strategy._prewarm_sent is True
        assert mock_model.prompt.call_count == 1

    def test_mixed_entry_points_fire_exactly_once(self):
        """start_prewarm + direct prewarm_arbiter_call racing = single fire."""
        orch = make_orchestrator(arbiter="arbiter-model")
        strategy = CacheMaxStrategy(orch)
        mock_model = Mock()
        mock_model.prompt.return_value.text.return_value = "x"

        with patch("llm.get_model", return_value=mock_model):
            t1 = threading.Thread(target=strategy.start_prewarm,
                                  args=("ORIGINAL", ["member-a"]))
            t2 = threading.Thread(target=strategy.prewarm_arbiter_call,
                                  args=("arbiter-model", "ORIGINAL"))
            t1.start(); t2.start()
            t1.join(timeout=5); t2.join(timeout=5)
            if strategy._prewarm_thread:
                strategy._prewarm_thread.join(timeout=5)

        assert mock_model.prompt.call_count == 1


class TestLearningLoopExclusion:
    def test_arbiter_prewarm_role_excluded_from_non_model_roles(self):
        from llm_consortium.learning import NON_MODEL_ROLES
        assert "arbiter-prewarm" in NON_MODEL_ROLES
        assert "arbiter" in NON_MODEL_ROLES

    def test_real_model_names_not_excluded(self):
        from llm_consortium.learning import NON_MODEL_ROLES, canonical_model
        for real in ("deepseek-chat", "gpt-4o", "claude-3-haiku"):
            assert canonical_model(real) not in NON_MODEL_ROLES
            assert not canonical_model(real).startswith(("arbiter", "prewarm"))


class TestCacheTelemetry:
    def _response_with_usage(self, usage):
        resp = Mock()
        resp.usage = usage
        resp.json.return_value = {"usage": usage or {}}
        return resp

    def test_extracts_deepseek_style_cache_fields(self):
        resp = self._response_with_usage({
            "prompt_cache_hit_tokens": 900,
            "prompt_cache_miss_tokens": 100,
        })
        out = CacheMaxStrategy.extract_cache_usage(resp)
        assert out["cache_hit_tokens"] == 900
        assert out["cache_hit_rate"] == 0.9

    def test_extracts_openai_style_cached_tokens(self):
        resp = self._response_with_usage({
            "prompt_tokens_details": {"cached_tokens": 500},
        })
        out = CacheMaxStrategy.extract_cache_usage(resp)
        assert out["cache_hit_tokens"] == 500

    def test_empty_when_provider_reports_nothing(self):
        assert CacheMaxStrategy.extract_cache_usage(self._response_with_usage(None)) == {}
        assert CacheMaxStrategy.extract_cache_usage(self._response_with_usage({})) == {}

    def test_never_raises_on_malformed_usage(self):
        resp = Mock()
        type(resp).usage = property(lambda self: (_ for _ in ()).throw(RuntimeError("x")))
        assert CacheMaxStrategy.extract_cache_usage(resp) == {}

    def test_handles_real_llm_response_api(self):
        """llm.Response.usage is a bound method; cache data lives in json()."""
        resp = Mock()
        resp.json.return_value = {"usage": {
            "prompt_tokens": 1000,
            "prompt_cache_hit_tokens": 960,
            "prompt_cache_miss_tokens": 40,
            "prompt_tokens_details": {"cached_tokens": 960},
        }}
        out = CacheMaxStrategy.extract_cache_usage(resp)
        assert out["cache_hit_tokens"] == 960
        assert out["cache_hit_rate"] == 0.96

    def test_json_failure_falls_back_safely(self):
        resp = Mock()
        resp.json.side_effect = ValueError("no json")
        assert CacheMaxStrategy.extract_cache_usage(resp) == {}

    def test_prewarm_report_returns_copy(self):
        strategy = CacheMaxStrategy(make_orchestrator())
        strategy._prewarm_info = {"arbiter": "m"}
        report = strategy.prewarm_report()
        report["arbiter"] = "mutated"
        assert strategy._prewarm_info["arbiter"] == "m"


class TestArbiterPromptParserContract:
    """The cache_max arbiter prompt must request tags that
    _parse_arbiter_response actually extracts (live eval caught confidence=0.0
    because the prompt asked for vague 'synthesis_output with synthesis')."""

    def _build_prompt(self):
        from llm_consortium.orchestrator import ConsortiumOrchestrator
        orch = make_orchestrator()
        strategy = CacheMaxStrategy(orch)
        orch.strategy = strategy
        inst = ConsortiumOrchestrator.__new__(ConsortiumOrchestrator)
        inst.strategy = strategy
        inst.system_prompt = orch.system_prompt
        inst._load_arbiter_prompt_template = lambda *a, **k: None
        return inst, inst._prepare_arbiter_prompt("ORIG", [], [])

    def test_prompt_requests_parser_aligned_tags(self):
        _, prompt = self._build_prompt()
        for tag in ("<synthesis>", "<confidence>", "<needs_iteration>",
                    "<refinement_areas>", "<ranking>"):
            assert tag in prompt, f"missing {tag}"

    def test_parser_extracts_from_prompt_conforming_response(self):
        inst, _ = self._build_prompt()
        fake_arbiter_reply = """<synthesis_output>
<analysis>A</analysis>
<synthesis>SYNTHESIZED ANSWER</synthesis>
<confidence>0.87</confidence>
<needs_iteration>false</needs_iteration>
<refinement_areas></refinement_areas>
<ranking><rank position="1">1</rank></ranking>
</synthesis_output>"""
        parsed = inst._parse_arbiter_response(fake_arbiter_reply)
        assert parsed["synthesis"] == "SYNTHESIZED ANSWER"
        assert parsed["confidence"] == pytest.approx(0.87)
        assert parsed["needs_iteration"] is False

"""CacheMax Consortium Strategy - maximum prefix-cache hit rate.

Extends CacheAwareStrategy with two arbitration optimizations:

1. ARBITER PROMPT ORDERING
   The arbiter user prompt is laid out as:
       [static prefix: system + original prompt + user instructions]
       [dynamic suffix: member responses + iteration history]
   If the arbiter model == a member model, its prefix matches the members'
   cached prefix (same system + same original prompt) so the full static
   portion is a cache hit and only the response block is new.

PROVIDER CAVEAT: both optimizations assume DeepSeek/Zen-style automatic prefix
caching. On providers without it the pre-warm costs one max_tokens=1 call and
yields nothing; it never changes synthesis output.

2. ARBITER PRE-WARMING (different arbiter model)
   When the arbiter is a different model than the members, the static
   prefix has never been seen by that model. We issue a max_tokens=1
   request to the arbiter with the exact static prefix concurrently with
   the first-wave member calls. When the real arbiter call later appends
   the member responses to that same prefix, DeepSeek/Zen-style prefix
   caching hits the warm prefix (cache hit == success).
"""

import logging
import threading
import time
from typing import List, Dict, Any, Optional

from .cache_aware import CacheAwareStrategy, execute_cache_aware_responses

logger = logging.getLogger(__name__)

# NOTE: the system prompt is delivered via the provider's system= channel in
# both member and arbiter calls (see orchestrator), NOT inline here. Inlining it
# would duplicate it and break byte-identical prefix matching with member calls.
ARBITER_STATIC_PREFIX = """Consortium arbitration task.
Original prompt:
{original_prompt}
"""


class CacheMaxStrategy(CacheAwareStrategy):
    def __init__(self, orchestrator, params=None):
        super().__init__(orchestrator, params)
        self.prewarm_arbiter = self.params.get('prewarm_arbiter', True)
        self.prewarm_max_tokens = int(self.params.get('prewarm_max_tokens', 1))
        self.arbiter_shared_prefix = self.params.get('arbiter_shared_prefix', True)
        self.same_model_arbiter_prefix = self.params.get('same_model_arbiter_prefix', True)
        self._prewarm_sent = False
        self._prewarm_thread = None
        self._prewarm_info = {}
        self._prewarm_lock = threading.Lock()

    def initialize_state(self):
        super().initialize_state()
        self._prewarm_sent = False
        self._prewarm_thread = None
        self._prewarm_info = {}

    def prepare_iteration_prompt(self, model_id, instance, original_prompt, iteration):
        """Members use the SAME canonical static prefix as the arbiter so a
        same-model arbiter reuses their warm prefix. Dynamic guidance is LAST."""
        guid = ""
        if self.orchestrator.iteration_history:
            prev = self.orchestrator.iteration_history[-1].get("synthesis", {}).get("synthesis", "")
            guid = """

Iteration %d guidance:
Improve upon the previous iteration based on this synthesis:
%s
""" % (iteration, prev)
        return self.get_arbiter_prefix(original_prompt) + guid

    def get_arbiter_prefix(self, original_prompt: str) -> str:
        return ARBITER_STATIC_PREFIX.format(original_prompt=original_prompt)

    def get_arbiter_system_prompt(self) -> Optional[str]:
        return self.orchestrator.system_prompt

    def should_prewarm(self, arbiter_model: str, member_models: List[str]) -> bool:
        if not self.prewarm_arbiter:
            return False
        if not self.arbiter_shared_prefix:
            return False
        if self.same_model_arbiter_prefix and arbiter_model in member_models:
            return False
        return True

    def start_prewarm(self, original_prompt: str, member_models: List[str]) -> None:
        """Fire the max_tokens=1 arbiter pre-warm in a background thread so it
        overlaps with the member calls (cache hit, no added latency)."""
        if not self.orchestrator.arbiter:
            return
        if not self.should_prewarm(self.orchestrator.arbiter, member_models):
            return
        # Claim the single-fire slot BEFORE launching so concurrent
        # start_prewarm callers cannot double-fire.
        if not self._claim_prewarm_slot():
            return
        self._prewarm_thread = threading.Thread(
            target=self._execute_prewarm,
            args=(self.orchestrator.arbiter, original_prompt),
            daemon=True,
        )
        self._prewarm_thread.start()
        logger.info("[CacheMax] start_prewarm launched in background")

    def _claim_prewarm_slot(self) -> bool:
        """Atomically claim the single pre-warm slot. Returns True exactly once."""
        with self._prewarm_lock:
            if self._prewarm_sent:
                return False
            self._prewarm_sent = True
            return True

    def prewarm_arbiter_call(self, arbiter_model: str, original_prompt: str):
        """Execute the pre-warm. Safe for direct calls: claims the slot first,
        so it fires at most once no matter how it is invoked."""
        if not self._claim_prewarm_slot():
            return None
        return self._execute_prewarm(arbiter_model, original_prompt)

    def _execute_prewarm(self, arbiter_model: str, original_prompt: str):
        """Un guarded execution; callers must have claimed the slot first."""
        prefix = self.get_arbiter_prefix(original_prompt)
        system = self.get_arbiter_system_prompt()
        start = time.time()
        try:
            import llm
            model = llm.get_model(arbiter_model)
            logger.info("[CacheMax] Pre-warming arbiter %s with max_tokens=%s", arbiter_model, self.prewarm_max_tokens)
            response = model.prompt(prefix, system=system, max_tokens=self.prewarm_max_tokens)
            text = response.text()
            self._prewarm_info = {
                "arbiter": arbiter_model,
                "prefix_chars": len(prefix),
                "elapsed": round(time.time() - start, 3),
                "response_head": text[:80].replace(chr(10), " "),
            }
            self._prewarm_info.update(self.extract_cache_usage(response))
            if hasattr(response, "id") and self.orchestrator.consortium_id:
                from ..db import log_response, save_consortium_member
                try:
                    log_response(response, arbiter_model, str(self.orchestrator.consortium_id))
                    save_consortium_member(str(self.orchestrator.consortium_id), str(response.id), "arbiter-prewarm", 0, 0)
                except Exception as e:
                    logger.debug("[CacheMax] prewarm db log failed: %s", e)
            return self._prewarm_info
        except Exception as e:
            logger.warning("[CacheMax] arbiter prewarm failed for %s: %s", arbiter_model, e)
            self._prewarm_info = {"error": str(e), "arbiter": arbiter_model}
            return self._prewarm_info
    @staticmethod
    def extract_cache_usage(response) -> Dict[str, Any]:
        """Best-effort extraction of provider cache telemetry (DeepSeek-style
        prompt_cache_hit_tokens / prompt_cache_miss_tokens) from a response's
        usage JSON. Returns {} when the provider reports nothing."""
        try:
            usage = response.usage
            # llm.Response exposes usage as a method; some mocks/dicts as attr
            if callable(usage):
                usage = None  # method object holds no data; use json() instead
            if usage is None:
                try:
                    usage = (response.json() or {}).get("usage")
                except Exception:
                    usage = None
            if usage is None:
                return {}
            data = usage if isinstance(usage, dict) else {}
            details = data.get("prompt_tokens_details") or {}
            hit = (data.get("prompt_cache_hit_tokens")
                   or details.get("cached_tokens") or 0)
            miss = data.get("prompt_cache_miss_tokens") or 0
            if hit or miss:
                total = hit + miss
                return {
                    "cache_hit_tokens": hit,
                    "cache_miss_tokens": miss,
                    "cache_hit_rate": round(hit / total, 3) if total else 0.0,
                }
        except Exception:
            pass
        return {}

    def prewarm_report(self) -> Dict[str, Any]:
        """Snapshot of the last pre-warm attempt for logging/evals."""
        return dict(self._prewarm_info)


def execute_cache_max_responses(orchestrator, prompt, models, iteration, get_response_fn):
    strategy = orchestrator.strategy
    if getattr(strategy, "start_prewarm", None) and orchestrator.arbiter:
        member_models = list(models.keys())
        strategy.start_prewarm(prompt, member_models)

    results = execute_cache_aware_responses(orchestrator, prompt, models, iteration, get_response_fn)
    return results

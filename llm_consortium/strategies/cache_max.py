"""CacheMax Consortium Strategy - maximum prefix-cache hit rate.

Extends CacheAwareStrategy with two arbitration optimizations:

1. ARBITER PROMPT ORDERING
   The arbiter user prompt is laid out as:
       [static prefix: system + original prompt + user instructions]
       [dynamic suffix: member responses + iteration history]
   If the arbiter model == a member model, its prefix matches the members'
   cached prefix (same system + same original prompt) so the full static
   portion is a cache hit and only the response block is new.

2. ARBITER PRE-WARMING (different arbiter model)
   When the arbiter is a different model than the members, the static
   prefix has never been seen by that model. We issue a max_tokens=1
   request to the arbiter with the exact static prefix concurrently with
   the first-wave member calls. When the real arbiter call later appends
   the member responses to that same prefix, DeepSeek/Zen-style prefix
   caching hits the warm prefix (cache hit == success).
"""

import concurrent.futures
import logging
import threading
import time
from typing import List, Dict, Any, Optional

from .cache_aware import CacheAwareStrategy, execute_cache_aware_responses

logger = logging.getLogger(__name__)

ARBITER_STATIC_PREFIX = """Consortium arbitration task.
Original prompt:
{original_prompt}

User instructions:
{user_instructions}
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
        return ARBITER_STATIC_PREFIX.format(
            original_prompt=original_prompt,
            user_instructions=self.orchestrator.system_prompt or ""
        )

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
        if not self.orchestrator.arbiter or self._prewarm_sent:
            return
        if not self.should_prewarm(self.orchestrator.arbiter, member_models):
            return
        self._prewarm_thread = threading.Thread(
            target=self.prewarm_arbiter_call,
            args=(self.orchestrator.arbiter, original_prompt),
            daemon=True,
        )
        self._prewarm_thread.start()
        logger.info("[CacheMax] start_prewarm launched in background")

    def prewarm_arbiter_call(self, arbiter_model: str, original_prompt: str):
        if self._prewarm_sent:
            return None
        self._prewarm_sent = True
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


def execute_cache_max_responses(orchestrator, prompt, models, iteration, get_response_fn):
    strategy = orchestrator.strategy
    if getattr(strategy, "start_prewarm", None) and orchestrator.arbiter:
        member_models = list(models.keys())
        strategy.start_prewarm(prompt, member_models)

    results = execute_cache_aware_responses(orchestrator, prompt, models, iteration, get_response_fn)
    return results

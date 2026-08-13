"""
Cascade Strategy: Start cheap, escalate on errors.
Based on backtest finding: "1+ errors = 92% failure rate."
"""
import logging
from .base import ConsortiumStrategy

logger = logging.getLogger(__name__)

class CascadeStrategy(ConsortiumStrategy):
    """Cost-aware: cheap model first, escalate to stronger model on errors."""
    def _validate_params(self):
        self.tiers = self.params.get("tiers")
        if not self.tiers or not isinstance(self.tiers, list):
            raise ValueError("cascade strategy requires 'tiers' parameter: List[List[str]]")
        self.error_threshold = int(self.params.get("error_threshold", 1))
        self.max_tier = int(self.params.get("max_tier", len(self.tiers) - 1))
        self.escalate_on_low_confidence = bool(self.params.get("escalate_on_low_confidence", True))
        self.confidence_floor = float(self.params.get("confidence_floor", 0.4))

    def initialize_state(self):
        super().initialize_state()
        self.iteration_state["current_tier"] = 0
        self.iteration_state["error_count"] = 0
        self.iteration_state["escalation_reason"] = None

    def select_models(self, available_models, current_prompt, iteration):
        tier_idx = min(self.iteration_state.get("current_tier", 0), self.max_tier)
        tier_models = self.tiers[tier_idx]
        selected = {}
        for model in tier_models:
            selected[model] = available_models.get(model, 1)
        reason = self.iteration_state.get("escalation_reason", "initial")
        logger.info(f"[Cascade] Iteration {iteration}: Tier {tier_idx} ({reason}) — {list(selected.keys())}")
        return selected

    def process_responses(self, successful_responses, iteration):
        return successful_responses

    def update_state(self, iteration_context):
        synthesis = iteration_context.synthesis
        errors = [r for r in iteration_context.model_responses if r.get("error")]
        self.iteration_state["error_count"] += len(errors)
        current_tier = self.iteration_state.get("current_tier", 0)
        should_escalate = False
        reason = None
        if self.iteration_state["error_count"] >= self.error_threshold:
            should_escalate = True
            reason = f"errors={self.iteration_state['error_count']}"
        elif self.escalate_on_low_confidence:
            conf = synthesis.get("confidence", 1.0)
            if conf < self.confidence_floor:
                should_escalate = True
                reason = f"low_confidence={conf:.2f}"
        if should_escalate and current_tier < self.max_tier:
            self.iteration_state["current_tier"] = current_tier + 1
            self.iteration_state["escalation_reason"] = reason
            self.iteration_state["error_count"] = 0
            logger.warning(f"[Cascade] ESCALATING tier {current_tier} → {current_tier + 1} ({reason})")

"""
Ring+Ling Strategy: Two-stage reasoning pipeline.
  Iteration 1: Reasoning model generates chain-of-thought
  Iteration 2: Answer model uses reasoning as context
"""
import re, logging
from .base import ConsortiumStrategy

logger = logging.getLogger(__name__)

def extract_reasoning(text: str) -> str:
    for tag in ['think', 'reasoning']:
        m = re.search(f'<{tag}>(.*?)</{tag}>', text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
    for pat in [r'(?i)(.*?)(?:\n\*{0,2}(?:Result|Answer|Conclusion|Final Answer)[:\*].*)$',
                r'(?i)(.*?)(?:\n#{1,3}\s*(?:Result|Answer|Conclusion).*)$']:
        m = re.search(pat, text, re.DOTALL)
        if m and len(m.group(1).strip()) > 100:
            return m.group(1).strip()
    if len(text) > 200:
        return text[:int(len(text) * 0.8)].strip()
    return text

class RingLingStrategy(ConsortiumStrategy):
    """Two-stage: reasoning model → answer model."""
    def _validate_params(self):
        self.reasoning_model = self.params.get("reasoning_model")
        self.answer_model = self.params.get("answer_model")
        self.max_reasoning_chars = int(self.params.get("max_reasoning_chars", 3000))
        if not self.reasoning_model:
            raise ValueError("ring_ling strategy requires 'reasoning_model' parameter")
        if not self.answer_model:
            raise ValueError("ring_ling strategy requires 'answer_model' parameter")

    def initialize_state(self):
        super().initialize_state()
        self.iteration_state["reasoning"] = None

    def select_models(self, available_models, current_prompt, iteration):
        if iteration == 1:
            logger.info(f"[RingLing] Iteration 1: Reasoning with {self.reasoning_model}")
            return {self.reasoning_model: 1}
        logger.info(f"[RingLing] Iteration {iteration}: Answering with {self.answer_model}")
        return {self.answer_model: 1}

    def process_responses(self, successful_responses, iteration):
        if iteration == 1 and successful_responses:
            text = successful_responses[0].get("response", "")
            reasoning = extract_reasoning(text)
            self.iteration_state["reasoning"] = reasoning[:self.max_reasoning_chars]
            logger.info(f"[RingLing] Extracted {len(reasoning)} chars of reasoning")
        return successful_responses

    def prepare_iteration_prompt(self, model_id, instance, original_prompt, iteration):
        if iteration == 1:
            return original_prompt
        reasoning = self.iteration_state.get("reasoning", "")
        if not reasoning:
            return original_prompt
        return f"""Original question: {original_prompt}

Here is detailed reasoning analysis from an expert reasoner:
{reasoning}

Based on this reasoning, provide a clear, accurate, and well-structured final answer.
You may correct any errors you find in the reasoning. Be concise."""

    def update_state(self, iteration_context):
        if iteration_context.model_responses and not self.iteration_state.get("reasoning"):
            resp = iteration_context.model_responses[0]
            if resp.get("response"):
                self.iteration_state["reasoning"] = extract_reasoning(resp["response"])[:self.max_reasoning_chars]

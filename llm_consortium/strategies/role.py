"""Role Strategy for llm-consortium.

This strategy assigns different cognitive roles or personalities to model
instances to prevent AI groupthink and ensure orthogonal perspectives.
"""

from .base import ConsortiumStrategy
from typing import List, Dict, Any, Optional
import random
import logging

logger = logging.getLogger(__name__)

class PersonalityGenerator:
    TRAITS = [
        "Skepticism", "Creativity", "Defensiveness", 
        "Precision", "Candor", "Lateral Thinking", 
        "Pessimism", "Optimism"
    ]

    @classmethod
    def generate(cls) -> Dict[str, int]:
        return {trait: random.randint(1, 20) for trait in cls.TRAITS}

    @classmethod
    def format_prompt_modifier(cls, matrix: Dict[str, int]) -> str:
        traits_str = ", ".join(f"{k} ({v}/20)" for k, v in matrix.items())
        return f"""
[DIVERGENCE MATRIX OVERRIDE]
You are operating with the following underlying cognitive trait matrix:
{traits_str}

Please adapt your tone, reasoning, and perspective to heavily reflect these traits while answering.
"""

class RoleStrategy(ConsortiumStrategy):
    """
    Strategy that forces models to adopt distinct personas.
    """
    
    DEFAULT_ROLES = [
        "The Generator: Solve this problem linearly and directly. Provide the best standard solution possible.",
        "The Devil's Advocate: You are a skeptical reviewer. Assume the most obvious approaches will fail. Propose a highly defensive or entirely alternative approach.",
        "The Fact Checker: Focus entirely on edge cases, syntax, context, and potential physical or logical constraints in the prompt. Find the flaws."
    ]

    def _validate_params(self):
        self.roles = self.params.get('roles', self.DEFAULT_ROLES)
        if isinstance(self.roles, str):
            self.roles = [self.roles]
        self.use_dynamic_personalities = str(self.params.get('use_dynamic_personalities', 'true')).lower() == 'true'

    def initialize_state(self):
        super().initialize_state()
        self.iteration_state['assigned_roles'] = {}

    def select_models(self, available_models: Dict[str, int], current_prompt: str, iteration: int) -> Dict[str, int]:
        return available_models.copy()

    def process_responses(self, successful_responses: List[Dict[str, Any]], iteration: int) -> List[Dict[str, Any]]:
        return successful_responses

    def get_instance_system_prompt(self, model: str, instance: int, default_prompt: Optional[str]) -> Optional[str]:
        instance_key = f"{model}-{instance}"
        # Ensure initialization in case not called
        if 'assigned_roles' not in self.iteration_state:
            self.iteration_state['assigned_roles'] = {}
            
        assigned = self.iteration_state['assigned_roles']
        
        if instance_key not in assigned:
            # Assign a role based on global count of assigned roles
            used_count = len(assigned)
            if used_count < len(self.roles):
                assigned[instance_key] = f"\n[COGNITIVE ROLE OVERRIDE]\n{self.roles[used_count]}\n"
            elif self.use_dynamic_personalities:
                matrix = PersonalityGenerator.generate()
                assigned[instance_key] = PersonalityGenerator.format_prompt_modifier(matrix)
            else:
                assigned[instance_key] = ""

        modifier = assigned[instance_key]
        base = default_prompt or ""
        
        if not modifier:
            return base if base else None
            
        return f"{base}\n{modifier}".strip()

    def prepare_iteration_prompt(self, model_id: str, instance: int, original_prompt: str, iteration: int) -> str:
        """
        Implements a cache-optimized prompt structure for subsequent iterations,
        ensuring the role or personality is heavily reflected.
        """
        if not self.orchestrator.iteration_history:
             return original_prompt
             
        prev_synth = self.orchestrator.iteration_history[-1].get("synthesis", {}).get("synthesis", "")
        
        guidance = f"""Iteration Guidance:
Please improve upon the previous iteration based on this synthesis:
{prev_synth}

Remember to strictly adhere to your assigned cognitive role/personality trait matrix."""

        if getattr(self.orchestrator, 'manual_context', False):
            # Cache-optimized layout
            return f"Original Context/Prompt: {original_prompt}\n---\n{guidance}"
        else:
            return guidance

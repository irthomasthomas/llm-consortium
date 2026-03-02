class Consortium:
    def __init__(self, config: Config):
        self.config = config
        self.manual_context = config.manual_context
        self.judging_method = config.judging_method

    def _get_arbiter_template(self) -> str:
        """Get appropriate template based on context mode and judging method"""
        if self.manual_context:
            # Keep full templates for manual mode
            template_map = {
                'default': 'arbiter_prompt.xml',
                'pick-one': 'pick_one_prompt.xml',
                'rank': 'rank_prompt.xml'
            }
        else:
            # Use lean templates for auto-context
            template_map = {
                'default': 'auto_arbiter_lean.xml',
                'pick-one': 'auto_arbiter_pick_lean.xml',
                'rank': 'auto_arbiter_rank_lean.xml'
            }
        
        template_name = template_map.get(self.judging_method, template_map['default'])
        return self._read_template(template_name)
    
    def _get_arbiter_system_prompt(self) -> str:
        """Get the arbiter system prompt from config"""
        return self.config.arbiter_system_prompt or ""
    
    def _build_iteration_focus(self, synthesis_result: Dict[str, Any]) -> str:
        """Create concise focus for next iteration"""
        confidence = synthesis_result.get("confidence", 0.0)
        areas = synthesis_result.get("refinement_areas", [])
        
        if confidence >= 0.8:
            return "Fine-tuning and polishing"
        elif confidence >= 0.6:
            focus_areas = areas[:2] if areas else ["quality improvement"]
            return f"Address: {', '.join(focus_areas)}"
        else:
            focus_areas = areas[:3] if areas else ["major improvements needed"]
            return f"Major improvements needed: {', '.join(focus_areas)}"
    
    def _log_token_efficiency(self, original_tokens: int, lean_tokens: int) -> None:
        """Log token usage efficiency metrics"""
        if original_tokens > 0:
            savings_pct = (1 - lean_tokens / original_tokens) * 100
            logger.info(
                f"Token efficiency: {savings_pct:.1f}% reduction "
                f"({original_tokens} → {lean_tokens})"
            )
    
    def _synthesize_responses_automatic(
        self,
        original_prompt: str,
        responses: List[Dict[str, Any]],
        iteration: int
    ) -> Dict[str, Any]:
        """Synthesize responses using automatic context with lean prompts"""
        # Filter valid responses
        valid_responses = [
            response for response in responses
            if response.get("confidence", 0.0) >= self.config.min_confidence
        ]
        
        # Set system prompt for arbiter conversation
        if self.arbiter_conversation:
            from llm import get_model
            
            # Check if system prompt is already set via alias options
            try:
                arbiter_model = get_model(self.arbiter)
                if hasattr(arbiter_model, 'system_prompt') and not arbiter_model.system_prompt:
                    # Inject lean system prompt
                    system_prompt = self._get_arbiter_system_prompt()
                    self.arbiter_conversation = self.arbiter_conversation.model.conversation()
                    self.arbiter_conversation.set_system_prompt(system_prompt)
            except Exception as e:
                logger.debug(f"Could not set system prompt: {e}")
        
        # Build iteration focus
        iteration_focus = "Initial synthesis"
        confidence_level = 0
        refinement_areas = "all aspects"
        
        if iteration > 1 and hasattr(self, '_last_synthesis'):
            iteration_focus = self._build_iteration_focus(self._last_synthesis)
            confidence_level = self._last_synthesis.get("confidence", 0) * 100
            areas = self._last_synthesis.get("refinement_areas", [])
            refinement_areas = ", ".join(areas) if areas else "all aspects"
        
        # Format responses
        formatted_responses = self._format_responses(responses)
        
        # Get lean template
        template = self._get_arbiter_template()
        
        # Build lean prompt
        lean_prompt = template.format(
            formatted_responses=formatted_responses,
            confidence_level=confidence_level,
            refinement_areas=refinement_areas
        )
        
        # Send to arbiter
        arbiter_response = self._send_to_arbiter(lean_prompt)
        
        # Store synthesis result for next iteration
        self._last_synthesis = synthesis_result
        
        return synthesis_result
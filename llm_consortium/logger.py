"""
Structured logging for llm-consortium with correlation context.
"""

import logging
import sys
from typing import Optional, Dict, Any

# Mock for testing - in production this would be real
class MockJsonFormatter:
    def __init__(self, fmt):
        self.fmt = fmt
        
    def format(self, record):
        return f"JSON: {record.getMessage()}"

try:
    from pythonjsonlogger import jsonlogger
except ImportError:
    # Mock for testing
    jsonlogger = type(sys)('jsonlogger')
    jsonlogger.JsonFormatter = MockJsonFormatter

from .tracing import consortium_id_var, request_id_var, iteration_id_var, model_id_var


def setup_structured_logging(level: str = "INFO"):
    """Set up structured logging for the consortium."""
    logger = logging.getLogger("llm_consortium")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Console handler
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s '
        '%(consortium_id)s %(request_id)s %(iteration_id)s %(model_id)s '
        '%(duration_ms)s %(tokens)s %(confidence)s %(event_type)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


class StructuredLogger:
    """Wrapper providing structured logging with automatic context extraction."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            setup_structured_logging()
    
    def _get_extra(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build extra fields from context variables and user-provided extras."""
        context_extra = {
            "consortium_id": consortium_id_var.get(None),
            "request_id": request_id_var.get(None),
            "iteration_id": iteration_id_var.get(None),
            "model_id": model_id_var.get(None),
        }
        
        if extra:
            context_extra.update(extra)
            
        return context_extra
    
    def debug(self, message: str, **kwargs):
        """Log debug message with structured context."""
        self.logger.debug(message, extra=self._get_extra(kwargs))
    
    def info(self, message: str, **kwargs):
        """Log info message with structured context."""
        self.logger.info(message, extra=self._get_extra(kwargs))
    
    def warning(self, message: str, **kwargs):
        """Log warning message with structured context."""
        self.logger.warning(message, extra=self._get_extra(kwargs))
    
    def error(self, message: str, **kwargs):
        """Log error message with structured context."""
        self.logger.error(message, extra=self._get_extra(kwargs))
    
    def log_model_call(
        self,
        model: str,
        prompt: str,
        response: str,
        tokens: int,
        duration_ms: float,
        confidence: float = 0.0,
        error: Optional[str] = None,
        **kwargs
    ):
        """
        Log a model call with full context and metrics.
        """
        event_type = "model_error" if error else "model_call"
        
        extra = {
            "event_type": event_type,
            "model_id": model,
            "duration_ms": duration_ms,
            "tokens": tokens,
            "confidence": confidence,
            "prompt_preview": prompt[:100] if prompt else "",
            "response_preview": response[:100] if response else "",
            "error": error,
            **kwargs
        }
        
        if error:
            self.error(f"Model call failed: {model} - {error}", **extra)
        else:
            self.info(f"Model call: {model} ({tokens} tokens, {duration_ms:.2f}ms)", **extra)
    
    def log_arbiter_decision(
        self,
        arbiter_model: str,
        evaluated_models: list,
        confidence: float,
        refinement_areas: list,
        raw_response: Optional[str] = None,
        **kwargs
    ):
        """
        Log an arbiter decision for evaluation and analysis.
        """
        extra = {
            "event_type": "arbiter_decision",
            "model_id": arbiter_model,
            "evaluated_models": evaluated_models,
            "confidence": confidence,
            "refinement_areas": refinement_areas,
            "raw_response_preview": raw_response[:200] if raw_response else "",
            **kwargs
        }
        
        self.info(
            f"Arbiter decision: {arbiter_model} evaluated {len(evaluated_models)} models "
            f"(confidence: {confidence:.2f})",
            **extra
        )
    
    def log_iteration_start(self, iteration: int, prompt: str, **kwargs):
        """Log the start of an iteration."""
        extra = {
            "event_type": "iteration_start",
            "iteration_id": iteration,
            "prompt_preview": prompt[:100],
            **kwargs
        }
        self.info(f"Starting iteration {iteration}", **extra)
    
    def log_iteration_end(self, iteration: int, confidence: float, **kwargs):
        """Log the end of an iteration."""
        extra = {
            "event_type": "iteration_end",
            "iteration_id": iteration,
            "confidence": confidence,
            **kwargs
        }
        self.info(f"Completed iteration {iteration} (confidence: {confidence:.2f})", **extra)


# Global logger instance
logger = StructuredLogger("llm_consortium")

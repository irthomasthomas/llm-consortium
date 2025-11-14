"""
Tracing and correlation context management for llm-consortium.
Provides automatic propagation of consortium execution context.
"""

import uuid
import contextvars
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import contextmanager

# Context variables for automatic propagation
consortium_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "consortium_id", default=None
)
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)
iteration_id_var: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "iteration_id", default=None
)
model_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "model_id", default=None
)


class TracingContext:
    """Manages correlation IDs and metrics for a consortium execution."""
    
    def __init__(self, consortium_id: Optional[str] = None):
        self.consortium_id = consortium_id or f"cons-{uuid.uuid4().hex[:16]}"
        self.start_time = time.perf_counter()
        self.metrics: Dict[str, Any] = {
            "total_tokens": 0,
            "total_time": 0.0,
            "model_calls": 0,
            "arbiter_calls": 0,
            "iteration_count": 0,
        }
        self.token_usage: Dict[str, int] = {}  # model -> token count
        self.errors: List[Dict[str, Any]] = []
        
    def get_context(self) -> Dict[str, Any]:
        """Get current tracing context as a dictionary."""
        return {
            "consortium_id": self.consortium_id,
            "request_id": request_id_var.get(),
            "iteration_id": iteration_id_var.get(),
            "model_id": model_id_var.get(),
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def add_tokens(self, model: str, tokens: int) -> None:
        """Add token usage for a model."""
        self.token_usage[model] = self.token_usage.get(model, 0) + tokens
        self.metrics["total_tokens"] += tokens
        
    def add_timing(self, duration_ms: float) -> None:
        """Add timing for a model call."""
        self.metrics["total_time"] += duration_ms
        
    def increment_model_calls(self) -> None:
        """Increment model call counter."""
        self.metrics["model_calls"] += 1
        
    def increment_arbiter_calls(self) -> None:
        """Increment arbiter call counter."""
        self.metrics["arbiter_calls"] += 1
        
    def add_error(self, error: Exception, context: Dict[str, Any]) -> None:
        """Record an error with context."""
        self.errors.append({
            "error": str(error),
            "type": type(error).__name__,
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
        })


@contextmanager
def consortium_context(consortium_id: Optional[str] = None):
    """
    Context manager for setting consortium-wide correlation IDs.
    """
    ctx = TracingContext(consortium_id)
    token = consortium_id_var.set(ctx.consortium_id)
    
    try:
        yield ctx
    finally:
        consortium_id_var.reset(token)


@contextmanager
def iteration_context(iteration: int):
    """
    Context manager for iteration-specific context.
    """
    token = iteration_id_var.set(iteration)
    try:
        yield
    finally:
        iteration_id_var.reset(token)


@contextmanager
def request_context(request_id: Optional[str] = None):
    """
    Context manager for individual request correlation.
    """
    req_id = request_id or f"req-{uuid.uuid4().hex[:12]}"
    token = request_id_var.set(req_id)
    try:
        yield req_id
    finally:
        request_id_var.reset(token)


@contextmanager
def model_context(model_id: str):
    """
    Context manager for model-specific context.
    """
    token = model_id_var.set(model_id)
    try:
        yield
    finally:
        model_id_var.reset(token)

"""
LLM Consortium Studio Backend
Direct Python API integration — no CLI subprocess.
Uses llm_consortium + llm modules directly.
"""
import asyncio
import concurrent.futures
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional, Dict, Any, List

# Point to the installed llm environment
LLM_SITE = Path.home() / ".local/share/uv/tools/llm/lib/python3.12/site-packages"
sys.path.insert(0, str(LLM_SITE))

import llm
from llm_consortium import ConsortiumOrchestrator, ConsortiumConfig
from llm_consortium.models import _get_consortium_configs, _save_consortium_config, parse_models
from llm_consortium.orchestrator import create_consortium
from llm_consortium.db import (
    DatabaseConnection, save_consortium_run, save_consortium_member,
    save_arbiter_decision, update_consortium_run
)

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── App Setup ─────────────────────────────────────
app = FastAPI(title="LLM Consortium Studio API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for blocking consortium runs
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
active_runs: Dict[str, asyncio.Event] = {}

# ── Pydantic Models ───────────────────────────────
class SaveConfigRequest(BaseModel):
    name: str
    models: list[str]          # ["model:count", ...]
    arbiter: Optional[str] = None
    confidence_threshold: float = 0.8
    max_iterations: int = 3
    min_iterations: int = 1
    strategy: str = "default"
    judging_method: str = "default"

class RunRequest(BaseModel):
    config_name: str
    prompt: str

class DeleteRequest(BaseModel):
    name: str

# ── Helpers ───────────────────────────────────────
def get_db():
    return DatabaseConnection.get_connection()

def model_list_to_dict(models: list[str]) -> Dict[str, int]:
    """Convert ['model:2', 'other'] -> {'model': 2, 'other': 1}"""
    result: Dict[str, int] = {}
    for entry in models:
        if ":" in entry:
            name, count = entry.rsplit(":", 1)
            result[name.strip()] = int(count)
        else:
            result[entry.strip()] = 1
    return result

def consortium_config_to_frontend(name: str, config: ConsortiumConfig) -> dict:
    """Convert internal config to frontend-friendly format."""
    models_str = ", ".join(f"{k}:{v}" for k, v in config.models.items())
    threshold_str = str(config.confidence_threshold)
    iterations_str = f"{config.minimum_iterations}-{config.max_iterations}"
    return {
        "name": name,
        "created": getattr(config, "created_at", ""),
        "strategy": config.strategy or "default",
        "models": models_str,
        "arbiter": config.arbiter or "",
        "threshold": f"{threshold_str} | Iterations: {iterations_str}",
        "judging": f"{config.judging_method} | Context: {'Manual' if config.manual_context else 'Auto'}",
        "system_prompt": config.system_prompt or "Default",
    }

def run_to_frontend(row: dict) -> dict:
    """Convert DB run row to frontend format."""
    return {
        "id": row.get("id", ""),
        "created_at": row.get("created_at", ""),
        "config_name": row.get("config_name"),
        "strategy": row.get("strategy", "default"),
        "judging_method": row.get("judging_method", "default"),
        "confidence_threshold": row.get("confidence_threshold", 0.8),
        "max_iterations": row.get("max_iterations", 3),
        "iteration_count": row.get("iteration_count", 0),
        "final_confidence": row.get("final_confidence", 0),
        "user_prompt": row.get("user_prompt", ""),
        "status": row.get("status"),
        "category": row.get("category"),
    }

# ── API Endpoints ─────────────────────────────────
@app.get("/api/models")
async def list_models():
    """List all available models (non-consortium)."""
    try:
        all_models = llm.get_models()
        model_ids = []
        for m in all_models:
            mid = m.model_id
            # Skip consortium models and OpenAI Chat wrapper names
            if mid and not mid.startswith("cns-") and not mid.startswith("consortium"):
                model_ids.append(mid)
        return {"models": sorted(set(model_ids))}
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.get("/api/consortiums")
async def list_consortiums():
    """List all saved consortium configurations."""
    try:
        configs = _get_consortium_configs()
        consortiums = [
            consortium_config_to_frontend(name, cfg)
            for name, cfg in configs.items()
        ]
        return {"consortiums": consortiums}
    except Exception as e:
        return {"consortiums": [], "error": str(e)}


@app.get("/api/strategies")
async def list_strategies():
    """List available consortium strategies."""
    try:
        from llm_consortium.strategies.factory import _strategy_registry
        strategies = []
        for name, cls in _strategy_registry.items():
            strategies.append({
                "name": name,
                "class": cls.__name__,
                "description": (cls.__doc__ or "").strip().split("\n")[0],
            })
        return {"strategies": strategies}
    except Exception as e:
        return {"strategies": [], "error": str(e)}


@app.get("/api/runs")
async def list_runs(limit: int = Query(50, ge=1, le=500)):
    """List recent consortium runs."""
    try:
        db = get_db()
        rows = list(db["consortium_runs"].rows_where(
            "1=1 order by created_at desc limit ?", [limit]
        ))
        return {"runs": [run_to_frontend(r) for r in rows]}
    except Exception as e:
        return {"runs": [], "error": str(e)}


@app.get("/api/runs/{run_id}")
async def get_run_detail(run_id: str):
    """Get detailed info about a specific run, including members and decisions."""
    try:
        db = get_db()
        run_row = db["consortium_runs"].get(run_id)
        if not run_row:
            raise HTTPException(status_code=404, detail="Run not found")

        run_data = run_to_frontend(run_row)

        # Members
        members = list(db["consortium_members"].rows_where(
            "consortium_run_id = ? order by iteration, model, instance", [run_id]
        ))
        run_data["members"] = [dict(m) for m in members]

        # Arbiter decisions
        decisions = list(db["arbiter_decisions"].rows_where(
            "consortium_run_id = ? order by iteration", [run_id]
        ))
        run_data["decisions"] = [dict(d) for d in decisions]

        return run_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str):
    """SSE stream polling for a running consortium execution."""
    async def event_generator():
        db = get_db()
        seen_member_count = 0
        seen_decision_count = 0
        try:
            while True:
                run = db["consortium_runs"].get(run_id)
                if not run:
                    break

                members = list(db["consortium_members"].rows_where(
                    "consortium_run_id = ?", [run_id]
                ))
                decisions = list(db["arbiter_decisions"].rows_where(
                    "consortium_run_id = ?", [run_id]
                ))

                if len(members) > seen_member_count or len(decisions) > seen_decision_count:
                    seen_member_count = len(members)
                    seen_decision_count = len(decisions)
                    data = run_to_frontend(run)
                    data["members"] = [dict(m) for m in members]
                    data["decisions"] = [dict(d) for d in decisions]
                    yield f"data: {json.dumps(data, default=str)}\n\n"

                if run.get("status") in ("success", "failed", "error"):
                    data = run_to_frontend(run)
                    data["members"] = [dict(m) for m in members]
                    data["decisions"] = [dict(d) for d in decisions]
                    yield f"data: {json.dumps(data, default=str)}\n\n"
                    yield "data: [DONE]\n\n"
                    break

                await asyncio.sleep(0.5)
        finally:
            db.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/consortiums/save")
async def save_consortium(config: SaveConfigRequest):
    """Save a new consortium configuration."""
    try:
        cfg = ConsortiumConfig(
            models=model_list_to_dict(config.models),
            arbiter=config.arbiter,
            confidence_threshold=config.confidence_threshold,
            max_iterations=config.max_iterations,
            minimum_iterations=config.min_iterations,
            strategy=config.strategy,
            judging_method=config.judging_method,
        )
        _save_consortium_config(config.name, cfg)
        return {"status": "saved", "name": config.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/consortiums/delete")
async def delete_consortium(req: DeleteRequest):
    """Remove a saved consortium configuration."""
    try:
        db = get_db()
        db["consortium_configs"].delete(req.name)
        db.conn.commit()
        return {"status": "deleted", "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/consortiums/run")
async def run_consortium(request: RunRequest):
    """Run a consortium asynchronously and stream results via SSE."""
    configs = _get_consortium_configs()
    if request.config_name not in configs:
        raise HTTPException(status_code=404, detail=f"Consortium '{request.config_name}' not found")

    config = configs[request.config_name]
    run_id = str(uuid.uuid4())
    stop_event = asyncio.Event()
    active_runs[run_id] = stop_event

    async def stream_output():
        try:
            # Initial status
            yield f"data: {json.dumps({'type': 'status', 'text': f'Run started: {run_id[:8]}', 'run_id': run_id})}\n\n"

            # Run orchestration in thread pool (it's synchronous/blocking)
            loop = asyncio.get_event_loop()

            def blocking_run():
                try:
                    orchestrator = ConsortiumOrchestrator(config, config_name=request.config_name)
                    result = orchestrator.orchestrate(
                        request.prompt,
                        consortium_id=run_id
                    )
                    return result
                except Exception as e:
                    return {"error": str(e)}

            future = loop.run_in_executor(executor, blocking_run)

            # Poll for intermediate results while the run is executing
            db = get_db()
            last_member_count = 0
            last_decision_count = 0

            while not future.done() and not stop_event.is_set():
                await asyncio.sleep(0.3)

                # Check for new DB entries
                try:
                    member_count = db["consortium_members"].count_where(
                        "consortium_run_id = ?", [run_id]
                    )
                    decision_count = db["arbiter_decisions"].count_where(
                        "consortium_run_id = ?", [run_id]
                    )

                    if member_count > last_member_count:
                        members = list(db["consortium_members"].rows_where(
                            "consortium_run_id = ? order by id desc limit 3", [run_id]
                        ))
                        for m in members:
                            model = m.get("model", "?")
                            iteration = m.get("iteration", "?")
                            yield f"data: {json.dumps({'type': 'member', 'model': model, 'iteration': iteration, 'text': f'[{model}] iteration {iteration}'})}\n\n"
                        last_member_count = member_count

                    if decision_count > last_decision_count:
                        decisions = list(db["arbiter_decisions"].rows_where(
                            "consortium_run_id = ? order by id desc limit 1", [run_id]
                        ))
                        for d in decisions:
                            conf = d.get("confidence", 0)
                            yield f"data: {json.dumps({'type': 'decision', 'confidence': conf, 'iteration': d.get('iteration'), 'text': f'Synthesis: confidence {conf:.0%}'})}\n\n"
                        last_decision_count = decision_count
                except Exception:
                    pass  # DB may not have entries yet

            db.close()

            # Get final result
            result = await future

            if "error" in result:
                yield f"data: {json.dumps({'type': 'error', 'text': result['error']})}\n\n"
            else:
                synthesis = result.get("synthesis", {})
                confidence = synthesis.get("confidence", 0)
                text = synthesis.get("synthesis", "")
                yield f"data: {json.dumps({'type': 'complete', 'run_id': run_id, 'confidence': confidence, 'text': text[:500]})}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            active_runs.pop(run_id, None)

    return StreamingResponse(stream_output(), media_type="text/event-stream")


@app.post("/api/consortiums/run/stop")
async def stop_run(run_id: str = Query(...)):
    """Stop a running consortium."""
    event = active_runs.get(run_id)
    if event:
        event.set()
        return {"status": "stopped", "run_id": run_id}
    raise HTTPException(status_code=404, detail="Run not found or already completed")


# ── Startup ───────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"Starting Consortium Studio API server...")
    print(f"LLM DB: {DatabaseConnection.get_connection().db_path}")
    uvicorn.run(app, host="0.0.0.0", port=8765)

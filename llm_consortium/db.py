import logging
import threading
import sqlite_utils
from typing import Optional, Dict, Any, List
import datetime
import json
import sqlite3
import pathlib
import click
import numpy as np

logger = logging.getLogger(__name__)

def user_dir() -> pathlib.Path:
    """Get or create user directory for storing application data."""
    path = pathlib.Path(click.get_app_dir("io.datasette.llm"))
    return path

def logs_db_path() -> pathlib.Path:
    """Get path to logs database."""
    return user_dir() / "consortium_logs.db"

class DatabaseConnection:
    _thread_local = threading.local()

    @classmethod
    def get_connection(cls) -> sqlite_utils.Database:
        """Get thread-local database connection to ensure thread safety."""
        if not hasattr(cls._thread_local, 'db'):
            # Use timeout=30 to wait for locks instead of failing immediately
            conn = sqlite3.connect(logs_db_path(), timeout=30)
            db = sqlite_utils.Database(conn)
            cls._thread_local.db = db
            
            # Initialize consortium schema
            db.execute("""
                CREATE TABLE IF NOT EXISTS consortium_runs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT,
                    config_name TEXT,
                    strategy TEXT,
                    judging_method TEXT,
                    confidence_threshold REAL,
                    max_iterations INTEGER,
                    iteration_count INTEGER,
                    final_confidence REAL,
                    user_prompt TEXT,
                    FOREIGN KEY (config_name) REFERENCES consortium_configs(name)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS consortium_members (
                    run_id TEXT,
                    response_id TEXT,
                    role TEXT,
                    iteration INTEGER,
                    member_index INTEGER,
                    PRIMARY KEY (run_id, response_id),
                    FOREIGN KEY (run_id) REFERENCES consortium_runs(id),
                    FOREIGN KEY (response_id) REFERENCES responses(id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS arbiter_decisions (
                    run_id TEXT,
                    iteration INTEGER,
                    response_id TEXT,
                    chosen_response_id TEXT,
                    confidence REAL,
                    synthesis TEXT,
                    decision_json TEXT,
                    ranking_json TEXT,
                    refinement_areas TEXT,
                    PRIMARY KEY (run_id, iteration),
                    FOREIGN KEY (run_id) REFERENCES consortium_runs(id),
                    FOREIGN KEY (response_id) REFERENCES responses(id),
                    FOREIGN KEY (chosen_response_id) REFERENCES responses(id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS consortium_configs (
                    name TEXT PRIMARY KEY,
                    config TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
        return cls._thread_local.db

def log_response(response, model: str, consortium_run_id: Optional[str] = None):
    """Log model response to database and log file."""
    try:
        db = DatabaseConnection.get_connection()
        response.log_to_db(db)
        
        logger.debug(f"Response from {model} logged to database")

        # Explicitly commit to release any locks held by this thread
        db.conn.commit()

        # Check for truncation in various formats
        if response.response_json:
            finish_reason = _get_finish_reason(response.response_json)
            truncation_indicators = ['length', 'max_tokens', 'max_token']

            if finish_reason and any(indicator in finish_reason for indicator in truncation_indicators):
                logger.warning(f"Response from {model} truncated. Reason: {finish_reason}")

    except Exception as e:
        logger.error(f"Error logging to database: {e}")

def _get_finish_reason(response_json: Dict[str, Any]) -> Optional[str]:
    """Helper function to extract finish reason from various API response formats."""
    if not isinstance(response_json, dict):
        return None
    # List of possible keys for finish reason (case-insensitive)
    reason_keys = ['finish_reason', 'finishReason', 'stop_reason']

    # Convert response to lowercase for case-insensitive matching
    lower_response = {k.lower(): v for k, v in response_json.items()}

    # Check each possible key
    for key in reason_keys:
        value = lower_response.get(key.lower())
        if value:
            return str(value).lower()

    return None

def save_consortium_run(
    run_id: str,
    strategy: str,
    judging_method: str,
    confidence_threshold: float,
    max_iterations: int,
    iteration_count: int,
    final_confidence: float,
    user_prompt: str,
    config_name: Optional[str] = None
):
    try:
        db = DatabaseConnection.get_connection()
        db["consortium_runs"].insert({
            "id": run_id,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "config_name": config_name,
            "strategy": strategy or "default",
            "judging_method": judging_method,
            "confidence_threshold": confidence_threshold,
            "max_iterations": max_iterations,
            "iteration_count": iteration_count,
            "final_confidence": final_confidence,
            "user_prompt": user_prompt
        }, ignore=True, alter=True)
        db.conn.commit()
    except Exception as e:
        logger.error(f"Error persisting consortium_run: {e}")


def update_consortium_run(
    run_id: str,
    iteration_count: int,
    final_confidence: float,
) -> None:
    try:
        db = DatabaseConnection.get_connection()
        db.conn.execute(
            "UPDATE consortium_runs SET iteration_count = ?, final_confidence = ? WHERE id = ?",
            [iteration_count, final_confidence, run_id],
        )
        db.conn.commit()
    except Exception as e:
        logger.error(f"Error updating consortium_run summary: {e}")

def save_consortium_member(
    run_id: str,
    response_id: str,
    role: str,
    iteration: int,
    member_index: int
):
    try:
        db = DatabaseConnection.get_connection()
        db["consortium_members"].insert({
            "run_id": run_id,
            "response_id": response_id,
            "role": role,
            "iteration": iteration,
            "member_index": member_index
        }, ignore=True)
        db.conn.commit()
    except Exception as e:
        logger.error(f"Error saving consortium member: {e}")

def save_arbiter_decision(
    run_id: str,
    iteration: int,
    response_id: str,
    parsed_result: Dict[str, Any],
    judging_method: str,
    geometric_confidence: Optional[float] = None,
    centroid_vector: Optional[List[float]] = None,
):
    try:
        db = DatabaseConnection.get_connection()
        chosen_id = parsed_result.get('chosen_response_id')
        db["arbiter_decisions"].insert({
            "run_id": run_id,
            "iteration": iteration,
            "response_id": response_id,
            "chosen_response_id": chosen_id,
            "confidence": parsed_result.get('confidence', 0.0),
            "synthesis": parsed_result.get('synthesis', ''),
            "decision_json": json.dumps(parsed_result) if judging_method != 'rank' else None,
            "ranking_json": json.dumps(parsed_result.get('ranking', [])) if judging_method == 'rank' else None,
            "refinement_areas": json.dumps(parsed_result.get('refinement_areas', [])),
            "geometric_confidence": geometric_confidence,
            "centroid_vector": json.dumps(centroid_vector) if centroid_vector is not None else None,
        }, ignore=True, alter=True)
        db.conn.commit()
    except Exception as e:
        logger.error(f"Error logging arbiter decision: {e}")


def save_response_embedding(
    response_id: str,
    run_id: str,
    vector: List[float],
    model: str,
    embedding_model: Optional[str] = None,
) -> None:
    try:
        db = DatabaseConnection.get_connection()
        db["response_embeddings"].insert({
            "response_id": response_id,
            "run_id": run_id,
            "model": model,
            "embedding_json": json.dumps(vector),
            "embedding_model": embedding_model,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }, pk="response_id", replace=True, alter=True)
        db.conn.commit()
    except Exception as e:
        logger.error(f"Error saving response embedding: {e}")


def get_embeddings_for_run(run_id: str) -> List[np.ndarray]:
    db = DatabaseConnection.get_connection()
    if "response_embeddings" not in db.table_names():
        return []

    rows = list(db.query(
        "SELECT embedding_json FROM response_embeddings WHERE run_id = ? ORDER BY created_at, response_id",
        [run_id],
    ))
    return [np.array(json.loads(row["embedding_json"]), dtype=float) for row in rows]


def get_embedding_records_for_run(run_id: str) -> List[Dict[str, Any]]:
    db = DatabaseConnection.get_connection()
    if "response_embeddings" not in db.table_names():
        return []

    geometric_confidence_select = "NULL AS geometric_confidence"
    if "arbiter_decisions" in db.table_names():
        arbiter_columns = {column.name for column in db["arbiter_decisions"].columns}
        if "geometric_confidence" in arbiter_columns:
            geometric_confidence_select = "ad.geometric_confidence"

    return [
        dict(row)
        for row in db.query(
            "SELECT re.response_id, re.run_id, re.model, re.embedding_json, re.embedding_model, re.created_at, "
            f"cm.iteration, cm.member_index, {geometric_confidence_select} "
            "FROM response_embeddings re "
            "LEFT JOIN consortium_members cm ON cm.response_id = re.response_id AND cm.run_id = re.run_id "
            "LEFT JOIN arbiter_decisions ad ON ad.run_id = re.run_id AND ad.iteration = cm.iteration "
            "WHERE re.run_id = ? ORDER BY cm.iteration, cm.member_index, re.response_id",
            [run_id],
        )
    ]


def save_cluster_metadata(run_id: str, iteration: int, clusters: List[Dict[str, Any]]) -> None:
    try:
        db = DatabaseConnection.get_connection()
        for cluster in clusters:
            db["consensus_clusters"].insert({
                "run_id": run_id,
                "iteration": iteration,
                "cluster_id": cluster.get("cluster_id", -1),
                "centroid_json": json.dumps(cluster.get("centroid", [])),
                "radius": cluster.get("radius", 0.0),
                "density": cluster.get("density", 0.0),
            }, alter=True)
        db.conn.commit()
    except Exception as e:
        logger.error(f"Error saving cluster metadata: {e}")


def save_run_visualization(run_id: str, visualization_json: str) -> None:
    try:
        db = DatabaseConnection.get_connection()
        run_columns = {column.name for column in db["consortium_runs"].columns}
        if "visualization_json" not in run_columns:
            db["consortium_runs"].add_column("visualization_json", str)

        existing = db.conn.execute(
            "SELECT 1 FROM consortium_runs WHERE id = ?",
            [run_id],
        ).fetchone()
        if existing:
            db.conn.execute(
                "UPDATE consortium_runs SET visualization_json = ? WHERE id = ?",
                [visualization_json, run_id],
            )
        else:
            db["consortium_runs"].insert({
                "id": run_id,
                "created_at": datetime.datetime.utcnow().isoformat(),
                "visualization_json": visualization_json,
            }, pk="id", alter=True)
        db.conn.commit()
    except Exception as e:
        logger.error(f"Error saving run visualization: {e}")

import logging
import threading
import sqlite_utils
from typing import Optional, Dict, Any, List
import datetime
import json
import sqlite3
import pathlib
import click

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
                    strategy TEXT,
                    judging_method TEXT,
                    confidence_threshold REAL,
                    max_iterations INTEGER,
                    iteration_count INTEGER,
                    final_confidence REAL,
                    user_prompt TEXT
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
    user_prompt: str
):
    try:
        db = DatabaseConnection.get_connection()
        db.execute("""
            INSERT OR IGNORE INTO consortium_runs 
            (id, created_at, strategy, judging_method, confidence_threshold, max_iterations, iteration_count, final_confidence, user_prompt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            run_id,
            datetime.datetime.utcnow().isoformat(),
            strategy or "default",
            judging_method,
            confidence_threshold,
            max_iterations,
            iteration_count,
            final_confidence,
            user_prompt
        ])
        db.conn.commit()
    except Exception as e:
        logger.error(f"Error persisting consortium_run: {e}")

def save_consortium_member(
    run_id: str,
    response_id: str,
    role: str,
    iteration: int,
    member_index: int
):
    try:
        db = DatabaseConnection.get_connection()
        db.execute("""
            INSERT OR IGNORE INTO consortium_members 
            (run_id, response_id, role, iteration, member_index) 
            VALUES (?, ?, ?, ?, ?)
        """, [run_id, response_id, role, iteration, member_index])
        db.conn.commit()
    except Exception as e:
        logger.error(f"Error saving consortium member: {e}")

def save_arbiter_decision(
    run_id: str,
    iteration: int,
    response_id: str,
    parsed_result: Dict[str, Any],
    judging_method: str
):
    try:
        db = DatabaseConnection.get_connection()
        chosen_id = parsed_result.get('chosen_response_id')
        db.execute("""
            INSERT OR IGNORE INTO arbiter_decisions 
            (run_id, iteration, response_id, chosen_response_id, confidence, synthesis, decision_json, ranking_json, refinement_areas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            run_id, iteration, response_id, chosen_id,
            parsed_result.get('confidence', 0.0), parsed_result.get('synthesis', ''),
            json.dumps(parsed_result) if judging_method != 'rank' else None,
            json.dumps(parsed_result.get('ranking', [])) if judging_method == 'rank' else None,
            json.dumps(parsed_result.get('refinement_areas', []))
        ])
        db.conn.commit()
    except Exception as e:
        logger.error(f"Error logging arbiter decision: {e}")

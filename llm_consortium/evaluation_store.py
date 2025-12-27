import sqlite3
import sqlite_utils
import json
import os
from typing import Optional, Dict, Any, List
from . import DatabaseConnection

class EvaluationStore:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = "~/.llm_consortium/evaluations.db"
        self.db_path = os.path.expanduser(db_path)
        self._is_memory = self.db_path == ":memory:"
        if not self._is_memory:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        if self._is_memory:
            self._memory_conn = sqlite_utils.Database(self.db_path)
        self._init_db()

    def _get_connection(self):
        if self._is_memory and hasattr(self, '_memory_conn'):
            return self._memory_conn
        return sqlite_utils.Database(self.db_path)

    def _init_db(self):
        db = self._get_connection()
        conn = db.conn
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    consortium_id TEXT NOT NULL,
                    request_id TEXT,
                    iteration_id INTEGER,
                    timestamp TEXT NOT NULL,
                    prompt_text TEXT,
                    arbiter_model TEXT NOT NULL,
                    evaluated_models TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    confidence REAL,
                    refinement_areas TEXT,
                    token_usage_json TEXT NOT NULL,
                    duration_ms INTEGER,
                    error TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS model_performance (
                    model TEXT NOT NULL,
                    consortium_id TEXT NOT NULL,
                    iteration_id INTEGER,
                    confidence REAL,
                    token_usage INTEGER,
                    duration_ms INTEGER,
                    timestamp TEXT,
                    chosen_count INTEGER DEFAULT 0,
                    PRIMARY KEY (model, consortium_id, iteration_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_consortium ON evaluations(consortium_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_timestamp ON evaluations(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_model_performance_model ON model_performance(model)")
            if not self._is_memory:
                conn.commit()
        finally:
            pass

    def store_evaluation(self, consortium_id, iteration_id, prompt_text, arbiter_model, evaluated_models, decision, token_usage, duration_ms, request_id=None, error=None):
        db = self._get_connection()
        conn = db.conn
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO evaluations (
                    timestamp, consortium_id, request_id, iteration_id, prompt_text,
                    arbiter_model, evaluated_models, decision_json, confidence,
                    refinement_areas, token_usage_json, duration_ms, error
                ) VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                consortium_id, request_id, iteration_id, prompt_text[:2000],
                arbiter_model, json.dumps(evaluated_models), json.dumps(decision),
                decision.get("confidence", 0.0), json.dumps(decision.get("refinement_areas", [])),
                json.dumps(token_usage), duration_ms, error,
            ))
            evaluation_id = cursor.lastrowid
            self._update_model_performance(conn, consortium_id, iteration_id, evaluated_models, decision, token_usage, duration_ms)
            if not self._is_memory:
                conn.commit()
            return evaluation_id
        finally:
            pass

    def _update_model_performance(self, conn, consortium_id, iteration_id, evaluated_models, decision, token_usage, duration_ms):
        for model in evaluated_models:
            model_tokens = token_usage.get(model, 0)
            conn.execute("""
                INSERT OR REPLACE INTO model_performance (
                    model, consortium_id, iteration_id, confidence, token_usage, duration_ms, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (model, consortium_id, iteration_id, decision.get("confidence", 0.0), model_tokens, duration_ms))

    def get_leaderboard(self, limit=10, since=None, model_filter=None):
        db = self._get_connection()
        query = """
            SELECT model, COUNT(*) as total_evaluations, AVG(confidence) as avg_confidence,
            AVG(token_usage) as avg_tokens, SUM(chosen_count) * 100.0 / COUNT(*) as win_rate
            FROM model_performance
        """
        params = []
        if since:
            query += " WHERE timestamp >= ?"
            params.append(since)
        if model_filter:
            query += (" AND " if since else " WHERE ") + "model LIKE ?"
            params.append(f"%{model_filter}%")
        query += " GROUP BY model ORDER BY avg_confidence DESC, total_evaluations DESC"
        if limit:
            query += f" LIMIT {limit}"
        return list(dict(row) for row in db.query(query, params))

    def get_recent_runs(self, limit=10, since=None):
        db = self._get_connection()
        query = """
            SELECT DISTINCT consortium_id, timestamp, evaluated_models as models,
            arbiter_model as arbiter, confidence as final_confidence, iteration_id,
            token_usage_json, duration_ms as total_duration_ms
            FROM evaluations
        """
        params = []
        if since:
            query += " WHERE timestamp >= ?"
            params.append(since)
        query += " ORDER BY timestamp DESC"
        if limit:
            query += f" LIMIT {limit}"
        return list(dict(row) for row in db.query(query, params))

    def get_run_details(self, consortium_id):
        db = self._get_connection()
        run = list(db.query("SELECT * FROM evaluations WHERE consortium_id = ? ORDER BY iteration_id DESC LIMIT 1", [consortium_id]))
        return dict(run[0]) if run else {}

evaluation_store = EvaluationStore()

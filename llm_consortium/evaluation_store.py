"""
Evaluation store for persisting arbiter decisions and model performance data.
Enables leaderboard generation, A/B testing, and training data creation.
"""

import sqlite3
import json
import os
from typing import Optional, Dict, Any, List


class EvaluationStore:
    """
    Persistent storage for arbiter evaluations and model performance metrics.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize evaluation store.
        
        Args:
            db_path: Path to SQLite database. Defaults to ~/.llm_consortium/evaluations.db
                     Use ":memory:" for in-memory database.
        """
        if db_path is None:
            db_path = "~/.llm_consortium/evaluations.db"
        
        self.db_path = os.path.expanduser(db_path)
        self._is_memory = self.db_path == ":memory:"
        
        if not self._is_memory:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Initialize schema
        self._init_db()
        
        # For in-memory databases, keep connection open
        if self._is_memory:
            self._memory_conn = sqlite3.connect(self.db_path)
    
    def _get_connection(self):
        """Get database connection (persistent for memory, temporary for file)."""
        if self._is_memory and hasattr(self, '_memory_conn'):
            return self._memory_conn
        else:
            return sqlite3.connect(self.db_path)
    
    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_connection()
        try:
            # Main evaluations table
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
            
            # Model performance summary table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS model_performance (
                    model TEXT NOT NULL,
                    consortium_id TEXT NOT NULL,
                    iteration_id INTEGER,
                    confidence REAL,
                    token_usage INTEGER,
                    duration_ms INTEGER,
                    timestamp TEXT,
                    PRIMARY KEY (model, consortium_id, iteration_id)
                )
            """)
            
            # Create indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_evaluations_consortium 
                ON evaluations(consortium_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_evaluations_timestamp 
                ON evaluations(timestamp)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_evaluations_confidence 
                ON evaluations(confidence)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_performance_model 
                ON model_performance(model)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_performance_timestamp 
                ON model_performance(timestamp)
            """)
            
            if not self._is_memory:
                conn.commit()
        finally:
            if not self._is_memory:
                conn.close()
    
    def store_evaluation(
        self,
        consortium_id: str,
        iteration_id: int,
        prompt_text: str,
        arbiter_model: str,
        evaluated_models: List[str],
        decision: Dict[str, Any],
        token_usage: Dict[str, int],
        duration_ms: int,
        request_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> int:
        """
        Store an arbiter evaluation.
        
        Returns:
            Row ID of the inserted evaluation
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO evaluations (
                    timestamp,
                    consortium_id,
                    request_id,
                    iteration_id,
                    prompt_text,
                    arbiter_model,
                    evaluated_models,
                    decision_json,
                    confidence,
                    refinement_areas,
                    token_usage_json,
                    duration_ms,
                    error
                ) VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                consortium_id,
                request_id,
                iteration_id,
                prompt_text[:2000],
                arbiter_model,
                json.dumps(evaluated_models),
                json.dumps(decision),
                decision.get("confidence", 0.0),
                json.dumps(decision.get("refinement_areas", [])),
                json.dumps(token_usage),
                duration_ms,
                error,
            ))
            
            evaluation_id = cursor.lastrowid
            
            # Update model performance table
            self._update_model_performance(
                conn, consortium_id, iteration_id, evaluated_models, 
                decision, token_usage, duration_ms
            )
            
            if not self._is_memory:
                conn.commit()
            
            return evaluation_id
        finally:
            if not self._is_memory:
                conn.close()
    
    def _update_model_performance(
        self,
        conn: sqlite3.Connection,
        consortium_id: str,
        iteration_id: int,
        evaluated_models: List[str],
        decision: Dict[str, Any],
        token_usage: Dict[str, int],
        duration_ms: int,
    ):
        """Update model performance statistics."""
        for model in evaluated_models:
            model_tokens = token_usage.get(model, 0)
            
            conn.execute("""
                INSERT OR REPLACE INTO model_performance (
                    model,
                    consortium_id,
                    iteration_id,
                    confidence,
                    token_usage,
                    duration_ms,
                    timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                model,
                consortium_id,
                iteration_id,
                decision.get("confidence", 0.0),
                model_tokens,
                duration_ms,
            ))
    
    def get_leaderboard(self, limit: int = 10, since: str = None, model_filter: str = None) -> List[Dict[str, Any]]:
        """
        Get model performance leaderboard.
        """
        query = """
            SELECT 
                model,
                COUNT(*) as evaluation_count,
                AVG(confidence) as avg_confidence,
                SUM(token_usage) as total_tokens,
                AVG(token_usage) as avg_tokens_per_call,
                AVG(duration_ms) as avg_duration_ms,
                MIN(timestamp) as first_seen,
                MAX(timestamp) as last_seen
            FROM model_performance
        """
        
        params = []
        if since:
            query += " WHERE timestamp >= ?"
            params.append(since)
            
        query += """
            GROUP BY model
            ORDER BY avg_confidence DESC, evaluation_count DESC
            LIMIT ?
        """
        
        params.append(limit)
        
        conn = self._get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            if not self._is_memory:
                conn.close()


# Global evaluation store instance

    def get_leaderboard(self, limit: int = 10, since: str = None, model_filter: str = None) -> List[Dict[str, Any]]:
        """Get model performance leaderboard."""
        db = DatabaseConnection.get_connection()
        query = """
            SELECT 
                model,
                COUNT(*) as total_evaluations,
                AVG(confidence) as avg_confidence,
                AVG(total_tokens) as avg_tokens,
                SUM(CASE WHEN chosen = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
            FROM evaluations
        """
        
        conditions = []
        params = []
        
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
            
        if model_filter:
            conditions.append("model LIKE ?")
            params.append(f"%{model_filter}%")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        query += " GROUP BY model ORDER BY avg_confidence DESC, total_evaluations DESC"
        
        if limit:
            query += f" LIMIT {limit}"
            
        results = db.query(query, params)
        return list(dict(row) for row in results)
    def get_recent_runs(self, limit: int = 10, since: str = None) -> List[Dict[str, Any]]:
        """Get recent consortium runs."""
        db = DatabaseConnection.get_connection()
        query = """
            SELECT DISTINCT
                consortium_id,
                timestamp,
                models,
                arbiter,
                confidence as final_confidence,
                iteration_count,
                total_tokens,
                total_duration_ms
            FROM evaluations
        """
        
        conditions = []
        params = []
        
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        query += " ORDER BY timestamp DESC"
        
        if limit:
            query += f" LIMIT {limit}"
            
        results = db.query(query, params)
        return list(dict(row) for row in results)
    
    def export_training_data(self, output_path: str, since: str = None, 
                           model_filter: str = None, min_confidence: float = None) -> int:
        """Export evaluations as training data in JSONL format."""
        db = DatabaseConnection.get_connection()
        query = """
            SELECT 
                prompt,
                model,
                chosen,
                analysis,
                confidence,
                tokens,
                iteration,
                arbiter,
                models as all_models
            FROM evaluations
        """
        
        conditions = []
        params = []
        
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
            
        if model_filter:
            conditions.append("model LIKE ?")
            params.append(f"%{model_filter}%")
            
        if min_confidence:
            conditions.append("confidence >= ?")
            params.append(min_confidence)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        results = db.query(query, params)
        
        count = 0
        with open(output_path, 'w') as f:
            for row in results:
                sample = {
                    "prompt": row["prompt"],
                    "chosen": bool(row["chosen"]),
                    "model": row["model"],
                    "analysis": row["analysis"],
                    "confidence": row["confidence"],
                    "all_models": row["all_models"]
                }
                f.write(json.dumps(sample) + "\n")
                count += 1
                
        return count
    
    def get_run_details(self, consortium_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific consortium run."""
        db = DatabaseConnection.get_connection()
        
        # Get basic run info
        run_query = """
            SELECT DISTINCT
                consortium_id,
                timestamp,
                models,
                arbiter,
                confidence,
                iteration_count,
                total_tokens,
                total_duration_ms
            FROM evaluations
            WHERE consortium_id = ?
        """
        
        run_result = db.execute(run_query, [consortium_id]).fetchone()
        if not run_result:
            return None
            
        result = dict(run_result)
        
        # Get iteration details
        iter_query = """
            SELECT
                iteration,
                confidence,
                total_tokens,
                GROUP_CONCAT(model) as model_list
            FROM evaluations
            WHERE consortium_id = ?
            GROUP BY iteration, confidence, total_tokens
            ORDER BY iteration
        """
        
        iterations = []
        for row in db.query(iter_query, [consortium_id]):
            iterations.append({
                "iteration": row["iteration"],
                "confidence": row["confidence"],
                "tokens": row["total_tokens"],
                "model_responses": row["model_list"].split(",") if row["model_list"] else []
            })
            
        result["iterations"] = iterations
        
        # Get final synthesis details
        synth_query = """
            SELECT synthesis, final_prompt
            FROM evaluations
            WHERE consortium_id = ? AND iteration = ?
            ORDER BY confidence DESC
            LIMIT 1
        """
        
        # Get last iteration number
        last_iter = max([i["iteration"] for i in iterations]) if iterations else 1
        
        synth_result = db.execute(synth_query, [consortium_id, last_iter]).fetchone()
        if synth_result:
            result["final_synthesis"] = synth_result["synthesis"]
            result["final_prompt"] = synth_result["final_prompt"]
        else:
            result["final_synthesis"] = ""
            result["final_prompt"] = ""
            
        return result


# Export main components
__all__ = ['EvaluationStore', 'setup_evaluation_store', 'evaluation_store']
# Create module-level instance (if appropriate)
evaluation_store = EvaluationStore()  # Optional: provide module-level convenience instance

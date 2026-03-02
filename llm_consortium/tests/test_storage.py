import sqlite3
import pytest
from llm_consortium.db import (
    DatabaseConnection,
    save_consortium_run,
    save_consortium_member,
    save_arbiter_decision
)

@pytest.fixture
def memory_db():
    import sqlite_utils
    # Replace the thread-local db specifically for isolated tests
    conn = sqlite3.connect(":memory:")
    db = sqlite_utils.Database(conn)
    DatabaseConnection._thread_local.db = db
    # Re-initialize schema that gets skipped if thread_local avoids get_connection init
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
        CREATE TABLE IF NOT EXISTS responses (
            id TEXT PRIMARY KEY,
            prompt TEXT,
            response TEXT
        )
    """)
    yield db
    conn.close()

def test_save_consortium_run(memory_db):
    run_id = "test-run-123"
    save_consortium_run(
        run_id=run_id,
        strategy="default",
        judging_method="rank",
        confidence_threshold=0.9,
        max_iterations=5,
        iteration_count=3,
        final_confidence=0.95,
        user_prompt="Who painted the Mona Lisa?"
    )

    rows = list(memory_db["consortium_runs"].rows)
    assert len(rows) == 1
    assert rows[0]["id"] == run_id
    assert rows[0]["strategy"] == "default"
    assert rows[0]["final_confidence"] == 0.95

def test_save_consortium_member(memory_db):
    # Setup Foreign keys
    memory_db["consortium_runs"].insert({"id": "run-456"})
    memory_db["responses"].insert({"id": "resp-789", "prompt": "a", "response": "b"})

    save_consortium_member("run-456", "resp-789", "arbiter", 2, 0)
    
    rows = list(memory_db["consortium_members"].rows)
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-456"
    assert rows[0]["role"] == "arbiter"

def test_save_arbiter_decision(memory_db):
    memory_db["consortium_runs"].insert({"id": "run-999"})
    memory_db["responses"].insert({"id": "arbiter-resp-1", "prompt": "a", "response": "b"})
    memory_db["responses"].insert({"id": "chosen-resp-2", "prompt": "c", "response": "d"})

    save_arbiter_decision(
        "run-999",
        1,
        "arbiter-resp-1",
        {
            "chosen_response_id": "chosen-resp-2",
            "confidence": 0.88,
            "synthesis": "This is chosen",
            "ranking": ["chosen-resp-2"],
            "refinement_areas": []
        },
        "rank"
    )

    rows = list(memory_db["arbiter_decisions"].rows)
    assert len(rows) == 1
    assert rows[0]["chosen_response_id"] == "chosen-resp-2"
    assert rows[0]["confidence"] == 0.88

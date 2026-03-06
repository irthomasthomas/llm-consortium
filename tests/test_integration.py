import pytest
from unittest.mock import patch, MagicMock
import tempfile
import pathlib
import os

from llm_consortium.orchestrator import create_consortium
from llm_consortium.db import DatabaseConnection, user_dir

@pytest.fixture
def isolated_db(monkeypatch):
    """Fixture to provide an isolated database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        
        # Monkeypatch the user_dir function directly to point to our temp dir
        monkeypatch.setattr('llm_consortium.db.user_dir', lambda: tmp_path)
        
        # We need to clear any cached thread-local db connections
        if hasattr(DatabaseConnection._thread_local, 'db'):
            delattr(DatabaseConnection._thread_local, 'db')
            
        yield tmp_path
        
        # Cleanup
        if hasattr(DatabaseConnection._thread_local, 'db'):
            delattr(DatabaseConnection._thread_local, 'db')

@patch('llm_consortium.orchestrator.llm.get_model')
def test_full_orchestration_cycle(mock_get_model, isolated_db):
    """End-to-End integration test for the basic orchestration cycle."""
    
    # Set up mock models
    mock_member1 = MagicMock()
    mock_member2 = MagicMock()
    mock_arbiter = MagicMock()

    # Create dummy models for members
    member1_response = MagicMock()
    member1_response.text.return_value = "Response from model1. <confidence>0.9</confidence>"
    member1_response.id = "response-m1-1"
    mock_member1.prompt.return_value = member1_response

    member2_response = MagicMock()
    member2_response.text.return_value = "Response from model2. <confidence>0.8</confidence>"
    member2_response.id = "response-m2-1"
    mock_member2.prompt.return_value = member2_response

    # Create dummy model for arbiter
    arbiter_response = MagicMock()
    arbiter_response.id = "response-arb-1"
    # Provide a well-formed XML response that the arbiter would produce
    arbiter_response.text.return_value = """
<synthesis>The models agree that the earth is round.</synthesis>
<confidence>0.95</confidence>
<analysis>Both models provided consistent responses.</analysis>
<needs_iteration>false</needs_iteration>
    """
    mock_arbiter.prompt.return_value = arbiter_response

    # Configure mock_get_model to return the appropriate mock
    def side_effect(model_id):
        if model_id == "member1": return mock_member1
        if model_id == "member2": return mock_member2
        if model_id == "arbiter_model": return mock_arbiter
        return MagicMock() # fallback
        
    mock_get_model.side_effect = side_effect

    # Initialize orchestrator
    orchestrator = create_consortium(
        models=["member1:1", "member2:1"],
        arbiter="arbiter_model",
        confidence_threshold=0.8,
        max_iterations=2,
        minimum_iterations=1,
        manual_context=True,
        judging_method="default"
    )

    # Run orchestration
    result = orchestrator.orchestrate("Is the earth round?")

    # Verify result
    assert result is not None
    assert "The models agree that the earth is round." in result["synthesis"]["synthesis"]
    assert result["synthesis"]["confidence"] == 0.95
    assert not result["synthesis"]["needs_iteration"]
    
    assert len(result["iterations"]) == 1 # converged after 1 iteration

    # Verify real DB logging happened
    db = DatabaseConnection.get_connection()
    
    # Check runs table
    runs = list(db["consortium_runs"].rows)
    assert len(runs) == 1
    run_id = runs[0]["id"]
    assert runs[0]["user_prompt"] == "Is the earth round?"
    assert runs[0]["iteration_count"] == 1
    assert runs[0]["final_confidence"] == 0.95
    
    # Check members table
    members = list(db["consortium_members"].rows)
    # 2 members + 1 arbiter = 3 responses
    assert len(members) == 3
    
    # Check decisions table
    decisions = list(db["arbiter_decisions"].rows)
    assert len(decisions) == 1
    assert decisions[0]["run_id"] == run_id
    assert decisions[0]["iteration"] == 1
    assert decisions[0]["confidence"] == 0.95

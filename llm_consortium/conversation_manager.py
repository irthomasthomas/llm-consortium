"""
Conversation Manager for LLM Consortium
Handles proper llm conversation management with persistence
"""

import llm
import json
import pathlib
import sqlite_utils
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import logging
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

@dataclass
class ConsortiumResponse:
    """Structured representation of consortium response"""
    model_id: str
    content: str
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    timestamp: str = ""
    conversation_id: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.conversation_id:
            self.conversation_id = str(uuid.uuid4())

class ConversationManager:
    """Manages LLM conversations with proper persistence"""
    
    def __init__(self, db_path: Optional[pathlib.Path] = None):
        if db_path is None:
            self.db_path = pathlib.Path.home() / '.config' / 'llm-consortium' / 'conversations.db'
        else:
            self.db_path = db_path
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite_utils.Database(self.db_path)
        self._init_tables()
        
    def _init_tables(self):
        """Initialize database tables for conversation management"""
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS consortium_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                prompt TEXT NOT NULL,
                strategy TEXT NOT NULL,
                models TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                final_result TEXT,
                metadata_json TEXT
            );
            
            CREATE TABLE IF NOT EXISTS model_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                response_content TEXT NOT NULL,
                confidence REAL,
                reasoning TEXT,
                iteration INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES consortium_sessions(session_id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_session_id ON model_responses(session_id);
            CREATE INDEX IF NOT EXISTS idx_conversation_id ON model_responses(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_timestamp ON model_responses(timestamp);
        """)
    
    def create_session(self, prompt: str, strategy: str, models: List[str]) -> str:
        """Create a new consortium session"""
        session_id = str(uuid.uuid4())
        
        self.db['consortium_sessions'].insert({
            'session_id': session_id,
            'prompt': prompt,
            'strategy': strategy,
            'models': json.dumps(models),
            'created_at': datetime.now().isoformat(),
            'metadata_json': json.dumps({})
        })
        
        return session_id
    
    def get_or_create_conversation(self, model_id: str, session_id: str) -> llm.Conversation:
        """Get or create a conversation for a specific model in a session"""
        try:
            # Try to get the model
            model = llm.get_model(model_id)
            if not model:
                raise ValueError(f"Model {model_id} not found")
            
            # Create a new conversation for each session
            conversation = model.conversation()
            
            logger.info(f"Created new conversation for model {model_id} in session {session_id}")
            return conversation
            
        except Exception as e:
            logger.error(f"Error creating conversation for model {model_id}: {e}")
            raise
    
    def send_prompt(self, conversation: llm.Conversation, prompt: str, 
                   system_prompt: Optional[str] = None) -> str:
        """Send a prompt to a conversation and return the response"""
        try:
            # Add system message if provided
            if system_prompt:
                conversation.prompt(prompt, system=system_prompt, stream=False)
            else:
                conversation.prompt(prompt, stream=False)

            # Get the latest response
            if conversation.responses:
                return conversation.responses[-1].text()
            else:
                logger.error("No response received from model")
                return ""
                
        except Exception as e:
            logger.error(f"Error sending prompt: {e}")
            raise
    
    def store_response(self, session_id: str, model_id: str, 
                      conversation_id: str, response_content: str,
                      confidence: Optional[float] = None,
                      reasoning: Optional[str] = None,
                      iteration: int = 0) -> int:
        """Store a model response in the database"""
        return self.db['model_responses'].insert({
            'session_id': session_id,
            'model_id': model_id,
            'conversation_id': conversation_id,
            'response_content': response_content,
            'confidence': confidence,
            'reasoning': reasoning,
            'iteration': iteration,
            'timestamp': datetime.now().isoformat()
        }).last_pk
    
    def get_session_responses(self, session_id: str, iteration: Optional[int] = None) -> List[Dict]:
        """Get all responses for a session, optionally filtered by iteration"""
        query = "SELECT * FROM model_responses WHERE session_id = ?"
        params = [session_id]
        
        if iteration is not None:
            query += " AND iteration = ?"
            params.append(iteration)
            
        query += " ORDER BY timestamp"
        
        return list(self.db.execute(query, params))
    
    def complete_session(self, session_id: str, final_result: str, metadata: Dict = None):
        """Mark a session as completed with final result"""
        update_data = {
            'completed_at': datetime.now().isoformat(),
            'final_result': final_result
        }
        
        if metadata:
            update_data['metadata_json'] = json.dumps(metadata)
        
        self.db['consortium_sessions'].update(session_id, update_data, pk='session_id')
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """Get session information"""
        try:
            return next(iter(self.db.execute(
                "SELECT * FROM consortium_sessions WHERE session_id = ?", 
                [session_id]
            )))
        except StopIteration:
            return None

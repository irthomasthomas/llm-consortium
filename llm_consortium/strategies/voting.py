"""Voting Strategy for llm-consortium.

This strategy selects the most common answer from multiple model responses,
implementing a consensus-based approach to model selection.
"""

from .base import ConsortiumStrategy
from typing import List, Dict, Any
from collections import Counter
import difflib
import re
import logging

logger = logging.getLogger(__name__)

class VotingStrategy(ConsortiumStrategy):
    """
    Strategy that selects the most common answer from multiple model responses.
    
    Strategy parameters (passed via params dict):
        - similarity_threshold: float (default 0.5)
          Threshold for considering two responses as similar (0.0-1.0)
        - answer_length: int (default 100)
          Number of characters to compare for similarity matching
        - require_majority: bool (default False)
          If True, only select consensus if majority (>50%) agree
        - fallback_to_all: bool (default True)
          If no consensus found, use all responses instead of filtering
    """
    
    def _validate_params(self):
        """Validate strategy-specific parameters"""
        self.similarity_threshold = float(
            self.params.get('similarity_threshold', 0.5)
        )
        self.answer_length = int(
            self.params.get('answer_length', 100)
        )
        self.require_majority = bool(
            self.params.get('require_majority', False)
        )
        self.fallback_to_all = bool(
            self.params.get('fallback_to_all', True)
        )
        
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")
        if self.answer_length < 10:
            raise ValueError("answer_length must be at least 10 characters")
    
    def initialize_state(self):
        """Initialize voting tracking state"""
        super().initialize_state()
        self.iteration_state['voting_history'] = []
        self.iteration_state['consensus_count'] = 0
        self.iteration_state['no_consensus_count'] = 0
    
    def select_models(self, available_models: Dict[str, int], 
                     current_prompt: str, iteration: int) -> Dict[str, int]:
        """Return all available models (voting happens in process_responses)"""
        logger.debug(f"[VotingStrategy Iteration {iteration}] Using all models: {available_models}")
        return available_models.copy()
    
    def _add_voting_metadata(self, responses: List[Dict[str, Any]], 
                           selected: bool, group_size: int, total: int):
        """Add voting metadata to responses."""
        for response in responses:
            response['voting_selected'] = selected
            response['voting_group_size'] = group_size
            response['voting_total'] = total
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text snippets."""
        # Normalize texts: lowercase, remove extra whitespace and punctuation
        def normalize(text):
            text = text.lower()
            # Remove common punctuation
            text = re.sub(r'[^\w\s]', '', text)
            # Normalize whitespace
            text = re.sub(r'\s+', ' ', text.strip())
            return text
        
        norm1 = normalize(text1)
        norm2 = normalize(text2)
        
        # Use difflib's sequence matcher for similarity
        similarity = difflib.SequenceMatcher(None, norm1, norm2).ratio()
        return similarity
    
    def _group_similar_responses(self, responses: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Group responses by similarity."""
        if not responses:
            return []
        
        groups = []
        used_indices = set()
        
        for i, response in enumerate(responses):
            if i in used_indices:
                continue
            
            # Start a new group
            current_group = [response]
            current_text = response['response'][:self.answer_length]
            used_indices.add(i)
            
            # Find all similar responses (only those with higher similarity)
            for j, other in enumerate(responses):
                if j <= i or j in used_indices:
                    continue
                
                other_text = other['response'][:self.answer_length]
                similarity = self._calculate_similarity(current_text, other_text)
                
                # Only add to group if similarity is high enough
                if similarity >= self.similarity_threshold:
                    current_group.append(other)
                    used_indices.add(j)
                    other['similarity_to_group'] = similarity
            
            groups.append(current_group)
        
        return groups
    
    def process_responses(self, successful_responses: List[Dict[str, Any]], 
                         iteration: int) -> List[Dict[str, Any]]:
        """Select most common answer from responses."""
        if not successful_responses:
            return []
        
        # Initialize state if needed
        if 'voting_history' not in self.iteration_state:
            self.iteration_state['voting_history'] = []
        if 'consensus_count' not in self.iteration_state:
            self.iteration_state['consensus_count'] = 0
        if 'no_consensus_count' not in self.iteration_state:
            self.iteration_state['no_consensus_count'] = 0
        
        if len(successful_responses) == 1:
            # Only one response, return it with voting metadata
            self._add_voting_metadata(successful_responses, True, 1, 1)
            self.iteration_state['voting_history'].append({
                'iteration': iteration,
                'groups': [{'size': 1, 'responses': successful_responses}],
                'selected': 'single_response'
            })
            return successful_responses
        
        # Group similar responses
        groups = self._group_similar_responses(successful_responses)
        
        # Find the largest group
        largest_group = max(groups, key=len)
        largest_size = len(largest_group)
        total_responses = len(successful_responses)
        
        # Check if we have a consensus
        has_consensus = False
        if self.require_majority:
            has_consensus = largest_size > total_responses / 2
        else:
            # Just pick the largest group, even if it's not a majority
            has_consensus = True
        
        # Record voting history
        self.iteration_state['voting_history'].append({
            'iteration': iteration,
            'groups': [{'size': len(g), 'responses': g} for g in groups],
            'selected_group_size': largest_size,
            'total_responses': total_responses,
            'consensus': has_consensus
        })
        
        if has_consensus:
            # Return responses from the consensus group
            self.iteration_state['consensus_count'] += 1
            logger.info(f"[VotingStrategy Iteration {iteration}] "
                       f"Consensus found: {largest_size}/{total_responses} responses agree")
            
            self._add_voting_metadata(largest_group, True, largest_size, total_responses)
            return largest_group
        else:
            # No consensus
            self.iteration_state['no_consensus_count'] += 1
            logger.info(f"[VotingStrategy Iteration {iteration}] "
                       f"No consensus: largest group {largest_size}/{total_responses}")
            
            if self.fallback_to_all:
                # Return all responses with voting metadata (marked as not selected)
                self._add_voting_metadata(successful_responses, False, largest_size, total_responses)
                return successful_responses
            else:
                # Return empty list to signal no consensus
                return []
    
    def update_state(self, iteration_context: 'IterationContext'):
        """Update voting statistics after iteration completes."""
        # Ensure counters are initialized
        if 'consensus_count' not in self.iteration_state:
            self.iteration_state['consensus_count'] = 0
        if 'no_consensus_count' not in self.iteration_state:
            self.iteration_state['no_consensus_count'] = 0
        
        # The main work is done in process_responses, but we can log stats here
        consensus_rate = (
            self.iteration_state['consensus_count'] / 
            max(1, self.iteration_state['consensus_count'] + self.iteration_state['no_consensus_count'])
        )
        
        logger.debug(f"[VotingStrategy] Consensus rate: {consensus_rate:.2%} "
                    f"({self.iteration_state['consensus_count']} consensus, "
                    f"{self.iteration_state['no_consensus_count']} no consensus)")

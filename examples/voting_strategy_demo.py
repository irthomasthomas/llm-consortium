"""Demonstration of the VotingStrategy in action."""

import logging
from llm_consortium.strategies.voting import VotingStrategy
from unittest.mock import Mock

# Enable logging to see the strategy in action
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def demo_voting_strategy():
    """Demonstrate the voting strategy with various scenarios."""
    
    print("=== VotingStrategy Demonstration ===\n")
    
    # Create strategy with custom parameters
    mock_orchestrator = Mock()
    strategy = VotingStrategy(mock_orchestrator, {
        'similarity_threshold': 0.6,  # Lower threshold for demo
        'answer_length': 50,
        'require_majority': False,  # Don't require majority for demo
        'fallback_to_all': True
    })
    strategy.initialize_state()
    
    print(f"Strategy initialized with parameters:")
    print(f"  - Similarity threshold: {strategy.similarity_threshold}")
    print(f"  - Answer comparison length: {strategy.answer_length}")
    print(f"  - Require majority: {strategy.require_majority}")
    print(f"  - Fallback to all: {strategy.fallback_to_all}")
    print()
    
    # Scenario 1: Clear consensus
    print("Scenario 1: Clear consensus")
    responses1 = [
        {'model': 'gpt-4', 'response': 'The capital of France is Paris, located in Western Europe.'},
        {'model': 'claude', 'response': 'Paris is the capital city of France in Western Europe.'},
        {'model': 'gemini', 'response': 'The capital of France is Paris, which is in Western Europe.'},
        {'model': 'llama', 'response': 'Actually, the capital is Lyon.'}
    ]
    
    result1 = strategy.process_responses(responses1, 1)
    print(f"  Total responses: {len(responses1)}")
    print(f"  Selected responses: {len(result1)}")
    print(f"  Models selected: {[r['model'] for r in result1]}")
    print(f"  Consensus reached: {result1 and result1[0]['voting_selected']}")
    print()
    
    # Scenario 2: No clear consensus
    print("Scenario 2: No clear consensus")
    responses2 = [
        {'model': 'gpt-4', 'response': 'The best programming language is Python.'},
        {'model': 'claude', 'response': 'JavaScript is the most versatile language.'},
        {'model': 'gemini', 'response': 'Rust offers the best performance.'},
        {'model': 'llama', 'response': 'Go is excellent for concurrency.'}
    ]
    
    result2 = strategy.process_responses(responses2, 2)
    print(f"  Total responses: {len(responses2)}")
    print(f"  Selected responses: {len(result2)}")
    print(f"  All responses used (fallback): {len(result2) == len(responses2)}")
    print(f"  Consensus reached: {result2 and result2[0]['voting_selected']}")
    print()
    
    # Scenario 3: Majority requirement
    print("Scenario 3: With majority requirement")
    strategy.require_majority = True
    
    responses3 = [
        {'model': 'gpt-4', 'response': 'Answer: 42'},
        {'model': 'claude', 'response': 'The answer is 42'},
        {'model': 'gemini', 'response': '42 is the answer'},
        {'model': 'llama', 'response': 'The answer is 24'}
    ]
    
    result3 = strategy.process_responses(responses3, 3)
    print(f"  Total responses: {len(responses3)}")
    print(f"  Selected responses: {len(result3)}")
    print(f"  Majority found: {len(result3) > len(responses3) / 2}")
    print()
    
    # Show voting statistics
    print("Voting Statistics:")
    history = strategy.iteration_state['voting_history']
    for i, record in enumerate(history, 1):
        print(f"  Iteration {i}: {record['selected_group_size']}/{record['total_responses']} "
              f"in consensus group (Consensus: {record.get('consensus', 'N/A')})")
    
    print(f"\nTotal consensus rate: {strategy.iteration_state['consensus_count']}/{len(history)}")
    
    print("\n✅ VotingStrategy demonstration complete!")

if __name__ == "__main__":
    demo_voting_strategy()

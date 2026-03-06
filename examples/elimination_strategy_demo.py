"""Demonstration of the EliminationStrategy in action."""

import logging
from llm_consortium import create_consortium

# Enable debug logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def demo_elimination_strategy():
    """Demonstrate the elimination strategy with synthetic models."""
    
    # Create a consortium with elimination strategy
    orchestrator = create_consortium(
        models={
            'gpt-4o-mini': 2,  # Fast, cheap models
            'claude-3-haiku': 2,
            'gemini-1.5-flash': 1,
        },
        arbiter='claude-3-opus-20240229',
        judging_method='rank', # Required: Elimination now relies on Arbiter rankings
        strategy='elimination',
        strategy_params={
            'eliminate_count': 1,  # Eliminate the lowest-ranked model each iteration
            'keep_minimum': 2,     # Always keep at least 2 models
            'elimination_delay': 1 # Start eliminating after 1st iteration
        },
        confidence_threshold=0.8,
        max_iterations=4,
        minimum_iterations=2
    )
    
    # Run with a complex prompt that might produce varying confidence
    prompt = """
    Analyze the potential economic impacts of universal basic income (UBI) 
    in developed countries over the next 20 years. Consider:
    1. Labor market effects
    2. Inflationary pressures  
    3. Social welfare outcomes
    4. Fiscal sustainability
    
    Provide specific examples and cite relevant studies where possible.
    """
    
    logger.info("Running consortium with elimination strategy...")
    result = orchestrator.orchestrate(prompt)
    
    # Analyze the results
    print("\n" + "="*60)
    print("ELIMINATION STRATEGY RESULTS")
    print("="*60)
    
    print(f"\nFinal confidence: {result['synthesis']['confidence']:.2f}")
    print(f"Total iterations: {result['metadata']['total_iterations']}")
    
    print("\nIteration details:")
    for i, iteration in enumerate(result['iterations'], 1):
        selected = list(iteration['selected_models'].keys())
        successful = len([r for r in iteration['model_responses'] if 'error' not in r])
        
        print(f"  Iteration {i}:")
        print(f"    Selected models: {selected}")
        print(f"    Successful responses: {successful}")
        print(f"    Synthesis confidence: {iteration['synthesis']['confidence']:.2f}")
        
        if i > 1:
            prev_selected = list(result['iterations'][i-2]['selected_models'].keys())
            eliminated = set(prev_selected) - set(selected)
            if eliminated:
                print(f"    Models eliminated: {list(eliminated)}")
    
    print("\nFinal synthesis:")
    print(result['synthesis']['synthesis'][:500] + "..." if len(result['synthesis']['synthesis']) > 500 else result['synthesis']['synthesis'])
    
    return result

if __name__ == "__main__":
    # Run the demo
    result = demo_elimination_strategy()

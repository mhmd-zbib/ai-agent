"""
Error handling example.

Demonstrates how the agent handles various error conditions:
- Invalid tool parameters
- Tool execution errors
- Non-existent tools
- Edge cases

Run with:
    python -m app.modules.agent.examples.error_handling
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.modules.agent.llm.openai_client import OpenAIClient
from app.modules.agent.schemas import AgentInput
from app.modules.agent.services.agent_service import AgentService
from app.modules.agent.services.tool_executor import ToolExecutor
from app.modules.tools import get_tool_registry
from app.shared.config import get_settings


def main():
    """Run error handling example."""
    print("=" * 80)
    print("ERROR HANDLING EXAMPLE")
    print("=" * 80)
    print()
    
    # Initialize components
    settings = get_settings()
    
    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY not set in environment")
        print("Please set it in your .env file or environment variables")
        return
    
    print("Initializing agent components...")
    
    # Create LLM client
    llm = OpenAIClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        system_prompt=settings.agent_system_prompt
    )
    
    # Create tool registry and executor
    tool_registry = get_tool_registry()
    tool_executor = ToolExecutor(tool_registry)
    
    print(f"✓ Tool registry loaded with {len(tool_registry._tools)} tools")
    print()
    
    # Create agent service
    agent_service = AgentService(
        llm=llm,
        tool_executor=tool_executor,
        tool_registry=tool_registry
    )
    
    # Test cases that might trigger errors
    test_cases = [
        {
            "message": "Calculate: 1/0",
            "description": "Division by zero error"
        },
        {
            "message": "What is the result of invalid_syntax@@#?",
            "description": "Invalid mathematical expression"
        },
        {
            "message": "Calculate something complex: import os; os.system('ls')",
            "description": "Attempting code injection"
        },
        {
            "message": "Just tell me about your capabilities without using tools",
            "description": "Normal chat (no tool needed)"
        },
    ]
    
    print("Testing error handling scenarios...")
    print("=" * 80)
    print()
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test Case {i}: {test_case['description']}")
        print("-" * 80)
        print(f"User: {test_case['message']}")
        print()
        
        # Create agent input
        agent_input = AgentInput(
            user_message=test_case['message'],
            session_id="error-test-session",
            history=[]
        )
        
        # Generate response
        try:
            response = agent_service.respond(agent_input, response_mode="chat")
            
            print(f"Agent: {response.message}")
            print()
            
            if response.tool_calls:
                print(f"✓ Tool Called: {response.tool_calls[0].name}")
                print(f"  Arguments: {response.tool_calls[0].arguments}")
                
                if response.tool_results:
                    result = response.tool_results[0].output
                    print(f"  Result: {result}")
                    
                    # Check if result contains error
                    if "error" in result.lower() or "invalid" in result.lower():
                        print("  ⚠ Tool returned error (handled gracefully)")
                    else:
                        print("  ✓ Tool executed successfully")
            else:
                print("⚠ No tool was called (expected for some cases)")
            
            print("✓ Request handled successfully (no crash)")
            
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            print("  This indicates an unhandled error case")
            import traceback
            traceback.print_exc()
        
        print()
        print()
    
    print("=" * 80)
    print("Error handling test complete!")
    print("All error cases should be handled gracefully without crashes.")
    print("=" * 80)


if __name__ == "__main__":
    main()

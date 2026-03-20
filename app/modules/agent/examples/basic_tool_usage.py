"""
Basic tool usage example.

Demonstrates a simple calculator tool execution through the agent flow.
Shows how the agent automatically detects when to use tools and executes them.

Run with:
    python -m app.modules.agent.examples.basic_tool_usage
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
    """Run basic tool usage example."""
    print("=" * 80)
    print("BASIC TOOL USAGE EXAMPLE")
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
    
    print(f"✓ Tool registry loaded with {len(tool_registry._tools)} tools:")
    for tool_name in tool_registry._tools.keys():
        print(f"  - {tool_name}")
    print()
    
    # Create agent service
    agent_service = AgentService(
        llm=llm,
        tool_executor=tool_executor,
        tool_registry=tool_registry
    )
    
    # Test cases
    test_cases = [
        {
            "message": "What is 25 * 4?",
            "expected": "calculator tool"
        },
        {
            "message": "Calculate the value of 100 + 50 - 25",
            "expected": "calculator tool"
        },
        {
            "message": "What is 2 + 2?",
            "expected": "calculator tool"
        }
    ]
    
    # Run test cases
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test Case {i}")
        print("-" * 80)
        print(f"User: {test_case['message']}")
        print(f"Expected: Should use {test_case['expected']}")
        print()
        
        # Create agent input
        agent_input = AgentInput(
            user_message=test_case['message'],
            session_id="example-session",
            history=[]
        )
        
        # Generate response with chat mode (which includes tools)
        try:
            response = agent_service.respond(agent_input, response_mode="chat")
            
            print(f"Agent: {response.message}")
            print()
            
            if response.tool_calls:
                print(f"✓ Tool Called: {response.tool_calls[0].name}")
                print(f"  Arguments: {response.tool_calls[0].arguments}")
                
                if response.tool_results:
                    print(f"  Result: {response.tool_results[0].output}")
            else:
                print("⚠ No tool was called")
            
            print()
            
        except Exception as e:
            print(f"✗ Error: {e}")
            print()
        
        print()
    
    print("=" * 80)
    print("Example complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()

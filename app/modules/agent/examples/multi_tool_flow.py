"""
Multi-tool flow example.

Demonstrates using multiple tools in a conversation flow.
Shows how the agent can chain tool usage and handle different tool types.

Run with:
    python -m app.modules.agent.examples.multi_tool_flow
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
    """Run multi-tool flow example."""
    print("=" * 80)
    print("MULTI-TOOL FLOW EXAMPLE")
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
    
    # Simulate a conversation with multiple tool uses
    conversation_history = []
    
    test_messages = [
        "What is 15 * 8?",
        "Now add 20 to that result",
        "What's the square root of 144?",
    ]
    
    print("Starting conversation with multiple tool uses...")
    print("=" * 80)
    print()
    
    for i, message in enumerate(test_messages, 1):
        print(f"Turn {i}")
        print("-" * 80)
        print(f"User: {message}")
        print()
        
        # Create agent input with conversation history
        agent_input = AgentInput(
            user_message=message,
            session_id="multi-tool-session",
            history=conversation_history
        )
        
        # Generate response
        try:
            response = agent_service.respond(agent_input, response_mode="chat")
            
            print(f"Agent: {response.message}")
            print()
            
            if response.tool_calls:
                print(f"✓ Tool Used: {response.tool_calls[0].name}")
                print(f"  Arguments: {response.tool_calls[0].arguments}")
                
                if response.tool_results:
                    print(f"  Result: {response.tool_results[0].output}")
            else:
                print("⚠ No tool was called")
            
            # Add to conversation history
            conversation_history.append({
                "role": "user",
                "content": message
            })
            conversation_history.append({
                "role": "assistant",
                "content": response.message
            })
            
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
        
        print()
        print()
    
    print("=" * 80)
    print("Multi-tool conversation complete!")
    print(f"Total turns: {len(conversation_history) // 2}")
    print("=" * 80)


if __name__ == "__main__":
    main()

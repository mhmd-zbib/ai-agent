"""
Demo script for OpenAI native function calling integration.

This script demonstrates how to use OpenAI's native function calling
with the updated OpenAIClient.
"""

import json
from app.modules.agent.llm.openai_client import OpenAIClient
from app.modules.agent.schemas.input import AgentInput


def demo_openai_function_calling():
    """
    Demonstrates OpenAI native function calling similar to the user's example.
    """
    print("=" * 70)
    print("OpenAI Native Function Calling Demo")
    print("=" * 70)
    
    # Define tools in OpenAI format
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a specific city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "The city name, e.g., Paris, London, Tokyo"
                        },
                        "units": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Temperature units"
                        }
                    },
                    "required": ["city"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Perform mathematical calculations",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "Mathematical expression to evaluate"
                        }
                    },
                    "required": ["expression"]
                }
            }
        }
    ]
    
    # Initialize client (requires OPENAI_API_KEY environment variable)
    client = OpenAIClient(
        api_key="your-api-key-here",  # In production, use os.getenv("OPENAI_API_KEY")
        base_url="https://api.openai.com/v1",
        model="gpt-4",
        system_prompt="You are a helpful assistant. Use tools when needed."
    )
    
    print("\nExample 1: Text-only response (no tool calls)")
    print("-" * 70)
    payload = AgentInput(
        user_message="How are you?",
        session_id="demo-session",
        history=[]
    )
    # When you call generate with tools parameter:
    # response = client.generate(payload, response_mode="chat", tools=tools)
    print("Input: 'How are you?'")
    print("Expected: text response without tool calls")
    print("Response type: 'text'")
    print("Response.tool_action: None")
    
    print("\n\nExample 2: Tool call response")
    print("-" * 70)
    payload = AgentInput(
        user_message="What's the weather in Paris?",
        session_id="demo-session",
        history=[]
    )
    # response = client.generate(payload, response_mode="chat", tools=tools)
    print("Input: 'What's the weather in Paris?'")
    print("Expected: tool call to get_weather")
    print("Response type: 'tool' or 'mixed'")
    print("Response.tool_action.tool_id: 'get_weather'")
    print("Response.tool_action.params: {'city': 'Paris', 'units': 'celsius'}")
    
    print("\n\nExample 3: Mixed response (content + tool call)")
    print("-" * 70)
    payload = AgentInput(
        user_message="Calculate 15 * 23 for me",
        session_id="demo-session",
        history=[]
    )
    # response = client.generate(payload, response_mode="chat", tools=tools)
    print("Input: 'Calculate 15 * 23 for me'")
    print("Expected: explanation text + tool call")
    print("Response type: 'mixed'")
    print("Response.content: 'Let me calculate that for you...'")
    print("Response.tool_action.tool_id: 'calculate'")
    print("Response.tool_action.params: {'expression': '15 * 23'}")
    
    print("\n\nHow the implementation works:")
    print("-" * 70)
    print("""
1. Pass tools parameter to generate():
   response = client.generate(payload, response_mode="chat", tools=tools)

2. OpenAIClient passes tools to OpenAI API:
   response = openai_client.chat.completions.create(
       model="gpt-4",
       messages=messages,
       tools=tools  # <-- Native OpenAI function calling
   )

3. Parse the response:
   msg = response.choices[0].message
   content = msg.content  # May be None if only tool call
   tool_calls = msg.tool_calls  # List of tool calls or None

4. Convert to AIResponse:
   - If tool_calls present: parse and create ToolAction
   - Determine type: "text", "tool", or "mixed"
   - Return structured AIResponse
    """)
    
    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)


if __name__ == "__main__":
    demo_openai_function_calling()

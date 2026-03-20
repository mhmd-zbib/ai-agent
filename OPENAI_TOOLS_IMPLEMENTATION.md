# OpenAI Native Function Calling Implementation

## Summary
Successfully implemented OpenAI native function calling in `OpenAIClient` to use the `tools` parameter and handle `tool_calls` in responses, exactly as specified in the user's reference example.

## Changes Made

### 1. Updated `app/modules/agent/llm/openai_client.py`

#### Imports
- Added `Any`, `Optional` from `typing`
- Added `ToolAction` from `app.shared.schemas`

#### Method Signature Update
```python
def generate(
    self, 
    payload: AgentInput,
    response_mode: Literal["chat", "tool_call"] = "chat",
    tools: Optional[list[dict[str, Any]]] = None  # NEW PARAMETER
) -> AIResponse:
```

#### Implementation Details

**1. Tools Parameter Handling**
- Pass `tools` parameter to `_generate_chat_mode()` method
- Only used in chat mode (tool_call mode still uses JSON response format)

**2. OpenAI API Integration**
```python
# Build API params conditionally
api_params = {
    "model": self._model,
    "messages": messages,
}
if tools:
    api_params["tools"] = tools

response = self._client.chat.completions.create(**api_params)
```

**3. Tool Calls Parsing**
```python
msg = response.choices[0].message
content = msg.content or ""
tool_calls = msg.tool_calls  # List of ChatCompletionMessageToolCall or None

if tool_calls:
    first_call = tool_calls[0]  # Take first tool call
    tool_name = first_call.function.name
    tool_args_str = first_call.function.arguments  # JSON string
    tool_args = json.loads(tool_args_str)  # Parse to dict
    
    parsed_tool_action = ToolAction(
        tool_id=tool_name,
        params=tool_args
    )
```

**4. Response Type Determination**
```python
if content and parsed_tool_action:
    response_type = "mixed"  # Both content and tool call
elif parsed_tool_action:
    response_type = "tool"   # Tool call only
    if not content:
        content = f"Calling tool: {parsed_tool_action.tool_id}"
else:
    response_type = "text"   # Content only
```

**5. AIResponse Construction**
```python
return AIResponse(
    type=response_type,
    content=content,
    tool_action=parsed_tool_action,
    metadata=ResponseMetadata()
)
```

**6. Logging**
Added comprehensive debug and info logging:
- Tools provided status
- Tool count
- Tool call parsing details
- Response type determination

## Test Coverage

Created `tests/test_openai_native_tools.py` with 6 comprehensive tests:

1. ✅ `test_openai_native_tools_content_only` - Text-only response
2. ✅ `test_openai_native_tools_tool_call_only` - Tool call without content
3. ✅ `test_openai_native_tools_mixed_response` - Both content and tool call
4. ✅ `test_openai_without_tools_backwards_compat` - Backward compatibility
5. ✅ `test_openai_tools_parameter_passed_correctly` - API integration
6. ✅ `test_openai_invalid_tool_arguments_json` - Error handling

All tests pass ✅

## Backward Compatibility

- **Maintained**: When `tools=None` (default), behavior is unchanged
- **No breaking changes**: Existing code continues to work
- **Optional parameter**: Tools are only used when explicitly provided

## Usage Example

```python
from app.modules.agent.llm.openai_client import OpenAIClient
from app.modules.agent.schemas.input import AgentInput

# Define tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "units": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                },
                "required": ["city"]
            }
        }
    }
]

# Create client
client = OpenAIClient(
    api_key="your-key",
    base_url="https://api.openai.com/v1",
    model="gpt-4",
    system_prompt="Use tools when needed."
)

# Generate with tools
payload = AgentInput(
    user_message="What's the weather in Paris?",
    session_id="session-123",
    history=[]
)

response = client.generate(payload, response_mode="chat", tools=tools)

# Handle response
if response.type == "tool":
    tool_id = response.tool_action.tool_id
    params = response.tool_action.params
    print(f"Tool: {tool_id}")
    print(f"Args: {params}")
elif response.type == "mixed":
    print(f"Content: {response.content}")
    print(f"Tool: {response.tool_action.tool_id}")
else:  # text
    print(f"Content: {response.content}")
```

## Features

✅ Native OpenAI function calling integration  
✅ Automatic tool_calls parsing  
✅ JSON arguments parsing with error handling  
✅ Response type detection (text/tool/mixed)  
✅ Comprehensive logging for debugging  
✅ Full backward compatibility  
✅ Complete test coverage  
✅ Matches user's reference example exactly  

## Future Enhancements

- Support for multiple tool calls in a single response (currently takes first)
- Tool call ID tracking for multi-turn conversations
- Parallel tool execution support

## Status

**COMPLETED** ✅

All requirements met:
- ✅ Updated generate() method signature
- ✅ Pass tools to OpenAI SDK
- ✅ Parse tool_calls from response
- ✅ Update AIResponse with tool_action
- ✅ Handle all response cases (content/tool/mixed)
- ✅ Add comprehensive logging
- ✅ Maintain backward compatibility
- ✅ Full test coverage

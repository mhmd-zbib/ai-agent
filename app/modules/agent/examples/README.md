# Agent Tool Integration Examples

This directory contains example scripts demonstrating how the agent service integrates with tools for function calling.

## Overview

The agent system now supports OpenAI native function calling, allowing the LLM to automatically select and execute tools based on user queries. These examples show the complete flow from user input to tool execution.

## Examples

### 1. Basic Tool Usage (`basic_tool_usage.py`)

Demonstrates simple calculator tool execution:
- Shows how the agent detects when to use tools
- Executes mathematical calculations
- Returns formatted results

**Run:**
```bash
python -m app.modules.agent.examples.basic_tool_usage
```

### 2. Multi-Tool Flow (`multi_tool_flow.py`)

Shows a conversation with multiple tool uses:
- Chains multiple tool calls
- Maintains conversation context
- Demonstrates tool selection logic

**Run:**
```bash
python -m app.modules.agent.examples.multi_tool_flow
```

### 3. Error Handling (`error_handling.py`)

Tests various error scenarios:
- Invalid tool parameters
- Mathematical errors (division by zero, invalid syntax)
- Security (code injection attempts)
- Graceful degradation

**Run:**
```bash
python -m app.modules.agent.examples.error_handling
```

## Architecture

The tool integration flow:

1. **ToolRegistry** - Central registry of all available tools
   - Stores tool definitions with parameters
   - Provides tools in OpenAI format via `get_tools_for_openai()`

2. **AgentService** - Orchestrates LLM and tool execution
   - Gets tools from registry
   - Passes tools to LLM client
   - Executes tool_calls when returned

3. **OpenAIClient** - Communicates with OpenAI API
   - Accepts `tools` parameter
   - Returns tool_calls in AIResponse
   - Supports native function calling

4. **ToolExecutor** - Executes tool calls
   - Resolves tool by name
   - Runs with provided arguments
   - Returns results

## Prerequisites

Before running examples:

1. Set up your environment:
   ```bash
   cp .env.example .env
   # Add your OPENAI_API_KEY to .env
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Ensure OpenAI API key is configured:
   ```bash
   export OPENAI_API_KEY="your-key-here"
   ```

## Available Tools

The examples use these tools (from `app/modules/tools/implementations/`):

- **calculator** - Performs mathematical calculations
- **web_search** - Searches the web (placeholder)
- **document_lookup** - RAG document search (placeholder)

## Key Features

✅ **Native Function Calling** - Uses OpenAI's built-in tool support  
✅ **Automatic Tool Selection** - LLM decides when to use tools  
✅ **Error Handling** - Gracefully handles tool errors  
✅ **Logging** - Comprehensive debug logging throughout  
✅ **Type Safety** - Full type hints and Pydantic validation  

## Extending

To add new tools:

1. Create tool class in `app/modules/tools/implementations/`
2. Extend `BaseTool` with `name`, `description`, `parameters`
3. Implement `run()` method
4. Register in `app/modules/tools/__init__.py`

Example:
```python
class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Input value"}
        },
        "required": ["input"]
    }
    
    def run(self, arguments: dict) -> str:
        return f"Result: {arguments['input']}"
```

## Troubleshooting

**No tool calls happening:**
- Check that tools are registered in `get_tool_registry()`
- Verify tools are passed to LLM via `tools` parameter
- Check system prompt mentions tool usage

**Tool execution errors:**
- Verify tool parameters match schema
- Check tool implementation handles edge cases
- Review logs for detailed error messages

**API errors:**
- Confirm OPENAI_API_KEY is set
- Check API rate limits
- Verify model supports function calling (gpt-3.5-turbo, gpt-4, etc.)

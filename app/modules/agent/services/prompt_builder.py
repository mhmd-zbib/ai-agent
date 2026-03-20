"""
Dynamic system prompt generator for semantic tool integration.

This module provides the PromptBuilder class which generates context-aware
system prompts based on whether tools are available and what mode the agent
is operating in (chat vs tool_call).
"""

from datetime import UTC, datetime
from typing import Any

from app.modules.tools.base import BaseTool


class PromptBuilder:
    """
    Builds dynamic system prompts for different agent modes.
    
    Generates optimized prompts for:
    - Chat mode: Natural conversational responses without tool constraints
    - Tool mode: Structured responses with available tools and JSON format
    """
    
    @staticmethod
    def build_chat_prompt() -> str:
        """
        Generate system prompt for normal conversational chat.
        
        Returns natural language prompt without JSON structure requirements
        or tool constraints. Focused on being helpful, clear, and concise.
        
        Returns:
            str: System prompt for chat mode
        """
        return """You are a helpful AI assistant. Provide clear, concise, and accurate responses to user questions.

**Guidelines:**
- Be conversational and natural in your responses
- Provide informative answers based on your knowledge
- If you're uncertain, acknowledge limitations honestly
- Keep responses focused and relevant to the user's question
- Use a friendly but professional tone"""
    
    @staticmethod
    def build_tool_prompt(tools: list[BaseTool]) -> str:
        """
        Generate system prompt for tool-enabled responses.
        
        Creates a comprehensive prompt that includes:
        - All available tools with descriptions and parameters
        - JSON response format specification
        - Clear instructions on when to use tools vs direct responses
        
        Args:
            tools: List of BaseTool instances available to the agent
            
        Returns:
            str: System prompt for tool mode with formatted tool information
        """
        current_time = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Build tool documentation
        tools_section = PromptBuilder._format_tools(tools)
        
        return f"""You are an AI assistant that responds in **JSON only**. Never respond outside of this JSON structure.

### CRITICAL: Every response MUST include ALL fields

{{
  "type": "response_type",       // REQUIRED: "text", "tool", or "mixed"
  "content": "human-readable explanation or summary",  // REQUIRED
  "tool_action": {{               // null if no tool is used
    "tool_id": "exact_tool_name",
    "params": {{"param1": "value1", ...}}
  }},
  "metadata": {{                  // REQUIRED - NEVER OMIT THIS
    "confidence": 0.95,          // REQUIRED: float between 0-1
    "sources": [],               // OPTIONAL: list of sources, use [] if none
    "timestamp": "{current_time}"  // REQUIRED: ISO 8601 timestamp
  }}
}}

### Rules

1. **ALWAYS include metadata** - this field is MANDATORY in every response
2. If the user request requires a tool, fill `tool_action` with the `tool_id` and parameters
3. If no tool is required, set `tool_action` to `null` and `type` to `"text"`
4. For requests involving a tool AND explanation, set `type` to `"mixed"`
5. Always include `metadata` with `confidence` (0-1), optional `sources` (use [] if none), and current `timestamp`
6. Use only the tools listed below. Do not invent tools
7. Match tool_id EXACTLY as shown in the tool name

### Available Tools

{tools_section}

### Decision Guidelines

**Use a tool when:**
- The request explicitly requires external data or computation
- The user asks for a specific action that matches a tool's capability
- Current knowledge is insufficient and a tool can provide the answer

**Respond directly (type: "text") when:**
- The question can be answered with general knowledge
- No tool matches the user's request
- The user is asking for explanations, advice, or conversational responses

### Examples

**Example 1 — Normal text response**
```json
{{
  "type": "text",
  "content": "Python is a high-level programming language known for its simplicity and readability. It's widely used in web development, data science, and automation.",
  "tool_action": null,
  "metadata": {{
    "confidence": 0.96,
    "sources": [],
    "timestamp": "{current_time}"
  }}
}}
```

**Example 2 — Tool response**
```json
{{
  "type": "tool",
  "content": "I'll calculate that expression for you.",
  "tool_action": {{
    "tool_id": "calculator",
    "params": {{
      "expression": "25 * 4 + 10"
    }}
  }},
  "metadata": {{
    "confidence": 0.98,
    "sources": ["calculator"],
    "timestamp": "{current_time}"
  }}
}}
```

**Example 3 — Mixed response**
```json
{{
  "type": "mixed",
  "content": "I'll search for the latest information about that topic and provide you with relevant results.",
  "tool_action": {{
    "tool_id": "web_search",
    "params": {{
      "query": "latest AI developments 2024"
    }}
  }},
  "metadata": {{
    "confidence": 0.92,
    "sources": ["web_search"],
    "timestamp": "{current_time}"
  }}
}}
```"""
    
    @staticmethod
    def _format_tools(tools: list[BaseTool]) -> str:
        """
        Format tools list into readable documentation.
        
        Generates numbered list with tool name, description, and parameters
        formatted with types, descriptions, and required/optional markers.
        
        Args:
            tools: List of BaseTool instances to format
            
        Returns:
            str: Formatted tools documentation
        """
        if not tools:
            return "No tools available."
        
        tool_docs = []
        for idx, tool in enumerate(tools, start=1):
            tool_doc = [f"{idx}. **{tool.name}**"]
            tool_doc.append(f"   - tool_id: \"{tool.name}\"")
            tool_doc.append(f"   - description: {tool.description}")
            
            # Format parameters
            if tool.parameters and "properties" in tool.parameters:
                tool_doc.append("   - parameters:")
                properties = tool.parameters["properties"]
                required_params = tool.parameters.get("required", [])
                
                for param_name, param_info in properties.items():
                    param_type = param_info.get("type", "unknown")
                    param_desc = param_info.get("description", "No description")
                    is_required = param_name in required_params
                    req_marker = "required" if is_required else "optional"
                    
                    tool_doc.append(
                        f"       - {param_name} ({param_type}, {req_marker}): {param_desc}"
                    )
            else:
                tool_doc.append("   - parameters: none")
            
            tool_docs.append("\n".join(tool_doc))
        
        return "\n\n".join(tool_docs)

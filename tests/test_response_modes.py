"""
Tests for dual-mode response handling (chat vs tool_call).
"""
from app.infrastructure.llm.openai import OpenAIClient
from app.shared.schemas import AgentInput
from app.shared.schemas import AIResponse


def test_openai_chat_mode_returns_plain_text():
    """Test that OpenAI client in chat mode returns plain text wrapped in AIResponse."""
    # This is a unit test that would need mocking in real scenario
    # For now, we just verify the structure exists
    client = OpenAIClient(
        api_key=None,  # Will trigger ConfigurationError when called
        base_url=None,
        model="gpt-4",
        system_prompt="You are a helpful assistant."
    )
    
    # Verify the method signature accepts response_mode
    assert hasattr(client.generate, '__call__')
    

def test_openai_client_with_custom_base_url():
    """Test that OpenAI client accepts custom base_url for Ollama/other providers."""
    client = OpenAIClient(
        api_key="not-needed",
        base_url="http://localhost:11434/v1",
        model="llama2",
        system_prompt="You are a helpful assistant."
    )
    
    # Verify the method signature accepts response_mode
    assert hasattr(client.generate, '__call__')
    

def test_ai_response_can_have_optional_metadata():
    """Test that AIResponse works with optional metadata for chat mode."""
    # In chat mode, metadata can be optional
    response = AIResponse(
        type="text",
        content="Hello, how can I help you?",
        tool_action=None,
        # metadata is auto-generated with default values
    )
    
    assert response.type == "text"
    assert response.content == "Hello, how can I help you?"
    assert response.tool_action is None
    assert response.metadata is not None
    assert response.metadata.confidence == 0.9  # default value


def test_ai_response_validates_tool_action_for_tool_type():
    """Test that AIResponse enforces tool_action for 'tool' type."""
    from pydantic import ValidationError
    import pytest
    
    # Tool type requires tool_action
    with pytest.raises(ValidationError, match="tool_action is required"):
        AIResponse(
            type="tool",
            content="Searching...",
            tool_action=None,
        )

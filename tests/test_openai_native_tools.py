"""
Tests for OpenAI native function calling integration.
"""
import json
from unittest.mock import Mock, MagicMock
import pytest

from app.modules.agent.llm.openai_client import OpenAIClient
from app.modules.agent.schemas import AgentInput
from app.shared.schemas import AIResponse


@pytest.fixture
def openai_client():
    """Create a mock OpenAI client for testing."""
    client = OpenAIClient(
        api_key="test-key",
        base_url="https://test.openai.com",
        model="gpt-4",
        system_prompt="You are a helpful assistant."
    )
    # Mock the OpenAI client
    client._client = Mock()
    return client


@pytest.fixture
def sample_tools():
    """Sample tools definition."""
    return [
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


def test_openai_native_tools_content_only(openai_client, sample_tools):
    """Test response with content only (no tool calls)."""
    # Mock response with only content
    mock_message = Mock()
    mock_message.content = "I'm doing great, thank you!"
    mock_message.tool_calls = None
    
    mock_choice = Mock()
    mock_choice.message = mock_message
    
    mock_response = Mock()
    mock_response.choices = [mock_choice]
    
    openai_client._client.chat.completions.create = Mock(return_value=mock_response)
    
    payload = AgentInput(user_message="How are you?", session_id="test-session", history=[])
    response = openai_client.generate(payload, response_mode="chat", tools=sample_tools)
    
    assert response.type == "text"
    assert response.content == "I'm doing great, thank you!"
    assert response.tool_action is None


def test_openai_native_tools_tool_call_only(openai_client, sample_tools):
    """Test response with tool call only (no content)."""
    # Mock response with tool call
    mock_function = Mock()
    mock_function.name = "get_weather"
    mock_function.arguments = json.dumps({"city": "Paris", "units": "celsius"})
    
    mock_tool_call = Mock()
    mock_tool_call.function = mock_function
    
    mock_message = Mock()
    mock_message.content = None
    mock_message.tool_calls = [mock_tool_call]
    
    mock_choice = Mock()
    mock_choice.message = mock_message
    
    mock_response = Mock()
    mock_response.choices = [mock_choice]
    
    openai_client._client.chat.completions.create = Mock(return_value=mock_response)
    
    payload = AgentInput(user_message="What's the weather in Paris?", session_id="test-session", history=[])
    response = openai_client.generate(payload, response_mode="chat", tools=sample_tools)
    
    assert response.type == "tool"
    assert "get_weather" in response.content  # Default content when none provided
    assert response.tool_action is not None
    assert response.tool_action.tool_id == "get_weather"
    assert response.tool_action.params == {"city": "Paris", "units": "celsius"}


def test_openai_native_tools_mixed_response(openai_client, sample_tools):
    """Test response with both content and tool call."""
    # Mock response with both content and tool call
    mock_function = Mock()
    mock_function.name = "get_weather"
    mock_function.arguments = json.dumps({"city": "London", "units": "fahrenheit"})
    
    mock_tool_call = Mock()
    mock_tool_call.function = mock_function
    
    mock_message = Mock()
    mock_message.content = "Let me check the weather for you."
    mock_message.tool_calls = [mock_tool_call]
    
    mock_choice = Mock()
    mock_choice.message = mock_message
    
    mock_response = Mock()
    mock_response.choices = [mock_choice]
    
    openai_client._client.chat.completions.create = Mock(return_value=mock_response)
    
    payload = AgentInput(user_message="What's the weather in London?", session_id="test-session", history=[])
    response = openai_client.generate(payload, response_mode="chat", tools=sample_tools)
    
    assert response.type == "mixed"
    assert response.content == "Let me check the weather for you."
    assert response.tool_action is not None
    assert response.tool_action.tool_id == "get_weather"
    assert response.tool_action.params == {"city": "London", "units": "fahrenheit"}


def test_openai_without_tools_backwards_compat(openai_client):
    """Test that the client works without tools parameter (backward compatibility)."""
    # Mock response without tools
    mock_message = Mock()
    mock_message.content = "Hello! How can I help you?"
    mock_message.tool_calls = None
    
    mock_choice = Mock()
    mock_choice.message = mock_message
    
    mock_response = Mock()
    mock_response.choices = [mock_choice]
    
    openai_client._client.chat.completions.create = Mock(return_value=mock_response)
    
    payload = AgentInput(user_message="Hello", session_id="test-session", history=[])
    response = openai_client.generate(payload, response_mode="chat")  # No tools
    
    assert response.type == "text"
    assert response.content == "Hello! How can I help you?"
    assert response.tool_action is None


def test_openai_tools_parameter_passed_correctly(openai_client, sample_tools):
    """Test that tools parameter is passed to OpenAI API."""
    # Mock response
    mock_message = Mock()
    mock_message.content = "Test"
    mock_message.tool_calls = None
    
    mock_choice = Mock()
    mock_choice.message = mock_message
    
    mock_response = Mock()
    mock_response.choices = [mock_choice]
    
    openai_client._client.chat.completions.create = Mock(return_value=mock_response)
    
    payload = AgentInput(user_message="Test", session_id="test-session", history=[])
    openai_client.generate(payload, response_mode="chat", tools=sample_tools)
    
    # Verify tools were passed to the API
    call_args = openai_client._client.chat.completions.create.call_args
    assert call_args[1]["tools"] == sample_tools


def test_openai_invalid_tool_arguments_json(openai_client, sample_tools):
    """Test handling of invalid JSON in tool arguments."""
    # Mock response with invalid JSON in arguments
    mock_function = Mock()
    mock_function.name = "get_weather"
    mock_function.arguments = "invalid json {"  # Invalid JSON
    
    mock_tool_call = Mock()
    mock_tool_call.function = mock_function
    
    mock_message = Mock()
    mock_message.content = None
    mock_message.tool_calls = [mock_tool_call]
    
    mock_choice = Mock()
    mock_choice.message = mock_message
    
    mock_response = Mock()
    mock_response.choices = [mock_choice]
    
    openai_client._client.chat.completions.create = Mock(return_value=mock_response)
    
    payload = AgentInput(user_message="Test", session_id="test-session", history=[])
    
    # Should raise an error due to invalid JSON
    with pytest.raises(Exception):
        openai_client.generate(payload, response_mode="chat", tools=sample_tools)


def test_openai_multiple_tool_calls_selects_first_valid(openai_client, sample_tools):
    """When multiple valid tool calls are returned, the first valid one is used."""
    first_function = Mock()
    first_function.name = "get_weather"
    first_function.arguments = json.dumps({"city": "Paris", "units": "celsius"})

    second_function = Mock()
    second_function.name = "get_weather"
    second_function.arguments = json.dumps({"city": "London", "units": "fahrenheit"})

    first_tool_call = Mock()
    first_tool_call.function = first_function

    second_tool_call = Mock()
    second_tool_call.function = second_function

    mock_message = Mock()
    mock_message.content = None
    mock_message.tool_calls = [first_tool_call, second_tool_call]

    mock_choice = Mock()
    mock_choice.message = mock_message

    mock_response = Mock()
    mock_response.choices = [mock_choice]

    openai_client._client.chat.completions.create = Mock(return_value=mock_response)

    payload = AgentInput(user_message="Check weather", session_id="test-session", history=[])
    response = openai_client.generate(payload, response_mode="chat", tools=sample_tools)

    assert response.type == "tool"
    assert response.tool_action is not None
    assert response.tool_action.tool_id == "get_weather"
    assert response.tool_action.params == {"city": "Paris", "units": "celsius"}


def test_openai_multiple_tool_calls_skips_invalid_and_uses_next_valid(openai_client, sample_tools):
    """If earlier tool calls are invalid, the first valid subsequent call is used."""
    invalid_function = Mock()
    invalid_function.name = "get_weather"
    invalid_function.arguments = "invalid json {"

    valid_function = Mock()
    valid_function.name = "get_weather"
    valid_function.arguments = json.dumps({"city": "Rome", "units": "celsius"})

    invalid_tool_call = Mock()
    invalid_tool_call.function = invalid_function

    valid_tool_call = Mock()
    valid_tool_call.function = valid_function

    mock_message = Mock()
    mock_message.content = "Let me check that for you."
    mock_message.tool_calls = [invalid_tool_call, valid_tool_call]

    mock_choice = Mock()
    mock_choice.message = mock_message

    mock_response = Mock()
    mock_response.choices = [mock_choice]

    openai_client._client.chat.completions.create = Mock(return_value=mock_response)

    payload = AgentInput(user_message="Check weather", session_id="test-session", history=[])
    response = openai_client.generate(payload, response_mode="chat", tools=sample_tools)

    assert response.type == "mixed"
    assert response.tool_action is not None
    assert response.tool_action.tool_id == "get_weather"
    assert response.tool_action.params == {"city": "Rome", "units": "celsius"}


def test_openai_multiple_tool_calls_all_invalid_raises_error(openai_client, sample_tools):
    """If all returned tool calls are invalid, generation fails."""
    first_invalid = Mock()
    first_invalid.name = "get_weather"
    first_invalid.arguments = "invalid json {"

    second_invalid = Mock()
    second_invalid.name = "get_weather"
    second_invalid.arguments = "still invalid json {"

    first_tool_call = Mock()
    first_tool_call.function = first_invalid

    second_tool_call = Mock()
    second_tool_call.function = second_invalid

    mock_message = Mock()
    mock_message.content = None
    mock_message.tool_calls = [first_tool_call, second_tool_call]

    mock_choice = Mock()
    mock_choice.message = mock_message

    mock_response = Mock()
    mock_response.choices = [mock_choice]

    openai_client._client.chat.completions.create = Mock(return_value=mock_response)

    payload = AgentInput(user_message="Check weather", session_id="test-session", history=[])

    with pytest.raises(Exception):
        openai_client.generate(payload, response_mode="chat", tools=sample_tools)

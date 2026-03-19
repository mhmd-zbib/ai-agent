"""
Standardized response schemas for AI agent responses.

This module defines Pydantic models for structured JSON responses
that the AI agent returns, ensuring consistency across all interactions.
"""

from datetime import UTC, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ToolAction(BaseModel):
    """
    Represents a tool or action to be executed.
    
    Attributes:
        tool_id: Unique identifier for the tool/action to execute
        params: Dictionary of parameters required for the tool execution
    """
    
    tool_id: str = Field(..., description="Unique identifier for the tool to execute")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters required for tool execution"
    )
    
    @field_validator('tool_id')
    @classmethod
    def validate_tool_id(cls, v: str) -> str:
        """Ensure tool_id is not empty."""
        if not v or not v.strip():
            raise ValueError("tool_id cannot be empty")
        return v.strip()


class ResponseMetadata(BaseModel):
    """
    Metadata about the AI response.
    
    Attributes:
        confidence: Confidence score between 0 and 1 indicating certainty
        sources: Optional list of data sources or APIs used
        timestamp: ISO 8601 timestamp when the response was generated
    """
    
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0 and 1"
    )
    sources: Optional[List[str]] = Field(
        default=None,
        description="List of sources or APIs consulted"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO 8601 timestamp of response generation"
    )
    
    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is within valid range."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0 and 1")
        return round(v, 2)


class AIResponse(BaseModel):
    """
    Standardized JSON response structure for AI agent interactions.
    
    This model ensures all AI responses follow a consistent format,
    making it easier for clients to parse and handle responses.
    
    Attributes:
        type: Type of response - "text" (explanation only), 
              "tool" (action required), or "mixed" (both)
        content: Human-readable explanation or summary of the response
        tool_action: Optional tool/action to execute if type is "tool" or "mixed"
        metadata: Additional metadata about the response including confidence and sources
    
    Example:
        {
            "type": "tool",
            "content": "I'll search for weather information in New York",
            "tool_action": {
                "tool_id": "weather_api",
                "params": {"city": "New York", "units": "metric"}
            },
            "metadata": {
                "confidence": 0.95,
                "sources": ["weather_api"],
                "timestamp": "2024-03-20T10:30:00Z"
            }
        }
    """
    
    type: Literal["text", "tool", "mixed"] = Field(
        ...,
        description="Response type: text, tool, or mixed"
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Human-readable explanation or summary"
    )
    tool_action: Optional[ToolAction] = Field(
        default=None,
        description="Tool action to execute (required if type is 'tool' or 'mixed')"
    )
    metadata: ResponseMetadata = Field(
        ...,
        description="Response metadata including confidence and sources"
    )
    
    @field_validator('tool_action')
    @classmethod
    def validate_tool_action(cls, v: Optional[ToolAction], info) -> Optional[ToolAction]:
        """
        Validate that tool_action is present when type requires it.
        
        For 'tool' and 'mixed' types, tool_action must be provided.
        For 'text' type, tool_action should be None.
        """
        response_type = info.data.get('type')
        
        if response_type in ('tool', 'mixed') and v is None:
            raise ValueError(f"tool_action is required when type is '{response_type}'")
        
        if response_type == 'text' and v is not None:
            raise ValueError("tool_action must be None when type is 'text'")
        
        return v
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "text",
                    "content": "The weather in Paris is currently sunny with 22°C.",
                    "tool_action": None,
                    "metadata": {
                        "confidence": 0.98,
                        "sources": ["weather_cache"],
                        "timestamp": "2024-03-20T10:30:00Z"
                    }
                },
                {
                    "type": "tool",
                    "content": "Fetching current weather data for London",
                    "tool_action": {
                        "tool_id": "weather_api",
                        "params": {"city": "London", "units": "metric"}
                    },
                    "metadata": {
                        "confidence": 0.95,
                        "sources": ["weather_api"],
                        "timestamp": "2024-03-20T10:30:00Z"
                    }
                }
            ]
        }
    }

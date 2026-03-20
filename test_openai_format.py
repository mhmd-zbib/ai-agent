#!/usr/bin/env python3
"""Test script to verify OpenAI tool format conversion."""

import json
from app.modules.tools.implementations.calculator import CalculatorTool
from app.modules.tools.implementations.web_search import WebSearchTool
from app.modules.tools.implementations.document_lookup import DocumentLookupTool
from app.modules.tools.converters import tools_to_openai_format


def test_individual_conversion():
    """Test individual tool conversion."""
    print("=" * 80)
    print("Testing individual tool conversion")
    print("=" * 80)
    
    calculator = CalculatorTool()
    openai_format = calculator.to_openai_tool()
    
    print("\n✓ CalculatorTool OpenAI format:")
    print(json.dumps(openai_format, indent=2))
    
    # Verify structure
    assert openai_format["type"] == "function"
    assert "function" in openai_format
    assert openai_format["function"]["name"] == "calculator"
    assert "description" in openai_format["function"]
    assert "parameters" in openai_format["function"]
    assert openai_format["function"]["parameters"]["type"] == "object"
    assert "properties" in openai_format["function"]["parameters"]
    assert "required" in openai_format["function"]["parameters"]
    
    print("\n✓ Structure validation passed!")


def test_batch_conversion():
    """Test batch conversion of all tools."""
    print("\n" + "=" * 80)
    print("Testing batch conversion")
    print("=" * 80)
    
    tools = [
        CalculatorTool(),
        WebSearchTool(),
        DocumentLookupTool()
    ]
    
    openai_tools = tools_to_openai_format(tools)
    
    print(f"\n✓ Converted {len(openai_tools)} tools")
    
    for i, tool_def in enumerate(openai_tools):
        tool_name = tool_def["function"]["name"]
        print(f"\n{i+1}. {tool_name}")
        print(f"   Description: {tool_def['function']['description'][:60]}...")
        print(f"   Parameters: {list(tool_def['function']['parameters']['properties'].keys())}")
        print(f"   Required: {tool_def['function']['parameters']['required']}")
    
    # Verify all tools have correct structure
    for tool_def in openai_tools:
        assert tool_def["type"] == "function"
        assert "function" in tool_def
        assert "name" in tool_def["function"]
        assert "description" in tool_def["function"]
        assert "parameters" in tool_def["function"]
    
    print("\n✓ All tools converted successfully!")
    
    return openai_tools


def test_parameters_schema():
    """Test that parameters schema matches OpenAI expectations."""
    print("\n" + "=" * 80)
    print("Testing parameter schema compatibility")
    print("=" * 80)
    
    tools = [CalculatorTool(), WebSearchTool(), DocumentLookupTool()]
    
    for tool in tools:
        openai_format = tool.to_openai_tool()
        params = openai_format["function"]["parameters"]
        
        print(f"\n✓ {tool.name}:")
        print(f"  - Has 'type': {params.get('type') == 'object'}")
        print(f"  - Has 'properties': {'properties' in params}")
        print(f"  - Has 'required': {'required' in params}")
        
        # All properties should have type and description
        for prop_name, prop_def in params["properties"].items():
            assert "type" in prop_def, f"Missing 'type' for {prop_name}"
            assert "description" in prop_def, f"Missing 'description' for {prop_name}"
            print(f"  - Parameter '{prop_name}': type={prop_def['type']}, has description=True")
    
    print("\n✓ All parameter schemas are valid!")


def test_openai_compatibility():
    """Test that the output is compatible with OpenAI API format."""
    print("\n" + "=" * 80)
    print("Testing OpenAI API compatibility")
    print("=" * 80)
    
    tools = tools_to_openai_format([CalculatorTool(), WebSearchTool(), DocumentLookupTool()])
    
    # This is the format OpenAI expects
    expected_structure = {
        "type": str,
        "function": {
            "name": str,
            "description": str,
            "parameters": {
                "type": str,
                "properties": dict,
                "required": list
            }
        }
    }
    
    def validate_structure(obj, expected, path=""):
        if isinstance(expected, dict):
            for key, value_type in expected.items():
                assert key in obj, f"Missing key '{key}' at {path}"
                validate_structure(obj[key], value_type, f"{path}.{key}")
        elif isinstance(expected, type):
            assert isinstance(obj, expected), f"Wrong type at {path}: expected {expected}, got {type(obj)}"
    
    for tool in tools:
        validate_structure(tool, expected_structure)
    
    print("\n✓ All tools match OpenAI API structure!")
    print("\n📋 Sample tool ready for OpenAI API:")
    print(json.dumps(tools[0], indent=2))


if __name__ == "__main__":
    try:
        test_individual_conversion()
        test_batch_conversion()
        test_parameters_schema()
        test_openai_compatibility()
        
        print("\n" + "=" * 80)
        print("✅ All tests passed! Tools are ready for OpenAI function calling.")
        print("=" * 80)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

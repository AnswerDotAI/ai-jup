"""Tests for the server handlers."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _blocks_to_text(blocks: list) -> str:
    """Helper to convert system prompt blocks to text for assertions."""
    return " ".join(block["text"] for block in blocks)


def test_build_system_prompt():
    """Test the system prompt building logic."""
    from ai_jup.handlers import PromptHandler
    
    # Create a mock handler to test the method
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_system_prompt = PromptHandler._build_system_prompt.__get__(handler, MockHandler)
    
    # Test with empty context - returns list of content blocks
    blocks = handler._build_system_prompt("", {}, {})
    assert isinstance(blocks, list)
    assert len(blocks) >= 1
    # First block should have cache_control
    assert blocks[0].get("cache_control") == {"type": "ephemeral"}
    prompt = _blocks_to_text(blocks)
    assert "AI assistant" in prompt
    assert "Jupyter notebook" in prompt
    print("✓ Basic system prompt works with caching")
    
    # Test with preceding code
    blocks = handler._build_system_prompt("import pandas as pd\nx = 5", {}, {})
    prompt = _blocks_to_text(blocks)
    assert "Preceding Code" in prompt
    assert "import pandas as pd" in prompt
    # Dynamic content should be in second block without cache_control
    assert len(blocks) == 2
    assert "cache_control" not in blocks[1]
    print("✓ System prompt with preceding code works")
    
    # Test with variables
    variables = {
        "df": {"type": "DataFrame", "repr": "   A  B\n0  1  2"},
        "x": {"type": "int", "repr": "42"}
    }
    blocks = handler._build_system_prompt("", variables, {})
    prompt = _blocks_to_text(blocks)
    assert "Available Variables" in prompt
    assert "df" in prompt
    assert "DataFrame" in prompt
    print("✓ System prompt with variables works")
    
    # Test with functions
    functions = {
        "calculate": {
            "signature": "(x: int, y: int) -> int",
            "docstring": "Add two numbers",
            "parameters": {"x": {"type": "int"}, "y": {"type": "int"}}
        }
    }
    blocks = handler._build_system_prompt("", {}, functions)
    prompt = _blocks_to_text(blocks)
    assert "Available Functions" in prompt
    assert "calculate" in prompt
    print("✓ System prompt with functions works")


def test_build_tools():
    """Test the tool building logic."""
    from ai_jup.handlers import PromptHandler
    
    class MockHandler:
        pass
    
    handler = MockHandler()
    handler._build_tools = PromptHandler._build_tools.__get__(handler, MockHandler)
    handler._python_type_to_json_schema = PromptHandler._python_type_to_json_schema.__get__(handler, MockHandler)
    
    # Test with empty functions
    tools = handler._build_tools({})
    assert tools == []
    print("✓ Empty tools works")
    
    # Test with functions
    functions = {
        "calculate": {
            "signature": "(x: int, y: int) -> int",
            "docstring": "Add two numbers",
            "parameters": {"x": {"type": "int"}, "y": {"type": "int"}}
        }
    }
    tools = handler._build_tools(functions)
    assert len(tools) == 1
    assert tools[0]["name"] == "calculate"
    assert "input_schema" in tools[0]
    print("✓ Tool building works")


if __name__ == '__main__':
    test_build_system_prompt()
    test_build_tools()
    print("\n✅ All handler tests passed!")

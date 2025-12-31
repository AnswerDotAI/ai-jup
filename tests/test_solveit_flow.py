"""End-to-end tests replicating SolveIt-style tool calling functionality.

Tests the core workflow from fast.ai's SolveIt:
1. Define Python functions in a notebook
2. Expose them to the AI as tools
3. Ask the AI to use them
4. Verify the tool call/result loop works

Run with: RUN_HAIKU_TESTS=1 ANTHROPIC_API_KEY=key pytest tests/test_solveit_flow.py -v
"""

import json
import os

import httpx
import pytest

BASE_URL = os.environ.get("JUPYTER_BASE_URL", "http://localhost:8888")
TOKEN = os.environ.get("JUPYTER_TOKEN", "debug-token")
MODEL = "claude-3-haiku-20240307"

pytestmark = [
    pytest.mark.external,
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("SKIP_LLM_TESTS") or not os.environ.get("ANTHROPIC_API_KEY"),
        reason="LLM tests skipped (set ANTHROPIC_API_KEY, or unset SKIP_LLM_TESTS)",
    ),
]


async def collect_sse_events(response) -> list[dict]:
    """Parse SSE stream into list of event dicts."""
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest.mark.asyncio
async def test_tool_call_flow():
    """Test that AI can call a Python function exposed as a tool.
    
    This replicates SolveIt's core feature: expose a function with &`function_name`
    and have the AI call it to accomplish a task.
    """
    # Define a simple function that the AI should call
    functions_context = {
        "multiply": {
            "signature": "(x: int, y: int) -> int",
            "docstring": "Multiply two integers and return the result.",
            "parameters": {
                "x": {"type": "integer", "description": "First number"},
                "y": {"type": "integer", "description": "Second number"},
            },
        }
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
            json={
                "prompt": "Please use the multiply tool to calculate 7 times 8 and tell me the result.",
                "context": {
                    "functions": functions_context,
                    "variables": {},
                    "preceding_code": "def multiply(x: int, y: int) -> int:\n    return x * y",
                },
                "model": MODEL,
            },
        ) as response:
            assert response.status_code == 200
            events = await collect_sse_events(response)
    
    # Verify we got a tool_call event
    tool_calls = [e for e in events if "tool_call" in e]
    assert len(tool_calls) > 0, f"Expected tool_call event, got: {events}"
    assert tool_calls[0]["tool_call"]["name"] == "multiply"
    
    # Verify we got tool_input events with the arguments
    tool_inputs = [e for e in events if "tool_input" in e]
    assert len(tool_inputs) > 0, f"Expected tool_input events, got: {events}"
    full_input = "".join(e["tool_input"] for e in tool_inputs)
    # The input should contain 7 and 8
    assert "7" in full_input and "8" in full_input, f"Expected 7 and 8 in tool input: {full_input}"
    
    # Verify done event
    done_events = [e for e in events if e.get("done")]
    assert len(done_events) == 1


@pytest.mark.asyncio
async def test_tool_with_context_variables():
    """Test that AI can see both variables and tools in context.
    
    Like SolveIt's $variable and &function syntax, the AI should be able
    to use context variables when calling tools.
    """
    functions_context = {
        "add": {
            "signature": "(a: int, b: int) -> int",
            "docstring": "Add two integers.",
            "parameters": {
                "a": {"type": "integer", "description": "First number"},
                "b": {"type": "integer", "description": "Second number"},
            },
        }
    }
    
    variables_context = {
        "my_number": {"type": "int", "repr": "42"},
        "other_number": {"type": "int", "repr": "8"},
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
            json={
                "prompt": "Use the add tool to add my_number and other_number together.",
                "context": {
                    "functions": functions_context,
                    "variables": variables_context,
                    "preceding_code": "my_number = 42\nother_number = 8\ndef add(a, b): return a + b",
                },
                "model": MODEL,
            },
        ) as response:
            assert response.status_code == 200
            events = await collect_sse_events(response)
    
    # Should have called the add tool
    tool_calls = [e for e in events if "tool_call" in e]
    assert len(tool_calls) > 0, f"Expected tool_call, got: {events}"
    assert tool_calls[0]["tool_call"]["name"] == "add"
    
    # Check tool input - AI may pass literal values or variable names
    tool_inputs = [e for e in events if "tool_input" in e]
    full_input = "".join(e["tool_input"] for e in tool_inputs)
    # Either the AI resolved the variables to their values, or passed the variable names
    has_values = "42" in full_input and "8" in full_input
    has_names = "my_number" in full_input and "other_number" in full_input
    assert has_values or has_names, f"Expected values (42, 8) or names in: {full_input}"


@pytest.mark.asyncio  
async def test_multiple_tools_available():
    """Test that AI can choose the right tool when multiple are available."""
    functions_context = {
        "add": {
            "signature": "(a: int, b: int) -> int",
            "docstring": "Add two integers.",
            "parameters": {
                "a": {"type": "integer", "description": "First number"},
                "b": {"type": "integer", "description": "Second number"},
            },
        },
        "multiply": {
            "signature": "(x: int, y: int) -> int",
            "docstring": "Multiply two integers.",
            "parameters": {
                "x": {"type": "integer", "description": "First number"},
                "y": {"type": "integer", "description": "Second number"},
            },
        },
        "divide": {
            "signature": "(numerator: int, denominator: int) -> float",
            "docstring": "Divide first number by second.",
            "parameters": {
                "numerator": {"type": "integer", "description": "Number to divide"},
                "denominator": {"type": "integer", "description": "Number to divide by"},
            },
        },
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
            json={
                "prompt": "What is 100 divided by 4? Use the appropriate tool.",
                "context": {
                    "functions": functions_context,
                    "variables": {},
                },
                "model": MODEL,
            },
        ) as response:
            assert response.status_code == 200
            events = await collect_sse_events(response)
    
    # Should have chosen divide
    tool_calls = [e for e in events if "tool_call" in e]
    assert len(tool_calls) > 0, f"Expected tool_call, got: {events}"
    assert tool_calls[0]["tool_call"]["name"] == "divide"
    
    # Check args
    tool_inputs = [e for e in events if "tool_input" in e]
    full_input = "".join(e["tool_input"] for e in tool_inputs)
    assert "100" in full_input and "4" in full_input


@pytest.mark.asyncio
@pytest.mark.xfail(reason="LLM behavior is non-deterministic; model may use tools unnecessarily")
async def test_no_tool_when_not_needed():
    """Test that AI doesn't call tools when a simple text response suffices."""
    functions_context = {
        "calculate": {
            "signature": "(expr: str) -> float",
            "docstring": "Evaluate a math expression.",
            "parameters": {
                "expr": {"type": "string", "description": "Math expression to evaluate"},
            },
        }
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
            json={
                "prompt": "What is the capital of France?",
                "context": {
                    "functions": functions_context,
                    "variables": {},
                },
                "model": MODEL,
            },
        ) as response:
            assert response.status_code == 200
            events = await collect_sse_events(response)
    
    # Should NOT have called any tool
    tool_calls = [e for e in events if "tool_call" in e]
    assert len(tool_calls) == 0, f"Did not expect tool_call for geography question: {events}"
    
    # Should have text response mentioning Paris
    text_events = [e for e in events if "text" in e]
    full_text = "".join(e["text"] for e in text_events).lower()
    assert "paris" in full_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

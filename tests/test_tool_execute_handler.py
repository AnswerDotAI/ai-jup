"""Tests for ToolExecuteHandler.

Unit tests for validation logic (no kernel needed) and integration tests
using a live Jupyter kernel for actual execution.
"""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_jup.handlers import ToolExecuteHandler

# Configuration for live kernel tests
BASE_URL = os.environ.get("JUPYTER_BASE_URL", "http://localhost:8888")
TOKEN = os.environ.get("JUPYTER_TOKEN", "debug-token")


@pytest.fixture
def mock_handler():
    """Create a mock ToolExecuteHandler for unit tests (validation logic only)."""
    handler = MagicMock(spec=ToolExecuteHandler)
    handler.settings = {}
    handler.log = MagicMock()
    handler.finish = MagicMock()
    handler.get_json_body = MagicMock()
    return handler


class TestToolExecuteValidation:
    """Unit tests for ToolExecuteHandler validation logic.
    
    These tests verify request validation without needing a kernel.
    """

    @pytest.mark.asyncio
    async def test_missing_kernel_id(self, mock_handler):
        """POST without kernel_id returns error."""
        mock_handler.get_json_body.return_value = {"name": "test_func", "input": {}}

        await ToolExecuteHandler.post(mock_handler)

        mock_handler.finish.assert_called_once()
        result = json.loads(mock_handler.finish.call_args[0][0])
        assert result == {"error": "kernel_id is required", "status": "error"}

    @pytest.mark.asyncio
    async def test_no_kernel_manager(self, mock_handler):
        """No kernel_manager in settings returns error."""
        mock_handler.get_json_body.return_value = {
            "name": "test_func",
            "input": {},
            "kernel_id": "test-kernel-123",
        }
        mock_handler.settings = {}

        await ToolExecuteHandler.post(mock_handler)

        mock_handler.finish.assert_called_once()
        result = json.loads(mock_handler.finish.call_args[0][0])
        assert result == {"error": "Kernel manager not available", "status": "error"}

    @pytest.mark.asyncio
    async def test_kernel_not_found(self, mock_handler):
        """Kernel manager returns None for unknown kernel."""
        mock_handler.get_json_body.return_value = {
            "name": "test_func",
            "input": {},
            "kernel_id": "nonexistent-kernel",
        }
        mock_kernel_manager = MagicMock()
        mock_kernel_manager.get_kernel.return_value = None
        mock_handler.settings = {"kernel_manager": mock_kernel_manager}

        await ToolExecuteHandler.post(mock_handler)

        mock_handler.finish.assert_called_once()
        result = json.loads(mock_handler.finish.call_args[0][0])
        assert result == {
            "error": "Kernel nonexistent-kernel not found",
            "status": "error",
        }

    @pytest.mark.asyncio
    async def test_missing_tool_name(self, mock_handler):
        """POST without tool name returns error."""
        mock_handler.get_json_body.return_value = {"input": {}, "kernel_id": "test-kernel"}

        await ToolExecuteHandler.post(mock_handler)

        mock_handler.finish.assert_called_once()
        result = json.loads(mock_handler.finish.call_args[0][0])
        assert result == {"error": "tool name is required", "status": "error"}

    @pytest.mark.asyncio
    async def test_tool_not_in_allowed_list(self, mock_handler):
        """POST with tool not in allowed_tools returns error."""
        mock_handler.get_json_body.return_value = {
            "name": "forbidden_func",
            "input": {},
            "kernel_id": "test-kernel",
            "allowed_tools": ["allowed_func", "another_func"]
        }

        await ToolExecuteHandler.post(mock_handler)

        mock_handler.finish.assert_called_once()
        result = json.loads(mock_handler.finish.call_args[0][0])
        assert result == {"error": "Tool 'forbidden_func' is not in allowed tools", "status": "error"}

    @pytest.mark.asyncio
    async def test_invalid_tool_argument_name_rejected(self, mock_handler):
        """Tool arg keys must be kwargs-compatible identifiers."""
        mock_handler.get_json_body.return_value = {
            "name": "test_func",
            "input": {"bad-key": 1},
            "kernel_id": "test-kernel",
        }

        await ToolExecuteHandler.post(mock_handler)

        mock_handler.finish.assert_called_once()
        result = json.loads(mock_handler.finish.call_args[0][0])
        assert result["status"] == "error"
        assert "Invalid tool argument name" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_tool_name_format_rejected(self, mock_handler):
        """POST with invalid tool name format returns error."""
        mock_handler.get_json_body.return_value = {
            "name": "invalid-name!",  # Contains invalid characters
            "input": {},
            "kernel_id": "test-kernel",
        }

        await ToolExecuteHandler.post(mock_handler)

        mock_handler.finish.assert_called_once()
        result = json.loads(mock_handler.finish.call_args[0][0])
        assert result["status"] == "error"
        assert "Invalid tool name" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_name_with_spaces_rejected(self, mock_handler):
        """POST with tool name containing spaces returns error."""
        mock_handler.get_json_body.return_value = {
            "name": "my tool",  # Contains space
            "input": {},
            "kernel_id": "test-kernel",
        }

        await ToolExecuteHandler.post(mock_handler)

        mock_handler.finish.assert_called_once()
        result = json.loads(mock_handler.finish.call_args[0][0])
        assert result["status"] == "error"
        assert "Invalid tool name" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_name_starting_with_number_rejected(self, mock_handler):
        """POST with tool name starting with number returns error."""
        mock_handler.get_json_body.return_value = {
            "name": "123func",  # Starts with number
            "input": {},
            "kernel_id": "test-kernel",
        }

        await ToolExecuteHandler.post(mock_handler)

        mock_handler.finish.assert_called_once()
        result = json.loads(mock_handler.finish.call_args[0][0])
        assert result["status"] == "error"
        assert "Invalid tool name" in result["error"]

    @pytest.mark.asyncio
    async def test_valid_tool_name_with_underscores_passes_validation(self, mock_handler):
        """POST with valid tool name (underscores, letters, numbers) passes validation."""
        mock_handler.get_json_body.return_value = {
            "name": "_my_func_123",  # Valid Python identifier
            "input": {},
            "kernel_id": "test-kernel",
        }
        # Need to set up kernel manager to get past name validation
        mock_kernel_manager = MagicMock()
        mock_kernel_manager.get_kernel.return_value = None  # Will fail at kernel lookup
        mock_handler.settings = {"kernel_manager": mock_kernel_manager}

        await ToolExecuteHandler.post(mock_handler)

        mock_handler.finish.assert_called_once()
        result = json.loads(mock_handler.finish.call_args[0][0])
        # Should get to kernel not found, not tool name validation error
        assert "Invalid tool name" not in result.get("error", "")
        assert "not found" in result.get("error", "").lower()


# Helper functions for live kernel tests

def get_or_create_kernel():
    """Get an existing kernel or create a new one."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{BASE_URL}/api/kernels?token={TOKEN}")
        if resp.status_code == 200:
            kernels = resp.json()
            if kernels:
                return kernels[0]["id"]
        
        resp = client.post(
            f"{BASE_URL}/api/kernels?token={TOKEN}",
            json={"name": "python3"}
        )
        if resp.status_code == 201:
            return resp.json()["id"]
        
        raise RuntimeError(f"Failed to create kernel: {resp.status_code} {resp.text}")


def execute_code_in_kernel(kernel_id: str, code: str) -> str:
    """Execute code in a kernel via websocket and return stdout output."""
    import websocket
    import uuid
    from urllib.parse import urlparse
    
    # Extract host:port from BASE_URL for websocket connection
    parsed = urlparse(BASE_URL)
    ws_host = parsed.netloc or "localhost:8888"
    ws_url = f"ws://{ws_host}/api/kernels/{kernel_id}/channels?token={TOKEN}"
    ws = websocket.create_connection(ws_url)
    
    msg_id = str(uuid.uuid4())
    execute_msg = {
        "header": {
            "msg_id": msg_id,
            "msg_type": "execute_request",
            "username": "test",
            "session": str(uuid.uuid4()),
            "version": "5.3"
        },
        "parent_header": {},
        "metadata": {},
        "content": {
            "code": code,
            "silent": False,
            "store_history": False,
            "user_expressions": {},
            "allow_stdin": False,
            "stop_on_error": True
        },
        "buffers": [],
        "channel": "shell"
    }
    
    ws.send(json.dumps(execute_msg))
    
    output = []
    while True:
        try:
            resp = ws.recv()
            msg = json.loads(resp)
            
            parent_id = msg.get("parent_header", {}).get("msg_id", "")
            if parent_id != msg_id:
                continue
            
            msg_type = msg.get("msg_type", "")
            content = msg.get("content", {})
            
            if msg_type == "stream" and content.get("name") == "stdout":
                output.append(content.get("text", ""))
            elif msg_type == "execute_result":
                data = content.get("data", {})
                if "text/plain" in data:
                    output.append(data["text/plain"])
            elif msg_type == "execute_reply":
                break
        except Exception as e:
            print(f"WebSocket error: {e}")
            break
    
    ws.close()
    return "".join(output).strip()


def tool_execute_request(kernel_id: str, name: str, input_args: dict, allowed_tools: list = None) -> dict:
    """Make a tool-execute request and return the response."""
    payload = {
        "name": name,
        "input": input_args,
        "kernel_id": kernel_id
    }
    if allowed_tools is not None:
        payload["allowed_tools"] = allowed_tools
    
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{BASE_URL}/ai-jup/tool-execute?token={TOKEN}",
            json=payload
        )
    
    assert resp.status_code == 200
    return resp.json()


# Live kernel integration tests

pytestmark_live = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_TESTS", "0") == "1",
    reason="Live kernel tests skipped (set SKIP_LIVE_TESTS=0 to run)"
)


@pytestmark_live
class TestToolExecuteLiveKernel:
    """Integration tests using a live Jupyter kernel.
    
    These tests execute actual Python code in a kernel and verify
    the tool-execute endpoint behavior end-to-end.
    """

    @pytest.fixture(scope="class")
    def kernel_id(self):
        """Get or create a kernel for testing."""
        return get_or_create_kernel()

    @pytest.fixture(scope="class")
    def setup_kernel(self, kernel_id):
        """Define test functions in the kernel."""
        code = '''
def add(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y

def greet(name: str) -> str:
    """Generate a greeting."""
    return f"Hello, {name}!"

def get_dict() -> dict:
    """Return sample data."""
    return {"items": [1, 2, 3], "count": 3}

def failing_func():
    """A function that raises an error."""
    raise ValueError("Intentional error for testing")

def silent_func():
    """A function that returns None."""
    pass

print("Test functions defined")
'''
        result = execute_code_in_kernel(kernel_id, code)
        assert "Test functions defined" in result
        return kernel_id

    def test_successful_integer_execution(self, setup_kernel):
        """Execute function returning integer."""
        result = tool_execute_request(setup_kernel, "add", {"x": 5, "y": 3})
        
        assert result["status"] == "success"
        assert result["result"]["type"] == "text"
        assert "8" in result["result"]["content"]

    def test_successful_string_execution(self, setup_kernel):
        """Execute function returning string."""
        result = tool_execute_request(setup_kernel, "greet", {"name": "World"})
        
        assert result["status"] == "success"
        assert "Hello, World!" in result["result"]["content"]

    def test_successful_dict_execution(self, setup_kernel):
        """Execute function returning dict."""
        result = tool_execute_request(setup_kernel, "get_dict", {})
        
        assert result["status"] == "success"
        assert "items" in result["result"]["content"]

    def test_missing_function(self, setup_kernel):
        """Execute non-existent function returns error."""
        result = tool_execute_request(setup_kernel, "nonexistent_function", {})
        
        assert result["status"] == "error"
        assert "not found" in result["error"].lower() or "not callable" in result["error"].lower()

    def test_function_error(self, setup_kernel):
        """Execute function that raises exception."""
        result = tool_execute_request(setup_kernel, "failing_func", {})
        
        assert result["status"] == "error"
        assert "Intentional error" in result["error"]

    def test_none_return_value(self, setup_kernel):
        """Execute function returning None."""
        result = tool_execute_request(setup_kernel, "silent_func", {})
        
        assert result["status"] == "success"
        assert result["result"]["type"] == "text"
        # None gets repr'd as 'None'
        assert "None" in result["result"]["content"]

    def test_allowed_tools_validation(self, setup_kernel):
        """Tool not in allowed_tools list is rejected."""
        result = tool_execute_request(
            setup_kernel,
            "add",
            {"x": 1, "y": 2},
            allowed_tools=["greet"]  # add is NOT allowed
        )
        
        assert result["status"] == "error"
        assert "not in allowed tools" in result["error"]

    def test_allowed_tools_permits_listed_function(self, setup_kernel):
        """Tool in allowed_tools list is permitted."""
        result = tool_execute_request(
            setup_kernel,
            "add",
            {"x": 10, "y": 20},
            allowed_tools=["add", "greet"]
        )
        
        assert result["status"] == "success"
        assert "30" in result["result"]["content"]


@pytestmark_live
class TestToolExecuteRichResults:
    """Integration tests for rich result types (DataFrame, matplotlib)."""

    @pytest.fixture(scope="class")
    def kernel_id(self):
        """Get or create a kernel for testing."""
        return get_or_create_kernel()

    @pytest.fixture(scope="class")
    def setup_dataframe_kernel(self, kernel_id):
        """Define DataFrame-returning function."""
        code = '''
import pandas as pd

def get_dataframe():
    """Return a sample DataFrame."""
    return pd.DataFrame({
        "name": ["Alice", "Bob"],
        "age": [25, 30]
    })

print("DataFrame function defined")
'''
        result = execute_code_in_kernel(kernel_id, code)
        assert "DataFrame function defined" in result
        return kernel_id

    def test_dataframe_returns_html(self, setup_dataframe_kernel):
        """DataFrame result is returned as HTML."""
        result = tool_execute_request(setup_dataframe_kernel, "get_dataframe", {})
        
        assert result["status"] == "success"
        assert result["result"]["type"] == "html"
        assert "<table" in result["result"]["content"].lower()


@pytestmark_live
class TestToolExecuteCodeGeneration:
    """Tests to verify the generated execution code is correct."""

    @pytest.fixture(scope="class")
    def kernel_id(self):
        """Get or create a kernel for testing."""
        return get_or_create_kernel()

    @pytest.fixture(scope="class")
    def setup_kernel(self, kernel_id):
        """Define a function to inspect."""
        code = '''
def big_result():
    """Return a large string to test truncation."""
    return "x" * 1000

print("Defined")
'''
        result = execute_code_in_kernel(kernel_id, code)
        assert "Defined" in result
        return kernel_id

    def test_result_truncation(self, setup_kernel):
        """Large results are truncated to 500 chars."""
        result = tool_execute_request(setup_kernel, "big_result", {})
        
        assert result["status"] == "success"
        # Result should be truncated (500 chars max)
        content = result["result"]["content"]
        assert len(content) <= 510  # Some slack for repr quotes


@pytestmark_live
class TestSecurityValidation:
    """Security-focused tests for tool execution."""

    @pytest.fixture(scope="class")
    def kernel_id(self):
        """Get or create a kernel for testing."""
        return get_or_create_kernel()

    @pytest.fixture(scope="class")
    def setup_kernel(self, kernel_id):
        """Define a safe function in the kernel."""
        code = '''
def safe_add(x: int, y: int) -> int:
    """A safe function for testing."""
    return x + y

print("Security test functions defined")
'''
        result = execute_code_in_kernel(kernel_id, code)
        assert "Security test functions defined" in result
        return kernel_id

    def test_dangerous_function_name_rejected_by_allowed_tools(self, setup_kernel):
        """Dangerous function names should be rejected when not in allowed_tools."""
        # Try to call __import__ (dangerous) when only safe_add is allowed
        result = tool_execute_request(
            setup_kernel,
            "__import__",
            {"name": "os"},
            allowed_tools=["safe_add"]
        )
        
        assert result["status"] == "error"
        assert "not in allowed tools" in result["error"]

    def test_eval_rejected_by_allowed_tools(self, setup_kernel):
        """eval should be rejected when not in allowed_tools."""
        result = tool_execute_request(
            setup_kernel,
            "eval",
            {"source": "1+1"},
            allowed_tools=["safe_add"]
        )
        
        assert result["status"] == "error"
        assert "not in allowed tools" in result["error"]

    def test_exec_rejected_by_allowed_tools(self, setup_kernel):
        """exec should be rejected when not in allowed_tools."""
        result = tool_execute_request(
            setup_kernel,
            "exec",
            {"source": "x=1"},
            allowed_tools=["safe_add"]
        )
        
        assert result["status"] == "error"
        assert "not in allowed tools" in result["error"]

    def test_allowed_tools_empty_blocks_all(self, setup_kernel):
        """Empty allowed_tools list should block all function calls."""
        result = tool_execute_request(
            setup_kernel,
            "safe_add",
            {"x": 1, "y": 2},
            allowed_tools=[]  # Empty list - nothing allowed
        )
        
        assert result["status"] == "error"
        assert "not in allowed tools" in result["error"]


@pytestmark_live
class TestResultTruncation:
    """Tests for result size limits."""

    @pytest.fixture(scope="class")
    def kernel_id(self):
        """Get or create a kernel for testing."""
        return get_or_create_kernel()

    @pytest.fixture(scope="class")
    def setup_kernel(self, kernel_id):
        """Define functions with large outputs."""
        code = '''
def huge_string():
    """Return a very large string."""
    return "x" * 10000

def huge_list():
    """Return a large list."""
    return list(range(1000))

def huge_dict():
    """Return a large dictionary."""
    return {f"key_{i}": f"value_{i}" for i in range(500)}

import pandas as pd

def huge_dataframe():
    """Return a large DataFrame."""
    return pd.DataFrame({"col": list(range(1000))})

print("Truncation test functions defined")
'''
        result = execute_code_in_kernel(kernel_id, code)
        assert "Truncation test functions defined" in result
        return kernel_id

    def test_large_string_truncated(self, setup_kernel):
        """Large string results are truncated to 500 chars."""
        result = tool_execute_request(setup_kernel, "huge_string", {})
        
        assert result["status"] == "success"
        assert result["result"]["type"] == "text"
        # repr adds quotes, so content is 'xxx...xxx' - should be ~502 chars max
        content = result["result"]["content"]
        assert len(content) <= 510

    def test_large_list_truncated(self, setup_kernel):
        """Large list results are truncated."""
        result = tool_execute_request(setup_kernel, "huge_list", {})
        
        assert result["status"] == "success"
        assert result["result"]["type"] == "text"
        content = result["result"]["content"]
        assert len(content) <= 510

    def test_large_dict_truncated(self, setup_kernel):
        """Large dict results are truncated."""
        result = tool_execute_request(setup_kernel, "huge_dict", {})
        
        assert result["status"] == "success"
        assert result["result"]["type"] == "text"
        content = result["result"]["content"]
        assert len(content) <= 510

    def test_large_dataframe_html_truncated(self, setup_kernel):
        """Large DataFrame HTML is truncated to 10000 chars."""
        result = tool_execute_request(setup_kernel, "huge_dataframe", {})
        
        assert result["status"] == "success"
        assert result["result"]["type"] == "html"
        content = result["result"]["content"]
        # HTML truncation limit is 10000
        assert len(content) <= 10100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

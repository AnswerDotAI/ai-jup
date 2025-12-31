"""Tests for tool loop termination and server-side tool execution.

Tests the max_steps limit and tool execution flow in PromptHandler.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class MockDelta:
    """Mock delta object for streaming events."""

    def __init__(self, text=None, partial_json=None):
        if text is not None:
            self.text = text
        if partial_json is not None:
            self.partial_json = partial_json


class MockContentBlock:
    """Mock content block for tool use events."""

    def __init__(self, block_type=None, name=None, block_id=None):
        self.type = block_type
        self.name = name
        self.id = block_id


class MockEvent:
    """Mock event object for streaming."""

    def __init__(self, event_type, delta=None, content_block=None):
        self.type = event_type
        self.delta = delta
        self.content_block = content_block


class MockStreamContext:
    """Mock context manager for Anthropic streaming."""

    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return iter(self.events)

    def __exit__(self, *args):
        pass


class MockRequest:
    """Mock tornado request."""

    def __init__(self):
        self.connection = MagicMock()


class MockApplication:
    """Mock tornado application."""

    def __init__(self):
        self.ui_modules = {}
        self.ui_methods = {}


class MockHandler:
    """Mock handler with required tornado attributes."""

    def __init__(self):
        self.request = MockRequest()
        self.application = MockApplication()
        self._headers_written = False
        self._finished = False
        self._status_code = 200
        self._headers = {}
        self._buffer = []
        self.log = MagicMock()
        self.settings = {"base_url": "/"}
        self._json_body = {}
        self.current_user = "test_user"

    def set_header(self, name, value):
        self._headers[name] = value

    def set_status(self, code):
        self._status_code = code

    def write(self, data):
        if isinstance(data, dict):
            self._buffer.append(json.dumps(data))
        else:
            self._buffer.append(data)

    def finish(self, data=None):
        if data:
            self.write(data)
        self._finished = True

    async def flush(self):
        pass

    def get_json_body(self):
        return self._json_body


@pytest.fixture
def handler():
    """Create a mock handler with PromptHandler methods bound."""
    from ai_jup.handlers import PromptHandler

    h = MockHandler()
    h._build_system_prompt = PromptHandler._build_system_prompt.__get__(h, MockHandler)
    h._build_tools = PromptHandler._build_tools.__get__(h, MockHandler)
    h._python_type_to_json_schema = PromptHandler._python_type_to_json_schema.__get__(h, MockHandler)
    h._write_sse = PromptHandler._write_sse.__get__(h, MockHandler)
    # Note: _execute_tool_in_kernel must be patched per-test since we bind the real post method
    h.post = PromptHandler.post.__get__(h, MockHandler)
    return h


class TestUnknownToolRejected:
    """Tests for unknown tool name rejection."""

    @pytest.mark.asyncio
    async def test_unknown_tool_rejected_with_error(self, handler):
        """Tool not in functions dict should produce error SSE event."""
        content_block = MockContentBlock(
            block_type="tool_use", name="unknown_tool", block_id="tool_1"
        )
        mock_events = [
            MockEvent("content_block_start", content_block=content_block),
            MockEvent("content_block_delta", delta=MockDelta(partial_json='{}')),
            MockEvent("content_block_stop"),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        mock_kernel = MagicMock()
        mock_kernel_manager = MagicMock()
        mock_kernel_manager.get_kernel.return_value = mock_kernel
        handler.settings["kernel_manager"] = mock_kernel_manager

        handler._json_body = {
            "prompt": "test",
            "context": {"functions": {"calc": {"signature": "()", "docstring": "calc", "parameters": {}}}},
            "kernel_id": "k1",
            "max_steps": 5,
        }

        mock_execute_tool = AsyncMock(return_value={"status": "success", "result": {"type": "text", "content": "42"}})

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
            patch("ai_jup.handlers.PromptHandler._execute_tool_in_kernel", mock_execute_tool),
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        assert "Unknown tool: unknown_tool" in response
        assert '{"done": true}' in response
        mock_execute_tool.assert_not_called()


class TestInvalidToolInputJSON:
    """Tests for invalid tool input JSON handling."""

    @pytest.mark.asyncio
    async def test_invalid_json_produces_error(self, handler):
        """Invalid JSON in tool input should produce error SSE event."""
        content_block = MockContentBlock(
            block_type="tool_use", name="calc", block_id="tool_1"
        )
        mock_events = [
            MockEvent("content_block_start", content_block=content_block),
            MockEvent("content_block_delta", delta=MockDelta(partial_json='not valid json')),
            MockEvent("content_block_stop"),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        mock_kernel = MagicMock()
        mock_kernel_manager = MagicMock()
        mock_kernel_manager.get_kernel.return_value = mock_kernel
        handler.settings["kernel_manager"] = mock_kernel_manager

        handler._json_body = {
            "prompt": "test",
            "context": {"functions": {"calc": {"signature": "()", "docstring": "calc", "parameters": {}}}},
            "kernel_id": "k1",
            "max_steps": 5,
        }

        mock_execute_tool = AsyncMock(return_value={"status": "success", "result": {"type": "text", "content": "42"}})

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
            patch("ai_jup.handlers.PromptHandler._execute_tool_in_kernel", mock_execute_tool),
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        assert "Invalid tool input JSON" in response
        assert '{"done": true}' in response
        mock_execute_tool.assert_not_called()


class TestInvalidToolArgumentName:
    """Tests for invalid tool argument names (prevents injection via kwargs)."""

    @pytest.mark.asyncio
    async def test_invalid_argument_key_produces_error(self, handler):
        content_block = MockContentBlock(block_type="tool_use", name="calc", block_id="tool_1")
        tool_input = json.dumps(
            {'x); __import__("os").system("echo injected"); #': 1}
        )
        mock_events = [
            MockEvent("content_block_start", content_block=content_block),
            MockEvent("content_block_delta", delta=MockDelta(partial_json=tool_input)),
            MockEvent("content_block_stop"),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        mock_kernel = MagicMock()
        mock_kernel_manager = MagicMock()
        mock_kernel_manager.get_kernel.return_value = mock_kernel
        handler.settings["kernel_manager"] = mock_kernel_manager

        handler._json_body = {
            "prompt": "test",
            "context": {"functions": {"calc": {"signature": "()", "docstring": "calc", "parameters": {}}}},
            "kernel_id": "k1",
            "max_steps": 5,
        }

        mock_execute_tool = AsyncMock(
            return_value={"status": "success", "result": {"type": "text", "content": "42"}}
        )

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
            patch("ai_jup.handlers.PromptHandler._execute_tool_in_kernel", mock_execute_tool),
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        assert "Invalid tool argument name" in response
        assert '{"done": true}' in response
        mock_execute_tool.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

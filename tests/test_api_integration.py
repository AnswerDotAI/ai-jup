"""Integration tests for the backend API endpoints.

Tests the PromptHandler in ai_jup/handlers.py with mocked Anthropic client.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class MockDelta:
    """Mock delta object for streaming events."""

    def __init__(self, text=None, partial_json=None):
        # Only set attributes that are not None, so hasattr() works correctly
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
    h._build_system_prompt = PromptHandler._build_system_prompt.__get__(
        h, MockHandler
    )
    h._build_tools = PromptHandler._build_tools.__get__(h, MockHandler)
    h._python_type_to_json_schema = PromptHandler._python_type_to_json_schema.__get__(h, MockHandler)
    h._write_sse = PromptHandler._write_sse.__get__(h, MockHandler)
    h.post = PromptHandler.post.__get__(h, MockHandler)
    return h


class TestMissingAnthropicPackage:
    """Tests for missing anthropic package."""

    @pytest.mark.asyncio
    async def test_missing_anthropic_package_returns_500(self, handler):
        """When HAS_ANTHROPIC is False, should return HTTP 500 with error JSON."""
        handler._json_body = {"prompt": "test", "context": {}}

        with patch("ai_jup.handlers.HAS_ANTHROPIC", False):
            await handler.post()

        assert handler._status_code == 500
        assert handler._finished
        response = json.loads(handler._buffer[0])
        assert "error" in response
        assert "anthropic" in response["error"].lower()


class TestMissingAPIKey:
    """Tests for missing API key."""

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_500(self, handler):
        """When ANTHROPIC_API_KEY is not set, should return HTTP 500 with error JSON."""
        handler._json_body = {"prompt": "test", "context": {}}

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {}, clear=True),
        ):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            await handler.post()

        assert handler._status_code == 500
        assert handler._finished
        response = json.loads(handler._buffer[0])
        assert "error" in response
        assert "ANTHROPIC_API_KEY" in response["error"]


class TestStreamingSSE:
    """Tests for streaming SSE responses."""

    @pytest.mark.asyncio
    async def test_streaming_sse_with_mock(self, handler):
        """Mock Anthropic client should produce multiple data: lines with final done."""
        handler._json_body = {"prompt": "hi", "context": {}}

        mock_events = [
            MockEvent("content_block_delta", delta=MockDelta(text="Hello ")),
            MockEvent("content_block_delta", delta=MockDelta(text="world")),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        assert 'data: {"text": "Hello "}' in response
        assert 'data: {"text": "world"}' in response
        assert 'data: {"done": true}' in response


class TestModelParameter:
    """Tests for model parameter handling."""

    @pytest.mark.asyncio
    async def test_model_parameter_passed_to_client(self, handler):
        """Specified model should be passed to Anthropic client."""
        handler._json_body = {
            "prompt": "test",
            "context": {},
            "model": "claude-3-haiku-20240307",
        }

        mock_events = [MockEvent("message_stop")]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        call_kwargs = mock_client.messages.stream.call_args.kwargs
        assert call_kwargs["model"] == "claude-3-haiku-20240307"

    @pytest.mark.asyncio
    async def test_default_model_used_when_omitted(self, handler):
        """Default model should be used when not specified in request."""
        handler._json_body = {"prompt": "test", "context": {}}

        mock_events = [MockEvent("message_stop")]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        call_kwargs = mock_client.messages.stream.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"


class TestToolsBuilding:
    """Tests for tools building from functions context."""

    @pytest.mark.asyncio
    async def test_tools_passed_when_functions_provided(self, handler):
        """Tools array should be passed when functions are in context."""
        handler._json_body = {
            "prompt": "test",
            "context": {
                "functions": {
                    "calculate": {
                        "signature": "(x: int) -> int",
                        "docstring": "Calculate something",
                        "parameters": {"x": {"type": "int"}},
                    }
                }
            },
        }

        mock_events = [MockEvent("message_stop")]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = "NOT_GIVEN_SENTINEL"
            await handler.post()

        call_kwargs = mock_client.messages.stream.call_args.kwargs
        assert call_kwargs["tools"] != "NOT_GIVEN_SENTINEL"
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["name"] == "calculate"

    @pytest.mark.asyncio
    async def test_no_tools_when_empty_functions(self, handler):
        """tools=anthropic.NOT_GIVEN when no functions provided."""
        handler._json_body = {"prompt": "test", "context": {"functions": {}}}

        mock_events = [MockEvent("message_stop")]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        not_given_sentinel = object()
        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = not_given_sentinel
            await handler.post()

        call_kwargs = mock_client.messages.stream.call_args.kwargs
        assert call_kwargs["tools"] is not_given_sentinel


class TestToolCallEvent:
    """Tests for tool_use content block events."""

    @pytest.mark.asyncio
    async def test_tool_call_event_in_sse(self, handler):
        """Mock tool_use content block should produce SSE with tool_call."""
        handler._json_body = {"prompt": "test", "context": {}}

        content_block = MockContentBlock(
            block_type="tool_use", name="calculate", block_id="tool_123"
        )
        mock_events = [
            MockEvent(
                "content_block_start", content_block=content_block
            ),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        assert "tool_call" in response
        assert "calculate" in response
        assert "tool_123" in response


class TestToolInputEvent:
    """Tests for partial_json delta events."""

    @pytest.mark.asyncio
    async def test_tool_input_event_in_sse(self, handler):
        """Mock partial_json delta should produce SSE with tool_input."""
        handler._json_body = {"prompt": "test", "context": {}}

        # Need content_block_start with tool_use first to set current_tool_call
        content_block = MockContentBlock(
            block_type="tool_use", name="test_fn", block_id="tool_456"
        )
        mock_events = [
            MockEvent("content_block_start", content_block=content_block),
            MockEvent(
                "content_block_delta", delta=MockDelta(partial_json='{"x": ')
            ),
            MockEvent(
                "content_block_delta", delta=MockDelta(partial_json="42}")
            ),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        assert 'data: {"tool_input": "{\\"x\\": "}' in response
        assert 'data: {"tool_input": "42}"}' in response


class TestModelsHandler:
    """Tests for ModelsHandler endpoint."""

    def test_models_handler_returns_models_list(self):
        """GET /ai-jup/models should return list of available models."""
        from ai_jup.handlers import ModelsHandler

        handler = MockHandler()
        handler.get = ModelsHandler.get.__get__(handler, MockHandler)
        handler.get()

        assert handler._finished
        response = json.loads(handler._buffer[0])
        assert "models" in response
        assert len(response["models"]) == 3
        
        model_ids = [m["id"] for m in response["models"]]
        assert "claude-sonnet-4-20250514" in model_ids
        assert "claude-3-5-sonnet-20241022" in model_ids
        assert "claude-3-haiku-20240307" in model_ids


class TestServerSideToolLoop:
    """Tests for server-side tool loop in PromptHandler."""

    @pytest.fixture
    def handler_with_kernel(self):
        """Create a mock handler with kernel support for tool loop tests."""
        from ai_jup.handlers import PromptHandler

        h = MockHandler()
        h._build_system_prompt = PromptHandler._build_system_prompt.__get__(h, MockHandler)
        h._build_tools = PromptHandler._build_tools.__get__(h, MockHandler)
        h._python_type_to_json_schema = PromptHandler._python_type_to_json_schema.__get__(h, MockHandler)
        h._write_sse = PromptHandler._write_sse.__get__(h, MockHandler)
        h._execute_tool_in_kernel = PromptHandler._execute_tool_in_kernel.__get__(h, MockHandler)
        h.post = PromptHandler.post.__get__(h, MockHandler)
        return h

    @pytest.mark.asyncio
    async def test_no_kernel_skips_tool_execution(self, handler_with_kernel):
        """When kernel_id is not provided, tool calls are not executed."""
        handler = handler_with_kernel
        handler._json_body = {
            "prompt": "test",
            "context": {"functions": {"calculate": {"signature": "(x: int) -> int", "docstring": "Calculate", "parameters": {"x": {"type": "int"}}}}},
            "max_steps": 5,
            # No kernel_id
        }

        content_block = MockContentBlock(block_type="tool_use", name="calculate", block_id="tool_1")
        mock_events = [
            MockEvent("content_block_start", content_block=content_block),
            MockEvent("content_block_delta", delta=MockDelta(partial_json='{"x": 42}')),
            MockEvent("content_block_stop"),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        # Should have tool_call event but no tool_result (no kernel)
        assert "tool_call" in response
        assert "tool_result" not in response
        assert '{"done": true}' in response

    @pytest.mark.asyncio
    async def test_unknown_tool_rejected(self, handler_with_kernel):
        """Tool not in functions context should produce error."""
        handler = handler_with_kernel
        
        # Mock kernel manager
        mock_kernel = MagicMock()
        mock_kernel_manager = MagicMock()
        mock_kernel_manager.get_kernel.return_value = mock_kernel
        handler.settings["kernel_manager"] = mock_kernel_manager

        handler._json_body = {
            "prompt": "test",
            "context": {"functions": {"other_func": {"signature": "() -> int", "docstring": "Other", "parameters": {}}}},
            "kernel_id": "test-kernel",
            "max_steps": 5,
        }

        # LLM tries to call "calculate" but only "other_func" is registered
        content_block = MockContentBlock(block_type="tool_use", name="calculate", block_id="tool_1")
        mock_events = [
            MockEvent("content_block_start", content_block=content_block),
            MockEvent("content_block_delta", delta=MockDelta(partial_json='{"x": 42}')),
            MockEvent("content_block_stop"),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        assert "Unknown tool: calculate" in response
        assert '{"done": true}' in response

    @pytest.mark.asyncio
    async def test_invalid_tool_input_json(self, handler_with_kernel):
        """Invalid JSON in tool input should produce error."""
        handler = handler_with_kernel
        
        mock_kernel = MagicMock()
        mock_kernel_manager = MagicMock()
        mock_kernel_manager.get_kernel.return_value = mock_kernel
        handler.settings["kernel_manager"] = mock_kernel_manager

        handler._json_body = {
            "prompt": "test",
            "context": {"functions": {"calculate": {"signature": "(x: int) -> int", "docstring": "Calc", "parameters": {"x": {"type": "int"}}}}},
            "kernel_id": "test-kernel",
            "max_steps": 5,
        }

        content_block = MockContentBlock(block_type="tool_use", name="calculate", block_id="tool_1")
        mock_events = [
            MockEvent("content_block_start", content_block=content_block),
            # Invalid JSON - missing closing brace
            MockEvent("content_block_delta", delta=MockDelta(partial_json='{"x": ')),
            MockEvent("content_block_stop"),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        assert "Invalid tool input JSON" in response
        assert '{"done": true}' in response

    @pytest.mark.asyncio
    async def test_max_steps_limits_tool_iterations(self, handler_with_kernel):
        """max_steps should limit number of tool loop iterations."""
        handler = handler_with_kernel
        
        mock_kernel = MagicMock()
        mock_kernel_manager = MagicMock()
        mock_kernel_manager.get_kernel.return_value = mock_kernel
        handler.settings["kernel_manager"] = mock_kernel_manager

        handler._json_body = {
            "prompt": "test",
            "context": {"functions": {"add": {"signature": "(x: int) -> int", "docstring": "Add", "parameters": {"x": {"type": "int"}}}}},
            "kernel_id": "test-kernel",
            "max_steps": 1,  # Only allow 1 tool call
        }

        tool_call_count = [0]

        async def mock_execute_tool(kernel, tool_name, tool_args, timeout=60):
            tool_call_count[0] += 1
            return {"status": "success", "result": {"type": "text", "content": "42"}}

        handler._execute_tool_in_kernel = mock_execute_tool

        content_block = MockContentBlock(block_type="tool_use", name="add", block_id="tool_1")
        
        # First call returns tool use, second call also returns tool use
        def stream_generator():
            mock_events_1 = [
                MockEvent("content_block_start", content_block=content_block),
                MockEvent("content_block_delta", delta=MockDelta(partial_json='{"x": 1}')),
                MockEvent("content_block_stop"),
                MockEvent("message_stop"),
            ]
            return MockStreamContext(mock_events_1)

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [stream_generator(), stream_generator()]

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        # Should only execute tool once due to max_steps=1
        assert tool_call_count[0] == 1
        response = "".join(handler._buffer)
        assert "tool_result" in response


class TestAnthropicError:
    """Tests for Anthropic client errors."""

    @pytest.mark.asyncio
    async def test_anthropic_error_produces_sse_error(self, handler):
        """Client exception should produce SSE error event and finish gracefully."""
        handler._json_body = {"prompt": "test", "context": {}}

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = Exception("API rate limit exceeded")

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        assert handler._finished
        response = "".join(handler._buffer)
        assert "error" in response
        assert "API rate limit exceeded" in response

    @pytest.mark.asyncio
    async def test_stream_iteration_error_handled(self, handler):
        """Error during stream iteration should be handled gracefully."""
        handler._json_body = {"prompt": "test", "context": {}}

        def failing_iter():
            yield MockEvent("content_block_delta", delta=MockDelta(text="Hello"))
            raise Exception("Stream interrupted")

        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=failing_iter())
        mock_stream.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        assert handler._finished
        response = "".join(handler._buffer)
        assert 'data: {"text": "Hello"}' in response
        assert "error" in response
        assert "Stream interrupted" in response


class TestInputValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_string_json_body_returns_400(self, handler):
        """When JSON body is a string instead of dict, should return HTTP 400."""
        handler.get_json_body = lambda: "not a dict"

        await handler.post()

        assert handler._status_code == 400
        assert handler._finished
        response = json.loads(handler._buffer[0])
        assert "error" in response
        assert "Invalid JSON body" in response["error"]

    @pytest.mark.asyncio
    async def test_list_json_body_returns_400(self, handler):
        """When JSON body is a list instead of dict, should return HTTP 400."""
        handler.get_json_body = lambda: ["prompt", "test"]

        await handler.post()

        assert handler._status_code == 400
        assert handler._finished
        response = json.loads(handler._buffer[0])
        assert "Invalid JSON body" in response["error"]


class TestToolNameValidation:
    """Tests for tool name validation."""

    @pytest.fixture
    def handler_with_kernel(self, handler):
        """Handler with a mock kernel manager."""
        mock_kernel = MagicMock()
        mock_kernel_manager = MagicMock()
        mock_kernel_manager.get_kernel.return_value = mock_kernel
        handler.settings["kernel_manager"] = mock_kernel_manager
        return handler

    @pytest.mark.asyncio
    async def test_invalid_tool_name_rejected(self, handler_with_kernel):
        """Tool names with invalid characters should be rejected."""
        handler = handler_with_kernel

        handler._json_body = {
            "prompt": "test",
            "context": {
                "functions": {
                    "valid_func": {"signature": "(x: int) -> int", "docstring": "Valid", "parameters": {"x": {"type": "int"}}}
                }
            },
            "kernel_id": "test-kernel",
            "max_steps": 5,
        }

        # LLM returns a tool name with invalid characters
        content_block = MockContentBlock(block_type="tool_use", name="invalid-name!", block_id="tool_1")
        mock_events = [
            MockEvent("content_block_start", content_block=content_block),
            MockEvent("content_block_delta", delta=MockDelta(partial_json='{"x": 1}')),
            MockEvent("content_block_stop"),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        assert "Invalid tool name" in response
        assert '{"done": true}' in response

    @pytest.mark.asyncio
    async def test_valid_tool_name_with_underscores_accepted(self, handler_with_kernel):
        """Tool names with underscores should be accepted."""
        handler = handler_with_kernel

        handler._json_body = {
            "prompt": "test",
            "context": {
                "functions": {
                    "my_valid_func_123": {"signature": "(x: int) -> int", "docstring": "Valid", "parameters": {"x": {"type": "int"}}}
                }
            },
            "kernel_id": "test-kernel",
            "max_steps": 5,
        }

        async def mock_execute_tool(kernel, tool_name, tool_args, timeout=60):
            return {"status": "success", "result": {"type": "text", "content": "42"}}

        handler._execute_tool_in_kernel = mock_execute_tool

        content_block = MockContentBlock(block_type="tool_use", name="my_valid_func_123", block_id="tool_1")
        mock_events = [
            MockEvent("content_block_start", content_block=content_block),
            MockEvent("content_block_delta", delta=MockDelta(partial_json='{"x": 1}')),
            MockEvent("content_block_stop"),
            MockEvent("message_stop"),
        ]

        def make_stream():
            return MockStreamContext(mock_events)

        call_count = [0]

        def stream_factory(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return make_stream()
            else:
                # Second call returns just text (end of loop)
                return MockStreamContext([
                    MockEvent("content_block_delta", delta=MockDelta(text="Done")),
                    MockEvent("message_stop"),
                ])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = stream_factory

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        # Should not have "Invalid tool name" error
        assert "Invalid tool name" not in response
        # Should have executed the tool
        assert "tool_result" in response


class TestToolCallStateReset:
    """Tests for proper tool call state management."""

    @pytest.fixture
    def handler_with_kernel(self, handler):
        """Handler with a mock kernel manager."""
        mock_kernel = MagicMock()
        mock_kernel_manager = MagicMock()
        mock_kernel_manager.get_kernel.return_value = mock_kernel
        handler.settings["kernel_manager"] = mock_kernel_manager
        return handler

    @pytest.mark.asyncio
    async def test_text_block_after_tool_block_handled_correctly(self, handler_with_kernel):
        """Text content block after tool block should not be misattributed."""
        handler = handler_with_kernel

        handler._json_body = {
            "prompt": "test",
            "context": {
                "functions": {
                    "calculate": {"signature": "(x: int) -> int", "docstring": "Calc", "parameters": {"x": {"type": "int"}}}
                }
            },
            "kernel_id": "test-kernel",
            "max_steps": 5,
        }

        async def mock_execute_tool(kernel, tool_name, tool_args, timeout=60):
            return {"status": "success", "result": {"type": "text", "content": "42"}}

        handler._execute_tool_in_kernel = mock_execute_tool

        # Simulate: tool block, then text block in same response
        tool_block = MockContentBlock(block_type="tool_use", name="calculate", block_id="tool_1")
        text_block = MockContentBlock(block_type="text")

        mock_events = [
            MockEvent("content_block_start", content_block=tool_block),
            MockEvent("content_block_delta", delta=MockDelta(partial_json='{"x": 5}')),
            MockEvent("content_block_stop"),  # Tool block ends here
            MockEvent("content_block_start", content_block=text_block),
            MockEvent("content_block_delta", delta=MockDelta(text="Let me explain...")),
            MockEvent("content_block_stop"),  # Text block ends - should not be treated as tool
            MockEvent("message_stop"),
        ]

        call_count = [0]

        def stream_factory(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockStreamContext(mock_events)
            else:
                return MockStreamContext([
                    MockEvent("content_block_delta", delta=MockDelta(text="Final answer")),
                    MockEvent("message_stop"),
                ])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = stream_factory

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            await handler.post()

        response = "".join(handler._buffer)
        # Should have the text streamed
        assert "Let me explain" in response
        # Should have executed the tool
        assert "tool_result" in response
        # Should complete successfully
        assert '{"done": true}' in response


class TestStreamClosedError:
    """Tests for StreamClosedError handling."""

    @pytest.mark.asyncio
    async def test_stream_closed_during_write_handled_gracefully(self, handler):
        """StreamClosedError during SSE write should not cause unhandled exception."""
        from tornado.iostream import StreamClosedError

        handler._json_body = {"prompt": "test", "context": {}}

        # Make flush raise StreamClosedError
        async def failing_flush():
            raise StreamClosedError()

        handler.flush = failing_flush

        mock_events = [
            MockEvent("content_block_delta", delta=MockDelta(text="Hello")),
            MockEvent("message_stop"),
        ]
        mock_stream = MockStreamContext(mock_events)
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream

        with (
            patch("ai_jup.handlers.HAS_ANTHROPIC", True),
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}),
            patch("ai_jup.handlers.anthropic") as mock_anthropic,
        ):
            mock_anthropic.Anthropic.return_value = mock_client
            mock_anthropic.NOT_GIVEN = object()
            # Should not raise - StreamClosedError should be caught
            await handler.post()

        # Handler should finish without error (client disconnected)
        # The key test is that no exception propagates


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

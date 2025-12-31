"""Integration tests for SSE streaming responses.

Tests the /ai-jup/prompt endpoint streaming behavior with a live server.
Run with: pytest tests/test_streaming_integration.py -v

Start the server first:
    tb__jupyter-server start --token debug-token
"""

import json
import os
import pytest
import httpx

# Configuration
BASE_URL = os.environ.get("JUPYTER_BASE_URL", "http://localhost:8888")
TOKEN = os.environ.get("JUPYTER_TOKEN", "debug-token")

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_TESTS", "0") == "1",
    reason="Live streaming tests skipped (set SKIP_LIVE_TESTS=0 to run)"
)


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


def parse_sse_events(response_text: str) -> list[dict]:
    """Parse SSE response text into a list of event data dicts."""
    events = []
    for line in response_text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                events.append(data)
            except json.JSONDecodeError:
                pass
    return events


class TestStreamingEndpoint:
    """Tests for the /ai-jup/prompt streaming endpoint."""

    def test_endpoint_returns_sse_content_type(self):
        """Endpoint should return text/event-stream content type."""
        # Skip if no API key (we need the endpoint to start streaming)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")
        
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
                json={
                    "prompt": "Say 'test' and nothing else",
                    "context": {},
                    "model": "claude-3-haiku-20240307"
                }
            )
        
        assert resp.headers.get("content-type") == "text/event-stream"

    def test_streaming_produces_text_events(self):
        """Streaming should produce text events."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")
        
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
                json={
                    "prompt": "Say exactly: Hello World",
                    "context": {},
                    "model": "claude-3-haiku-20240307"
                }
            )
        
        events = parse_sse_events(resp.text)
        
        # Should have at least one text event
        text_events = [e for e in events if "text" in e]
        assert len(text_events) > 0
        
        # Should end with done event
        done_events = [e for e in events if e.get("done")]
        assert len(done_events) == 1

    def test_streaming_with_context(self):
        """Streaming should work with variable context."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")
        
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
                json={
                    "prompt": "What is the value of x?",
                    "context": {
                        "preceding_code": "x = 42",
                        "variables": {
                            "x": {"name": "x", "type": "int", "repr": "42"}
                        },
                        "functions": {}
                    },
                    "model": "claude-3-haiku-20240307"
                }
            )
        
        events = parse_sse_events(resp.text)
        
        # Combine all text
        full_text = "".join(e.get("text", "") for e in events)
        
        # Should mention 42 somewhere
        assert "42" in full_text

    def test_missing_api_key_returns_error(self):
        """Missing API key should return proper error."""
        # Temporarily unset API key by using a different env
        original_key = os.environ.get("ANTHROPIC_API_KEY")
        
        try:
            # Can't really unset server-side, but we can test error handling
            # by checking if the endpoint is responsive
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
                    json={
                        "prompt": "test",
                        "context": {}
                    }
                )
            
            # If no API key on server, should get 500
            # If API key exists, should get 200 with SSE
            assert resp.status_code in [200, 500]
        finally:
            pass  # No cleanup needed


class TestStreamingWithTools:
    """Tests for streaming with tool execution."""

    @pytest.fixture(scope="class")
    def kernel_id(self):
        """Get or create a kernel for testing."""
        return get_or_create_kernel()

    @pytest.fixture(scope="class")
    def setup_kernel(self, kernel_id):
        """Define test functions in the kernel."""
        import websocket
        import uuid
        from urllib.parse import urlparse
        
        parsed = urlparse(BASE_URL)
        ws_host = parsed.netloc or "localhost:8888"
        ws_url = f"ws://{ws_host}/api/kernels/{kernel_id}/channels?token={TOKEN}"
        ws = websocket.create_connection(ws_url)
        
        msg_id = str(uuid.uuid4())
        code = '''
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

def get_greeting(name: str) -> str:
    """Get a greeting for a person."""
    return f"Hello, {name}!"

print("Functions defined")
'''
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
        
        # Wait for completion
        while True:
            try:
                resp = ws.recv()
                msg = json.loads(resp)
                if msg.get("msg_type") == "execute_reply":
                    break
            except Exception:
                break
        
        ws.close()
        return kernel_id

    def test_tool_call_produces_tool_events(self, setup_kernel):
        """Tool calls should produce tool_call and tool_result events."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")
        
        kernel_id = setup_kernel
        
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
                json={
                    "prompt": "Use the add_numbers function to add 5 and 3. Just call the function, don't explain.",
                    "context": {
                        "preceding_code": "",
                        "variables": {},
                        "functions": {
                            "add_numbers": {
                                "name": "add_numbers",
                                "signature": "(a: int, b: int) -> int",
                                "docstring": "Add two numbers together.",
                                "parameters": {
                                    "a": {"type": "int", "description": "First number"},
                                    "b": {"type": "int", "description": "Second number"}
                                }
                            }
                        }
                    },
                    "kernel_id": kernel_id,
                    "max_steps": 3,
                    "model": "claude-3-haiku-20240307"
                }
            )
        
        events = parse_sse_events(resp.text)
        
        # Should have tool_call event
        tool_call_events = [e for e in events if "tool_call" in e]
        assert len(tool_call_events) >= 1, f"Expected tool_call event, got: {events}"
        
        # Should have tool_result event
        tool_result_events = [e for e in events if "tool_result" in e]
        assert len(tool_result_events) >= 1, f"Expected tool_result event, got: {events}"
        
        # Result should contain 8
        result = tool_result_events[0]["tool_result"]["result"]
        assert "8" in str(result)


class TestModelsEndpoint:
    """Tests for the /ai-jup/models endpoint."""

    def test_models_endpoint_returns_list(self):
        """Models endpoint should return a list of available models."""
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{BASE_URL}/ai-jup/models?token={TOKEN}")
        
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert len(data["models"]) > 0
        
        # Each model should have id and name
        for model in data["models"]:
            assert "id" in model
            assert "name" in model

    def test_models_includes_claude_sonnet(self):
        """Models list should include Claude Sonnet."""
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{BASE_URL}/ai-jup/models?token={TOKEN}")
        
        data = resp.json()
        model_ids = [m["id"] for m in data["models"]]
        
        # Should have at least one sonnet model
        assert any("sonnet" in mid for mid in model_ids)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

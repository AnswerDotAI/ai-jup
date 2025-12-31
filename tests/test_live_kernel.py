"""Live integration tests for tool execution with a real Jupyter kernel.

These tests require a running JupyterLab server with the ai-jup extension.
Run with: pytest tests/test_live_kernel.py -v

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
    reason="Live kernel tests skipped (set SKIP_LIVE_TESTS=0 to run)"
)


def get_or_create_kernel():
    """Get an existing kernel or create a new one."""
    with httpx.Client(timeout=30.0) as client:
        # List existing kernels
        resp = client.get(f"{BASE_URL}/api/kernels?token={TOKEN}")
        if resp.status_code == 200:
            kernels = resp.json()
            if kernels:
                return kernels[0]["id"]
        
        # Create a new kernel
        resp = client.post(
            f"{BASE_URL}/api/kernels?token={TOKEN}",
            json={"name": "python3"}
        )
        if resp.status_code == 201:
            return resp.json()["id"]
        
        raise RuntimeError(f"Failed to create kernel: {resp.status_code} {resp.text}")


def execute_code_in_kernel(kernel_id: str, code: str) -> str:
    """Execute code in a kernel and return stdout output."""
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


class TestLiveToolExecution:
    """Tests using the actual tool-execute endpoint with a live kernel."""

    @pytest.fixture(scope="class")
    def kernel_id(self):
        """Get or create a kernel for testing."""
        return get_or_create_kernel()

    @pytest.fixture(scope="class")
    def setup_kernel(self, kernel_id):
        """Define test functions in the kernel."""
        # Define test functions
        code = '''
def add(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y

def greet(name: str) -> str:
    """Generate a greeting."""
    return f"Hello, {name}!"

def get_data() -> dict:
    """Return sample data."""
    return {"items": [1, 2, 3], "count": 3}

def slow_function():
    """A function that takes time (but not too long for tests)."""
    import time
    time.sleep(0.5)
    return "done"

print("Test functions defined")
'''
        result = execute_code_in_kernel(kernel_id, code)
        assert "Test functions defined" in result
        return kernel_id

    def test_simple_function_call(self, setup_kernel):
        """Test calling a simple function via tool-execute."""
        kernel_id = setup_kernel
        
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/tool-execute?token={TOKEN}",
                json={
                    "name": "add",
                    "input": {"x": 5, "y": 3},
                    "kernel_id": kernel_id
                }
            )
        
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "success"
        assert result["result"]["type"] == "text"
        assert "8" in result["result"]["content"]

    def test_string_function_call(self, setup_kernel):
        """Test calling a function that returns a string."""
        kernel_id = setup_kernel
        
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/tool-execute?token={TOKEN}",
                json={
                    "name": "greet",
                    "input": {"name": "World"},
                    "kernel_id": kernel_id
                }
            )
        
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "success"
        assert "Hello, World!" in result["result"]["content"]

    def test_dict_function_call(self, setup_kernel):
        """Test calling a function that returns a dict."""
        kernel_id = setup_kernel
        
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/tool-execute?token={TOKEN}",
                json={
                    "name": "get_data",
                    "input": {},
                    "kernel_id": kernel_id
                }
            )
        
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "success"
        assert "items" in result["result"]["content"]

    def test_missing_function(self, setup_kernel):
        """Test calling a function that doesn't exist."""
        kernel_id = setup_kernel
        
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/tool-execute?token={TOKEN}",
                json={
                    "name": "nonexistent_function",
                    "input": {},
                    "kernel_id": kernel_id
                }
            )
        
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "error"
        assert "not found" in result["error"].lower() or "not callable" in result["error"].lower()

    def test_allowed_tools_validation(self, setup_kernel):
        """Test that allowed_tools restricts which functions can be called."""
        kernel_id = setup_kernel
        
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/tool-execute?token={TOKEN}",
                json={
                    "name": "add",
                    "input": {"x": 1, "y": 2},
                    "kernel_id": kernel_id,
                    "allowed_tools": ["greet"]  # add is NOT in allowed list
                }
            )
        
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "error"
        assert "not in allowed tools" in result["error"]


class TestLiveDataFrameRendering:
    """Tests for DataFrame HTML rendering."""

    @pytest.fixture(scope="class")
    def kernel_id(self):
        """Get or create a kernel for testing."""
        return get_or_create_kernel()

    @pytest.fixture(scope="class")
    def setup_kernel(self, kernel_id):
        """Define DataFrame-returning function in the kernel."""
        code = '''
import pandas as pd

def get_dataframe():
    """Return a sample DataFrame."""
    return pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie"],
        "age": [25, 30, 35],
        "city": ["NYC", "LA", "Chicago"]
    })

print("DataFrame function defined")
'''
        result = execute_code_in_kernel(kernel_id, code)
        assert "DataFrame function defined" in result
        return kernel_id

    def test_dataframe_returns_html(self, setup_kernel):
        """Test that DataFrames are rendered as HTML."""
        kernel_id = setup_kernel
        
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/tool-execute?token={TOKEN}",
                json={
                    "name": "get_dataframe",
                    "input": {},
                    "kernel_id": kernel_id
                }
            )
        
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "success"
        # DataFrame should return HTML type
        assert result["result"]["type"] == "html"
        # HTML should contain table markup
        assert "<table" in result["result"]["content"].lower()


class TestLiveMatplotlibRendering:
    """Tests for matplotlib figure rendering."""

    @pytest.fixture(scope="class")
    def kernel_id(self):
        """Get or create a kernel for testing."""
        return get_or_create_kernel()

    @pytest.fixture(scope="class")
    def setup_kernel(self, kernel_id):
        """Define matplotlib-returning function in the kernel."""
        code = '''
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt

def make_plot():
    """Create and return a matplotlib figure."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9])
    ax.set_title("Test Plot")
    return fig

print("Matplotlib function defined")
'''
        result = execute_code_in_kernel(kernel_id, code)
        assert "Matplotlib function defined" in result
        return kernel_id

    def test_figure_returns_image(self, setup_kernel):
        """Test that matplotlib figures are rendered as images."""
        kernel_id = setup_kernel
        
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{BASE_URL}/ai-jup/tool-execute?token={TOKEN}",
                json={
                    "name": "make_plot",
                    "input": {},
                    "kernel_id": kernel_id
                }
            )
        
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "success"
        # Figure should return image type
        assert result["result"]["type"] == "image"
        assert result["result"]["format"] == "png"
        # Should have base64-encoded content
        assert len(result["result"]["content"]) > 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

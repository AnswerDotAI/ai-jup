"""Real API integration tests using Claude Haiku.

Run with: RUN_HAIKU_TESTS=1 ANTHROPIC_API_KEY=key pytest tests/test_haiku_integration.py -v

These tests are skipped by default to avoid API costs and requiring credentials.
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
async def test_minimal_roundtrip():
    """Verify basic request/response works with greeting prompt."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
            json={"prompt": "Say hello", "context": {}, "model": MODEL},
        ) as response:
            assert response.status_code == 200
            events = await collect_sse_events(response)

            text_events = [e for e in events if "text" in e]
            done_events = [e for e in events if e.get("done")]

            assert len(text_events) > 0, "Expected at least one text event"
            assert len(done_events) == 1, "Expected exactly one done event"

            full_text = "".join(e["text"] for e in text_events).lower()
            assert any(
                word in full_text for word in ["hello", "hi", "hey", "greetings"]
            ), f"Expected greeting in response: {full_text}"


@pytest.mark.asyncio
async def test_context_presence():
    """Verify context variables are passed to the model."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
            json={
                "prompt": "What is the value of x?",
                "context": {
                    "variables": {"x": {"type": "int", "repr": "5"}},
                    "functions": {},
                    "preceding_code": "x = 5",
                },
                "model": MODEL,
            },
        ) as response:
            assert response.status_code == 200
            events = await collect_sse_events(response)

            text_events = [e for e in events if "text" in e]
            assert len(text_events) > 0

            full_text = "".join(e["text"] for e in text_events).lower()
            assert "5" in full_text or "five" in full_text, (
                f"Expected '5' or 'five' in response: {full_text}"
            )


@pytest.mark.asyncio
async def test_variable_substitution():
    """Verify model can reference data values from context."""
    data = [1, 2, 3]
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
            json={
                "prompt": "What are the values in the data list?",
                "context": {
                    "variables": {"data": {"type": "list", "repr": "[1, 2, 3]"}},
                    "functions": {},
                    "preceding_code": "data = [1, 2, 3]",
                },
                "model": MODEL,
            },
        ) as response:
            assert response.status_code == 200
            events = await collect_sse_events(response)

            text_events = [e for e in events if "text" in e]
            assert len(text_events) > 0

            full_text = "".join(e["text"] for e in text_events)
            assert any(
                str(val) in full_text for val in data
            ), f"Expected data values in response: {full_text}"


@pytest.mark.asyncio
async def test_streaming_completion():
    """Verify streaming returns text events followed by done event."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/ai-jup/prompt?token={TOKEN}",
            json={"prompt": "Count to 3", "context": {}, "model": MODEL},
        ) as response:
            assert response.status_code == 200
            events = await collect_sse_events(response)

            text_events = [e for e in events if "text" in e]
            done_events = [e for e in events if e.get("done")]

            assert len(text_events) >= 1, "Expected at least one text event"
            assert len(done_events) == 1, "Expected exactly one done event"

            last_event = events[-1]
            assert last_event.get("done") is True, "Last event should be done=True"
